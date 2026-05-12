"""
graph_search.py — NetworkX によるグラフ検索モジュール

担当: Bさん（グラフ＆ロジック担当）

【このファイルの役割】
- nodes.json / edges.json を読み込んでNetworkXグラフを構築する
- ノードIDのリストを受け取り、depth=1 で隣接ノードを返す
- ChromaDB検索結果と組み合わせて、3軸のコンテキストテキストを生成する（Context Builder）

【使うライブラリ】
- networkx: グラフ構造の構築と検索
"""

import json
import os
import networkx as nx

# --- 定数 ---
GRAPH_DIR = os.path.join(os.path.dirname(__file__), "../data/graph")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")


def build_graph() -> nx.Graph:
    """
    nodes.json と edges.json を読み込み、NetworkX グラフを構築して返す。

    Returns:
        nx.Graph: 構築済みのグラフ
    """
    G = nx.Graph()

    with open(os.path.join(GRAPH_DIR, "nodes.json"), "r", encoding="utf-8") as f:
        nodes = json.load(f)
    for node in nodes:
        G.add_node(node["id"], **node)

    with open(os.path.join(GRAPH_DIR, "edges.json"), "r", encoding="utf-8") as f:
        edges = json.load(f)
    for edge in edges:
        G.add_edge(edge["source"], edge["target"], relation=edge["relation"])

    return G


def get_neighbors(node_ids: list[str], graph: nx.Graph = None) -> list[dict]:
    """
    ノードIDのリストを受け取り、depth=1 で隣接する全ノードの情報を返す。

    Args:
        node_ids (list[str]): 起点となるノードIDのリスト
        graph (nx.Graph): グラフ（省略時は自動構築）

    Returns:
        list[dict]: 隣接ノードの情報リスト
        例:
        [
          {"id": "person_001", "label": "田中 誠", "type": "person", "relation": "担当できる"},
          ...
        ]
    """
    if graph is None:
        graph = build_graph()

    seen = set()
    results = []
    for node_id in node_ids:
        if node_id not in graph:
            continue
        for neighbor in graph.neighbors(node_id):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            node_attrs = graph.nodes[neighbor]
            relation = graph[node_id][neighbor].get("relation", "")
            results.append({
                "id": neighbor,
                "label": node_attrs.get("label", neighbor),
                "type": node_attrs.get("type", ""),
                "relation": relation,
            })
    return results


def build_context(vector_results: list[dict], graph: nx.Graph = None) -> dict:
    """
    ChromaDB の検索結果を受け取り、グラフ検索で拡張して3軸のコンテキストを返す。
    （Context Builder）

    Args:
        vector_results (list[dict]): vector_store.search() の返り値
        graph (nx.Graph): グラフ（省略時は自動構築）

    Returns:
        dict: 3軸のコンテキストテキスト
        例:
        {
          "external_context": "【市場情報】...\n【規制情報】...",
          "internal_context": "【保有技術】...\n【失敗事例】...",
          "org_context":      "【キーマン】..."
        }
    """
    if graph is None:
        graph = build_graph()

    # source ごとに仕分け
    external = [r for r in vector_results if r["source"] == "external"]
    internal = [r for r in vector_results if r["source"] == "internal"]
    persons  = [r for r in vector_results if r["source"] == "persons"]

    # グラフ隣接から person ノードを追加（persons 検索で漏れた人物を補完）
    all_ids = [r["id"] for r in vector_results]
    person_ids = {r["id"] for r in persons}
    extra_persons = [
        f"{nb['label']}（{nb['relation']}）"
        for nb in get_neighbors(all_ids, graph)
        if nb["type"] == "person" and nb["id"] not in person_ids
    ]

    # 3軸テキストを組み立て
    external_context = "【外部情報】\n" + "\n".join(r["content"] for r in external) if external else ""
    internal_context = "【社内情報】\n" + "\n".join(r["content"] for r in internal) if internal else ""
    org_lines = [r["content"] for r in persons] + extra_persons
    org_context = "【キーマン】\n" + "\n".join(org_lines) if org_lines else ""

    return {
        "external_context": external_context,
        "internal_context": internal_context,
        "org_context": org_context,
    }


if __name__ == "__main__":
    # 動作確認用: このファイルを直接実行してテストする
    # 実行: python retrieval/graph_search.py
    G = build_graph()
    print(f"ノード数: {G.number_of_nodes()}, エッジ数: {G.number_of_edges()}")

    neighbors = get_neighbors(["tech_001"])
    print("tech_001 の隣接ノード:", neighbors)
