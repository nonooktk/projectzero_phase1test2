from dataclasses import asdict, dataclass
import logging
from typing import Any
from uuid import uuid4

from app.ports.graph_search import (
    AnalysisContext,
    GraphEdge,
    GraphHit,
    GraphNode,
    GraphSearchPort,
    GraphView,
)
from app.ports.llm import LLMAnalysis, LLMPort
from app.ports.repository import AnalysisRepositoryPort
from app.ports.vector_search import SearchHit, VectorSearchPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisInput:
    target_market: str
    assets: str
    idea_detail: str

    def to_theme(self) -> str:
        return (
            f"【想定顧客/市場】{self.target_market}\n"
            f"【活用アセット】{self.assets}\n"
            f"【アイデア概要】{self.idea_detail}"
        )

    def to_dict(self) -> dict:
        return {
            "target_market": self.target_market,
            "assets": self.assets,
            "idea_detail": self.idea_detail,
        }


@dataclass(frozen=True)
class AnalysisDraft:
    analysis_id: str
    status: str
    summary: str
    vector_results: list[SearchHit]
    graph_results: list[GraphHit]
    graph_view: GraphView
    context: AnalysisContext
    llm_analysis: LLMAnalysis | None = None

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "status": self.status,
            "summary": self.summary,
            "vector_results": [asdict(hit) for hit in self.vector_results],
            "graph_results": [asdict(hit) for hit in self.graph_results],
            "graph_view": asdict(self.graph_view),
            "context": asdict(self.context),
            "llm_analysis": (
                asdict(self.llm_analysis) if self.llm_analysis is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "AnalysisDraft":
        return cls(
            analysis_id=payload["analysis_id"],
            status=payload.get("status", "succeeded"),
            summary=payload.get("summary", ""),
            vector_results=[
                SearchHit(**hit) for hit in payload.get("vector_results", [])
            ],
            graph_results=[
                GraphHit(**hit) for hit in payload.get("graph_results", [])
            ],
            graph_view=cls._graph_view_from_dict(payload.get("graph_view", {})),
            context=AnalysisContext(**payload.get("context", {})),
            llm_analysis=(
                LLMAnalysis(**payload["llm_analysis"])
                if payload.get("llm_analysis") is not None
                else None
            ),
        )

    @staticmethod
    def _graph_view_from_dict(payload: dict) -> GraphView:
        return GraphView(
            nodes=[GraphNode(**node) for node in payload.get("nodes", [])],
            edges=[GraphEdge(**edge) for edge in payload.get("edges", [])],
        )


class AnalysisService:
    def __init__(
        self,
        vector_search: VectorSearchPort,
        graph_search: GraphSearchPort,
        llm: LLMPort,
        repository: AnalysisRepositoryPort | None = None,
    ) -> None:
        self._vector_search = vector_search
        self._graph_search = graph_search
        self._llm = llm
        self._repository = repository

    def start(
        self,
        payload: AnalysisInput,
        idempotency_key: str,
        n_results: int = 5,
    ) -> AnalysisDraft:
        if self._repository is not None:
            existing = self._find_existing(idempotency_key)
            if existing is not None:
                return AnalysisDraft.from_dict(existing)

        theme = payload.to_theme()
        vector_results = self._vector_search.search(theme, n=n_results)
        graph_results = self._graph_search.get_neighbors(
            [hit.id for hit in vector_results]
        )
        graph_view = self._graph_search.build_graph_view(vector_results)
        context = self._graph_search.build_context(vector_results)
        llm_analysis = self._llm.evaluate(theme, context, vector_results)

        draft = AnalysisDraft(
            analysis_id=str(uuid4()),
            status="evaluated",
            summary=llm_analysis.approver_summary,
            vector_results=vector_results,
            graph_results=graph_results,
            graph_view=graph_view,
            context=context,
            llm_analysis=llm_analysis,
        )
        if self._repository is not None:
            save_payload = draft.to_dict()
            save_payload["theme"] = theme
            save_payload["input"] = payload.to_dict()
            self._save_success(idempotency_key, save_payload)
        return draft

    def _find_existing(self, idempotency_key: str) -> dict[str, Any] | None:
        if self._repository is None:
            return None
        try:
            return self._repository.find_by_idempotency_key(idempotency_key)
        except Exception:
            logger.exception("Failed to read analysis by idempotency key")
            return None

    def _save_success(self, idempotency_key: str, payload: dict[str, Any]) -> None:
        if self._repository is None:
            return
        try:
            self._repository.save_success(idempotency_key, payload)
        except Exception:
            logger.exception("Failed to save analysis result")
