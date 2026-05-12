from app.domain.analysis_service import AnalysisInput, AnalysisService
from app.ports.graph_search import AnalysisContext, GraphEdge, GraphHit, GraphNode, GraphView
from app.ports.llm import LLMAnalysis
from app.ports.vector_search import SearchHit


class FakeVectorSearch:
    def search(self, query: str, n: int = 5) -> list[SearchHit]:
        return [SearchHit("proj_001", "BEMS事業", 0.9, "internal")]


class FakeGraphSearch:
    def get_neighbors(self, node_ids: list[str]) -> list[GraphHit]:
        return [GraphHit("person_001", "田村 浩二", "person", "過去に担当")]

    def build_context(self, vector_results: list[SearchHit]) -> AnalysisContext:
        return AnalysisContext(
            external_context="【外部情報】BEMS市場",
            internal_context="【社内情報】BEMS事業",
            org_context="【キーマン】田村 浩二",
        )

    def build_graph_view(self, vector_results: list[SearchHit]) -> GraphView:
        return GraphView(
            nodes=[
                GraphNode("proj_001", "BEMS事業", "project", "seed"),
                GraphNode("person_001", "田村 浩二", "person", "related"),
            ],
            edges=[GraphEdge("proj_001", "person_001", "過去に担当")],
        )


class FakeLLM:
    def evaluate(self, theme, context, search_results) -> LLMAnalysis:
        return LLMAnalysis(
            stage1={"internal": {"score": "○"}},
            stage2={"approver_summary": "GO。BEMS市場への参入を推奨する。"},
            go_no_verdict="GO（全軸スコアが◎○のため即時推進可）",
            approver_summary="GO。BEMS市場への参入を推奨する。",
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: dict | None = None

    def find_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        return None

    def save_success(self, idempotency_key: str, payload: dict) -> str:
        self.saved = payload
        return payload["analysis_id"]


def test_analysis_service_runs_llm_after_search() -> None:
    repo = FakeRepository()
    service = AnalysisService(FakeVectorSearch(), FakeGraphSearch(), FakeLLM(), repo)

    result = service.start(
        AnalysisInput(
            target_market="BEMS市場",
            assets="薄膜太陽電池",
            idea_detail="省エネ管理SaaS",
        ),
        idempotency_key="idem-1",
    )

    assert result.status == "evaluated"
    assert result.llm_analysis is not None
    assert result.llm_analysis.go_no_verdict.startswith("GO")
    assert result.summary == "GO。BEMS市場への参入を推奨する。"
    assert repo.saved is not None


def test_analysis_service_returns_saved_result_for_same_key() -> None:
    class SavedRepository:
        def find_by_idempotency_key(self, idempotency_key: str) -> dict:
            return {
                "analysis_id": "saved-id",
                "status": "succeeded",
                "summary": "保存済み",
                "vector_results": [],
                "graph_results": [],
                "graph_view": {"nodes": [], "edges": []},
                "context": {
                    "external_context": "",
                    "internal_context": "",
                    "org_context": "",
                },
                "llm_analysis": None,
            }

        def save_success(self, idempotency_key: str, payload: dict) -> str:
            raise AssertionError("save_success should not be called")

    service = AnalysisService(
        FakeVectorSearch(),
        FakeGraphSearch(),
        FakeLLM(),
        SavedRepository(),
    )

    result = service.start(
        AnalysisInput("BEMS市場", "薄膜太陽電池", "省エネ管理SaaS"),
        idempotency_key="idem-1",
    )

    assert result.analysis_id == "saved-id"
    assert result.summary == "保存済み"
