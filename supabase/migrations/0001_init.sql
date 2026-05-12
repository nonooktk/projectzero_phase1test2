-- ============================================================
-- 0001_init.sql
-- Tech0 Search 暫定実装の初期スキーマ（JSONB ヘビー設計）
--
-- 設計方針：
--   - ChromaDB が main で検索・フィルタを担うため、Supabase は
--     raw JSON を `data` 列に保存。頻繁に WHERE する列だけ昇格。
--   - Azure 移行時（仕様§3.3）に AI Search のインデックス設計を
--     再構築する前提で柔軟性を優先。
--
-- 詳細は SUPABASE_SCHEMA.md を参照
-- ============================================================

create extension if not exists vector;
create extension if not exists pgcrypto;

-- ============================================================
-- RAG: 外部情報（市場・規制・競合）
-- ============================================================
create table rag_external (
  id          text primary key,                       -- mkt_001, reg_001, comp_001
  category    text not null,                          -- market_trend / regulation / competitor
  title       text not null,                          -- JSON.name
  content     text not null,                          -- ChromaDB 検索対象
  embedding   vector(384),                            -- all-MiniLM-L6-v2（バックアップ用）
  data        jsonb not null default '{}'::jsonb,    -- 元 JSON 全体
  created_at  timestamptz not null default now()
);
create index on rag_external(category);

-- ============================================================
-- RAG: 内部情報（技術・過去PJ）
-- ============================================================
create table rag_internal (
  id              text primary key,                   -- tech_001, proj_001
  category        text not null,                      -- technology / past_project
  title           text not null,
  content         text not null,
  embedding       vector(384),
  outcome_status  text,                               -- discontinued / success / etc.（過去PJ）
  risk_level_now  text,                               -- 低 / 中 / 高
  data            jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now()
);
create index on rag_internal(category);
create index on rag_internal(outcome_status);

-- ============================================================
-- conditions_now（過去PJ の核心データ・dict 構造を行展開）
-- ============================================================
create table project_conditions (
  id              uuid primary key default gen_random_uuid(),
  project_id      text not null references rag_internal(id) on delete cascade,
  condition_name  text not null,                      -- 例: "施工会社ネットワーク"
  status_now      text not null,                      -- 解決済 / 一部解決 / 未解決
  detail          text,
  year_assessed   int
);
create index on project_conditions(project_id);
create index on project_conditions(status_now);

-- ============================================================
-- RAG: キーマン
-- ============================================================
create table rag_persons (
  id            text primary key,                     -- person_001
  name          text not null,
  department    text,
  content       text not null,
  embedding     vector(384),
  availability  text,                                 -- 相談しやすい / 要アポ / 要上長承認
  data          jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now()
);

-- ============================================================
-- Graph
-- ============================================================
create table graph_nodes (
  id              text primary key,
  label           text not null,
  type            text not null check (type in ('technology','past_project','person','market'))
);

create table graph_edges (
  id              uuid primary key default gen_random_uuid(),
  source_id       text not null references graph_nodes(id) on delete cascade,
  target_id       text not null references graph_nodes(id) on delete cascade,
  relation        text not null
);
create index on graph_edges(source_id);
create index on graph_edges(target_id);

-- ============================================================
-- アプリ: 分析結果
-- ============================================================
create table analyses (
  id              uuid primary key default gen_random_uuid(),
  idea_text       text not null,
  go_no_go        text check (go_no_go in ('GO','NO','HOLD')),
  rationale       text,
  context_used    jsonb,
  llm_output      jsonb,
  created_at      timestamptz not null default now()
);
create index on analyses(created_at desc);

-- ============================================================
-- アプリ: ジョブ（冪等性）
-- ============================================================
create table jobs (
  id              uuid primary key default gen_random_uuid(),
  idempotency_key text unique not null,
  analysis_id     uuid references analyses(id) on delete set null,
  status          text not null check (status in ('queued','running','succeeded','failed')),
  error           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index on jobs(status);
