from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import networkx as nx

from app.ports.graph_search import (
    AnalysisContext,
    GraphEdge,
    GraphHit,
    GraphNode,
    GraphSearchPort,
    GraphView,
)
from app.ports.vector_search import SearchHit


class NetworkXGraphSearchAdapter(GraphSearchPort):
    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path(__file__).resolve().parents[3] / "data"
        self._graph: nx.Graph | None = None
        self._related_failures: dict[str, str] | None = None

    def get_neighbors(self, node_ids: list[str]) -> list[GraphHit]:
        graph = self._get_graph()
        seen: set[str] = set()
        hits: list[GraphHit] = []

        for node_id in self._expand_node_ids(node_ids):
            if node_id not in graph:
                continue
            for neighbor in graph.neighbors(node_id):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                node_attrs = graph.nodes[neighbor]
                hits.append(
                    GraphHit(
                        id=neighbor,
                        label=str(node_attrs.get("label", neighbor)),
                        type=str(node_attrs.get("type", "")),
                        relation=str(graph[node_id][neighbor].get("relation", "")),
                    )
                )
        return hits

    def build_context(self, vector_results: list[SearchHit]) -> AnalysisContext:
        external = [hit.content for hit in vector_results if hit.source == "external"]
        internal = [hit.content for hit in vector_results if hit.source == "internal"]
        persons = [hit for hit in vector_results if hit.source == "persons"]

        person_ids = {hit.id for hit in persons}
        extra_persons = [
            f"{hit.label}（{hit.relation}）"
            for hit in self.get_neighbors([item.id for item in vector_results])
            if hit.type == "person" and hit.id not in person_ids
        ]

        org_lines = [hit.content for hit in persons] + extra_persons
        return AnalysisContext(
            external_context=self._section("外部情報", external),
            internal_context=self._section("社内情報", internal),
            org_context=self._section("キーマン", org_lines),
        )

    def build_graph_view(self, vector_results: list[SearchHit]) -> GraphView:
        graph = self._get_graph()
        seed_ids = self._expand_hits(vector_results)
        node_ids: set[str] = set()
        edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()

        for seed_id in seed_ids:
            if seed_id not in graph:
                continue
            node_ids.add(seed_id)
            for neighbor in graph.neighbors(seed_id):
                node_ids.add(neighbor)
                relation = str(graph[seed_id][neighbor].get("relation", ""))
                edge_key = tuple(sorted([seed_id, neighbor]) + [relation])
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append(
                    GraphEdge(
                        source_id=seed_id,
                        target_id=str(neighbor),
                        relation=relation,
                    )
                )

        nodes = [
            self._to_graph_node(node_id, "seed" if node_id in seed_ids else "related")
            for node_id in sorted(node_ids)
        ]
        return GraphView(nodes=nodes, edges=edges)

    def _get_graph(self) -> nx.Graph:
        if self._graph is not None:
            return self._graph

        graph = nx.Graph()
        nodes = self._load_json("graph/nodes.json")
        edges = self._load_json("graph/edges.json")

        for node in nodes:
            graph.add_node(node["id"], **node)
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"], relation=edge["relation"])

        self._graph = graph
        return graph

    def _load_json(self, relative_path: str) -> list[dict[str, Any]]:
        return json.loads((self._data_dir / relative_path).read_text(encoding="utf-8"))

    def _expand_node_ids(self, node_ids: list[str]) -> list[str]:
        related_failures = self._get_related_failures()
        expanded: list[str] = []
        seen: set[str] = set()
        for node_id in node_ids:
            for candidate in [node_id, related_failures.get(node_id, "")]:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
        return expanded

    def _expand_hits(self, vector_results: list[SearchHit]) -> list[str]:
        graph = self._get_graph()
        expanded: list[str] = []
        seen: set[str] = set()
        related_failures = self._get_related_failures()

        for hit in vector_results:
            candidates = [hit.id, related_failures.get(hit.id, "")]
            candidates.extend(self._market_aliases(hit))
            candidates.extend(self._person_project_ids(hit))
            for candidate in candidates:
                if candidate and candidate in graph and candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
        return expanded

    def _market_aliases(self, hit: SearchHit) -> list[str]:
        text = f"{hit.id} {hit.content}"
        aliases: list[str] = []
        if hit.id == "mkt_001" or "BEMS" in text or "ビルエネルギー" in text:
            aliases.append("market_bems")
        if "医療" in text or "ヘルスケア" in text:
            aliases.append("market_medical")
        if "ウェアラブル" in text or "wearable" in text.lower():
            aliases.append("market_wearable")
        return aliases

    def _person_project_ids(self, hit: SearchHit) -> list[str]:
        if hit.source != "persons":
            return []

        rows = [row for row in self._load_json("persons.json") if row["id"] == hit.id]
        if not rows:
            return []

        row = rows[0]
        project_ids = list(row.get("past_projects", []))
        for asset in row.get("holds_assets", []):
            project_ids.extend(re.findall(r"proj_\d+", asset))
        return project_ids

    def _to_graph_node(self, node_id: str, source: str) -> GraphNode:
        graph = self._get_graph()
        attrs = graph.nodes[node_id]
        return GraphNode(
            id=node_id,
            label=str(attrs.get("label", node_id)),
            type=str(attrs.get("type", "")),
            source=source,
        )

    def _get_related_failures(self) -> dict[str, str]:
        if self._related_failures is not None:
            return self._related_failures

        related: dict[str, str] = {}
        for filename in ["external.json", "internal.json"]:
            for row in self._load_json(filename):
                if row.get("related_failure"):
                    related[row["id"]] = row["related_failure"]
        self._related_failures = related
        return related

    @staticmethod
    def _section(title: str, lines: list[str]) -> str:
        if not lines:
            return ""
        return f"【{title}】\n" + "\n".join(lines)
