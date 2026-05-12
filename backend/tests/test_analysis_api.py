from app.domain.analysis_service import AnalysisDraft
from app.infra.di import get_analysis_service
from app.main import app
from app.ports.graph_search import AnalysisContext, GraphEdge, GraphHit, GraphNode, GraphView
from app.ports.vector_search import SearchHit
from fastapi.testclient import TestClient


class FakeAnalysisService:
    def start(
        self,
        payload,
        idempotency_key: str,
        n_results: int = 5,
    ) -> AnalysisDraft:
        return AnalysisDraft(
            analysis_id="analysis-test",
            status="searched",
            summary=f"received: {payload.idea_detail}",
            vector_results=[
                SearchHit("tech_001", "技術情報", 0.9, "internal"),
            ],
            graph_results=[
                GraphHit("person_001", "田村 浩二", "person", "過去に担当"),
            ],
            graph_view=GraphView(
                nodes=[
                    GraphNode("proj_001", "BEMS事業", "project", "seed"),
                    GraphNode("person_001", "田村 浩二", "person", "related"),
                ],
                edges=[GraphEdge("proj_001", "person_001", "過去に担当")],
            ),
            context=AnalysisContext(
                external_context="",
                internal_context="【社内情報】\n技術情報",
                org_context="【キーマン】\n田村 浩二（過去に担当）",
            ),
            llm_analysis=None,
        )


def test_create_analysis_returns_search_context() -> None:
    app.dependency_overrides[get_analysis_service] = lambda: FakeAnalysisService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyses",
        headers={"Idempotency-Key": "test-key"},
        json={
            "target_market": "BEMS市場",
            "assets": "薄膜太陽電池",
            "idea_detail": "省エネ管理SaaS",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "searched"
    assert body["vector_results"][0]["id"] == "tech_001"
    assert "田村" in body["context"]["org_context"]
