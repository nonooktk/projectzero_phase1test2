# SUPABASE_SCHEMA.md

Supabase（Postgres + pgvector）のスキーマ設計と運用方針。途中参加者・再開時のキャッチアップ起点。

| 項目 | 値 |
|---|---|
| 対象 | RAG 元データ・グラフ・分析結果・ジョブの永続化 |
| プラン | Supabase Free（500 MB DB / 1 GB Storage） |
| 拡張 | pgvector（バックアップ用途。検索主役は ChromaDB） |
| RLS | 暫定では無効。Azure 本番で必須（仕様§13.5） |
| マイグレーション | `supabase/migrations/0001_init.sql` |
| 最終更新 | 2026-05-10 |

---

## 1. 設計方針（4 つの判断）

| 論点 | 決定 | 理由 |
|---|---|---|
| RAG データのテーブル分割 | source 別 3 テーブル | 検索粒度・属性が source ごとに大きく異なる |
| **データの持ち方** | **JSONB ヘビー設計**：raw JSON を `data` 列に丸ごと保存し、頻繁に WHERE する列だけ昇格 | ChromaDB が main で検索を担うので Supabase 側で全フィールドを列にする必要がない。柔軟性優先 |
| `conditions_now` の持ち方 | 別テーブル `project_conditions`（dict → 行展開） | GO/NO 判定で条件単位の WHERE が必要。dict の key を `condition_name` 列に展開 |
| pgvector | 入れる（カラム用意・インデックスは作らない） | バックアップ＆将来 Azure AI Search 移行時の中間データ。検索主役は ChromaDB |

①「pgvector」= Postgres に `vector(N)` 型と類似度演算子（`<=>` cosine 等）を追加する拡張。
② ChromaDB は in-memory なので Render 再起動で消える。Supabase に embedding を持っておけば snapshot ファイルが壊れても復元可能。
③ ivfflat インデックスは作らない。Azure 移行時に AI Search で別途設計（仕様§3.3）。

## 2. テーブル一覧（8 テーブル）

| カテゴリ | テーブル | 件数（初期投入） | 主キー |
|---|---|---|---|
| RAG 元データ | `rag_external` | 39 | id (text) |
| RAG 元データ | `rag_internal` | 45 | id (text) |
| RAG 元データ | `rag_persons` | 20 | id (text) |
| RAG 元データ | `project_conditions` | ~75 | id (uuid) |
| グラフ | `graph_nodes` | 15 | id (text) |
| グラフ | `graph_edges` | 16 | id (uuid) |
| アプリ | `analyses` | 0 | id (uuid) |
| アプリ | `jobs` | 0 | id (uuid) |

## 3. ER 概要

```
rag_external ─┐
              │  （弱参照: related_failure → rag_internal.id）
rag_internal ─┼─< project_conditions
              │
rag_persons ──┤
              │
graph_nodes ──< graph_edges >── graph_nodes
              │
              │  ※graph_nodes.id は rag_*.id と同じ ID 体系（tech_001 等）
              │   ただし FK は張らない（学習段階で結合不要）

analyses ──< jobs（idempotency_key で冪等性確保）
```

## 4. RAG 投入フロー

```
data/external.json  ─┐
data/internal.json  ─┼─▶ scripts/seed_supabase.py
data/persons.json   ─┘            │
                                   │ ① テーブル投入
data/graph/*.json   ─────────────▶│ ② embedding 生成（MiniLM-L6-v2, dim=384）
                                   │ ③ pgvector カラムへ格納
                                   ▼
                              Supabase (Postgres)
                                   │
                                   ▼ bootstrap.py（FastAPI 起動時）
                              ChromaDB (in-memory)
```

## 5. RLS 方針

| 環境 | RLS | 認可方式 |
|---|---|---|
| 暫定（学習） | 無効 | service_role キー（API バックエンドからのみ利用） |
| Azure 本番（仕様§13.5） | 有効 | `auth.uid()` ベースで部署単位の行制御 |

## 6. 主要カラム解説

### 共通：`data jsonb`
- 元 JSON ファイル（external/internal/persons）の **1 レコード全体**を丸ごと格納
- `tags`/`patents`/`market_sizing`/`lessons_learned` 等は全部ここに入る
- FastAPI は `data->>'tags'` のように JSONB 演算子で取り出す

### `rag_internal`（昇格列のみ抜粋）
- `outcome_status`: `discontinued` / `success` 等（過去PJ）
- `risk_level_now`: 低 / 中 / 高（過去PJ）

### `project_conditions`（過去PJ × 条件 N:1・dict 行展開）
- `condition_name`: dict の key（例：「施工会社ネットワーク」「初期導入コスト」）
- `status_now`: 解決済 / 一部解決 / 未解決
- `detail`: 補足説明
- `year_assessed`: 評価年

→ GO/NO 判定の核：`select count(*) from project_conditions where project_id = $1 and status_now = '未解決'`

### `analyses`
- `context_used` (jsonb): LLM に渡した3軸コンテキスト全文（再現性のため保存）
- `llm_output` (jsonb): LLM 生応答（プロンプト改善・監査用）

### `jobs`
- `idempotency_key`: クライアント発行 UUID。同じキーでの重複 POST を防止（仕様§12.3）

## 7. マイグレーション運用（暫定）

| 操作 | 暫定 | 本番（仕様§12.4） |
|---|---|---|
| 適用 | `supabase db push` または手動 SQL | Alembic で冪等マイグレーション |
| ロールバック | DROP & 再投入 | 前方互換マイグレーション必須 |
| 環境差 | dev / prod のみ | dev / staging / prod の 3 環境 |

## 8. ファイル所在

| ファイル | 役割 |
|---|---|
| `supabase/migrations/0001_init.sql` | 全テーブル DDL |
| `scripts/seed_supabase.py` | JSON → Supabase 投入（embedding 生成同時） |
| `data/*.json` | 投入元（mvp_streamlit から移管予定） |

## 9. 次のアクション

| # | やること | 担当 | 状態 |
|---|---|---|---|
| 1 | `0001_init.sql` 作成（JSONB ヘビー設計に修正済） | Claude | **完了** |
| 2 | Supabase プロジェクト作成・`.env` に接続情報格納 | C | **完了** |
| 3 | `0001_init.sql` を適用 | Claude(MCP) | **完了** |
| 4 | `data/*.json` を `mvp_streamlit/data/` から `data/` へコピー | Claude | **完了** |
| 5 | raw データ投入（embedding なし） | Claude | **完了** |
| 6 | embedding 生成（`seed_supabase.py` 完成） | C | 未着手・学習材 |
| 7 | Storage バケット `chroma-snapshots` 作成 | C | 未着手 |
