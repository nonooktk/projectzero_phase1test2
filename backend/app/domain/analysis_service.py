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
        enable_idempotency: bool = True,
        enable_repository_save: bool = True,
    ) -> None:
        self._vector_search = vector_search
        self._graph_search = graph_search
        self._llm = llm
        self._repository = repository
        self._enable_idempotency = enable_idempotency
        self._enable_repository_save = enable_repository_save

    def start(
        self,
        payload: AnalysisInput,
        idempotency_key: str,
        n_results: int = 5,
    ) -> AnalysisDraft:
        if self._repository is not None and self._enable_idempotency:
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
        llm_analysis = self._evaluate_llm(theme, context, vector_results)

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
        if self._repository is not None and self._enable_repository_save:
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

    def _evaluate_llm(
        self,
        theme: str,
        context: AnalysisContext,
        vector_results: list[SearchHit],
    ) -> LLMAnalysis:
        try:
            return self._llm.evaluate(theme, context, vector_results)
        except Exception:
            logger.exception("Failed to evaluate analysis with LLM")
            return self._fallback_llm_analysis(context, vector_results)

    @staticmethod
    def _fallback_llm_analysis(
        context: AnalysisContext,
        vector_results: list[SearchHit],
    ) -> LLMAnalysis:
        has_external = any(hit.source == "external" for hit in vector_results)
        has_internal = any(hit.source == "internal" for hit in vector_results)
        has_org = bool(context.org_context)

        stage1 = {
            "external": {
                "score": "○" if has_external else "△",
                "reason": "関連する外部情報を検索結果から確認した。LLM接続失敗時の暫定評価である。",
                "key_points": ["市場・規制・競合情報の追加確認が必要"],
            },
            "internal": {
                "score": "○" if has_internal else "△",
                "reason": "関連する社内情報を検索結果から確認した。LLM接続失敗時の暫定評価である。",
                "key_points": ["再利用可能な技術・過去PJの詳細確認が必要"],
            },
            "org": {
                "score": "○" if has_org else "△",
                "reason": "関連ノードから候補キーマンを補完した。LLM接続失敗時の暫定評価である。",
                "key_points": ["担当候補者へのヒアリングが必要"],
            },
        }
        summary = (
            "条件付きGO。OpenAI APIへの接続に失敗したため、検索結果と関連ノードに基づく"
            "暫定評価を表示している。正式判断前にLLM評価を再実行する。"
        )
        return LLMAnalysis(
            stage1=stage1,
            stage2={
                "proposals": [
                    {
                        "title": "暫定事業仮説の検証",
                        "summary": "検索結果で見つかった市場情報・社内資産・キーマンを起点に、事業仮説を短期検証する。",
                        "timing_score": "○",
                        "timing_reason": "関連市場と既存アセットが確認できるため、初期検証に進める。",
                        "tech_fit_score": "○",
                        "tech_fit_reason": "社内情報に関連技術・過去事業の接点がある。",
                        "bottleneck": "LLM評価が未完了",
                        "bottleneck_solution": "OpenAI接続を復旧後、同じ入力で再分析する。",
                        "next_actions": [
                            {
                                "person": "事業開発担当",
                                "action": "検索根拠と関連ノードを確認し、検証論点を整理する。",
                            }
                        ],
                    }
                ],
                "approver_summary": summary,
            },
            go_no_verdict="条件付きGO（LLM接続失敗のため暫定評価）",
            approver_summary=summary,
        )
