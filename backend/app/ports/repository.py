from typing import Any, Protocol


class AnalysisRepositoryPort(Protocol):
    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        """Return a saved analysis response payload for a repeated request."""

    def save_success(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> str:
        """Persist a completed analysis and return its analysis id."""
