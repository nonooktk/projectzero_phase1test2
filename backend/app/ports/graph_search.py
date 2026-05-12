from dataclasses import dataclass
from typing import Protocol

from app.ports.vector_search import SearchHit


@dataclass(frozen=True)
class GraphHit:
    id: str
    label: str
    type: str
    relation: str


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    type: str
    source: str = "graph"


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    relation: str


@dataclass(frozen=True)
class GraphView:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(frozen=True)
class AnalysisContext:
    external_context: str
    internal_context: str
    org_context: str


class GraphSearchPort(Protocol):
    def get_neighbors(self, node_ids: list[str]) -> list[GraphHit]:
        """Return graph nodes adjacent to the given ids."""

    def build_context(self, vector_results: list[SearchHit]) -> AnalysisContext:
        """Build the three-axis context used by later LLM analysis."""

    def build_graph_view(self, vector_results: list[SearchHit]) -> GraphView:
        """Build nodes and edges for the frontend knowledge graph."""
