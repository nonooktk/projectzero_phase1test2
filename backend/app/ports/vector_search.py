from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchHit:
    id: str
    content: str
    score: float
    source: str


class VectorSearchPort(Protocol):
    def search(self, query: str, n: int = 5) -> list[SearchHit]:
        """Return semantically related source records."""
