# 実装プラン（暫定環境版）— Tech0 Search

作成日: 2026-05-06
対象: `03_PROJECT_ZERO_要件定義書_ver07.docx` / `04_PROJECT_ZERO_仕様設計書_ver03.docx`
位置づけ: 既存 `IMPLEMENTATION_PLAN.md`（文書整備プラン）の補完。本書は実装作業の方針書。
方針: Azure 環境がまだ使えない期間でも Phase 1 PoC 相当の動作確認まで到達する暫定構成と、Azure 到達時の最小コード変更で本番化できる設計を両立する。

---

## 0. 前提と本書のゴール

| 項目 | 内容 |
|---|---|
| 確定済み技術スタック | フロント Next.js（TypeScript）＋Tailwind CSS、API FastAPI（Python）（仕様§1.3／要件§4.2） |
| 本番のターゲット構成 | Azure テナント内に閉じる（要件§7.4）。検索 Azure AI Search、ナレッジ Cosmos DB、推論 Microsoft GraphRAG、LLM Azure OpenAI、業務 DB Azure Database for MySQL、キャッシュ Azure Cache for Redis、OCR AI Document Intelligence |
| 暫定運用が必要な理由 | Azure サブスクリプション・閉域接続・Entra ID 連携の手配が完了するまで、開発と PoC 動作確認を止めない |
| 達成基準 | アイデア入力 → ハイブリッド検索 → GraphRAG 関連性補完 → 3 軸 LLM 評価 → GO/NO 判定 → 結果画面表示の一気通貫フローを暫定環境で再現する |
| 移行コストの目標 | Azure 到達時のコード変更を「設定値とアダプタ実装の差し替え」に限定。ドメイン層・ユースケース層・API 仕様は不変 |

参考章: 要件§1（プロジェクト概要）、要件§4（アーキテクチャ方針）、要件§7（制約条件）、仕様§1（アーキテクチャ設計）、仕様§5（インフラ仕様）、仕様§15（サーバーレス適用）。

---

## 1. アーキテクチャ方針

### 1.1 採用パターン

| 方針 | 採用形態 | 根拠 |
|---|---|---|
| アプリ全体 | モジュラーモノリス（Phase 1）→ マイクロサービス分解（Phase 2 以降） | 仕様§1／要件§4.3 |
| 外部依存の抽象化 | ヘキサゴナル（Port-Adapter） | 要件§4.3「LLM プロバイダーの切替をアダプター交換のみで対応」、§4.4「依存性逆転の原則」 |
| API スタイル | REST / OpenAPI 3.0 / RFC 7807 | 仕様§3.1／要件§4.4.1 |
| 並行性 | FastAPI の async + ThreadPoolExecutor | 要件§4.3／FR-004／FR-005 |
| バージョニング | URL パス（/api/v1/） | 仕様§3.1 |

### 1.2 レイヤー構造

```mermaid
flowchart TB
    UI["frontend (Next.js)<br/>Tailwind / fetch"] -->|HTTPS| API["api (FastAPI)<br/>OpenAPI 3.0"]

    subgraph Backend["FastAPI 内部"]
        API --> Service["application layer<br/>ユースケース・ワークフロー"]
        Service --> Domain["domain layer<br/>エンティティ／値オブジェクト"]
        Service -.uses.-> Ports["ports<br/>抽象IF"]
        Ports -.実装.-> Adapters["adapters/<br/>interim/ または azure/"]
    end

    Adapters -->|暫定| ExtInterim["OpenAI / Neon Postgres<br/>Upstash Redis / Tesseract"]
    Adapters -->|本番| ExtAzure["Azure OpenAI / MySQL<br/>AI Search / Cosmos DB<br/>Cache for Redis / DocIntel"]
```

### 1.3 Port-Adapter の二系統運用

「暫定実装」と「Azure 実装」を 2 つのアダプタファミリーとして同居させ、環境変数で切替する。Service 層と Domain 層は Port にのみ依存し、アダプタ実装を知らない。Azure 環境到達時はアダプタ差し替えと環境変数更新のみで切替が完了する設計とする。

切替単位は環境変数 `ADAPTER_PROFILE=interim|azure` の 1 値とし、DI コンテナ（後述§4.3）が起動時に対応するアダプタファミリーを束ねて Service 層へ注入する。

---

## 2. 暫定デプロイ環境の選定

### 2.1 各層のサービス比較と推奨

#### 2.1.1 フロントエンド（Next.js）

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Vercel | ◎（採用） | Next.js 公式の最適化・ブランチプレビュー・Edge Network・無料枠で十分 | 商用利用は Pro 必須（PoC は Hobby で可） |
| Cloudflare Pages | ◯ | 無料枠が広い・Workers 連携 | Next.js SSR は Workers 経由で制約あり |
| Netlify | △ | 老舗で安定 | Next.js 14 以降の機能対応は Vercel に劣る |

採用根拠: Next.js のフレームワーク連携が最良で、ブランチごとのプレビュー URL が自動生成される。Phase 2 移行時は Static Web Apps へ静的アセットだけ持ち出せばよい（仕様§5.1）。

#### 2.1.2 バックエンド（FastAPI）

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Render | ◎（採用） | GitHub 連携・自動デプロイ・Docker サポート・無料枠あり | 無料枠はコールドスタートあり（数十秒） |
| Fly.io | ◯ | Edge 配置・WebSocket／長時間処理に強い | 課金が複雑、無料枠は限定的 |
| Railway | △ | DX 良好 | 無料枠が縮小傾向 |
| Koyeb | △ | 欧州拠点・無料枠あり | エコシステムが小さい |

採用根拠: PoC 段階では Starter $7/月で常時起動とログ／メトリクスを確保する。Docker 直接デプロイ可で、Azure Container Apps へ後日移行する際もコンテナイメージをそのまま再利用できる。

#### 2.1.3 業務 DB

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Neon（Postgres） | ◎（採用） | 無料 3GB・サーバーレス・ブランチ機能・pgvector 標準サポート | MySQL でなく Postgres |
| Supabase | ◯ | Auth／Storage が同居 | Auth は Phase 2 で Entra ID へ置き換えるため過剰機能 |
| PlanetScale（MySQL） | △ | 本番（Azure DB for MySQL）に近い | 無料枠が縮小・ブランチ機能は便利だが本件には過剰 |
| Render Postgres | ◯ | 同 PaaS で完結 | ブランチ機能なし |

採用根拠: 暫定段階で MySQL に拘ると pgvector などの機能を別途用意する必要がある。Postgres を採用してアプリ層は SQLAlchemy／Alembic で吸収し、本番移行時にスキーマ DDL のみ MySQL 用に再生成する（仕様§4.1／付録 A「DB 移行ハマりポイント」）。

#### 2.1.4 ベクトル検索

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Neon + pgvector | ◎（採用） | 同一 DB で完結・運用コストゼロ・pgvector はハイブリッド検索ライブラリ充実 | 大規模では性能劣化（Phase 1 規模では問題なし） |
| Qdrant Cloud | ◯ | 専用エンジンで高速・無料クラスタあり | 別サービス追加で運用負荷増 |
| Pinecone | △ | マネージド検索の老舗 | 無料枠が小さい |

採用根拠: 暫定では Postgres に集約して構成を最小化する。VectorSearchPort 経由のため、本番 Azure AI Search への切替はアダプタ差し替えのみで完結する。BM25 は Postgres の `tsvector` ＋ pgvector のスコア合成で「ハイブリッド検索」を再現する（仕様§3.2／FR-002）。

#### 2.1.5 キャッシュ

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Upstash Redis | ◎（採用） | Serverless・REST／TLS／無料 10K cmd/日 | スループット上限あり |
| Redis Cloud Free | ◯ | 標準 Redis API | 無料枠 30MB |

採用根拠: cache-aside パターン（仕様§8.1）の実装が標準 Redis API でそのまま動く。本番 Azure Cache for Redis への切替は接続文字列のみ変更。

#### 2.1.6 LLM

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| OpenAI API（直接） | ◎（採用） | Azure OpenAI と同一モデル系列（GPT-4o-mini）・SDK 互換 | 機密データ投入は不可（PoC ダミーデータ前提） |
| Anthropic Claude API | ◯ | 性能高 | Azure OpenAI への移行時にプロンプト再調整必要 |

採用根拠: 本番で Azure OpenAI（要件§8.3.1）を採用するため、API 互換性のある OpenAI 直接が暫定として最良。`openai` ライブラリは `base_url` を `https://*.openai.azure.com/` に切替えれば Azure OpenAI を使える。**機密データは投入しない**ことを暫定環境のルールとして明文化する（後述§9）。

#### 2.1.7 OCR

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Tesseract（OSS） | ◎（採用） | 無料・コンテナ同梱可・追加 API 不要 | 精度は AI Document Intelligence に劣る |
| Google Cloud Vision | △ | 精度高 | 別ベンダーへの依存が増える |

採用根拠: 70 年分の劣化資料の高精度 OCR は AI Document Intelligence の役割（要件§7.4／仕様§12.2）。暫定では PDF テキスト抽出と低劣化資料に限定し、Tesseract で十分。OCRPort 経由のため切替容易。

#### 2.1.8 GraphRAG

暫定でも本番でも Microsoft GraphRAG（OSS）パッケージを使用する。要件§4.2／§4.5、仕様§1.3 に従う。Cosmos DB の代替として Postgres JSONB で永続化し、Blob Storage の代替としてローカル Volume または S3 互換ストレージ（後述）を用いる。

#### 2.1.9 Blob ストレージ

| 候補 | 推奨度 | 強み | 弱み |
|---|---|---|---|
| Cloudflare R2 | ◎（採用） | S3 互換・無料 10GB・エグレス無料 | リージョン選定が限定的 |
| AWS S3 | ◯ | 業界標準 | エグレス課金あり |
| Render Disk | △ | 同 PaaS で完結 | ボリューム上限あり |

採用根拠: PDF 添付・GraphRAG 中間ファイル（Parquet 等）の保存先として S3 互換が最も汎用。Azure Blob Storage への切替は SDK の差し替えのみ（`boto3` → `azure-storage-blob`）。

### 2.2 暫定環境スタック総括

| 層 | 暫定 | 本番（Azure） | 移行時の作業 |
|---|---|---|---|
| フロント配信 | Vercel | Static Web Apps | ビルド成果物のホスト切替・環境変数更新 |
| API 配信 | Render | Container Apps / AKS | コンテナイメージを Azure Container Registry に push |
| 業務 DB | Neon Postgres | Azure DB for MySQL | DDL 再生成・データ移行（仕様§12） |
| 検索／ベクトル | Neon pgvector | Azure AI Search | インデックス再構築・アダプタ差替 |
| ナレッジ DB | Neon JSONB | Azure Cosmos DB | JSON エクスポート → Cosmos インポート |
| キャッシュ | Upstash Redis | Azure Cache for Redis | 接続文字列のみ変更 |
| Blob | Cloudflare R2 | Azure Blob Storage | アダプタ差替・データ移行 |
| LLM | OpenAI API | Azure OpenAI | base_url・API key 差替 |
| OCR | Tesseract | AI Document Intelligence | アダプタ差替 |
| GraphRAG | Microsoft GraphRAG（OSS） | 同左（Azure 上） | 不要（同パッケージ） |
| 認証 | なし（社内限定 URL ＋ IP 制限） | Entra ID SSO + RBAC | アダプタ差替・ミドルウェア差替（仕様§3.1） |

---

## 3. Port / Adapter 境界設計

### 3.1 抽象 IF（Port）一覧

| Port 名 | 責務 | 主要メソッド | 暫定 Adapter | Azure Adapter |
|---|---|---|---|---|
| `LLMPort` | LLM 呼び出し（chat completion） | `complete(messages, model, **opts)` | `OpenAIAdapter` | `AzureOpenAIAdapter` |
| `VectorSearchPort` | ハイブリッド検索（FR-002） | `hybrid_search(query, n, filters)` | `PgVectorAdapter`（pgvector + tsvector） | `AzureAISearchAdapter` |
| `KnowledgeStorePort` | グラフノード／文書 JSON 保管 | `upsert(doc)`、`get(id)`、`change_feed()` | `PgJsonbAdapter` | `CosmosDBAdapter` |
| `RelationalDBPort` | 業務エンティティ CRUD | SQLAlchemy セッション提供 | `PostgresAdapter` | `MySQLAdapter` |
| `CachePort` | cache-aside キャッシュ | `get/set/delete/setex` | `UpstashRedisAdapter` | `AzureCacheRedisAdapter` |
| `BlobPort` | バイナリ／中間ファイル保管 | `put/get/url` | `R2Adapter`（boto3 互換） | `AzureBlobAdapter` |
| `OCRPort` | PDF・画像のテキスト抽出 | `extract(file)` | `TesseractAdapter` | `DocumentIntelligenceAdapter` |
| `AuthPort` | 認証・テナント解決 | `verify(token)`、`current_user()` | `NoneAdapter`（DEV ヘッダーで擬似） | `EntraIDAdapter` |
| `ObservabilityPort` | ログ・メトリクス・トレース | OpenTelemetry SDK ラッパ | `OtelStdoutAdapter` | `OtelAzureMonitorAdapter` |

### 3.2 切替の実装イメージ

```python
# src/infra/container.py
from src.config import settings

if settings.adapter_profile == "azure":
    from src.adapters.azure import (
        AzureOpenAIAdapter as LLM,
        AzureAISearchAdapter as VectorSearch,
        ...
    )
else:
    from src.adapters.interim import (
        OpenAIAdapter as LLM,
        PgVectorAdapter as VectorSearch,
        ...
    )

container = Container(llm=LLM(...), vector=VectorSearch(...), ...)
```

Service 層は `container.llm.complete(...)` の呼び方しか知らない。アダプタの実体差し替えで暫定 ↔ 本番の切替が完了する。

### 3.3 GraphRAG の扱い

GraphRAG（OSS）は内部で LLM・ベクトル DB・グラフストアを呼ぶ。これらは GraphRAG 設定ファイル（`settings.yaml`）の `llm.api_base`・`embeddings.api_base`・`storage.type` で制御できる。アプリは GraphRAG を `RAGEnginePort` 越しに呼び出し、設定ファイルだけを `interim/` `azure/` で切替える。

---

## 4. リポジトリ構造

### 4.1 構成方針

monorepo（単一リポジトリ・複数アプリ）を採用する。フロント・バック・共有型・インフラ定義を一箇所で管理し、PR 単位で全体整合を取りやすくする。Phase 2 のマイクロサービス分解時に分割する。

### 4.2 ディレクトリ階層

```
project-zero/
├── apps/
│   ├── frontend/                  # Next.js 14 (App Router) + Tailwind
│   │   ├── src/
│   │   │   ├── app/               # ルーティング（/、/history）
│   │   │   ├── components/        # SearchBox, ResultDashboard など
│   │   │   ├── lib/               # APIクライアント・型
│   │   │   └── styles/
│   │   ├── public/
│   │   ├── package.json
│   │   └── next.config.mjs
│   │
│   └── backend/                   # FastAPI
│       ├── src/
│       │   ├── api/               # FastAPI ルータ（/api/v1/*）
│       │   │   ├── search.py
│       │   │   ├── analyses.py
│       │   │   └── health.py
│       │   ├── application/       # ユースケース層（仕様§7.3 等）
│       │   │   ├── analyze_idea.py        # FR-001〜005 ワークフロー
│       │   │   └── hybrid_search.py
│       │   ├── domain/            # エンティティ・VO
│       │   │   ├── analysis.py
│       │   │   ├── score.py
│       │   │   └── citation.py
│       │   ├── ports/             # 抽象IF
│       │   │   ├── llm.py
│       │   │   ├── vector_search.py
│       │   │   └── ...
│       │   ├── adapters/
│       │   │   ├── interim/       # 暫定アダプタ群
│       │   │   │   ├── openai_llm.py
│       │   │   │   ├── pgvector_search.py
│       │   │   │   └── ...
│       │   │   └── azure/         # 本番アダプタ群（実装は段階的に）
│       │   │       ├── azure_openai_llm.py
│       │   │       └── ...
│       │   ├── infra/             # DI コンテナ・設定・観測
│       │   │   ├── container.py
│       │   │   ├── config.py
│       │   │   ├── otel.py
│       │   │   └── circuit_breaker.py     # 仕様§10.1
│       │   ├── graphrag/          # GraphRAG 設定とラッパ
│       │   │   ├── settings.interim.yaml
│       │   │   └── settings.azure.yaml
│       │   └── main.py
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   └── e2e/
│       ├── alembic/               # マイグレーション（仕様§12.4）
│       ├── pyproject.toml
│       └── Dockerfile
│
├── packages/
│   └── shared-types/              # OpenAPI 3.0 から両側に型生成
│       └── openapi.yaml
│
├── infra/
│   ├── docker-compose.yml         # ローカル: Postgres+pgvector+Redis+app
│   ├── render.yaml                # Render Blueprint
│   └── vercel.json                # Vercel 設定
│
├── .github/
│   └── workflows/
│       ├── ci.yml                 # lint/test/build
│       ├── deploy-frontend.yml
│       └── deploy-backend.yml
│
├── docs/
│   └── architecture-decisions/    # ADR
│
├── .env.example
├── README.md
└── CLAUDE.md
```

### 4.3 設定ファイル方針

| ファイル | 役割 |
|---|---|
| `apps/backend/src/infra/config.py` | Pydantic Settings。環境変数を型付きでロード（`ADAPTER_PROFILE`、各種接続文字列、レート制限値） |
| `apps/backend/.env.example` | dev／interim／azure の差分が分かるテンプレート |
| `packages/shared-types/openapi.yaml` | フロント・バック・テストの共有 source of truth。仕様§3.1 |
| `infra/docker-compose.yml` | ローカル統合テスト用（Postgres + Redis + Tesseract コンテナ） |

---

## 5. デプロイワークフロー

### 5.1 ブランチ戦略

| ブランチ | 用途 | デプロイ先 |
|---|---|---|
| `main` | 安定版 | Vercel Production／Render Production |
| `develop` | 統合用 | Vercel Preview／Render Staging |
| `feature/*` | PR 単位 | Vercel Preview（自動）／Render は build のみ |

### 5.2 CI（GitHub Actions）

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `ci.yml` | PR・push | フロント lint／test／build、バック lint／pytest／OpenAPI 整合チェック |
| `deploy-frontend.yml` | `main` push | Vercel が自動デプロイ（GitHub 連携）。Actions は通知のみ |
| `deploy-backend.yml` | `main` push | Docker build → Render に push（Blueprint 経由）または Render Auto-Deploy 機能 |
| `migrate.yml` | 手動 | Alembic マイグレーション実行（本番 DB に対して） |

### 5.3 環境変数とシークレット

| ストア | 用途 | 採用 |
|---|---|---|
| Doppler | 中央集中シークレット管理／環境別配信／CLI 連携 | ◎ |
| GitHub Actions Secrets | CI/CD 内で使用するキー | ◎（Doppler と併用） |
| Vercel 環境変数 | フロント側ビルド時／実行時 | 標準 |
| Render 環境変数 | バック実行時 | 標準 |

Doppler を「中央 source of truth」とし、Vercel／Render／GitHub Actions が起動時に取得する形で同期する。Azure 移行時は Azure Key Vault に置換する（仕様§13.1）。

### 5.4 デプロイの流れ

```mermaid
sequenceDiagram
    actor Dev as 開発者
    participant GH as GitHub
    participant CI as Actions
    participant Doppler as Doppler
    participant Vercel as Vercel
    participant Render as Render
    participant Neon as Neon Postgres

    Dev->>GH: PR push (feature ブランチ)
    GH->>CI: lint / test / build
    CI-->>GH: ✓
    GH->>Vercel: Preview デプロイ（フロント）
    Dev->>GH: PR merge to main
    GH->>Vercel: Production デプロイ
    GH->>Render: Auto-Deploy（バック）
    Render->>Doppler: 環境変数取得
    Render->>Neon: 起動時マイグレーション実行
    Render-->>Vercel: API ready
```

---

## 6. 暫定 → Azure 移行手順

### 6.1 移行ステップ

| 段階 | 内容 | 影響範囲 |
|---|---|---|
| S1 | Azure サブスクリプション・リソースグループ・VNet 準備（IT 部門と連携） | インフラのみ |
| S2 | Azure 側のリソース構築（AI Search／Cosmos DB／MySQL／Cache for Redis／Blob／OpenAI／Document Intelligence） | インフラのみ |
| S3 | `adapters/azure/` の各アダプタ実装を完成させる（IF は確定済み） | アプリコード |
| S4 | Stage 環境で `ADAPTER_PROFILE=azure` を有効化し、E2E テストを通す | 設定値 |
| S5 | データ移行（仕様§12 準拠）。Postgres → MySQL は Alembic で生成した DDL を MySQL 用に変換、データは pg_dump → CSV → mysqlimport | データ |
| S6 | Vector データ移行（pgvector → AI Search）。仕様§12.5 のチェックサム検証 | データ |
| S7 | DNS／ホストの切替（Vercel → Static Web Apps、Render → Container Apps） | インフラのみ |
| S8 | Entra ID 連携と RBAC 有効化（仕様§13.5、要件§NFR-009） | アプリ＋設定 |

### 6.2 認証の段階的切替

| 段階 | 状態 | 実装 |
|---|---|---|
| 暫定 PoC | 認証なし／社内限定 URL ＋ IP 制限 | `AuthPort = NoneAdapter`。dev ヘッダー `X-Dev-User` で疑似ログイン |
| 暫定強化 | 静的 API キー | `AuthPort = ApiKeyAdapter`。Render 環境変数で配布 |
| Azure 切替 | Entra ID Bearer Token | `AuthPort = EntraIDAdapter`。仕様§3.1（Phase 2 で Bearer Token） |

### 6.3 環境変数の差分テンプレート

| 変数名 | 暫定値（例） | 本番値（例） |
|---|---|---|
| `ADAPTER_PROFILE` | `interim` | `azure` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | `https://<resource>.openai.azure.com/` |
| `LLM_API_KEY` | OpenAI API key | Azure OpenAI key（Key Vault 参照） |
| `DB_URL` | `postgres://user:pass@neon...` | `mysql+pymysql://user:pass@azure-mysql...` |
| `VECTOR_BACKEND` | `pgvector` | `azure_ai_search` |
| `BLOB_BACKEND` | `r2` | `azure_blob` |
| `CACHE_URL` | Upstash REST URL | Azure Cache for Redis 接続文字列 |
| `OCR_BACKEND` | `tesseract` | `document_intelligence` |
| `AUTH_BACKEND` | `none` | `entra_id` |

---

## 7. Phase 1 PoC 受入基準との整合

### 7.1 性能要件マトリクス（暫定環境で測れる範囲）

仕様§14.1／要件§7.3 と対応。

| SLI | 仕様§14.1（Phase 1 SLO） | 暫定環境で測定可能か | 備考 |
|---|---|---|---|
| 同期 API p95（対象1） | < 1.5 秒 | ◎ | Render Starter で常時起動。コールドスタート問題なし |
| フル分析 p95（対象2） | < 25 秒 | ◯ | OpenAI API のレイテンシは Azure OpenAI と概ね同等。リージョン差は誤差 |
| LLM 単発 p95（対象3） | < 8 秒 | ◯ | OpenAI API モデル別レイテンシで再現可能 |
| 可用性（SLI-1） | 99.9% | △ | Render 無料枠は SLA なし。Starter プラン以上で限定的に測定 |
| ハルシネーション率（SLI-3） | < 3% | ◎ | 評価方法は §7.2 |
| 情報漏洩（SLI-4） | 0 件 | △ | 暫定は機密データ未投入のため計測対象外（後述§9） |

### 7.2 ハルシネーション率の評価方法

要件§7.3 マイルストーン1 合格基準（ハルシネーション率 < 3%）に対する暫定環境での評価フローを以下に定義する。

| ステップ | 内容 |
|---|---|
| 1 | ゴールデンデータセット 50 件を専門家工数で構築（要件§4.5.1／仕様§12.1） |
| 2 | 各テストアイデアに対し AI 出力を生成し、Citation（出典）の正確性を専門家がレビュー |
| 3 | 「Citation がない」「Citation の指す元文書に該当記述がない」「3C 分析の事実誤認」を hallucination としてカウント |
| 4 | 週次で 50 サンプル評価し、率を Grafana ダッシュボードに記録（仕様§11.1 SLI-3） |

### 7.3 動作確認フロー（暫定環境での E2E）

```mermaid
flowchart LR
    U["利用者"] -->|3項目入力＋PDF添付| V["Vercel<br/>Next.js"]
    V -->|POST /api/v1/analyses<br/>+Idempotency-Key| R["Render<br/>FastAPI"]
    R --> N["Neon Postgres<br/>analyses INSERT"]
    R --> NV["Neon pgvector<br/>ハイブリッド検索"]
    R --> RG["GraphRAG OSS<br/>関連性補完"]
    R --> O["OpenAI API<br/>Pass1/Pass2 並列"]
    O --> R
    R --> N2["analysis_results<br/>UPDATE"]
    R -->|202 → 200 OK| V
    V -->|GO/NO 表示<br/>Citation付き| U
```

PoC 受入条件: 上記フローを 30 秒以内に完了し、Citation 付き GO/NO 判定が画面表示される。

---

## 8. コスト見積（暫定環境）

### 8.1 月額概算（Phase 1 PoC 規模／約 300 名・DAU 250 名）

| サービス | プラン | 月額 | 備考 |
|---|---|---|---|
| Vercel | Hobby | $0 | 無料枠で十分 |
| Render | Starter（バックエンド） | $7 | 常時起動・512MB RAM |
| Neon Postgres | Launch | $19 | 10GB ストレージ・常時起動・自動バックアップ |
| Upstash Redis | Free | $0 | 10K cmd/日 |
| Cloudflare R2 | Free | $0 | 10GB 無料・エグレス無料 |
| OpenAI API | 従量 | $50〜200 | GPT-4o-mini × 月 1,000 分析想定 |
| Doppler | Developer | $0 | 個人〜小チーム無料 |
| ドメイン（独自） | 任意 | $1〜2 | $15／年程度 |
| 監視（任意） | Better Uptime Free | $0 | エンドポイント死活監視 |
| **合計** | | **$77〜228／月** | LLM 利用量で変動 |

### 8.2 コスト管理の方針

| 観点 | 方針 |
|---|---|
| LLM コスト上限 | OpenAI API ダッシュボードで月額上限を $300 に設定。超過時は自動停止 |
| キャッシュ徹底 | 仕様§8 のとおり 24 時間 TTL を厳守。同一クエリの LLM 再呼び出しを抑制 |
| 並列度制御 | Pass 1 / Pass 2 の `ThreadPoolExecutor` 上限を 5 に設定（仕様§10.3） |
| プロンプト圧縮 | システムプロンプトのトークン数を都度計測し、不要文を削る |

---

## 9. 想定リスク・前提

### 9.1 暫定環境特有の制約

| リスク | 影響 | 対策 |
|---|---|---|
| Render Starter のメモリ不足（512MB） | GraphRAG ロード時に OOM | Phase 1 中盤で 2GB プランへ昇格、または GraphRAG をワーカー分離 |
| OpenAI API のレート制限 | フル分析の同時並列数に上限 | バルクヘッド（仕様§10.3）の上限を Tier に合わせて設定 |
| Neon Free 3GB 上限 | データ拡大時に容量不足 | Launch プランに昇格、もしくは古い `audit_logs` を S3 に退避 |
| Upstash 10K cmd/日 | キャッシュヒットが低いと枯渇 | プリウォーム（仕様§8.3）で「人気クエリ Top20」を固定キャッシュ |
| Vercel Hobby は商用利用不可 | 本格運用に支障 | PoC 段階のみ Hobby、Pilot 移行と同時に Pro に切替（または Azure に移行） |
| 暫定環境はインターネット直結 | 機密データ投入は禁止 | **暫定はダミーデータのみ。実機密データは Azure 環境到達まで触れない**（要件§7.4／§8.3.1） |
| OpenAI 直叩きで学習利用される懸念 | 入力データの保護方針が違う | OpenAI API の opt-out 設定を有効化／組織契約。さらに「ダミーデータのみ」を社内ルール化 |
| 認証なし状態の暴露 | 部外者アクセスのリスク | Render Web Service は無料枠でも IP 制限可能。社内 VPN／IP からのみ許可 |

### 9.2 前提条件

| 項目 | 前提 |
|---|---|
| 利用データ | 暫定期間中はダミーデータ・公開情報・合成データのみ |
| 利用者 | 開発チーム＋指定レビュアーのみ。一般社員には公開しない |
| 本番判定 | Phase 1 PoC の合格基準（要件§7.3）の達成判定は、Azure 環境構築後に再実施する |
| 暫定 → Azure の所要 | アダプタ実装と環境構築を並行して進める前提で、Azure 切替まで 4〜6 週間を想定 |

### 9.3 受け入れる技術負債

| 項目 | 負債 | 解消時期 |
|---|---|---|
| Postgres 採用 | 本番 MySQL と DDL が異なる | Azure 移行時に Alembic で MySQL 用 DDL を再生成 |
| 認証なし | 本格運用に不可 | Phase 2 で Entra ID Bearer Token に切替（仕様§3.1） |
| Tesseract OCR | 精度が AI Document Intelligence に劣る | Wave 1 取り込み（仕様§12.1）の手前で AI Document Intelligence に切替 |
| Render 単一インスタンス | SPOF（仕様§10.5） | Azure Container Apps の最小 2 レプリカに移行 |

---

## 10. 次のアクション（優先度順）

| 優先度 | タスク | 着手目安 | 完了の定義 |
|---|---|---|---|
| **P0** | リポジトリ雛形作成（monorepo・ディレクトリ階層・`.env.example`・OpenAPI YAML 雛形・Docker Compose） | 即日 | `git clone` ＋ `docker compose up` で空の FastAPI（`/health` 200 応答）と Next.js（トップ画面）が起動する |
| **P0** | Port インターフェイス定義と DI コンテナ実装（§3.1 の 9 Port） | 1 週目 | `LLMPort` などの抽象 IF が `src/ports/` に存在し、`Container` がプロファイル別に注入できる |
| **P1** | 暫定アダプタの実装（OpenAI／pgvector／Postgres／Upstash／Tesseract／R2／OtelStdout） | 1〜2 週目 | 各アダプタの単体テストが緑になり、`/api/v1/search`・`/api/v1/analyses` のスタブが動作する |
| **P1** | 暫定デプロイ環境の構築（Vercel・Render・Neon・Upstash・R2・Doppler のアカウント開設と接続検証） | 1 週目末 | Vercel Preview と Render Staging が `develop` ブランチで自動デプロイされる |
| **P2** | E2E スモークテストの作成（仕様§14.3 を縮小した k6 シナリオ：1 ユーザーで分析リクエスト → 30 秒以内に GO/NO 判定取得） | 2 週目末 | GitHub Actions の `ci.yml` で E2E が緑になる |

---

## 参考資料

| 文書 | バージョン | 参照箇所（主） |
|---|---|---|
| 要件定義書 | ver07 | §1 概要／§4 アーキテクチャ方針／§5 機能要件／§7 制約条件／§8 セキュリティ／§NFR 全般 |
| 仕様設計書 | ver03 | §1 アーキテクチャ／§3 API 仕様／§5 インフラ／§7 API 詳細／§8 キャッシュ／§10 可用性／§11 可観測性／§12 マイグレーション／§13 セキュリティ／§14 性能／§15 12 Factor／付録 A |
| 既存 IMPLEMENTATION_PLAN.md | 2026-05-02 | 文書整備プランの上位計画。本書はその実装フェーズへの橋渡し |
