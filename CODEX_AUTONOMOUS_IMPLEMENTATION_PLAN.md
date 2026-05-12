# Codex 自走実装プラン

作成日: 2026-05-12
目的: 学習支援ではなく、Codex が Tech0 Search 暫定実装を完成まで主導するための再現可能な作業計画。

## 0. 完成条件

ローカル環境で以下の E2E が通る状態を完成とする。

1. Next.js 画面から事業アイデアを入力できる
2. FastAPI `/api/v1/analyses` が入力を受け取る
3. ChromaDB で関連データを検索する
4. NetworkX で関連ノードを補完する
5. OpenAI API で 3 軸評価と GO/NO 判定を生成する
6. Next.js 画面に結果を表示する
7. ローカル開発環境で E2E を確認できる

## 1. 実装フェーズ

| Phase | ゴール | 成果物 |
|---|---|---|
| 1 | Next.js / FastAPI の最小構成を作る | `frontend/`, `backend/`, `infra/docker-compose.yml`, `.env.example` |
| 2 | MVP の検索・グラフ処理を FastAPI に移植する | `VectorSearchPort`, `GraphSearchPort`, ChromaDB / NetworkX adapters |
| 3 | LLM 評価処理を service 層に移植する | `LLMPort`, OpenAI adapter, analysis service |
| 4 | Supabase 永続化を実装する | repository adapter, `analyses`, `jobs` 保存 |
| 5 | Next.js 画面を仕上げる | 入力フォーム、結果表示、API client |
| 6 | 開発環境 E2E と最小テストを整える | backend unit tests, ローカル起動手順 |

## 2. 実装順

1. FastAPI の `/health` と `/api/v1/analyses` 仮エンドポイントを作る
2. Next.js の入力フォームを作り、FastAPI に POST できるようにする
3. MVP の `vector_store.py` を ChromaDB adapter に移す
4. MVP の `graph_search.py` を NetworkX adapter に移す
5. MVP の `analyzer.py` / `prompts.py` を LLM adapter と service に分ける
6. Supabase repository を追加し、分析結果を保存する
7. Docker Compose で frontend / backend を同時起動する
8. README にローカル起動、環境変数、E2E 手順を書く

## 3. 守る境界

| 境界 | 方針 |
|---|---|
| MVP | `mvp_streamlit/` は参照元として扱い、原則編集しない |
| Backend | domain / ports / adapters / api を分ける |
| Frontend | App Router を使い、API 呼び出しは `frontend/lib/api.ts` に寄せる |
| Supabase | service role key は backend のみで使い、frontend へ出さない |
| Azure 移行 | ChromaDB / NetworkX / OpenAI / Supabase は Port 経由にする |

## 4. 検証方針

| 段階 | 検証 |
|---|---|
| Phase 1 | `python -m compileall backend/app` と frontend の型構成確認 |
| Phase 2-3 | Port 単位の unit test |
| Phase 4 | Supabase 接続なしでも mock repository で動くこと |
| Phase 5 | ブラウザで入力から結果表示まで確認 |
| Phase 6 | `pytest` と手動 E2E |

## 5. 本番接続

今回のターゲットは開発環境での動作確認までとし、Vercel / Render へのデプロイは実施しない。本番化する場合は仕様§3.3 に従い、検索は Azure AI Search、GraphRAG は Microsoft GraphRAG、LLM は Azure OpenAI、DB は Azure 管理 DB へ Adapter 差し替えで移行する。

## 6. 進捗ログ

| 日付 | Phase | 状態 | メモ |
|---|---|---|---|
| 2026-05-12 | 1 | 完了 | FastAPI / Next.js の最小構成、build、pytest、ブラウザ疎通まで確認 |
| 2026-05-12 | 2 | 完了 | ChromaDB / NetworkX を Port-Adapter として backend に移植。API で検索結果と3軸コンテキストを返す |
| 2026-05-12 | 3 | 完了 | OpenAI LLM 評価処理を Port-Adapter として backend に移植。API で `status=evaluated`、GO/NO、Stage1/Stage2 を返す |
| 2026-05-12 | 4 | 完了 | Supabase に `analyses` / `jobs` を保存。同一 `Idempotency-Key` の2回目は保存済み分析を返す |
| 2026-05-12 | 5 | 完了 | Next.js 結果画面で承認者サマリー、3軸評価、提案、検索根拠、関連ノードを表示 |
| 2026-05-12 | 6 | 完了 | README に開発環境起動、E2E確認、検証コマンドを記録。デプロイは対象外 |

## 7. 環境メモ

| 項目 | 状態 |
|---|---|
| Python | ローカル実行環境は 3.11.7。`backend/pyproject.toml` は `>=3.11` に調整済み |
| Docker | `infra/docker-compose.yml` は Python 3.12 イメージを使うため、推奨環境との整合は維持 |
| pip check | 共有 Anaconda 環境に既存パッケージ衝突あり。以後は専用 venv または Docker での検証を優先する |
