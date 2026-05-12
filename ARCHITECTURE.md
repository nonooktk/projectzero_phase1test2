# ARCHITECTURE.md

Tech0 Search 暫定実装のアーキテクチャ・ディレクトリ構造・確定事項を記録する。途中参加者・再開時のキャッチアップ起点。

| 項目 | 値 |
|---|---|
| 対象 | Streamlit MVP → Next.js + FastAPI + Supabase + ChromaDB + NetworkX 移行 |
| 期間 | 1〜1.5 週間（3 名） |
| コスト | 月 $0〜$5（OpenAI 試打分のみ） |
| 決定根拠 | `IMPLEMENTATION_PLAN_INTERIM.md` v3 / `LEARNING_ACTION_PLAN.md` |
| 最終更新 | 2026-05-10 |

---

## 1. 全体アーキテクチャ

```
┌─────────────────────┐         ┌──────────────────────────┐
│  Next.js (Vercel)   │  HTTPS  │  FastAPI (Render Free)   │
│  - App Router       │ ──────▶ │  - /api/v1/analyses      │
│  - Server Actions   │         │  - Hexagonal: domain ⇄   │
│  - SSE で進捗購読   │ ◀────── │    ports ⇄ adapters      │
└─────────────────────┘   SSE   └────────┬─────────────────┘
                                          │
            ┌─────────────────────────────┼──────────────────────────┐
            │                             │                          │
            ▼                             ▼                          ▼
   ┌────────────────┐         ┌──────────────────────┐    ┌────────────────────┐
   │ ChromaDB       │         │ Supabase Free        │    │ OpenAI API         │
   │ (in-memory)    │         │ - Postgres + pgvec   │    │ (gpt-4o-mini)      │
   │ NetworkX graph │         │ - Storage(バックアップ)│    │ LLMPort 経由       │
   │ ※起動時ロード  │         │ - Auth(将来)          │    │                    │
   └────────────────┘         └──────────────────────┘    └────────────────────┘
```

| 層 | 採用 | 役割 | Azure 本番（仕様§3.3） |
|---|---|---|---|
| UI | Next.js 14 + Tailwind | 入力／結果表示／SSE 進捗 | Azure Static Web Apps |
| API | FastAPI + Pydantic v2 | ユースケース起動・冪等処理 | Azure Container Apps |
| 検索 | ChromaDB（in-memory） | ベクトル検索（cosine） | Azure AI Search |
| グラフ | NetworkX | 隣接補完（depth=1） | Microsoft GraphRAG |
| DB | Supabase（Postgres + pgvector） | 原本データ・ジョブ・結果 | Azure DB for PostgreSQL |
| LLM | OpenAI gpt-4o-mini | 評価・GO/NO 判定 | Azure OpenAI |

## 2. 確定事項サマリ

| 項目 | 決定 | 理由 |
|---|---|---|
| ベクトルDB | ChromaDB（in-memory）主役 | MVP 資産流用・Azure では AI Search に置換（仕様§3.3） |
| 永続化 | Supabase Storage に snapshot／起動時 restore | Render Free 永続ディスク不可の制約を回避 |
| ジョブ | BackgroundTasks + SSE 進捗 | LLM 5〜15 秒想定。タイムアウト回避と学習負荷のバランス |
| リポ構成 | モノレポ（tech0-search 配下） | Vercel root=`frontend/`、Render root=`backend/` |
| Port 数 | 最小 3 つ（VectorSearch / LLM / AnalysisRepo） | 学習段階では乱立を避ける（仕様§3.3 差替対象に絞る） |

## 3. ディレクトリ構造

```
tech0-search/
├── frontend/                       # Next.js (担当: 1 名)
│   ├── app/
│   │   ├── page.tsx                # アイデア入力フォーム
│   │   ├── analyses/[id]/page.tsx  # 結果表示（SSE 購読）
│   │   └── api/                    # Route Handler（薄い proxy のみ）
│   ├── components/
│   │   ├── IdeaForm.tsx
│   │   ├── AnalysisResult.tsx
│   │   └── ProgressStream.tsx
│   ├── lib/
│   │   └── api-client.ts           # FastAPI への fetch ラッパ
│   ├── package.json
│   └── .env.local.example
│
├── backend/                        # FastAPI (担当: 2 名)
│   ├── app/
│   │   ├── main.py                 # FastAPI エントリ・ルータ登録
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── analyses.py     # POST /analyses, GET /analyses/{id}
│   │   │       └── health.py
│   │   ├── domain/                 # ★ ビジネスロジック（外部依存なし）
│   │   │   ├── models.py           # AnalysisRequest, AnalysisResult, GoNoGo
│   │   │   ├── services.py         # AnalysisService（ユースケース）
│   │   │   └── prompts.py          # LLM プロンプトテンプレ
│   │   ├── ports/                  # ★ 抽象 IF（Protocol）
│   │   │   ├── vector_search.py    # VectorSearchPort
│   │   │   ├── graph_search.py     # GraphSearchPort
│   │   │   ├── llm.py              # LLMPort
│   │   │   └── repository.py       # AnalysisRepoPort
│   │   ├── adapters/               # ★ 具象実装
│   │   │   ├── chroma_adapter.py   # ChromaDB 実装
│   │   │   ├── networkx_adapter.py # NetworkX 実装
│   │   │   ├── openai_adapter.py   # OpenAI 実装
│   │   │   └── supabase_adapter.py # Supabase
│   │   ├── infra/
│   │   │   ├── settings.py         # pydantic-settings
│   │   │   ├── di.py               # 依存注入（FastAPI Depends）
│   │   │   └── bootstrap.py        # 起動時ロード（Storage→Chroma 復元）
│   │   └── workers/
│   │       └── analysis_worker.py  # BackgroundTasks で実行
│   ├── tests/
│   │   ├── unit/                   # ドメイン単体テスト（モック Port）
│   │   └── integration/            # 実 ChromaDB／実 Supabase
│   ├── pyproject.toml
│   ├── Dockerfile                  # Render Free 用
│   └── .env.example
│
├── data/                           # 原本データ（mvp_streamlit から移管）
│   ├── external.json
│   ├── internal.json
│   ├── persons.json
│   └── graph/
│       ├── nodes.json
│       └── edges.json
│
├── supabase/                       # Supabase 設定（担当: 3 名目）
│   ├── migrations/
│   │   ├── 0001_init.sql
│   │   └── 0002_pgvector.sql
│   ├── seed.sql
│   └── README.md
│
├── scripts/
│   ├── seed_supabase.py            # JSON → Supabase 投入
│   ├── snapshot_chroma.py          # Chroma → Supabase Storage
│   └── restore_chroma.py           # Storage → Chroma（起動時）
│
├── mvp_streamlit/                  # 既存 MVP（参照用・編集しない）
├── docs/
│   ├── learning-notes/{name}/
│   ├── glossary.md
│   └── adr/
├── archive/
├── CLAUDE.md
├── ARCHITECTURE.md                 # 本ファイル
├── IMPLEMENTATION_PLAN_INTERIM.md
├── LEARNING_ACTION_PLAN.md
└── README.md
```

## 4. リクエスト処理シーケンス

```
[UI] POST /api/v1/analyses {idea, idem_key}
      ↓
[FastAPI] analyses.py → AnalysisService.start()
      ↓
   ① VectorSearchPort.search(idea, n=5)        ← ChromaAdapter
   ② GraphSearchPort.expand(ids)                ← NetworkXAdapter
   ③ build_context(vector + graph)              ← domain
   ④ LLMPort.evaluate(context, idea)            ← OpenAIAdapter
   ⑤ AnalysisRepoPort.save(result)              ← SupabaseAdapter
      ↓
[UI] GET /api/v1/analyses/{id} or SSE で結果取得
```

## 5. 担当割り（仮）

| 担当 | 範囲 | 主な学び |
|---|---|---|
| A | `frontend/` 全般 | Next.js App Router・Server Actions・SSE |
| B | `backend/domain` `ports` `adapters/{chroma,networkx,openai}_adapter.py` | FastAPI・Hexagonal・Pydantic v2 |
| C | `backend/adapters/supabase_adapter.py` `supabase/` `scripts/` | Supabase・pgvector・SQL マイグレーション |

## 6. 着手順（次の判断ポイント）

| # | やること | 担当 | 状態 |
|---|---|---|---|
| 1 | Supabase テーブル設計（`rag_documents` / `analyses` / `jobs`） | C | **進行中** |
| 2 | `data/*.json` → Supabase 投入スクリプト | C | 未着手 |
| 3 | 起動時 `bootstrap.py` で Supabase → ChromaDB ロード | B | 未着手 |
| 4 | `ports/*.py` の Protocol 定義 → adapters の最小実装 | B | 未着手 |
| 5 | `frontend/app/page.tsx` の入力フォーム＋ API 連携 | A | 未着手 |

詳細スキーマは別ファイル `SUPABASE_SCHEMA.md` を参照。
