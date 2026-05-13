from app.adapters.simple_vector_search import SimpleVectorSearchAdapter


def test_simple_vector_search_returns_bems_records() -> None:
    adapter = SimpleVectorSearchAdapter()

    hits = adapter.search("BEMS 省エネ ビル 太陽電池", n=5)

    assert hits
    assert any("BEMS" in hit.content for hit in hits)
