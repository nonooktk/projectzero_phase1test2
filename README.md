# Tech0 Search

Streamlit MVP を Next.js + FastAPI + Supabase + ChromaDB + NetworkX + OpenAI 構成へ移植したアプリ。Phase 1 ではローカル開発環境で E2E を通し、その後 Render / Vercel への暫定デプロイへ進む。

## 現在の到達点

| Phase | 状態 | 内容 |
|---|---|---|
| 1 | 完了 | Next.js / FastAPI の最小構成 |
| 2 | 完了 | ChromaDB 検索 + NetworkX 関連ノード補完 |
| 3 | 完了 | OpenAI による Stage1 / Stage2 評価 |
| 4 | 完了 | Supabase `analyses` / `jobs` 保存と冪等性 |
| 5 | 完了 | 結果画面の実用表示 |
| 6 | 完了 | 開発環境E2E手順 |

## 構成

| パス | 役割 |
|---|---|
| `frontend/` | Next.js App Router。入力フォームと分析結果表示 |
| `backend/` | FastAPI。検索、グラフ補完、LLM評価、Supabase保存 |
| `data/` | ChromaDB / NetworkX の元データ |
| `supabase/migrations/0001_init.sql` | Supabase 初期DDL |
| `CODEX_AUTONOMOUS_IMPLEMENTATION_PLAN.md` | Codex自走実装の進捗ログ |

## 必要な環境変数

ルートの `.env` に以下を設定する。

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
CORS_ORIGINS_RAW=http://localhost:3000
VECTOR_SEARCH_BACKEND=simple
ENABLE_SUPABASE_SAVE=true
ENABLE_IDEMPOTENCY=true
ENABLE_LLM_FALLBACK=true
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=2
```

`SUPABASE_SERVICE_ROLE_KEY` は backend 専用である。frontend には渡さない。
`VECTOR_SEARCH_BACKEND=simple` は Render Free 向けの軽量検索である。ローカルで ChromaDB + SentenceTransformer を使う場合は `VECTOR_SEARCH_BACKEND=chroma` に変更する。

## ローカル起動

### 1. Backend

```bash
cd backend
python -m pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend

別ターミナルで実行する。

```bash
cd frontend
npm install
npm run dev
```

画面は `http://localhost:3000`、API health check は `http://127.0.0.1:8000/api/v1/health` で確認する。

## Docker Compose

ルート `.env` を用意したうえで実行する。

```bash
cd infra
docker compose up
```

初回は Python / Node 依存関係と SentenceTransformer モデルの取得で時間がかかる。

## Render Backend Deploy

Render の New Web Service では、リポジトリルートをサービスのRoot Directoryとして使う。`backend/` をRoot Directoryにすると、実行時にルート直下の `data/` が見えなくなるためである。

| 項目 | 値 |
|---|---|
| Repository | `https://github.com/nonooktk/projectzero_phase1test2` |
| Branch | `main` |
| Root Directory | 空欄 |
| Runtime | `Python 3` |
| Build Command | `pip install --upgrade pip && pip install -e backend` |
| Start Command | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/v1/health` |

Render の環境変数には以下を設定する。

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
CORS_ORIGINS_RAW=http://localhost:3000
VECTOR_SEARCH_BACKEND=simple
ENABLE_SUPABASE_SAVE=false
ENABLE_IDEMPOTENCY=false
ENABLE_LLM_FALLBACK=false
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=2
```

フロントエンドをVercelへデプロイした後は、`CORS_ORIGINS_RAW` にVercel URLをカンマ区切りで追加する。

## Vercel Frontend Deploy

Vercel では `frontend/` だけを Next.js アプリとしてデプロイする。バックエンドURLは build 時に `NEXT_PUBLIC_API_BASE_URL` として埋め込まれるため、Render のURLを先に用意しておく。

| 項目 | 値 |
|---|---|
| Repository | `https://github.com/nonooktk/projectzero_phase1test2` |
| Branch | `main` |
| Root Directory | `frontend` |
| Framework Preset | `Next.js` |
| Build Command | `npm run build` |
| Output Directory | `.next` |
| Install Command | `npm install` |

Vercel の環境変数には以下を設定する。

```bash
NEXT_PUBLIC_API_BASE_URL=https://<RenderのサービスURL>
```

Vercel のデプロイURLが発行されたら、Render 側の `CORS_ORIGINS_RAW` を以下のように更新して、Render を再デプロイする。

```bash
CORS_ORIGINS_RAW=http://localhost:3000,https://<VercelのURL>
```

反映後、Vercel の画面からテンプレート入力 → 分析スタートを実行し、API通信が通ることを確認する。

## E2E確認

画面から以下のような入力で分析を実行する。

| 項目 | 例 |
|---|---|
| ターゲット市場 | BEMS市場 |
| 活用アセット | 薄膜太陽電池とIoTセンサー |
| アイデア詳細 | 中小ビル向けに省エネ管理SaaSを提供し、施工会社ネットワークと既存センサー技術を活用して初期導入コストを下げる |

期待結果:

- `status` が `evaluated` になる
- GO/NO 判定が表示される
- 3軸評価、事業提案、検索根拠、関連ノードが表示される
- Supabase の `analyses` と `jobs` に保存される
- 同じ `Idempotency-Key` の API POST では同じ `analysis_id` が返る

## 検証コマンド

```bash
cd backend
python -m pytest tests

cd ../frontend
npm run build
npm audit --omit=dev
```

## 注意

ローカルの共有 Anaconda 環境では既存パッケージ衝突により `pip check` が失敗する場合がある。開発継続時は専用 venv か Docker Compose を優先する。

Azure 本番化時は仕様§3.3 に従い、ChromaDB / NetworkX / OpenAI / Supabase を Adapter 差し替えで Azure AI Search / Microsoft GraphRAG / Azure OpenAI / Azure DB 系へ移行する。
