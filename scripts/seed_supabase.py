"""
seed_supabase.py
data/*.json を Supabase に投入する。embedding は MiniLM-L6-v2 で生成して同時格納。

学習スケルトン：TODO を順に埋めて動かしてみる。
最初から完成形を写経しないこと（CLAUDE.md ①②③テンプレ参照）。

実行例:
  uv run python scripts/seed_supabase.py
依存:
  pip install supabase sentence-transformers
環境変数:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client

load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def load_json(name: str) -> list[dict]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def embed(texts: list[str], model: SentenceTransformer) -> list[list[float]]:
    # TODO: バッチサイズを意識する。今は全件一括で OK
    return [v.tolist() for v in model.encode(texts)]


def seed_external(sb: Client, model: SentenceTransformer) -> None:
    rows = load_json("external.json")
    vectors = embed([r["content"] for r in rows], model)
    payload = [
        {"id": r["id"], "category": r["category"], "title": r["name"],
         "content": r["content"],"embedding": v, "data": r}
         for r, v in zip(rows, vectors)
    ]
    sb.table("rag_external").upsert(payload).execute()
    print(f"rag_external: {len(payload)} row upserted")

def seed_internal(sb: Client, model: SentenceTransformer) -> None:
    rows = load_json("internal.json")
    vectors = embed([r["content"] for r in rows], model)
    payload = [
        {"id": r["id"], "category": r["category"], "title": r["name"],
         "content": r["content"], "outcome_status": r.get("outcome_status"),
         "risk_level_now": r.get("risk_level_now"), "embedding": v, "data": r}
         for r, v in zip(rows, vectors)
    ]
    sb.table("rag_internal").upsert(payload).execute()
    print(f"rag_internal: {len(payload)} row upserted")

    cond_payload = []
    for r in rows:
        conditions = r.get("conditions_now", {})
        for name, v in conditions.items():
            cond_payload.append({
                "project_id": r["id"],
                "condition_name": name,
                "status_now": v["status"],
                "detail": v["detail"],
                "year_assessed": v["year_assessed"]
            })
    if cond_payload:
        sb.table("project_conditions").upsert(cond_payload).execute()
        print(f"project_conditions: {len(cond_payload)} rows upserted")


def seed_persons(sb: Client, model: SentenceTransformer) -> None:
    # TODO: rag_persons を upsert
    rows = load_json("persons.json")
    vectors = embed([r["content"] for r in rows], model)
    payload = [
        {"id": r["id"], "name": r["name"], "department": r["department"],
         "content": r["content"],"embedding": v, "availability": r["availability"],
         "data": r}
         for r, v in zip(rows, vectors)
    ]
    sb.table("rag_persons").upsert(payload).execute()
    print(f"rag_persons: {len(payload)} row upserted")


def seed_graph(sb: Client) -> None:
    nodes = load_json("graph/nodes.json")
    edges = load_json("graph/edges.json")
    # TODO: graph_nodes → graph_edges の順で upsert
    payload_nodes = [
        {"id": r["id"], "label": r["label"], "type": r["type"]}
         for r in nodes
    ]
    sb.table("graph_nodes").upsert(payload_nodes).execute()
    print(f"nodes: {len(payload_nodes)} row upserted")

    payload_edges = [
        {"source_id": r["source"], "target_id": r["target"], "relation": r["relation"]}
         for r in edges
    ]
    sb.table("graph_edges").upsert(payload_edges).execute()
    print(f"edges: {len(payload_edges)} row upserted")


def main() -> None:
    sb = get_client()
    model = SentenceTransformer(EMBEDDING_MODEL)
    seed_external(sb, model)
    seed_internal(sb, model)
    seed_persons(sb, model)
    seed_graph(sb)
    print("done.")


if __name__ == "__main__":
    main()
