from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.ports.vector_search import SearchHit, VectorSearchPort


class SimpleVectorSearchAdapter(VectorSearchPort):
    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path(__file__).resolve().parents[3] / "data"
        self._records: list[dict[str, Any]] | None = None

    def search(self, query: str, n: int = 5) -> list[SearchHit]:
        query_terms = self._terms(query)
        hits: list[SearchHit] = []

        for record in self._load_records():
            text = f"{record['id']} {record['content']}"
            terms = self._terms(text)
            overlap = len(query_terms & terms)
            substring_bonus = sum(1 for term in query_terms if term and term in text)
            score = overlap + substring_bonus * 0.5
            if score <= 0:
                continue
            hits.append(
                SearchHit(
                    id=record["id"],
                    content=record["content"],
                    score=round(score, 4),
                    source=record["source"],
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        if len(hits) >= n:
            return hits[:n]

        fallback_ids = {hit.id for hit in hits}
        for record in self._load_records():
            if record["id"] in fallback_ids:
                continue
            hits.append(
                SearchHit(
                    id=record["id"],
                    content=record["content"],
                    score=0,
                    source=record["source"],
                )
            )
            if len(hits) >= n:
                break
        return hits

    def _load_records(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records

        records: list[dict[str, Any]] = []
        for filename, source in [
            ("external.json", "external"),
            ("internal.json", "internal"),
            ("persons.json", "persons"),
        ]:
            rows = json.loads((self._data_dir / filename).read_text(encoding="utf-8"))
            for row in rows:
                records.append({**row, "source": source})
        self._records = records
        return records

    @staticmethod
    def _terms(text: str) -> set[str]:
        normalized = text.lower()
        ascii_terms = set(re.findall(r"[a-z0-9_]+", normalized))
        japanese_terms = {
            term
            for term in [
                "bems",
                "医療",
                "病院",
                "在宅",
                "ウェアラブル",
                "素材",
                "植物",
                "ポリマー",
                "省エネ",
                "エネルギー",
                "太陽電池",
                "センサー",
                "ビル",
                "工場",
            ]
            if term in normalized
        }
        return ascii_terms | japanese_terms
