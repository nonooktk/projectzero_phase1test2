from dataclasses import dataclass
from typing import Any, Protocol

from app.ports.graph_search import AnalysisContext
from app.ports.vector_search import SearchHit


@dataclass(frozen=True)
class LLMAnalysis:
    stage1: dict[str, Any]
    stage2: dict[str, Any]
    go_no_verdict: str
    approver_summary: str


class LLMPort(Protocol):
    def evaluate(
        self,
        theme: str,
        context: AnalysisContext,
        search_results: list[SearchHit],
    ) -> LLMAnalysis:
        """Evaluate an idea with the three-axis context."""
