from app.adapters.networkx_graph_search import NetworkXGraphSearchAdapter
from app.ports.vector_search import SearchHit


def test_get_neighbors_returns_related_person() -> None:
    adapter = NetworkXGraphSearchAdapter()

    hits = adapter.get_neighbors(["proj_001"])

    assert any(hit.id == "person_001" for hit in hits)


def test_get_neighbors_expands_market_hit_to_related_project() -> None:
    adapter = NetworkXGraphSearchAdapter()

    hits = adapter.get_neighbors(["mkt_001"])

    assert any(hit.id == "person_001" for hit in hits)
    assert any(hit.id == "market_bems" for hit in hits)


def test_build_context_groups_hits_and_graph_people() -> None:
    adapter = NetworkXGraphSearchAdapter()
    vector_hits = [
        SearchHit(
            id="market_bems",
            content="BEMS市場の成長が続く。",
            score=0.9,
            source="external",
        ),
        SearchHit(
            id="proj_001",
            content="過去のBEMS事業。",
            score=0.8,
            source="internal",
        ),
    ]

    context = adapter.build_context(vector_hits)

    assert "BEMS市場" in context.external_context
    assert "過去のBEMS事業" in context.internal_context
    assert "田村 浩二" in context.org_context


def test_build_graph_view_expands_market_hit_to_nodes_and_edges() -> None:
    adapter = NetworkXGraphSearchAdapter()
    vector_hits = [
        SearchHit(
            id="mkt_001",
            content="BEMS市場は補助金で拡大している。",
            score=0.91,
            source="external",
        )
    ]

    graph_view = adapter.build_graph_view(vector_hits)
    node_ids = {node.id for node in graph_view.nodes}
    edge_pairs = {(edge.source_id, edge.target_id) for edge in graph_view.edges}

    assert "market_bems" in node_ids
    assert "proj_001" in node_ids
    assert "person_001" in node_ids
    assert ("proj_001", "person_001") in edge_pairs
