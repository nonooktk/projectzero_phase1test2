from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.ports.repository import AnalysisRepositoryPort


class SupabaseAnalysisRepository(AnalysisRepositoryPort):
    def __init__(self, url: str, service_role_key: str) -> None:
        if not url or not service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self._client: Client = create_client(url, service_role_key)

    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        job_res = (
            self._client.table("jobs")
            .select("analysis_id,status")
            .eq("idempotency_key", idempotency_key)
            .limit(1)
            .execute()
        )
        if not job_res.data:
            return None

        job = job_res.data[0]
        analysis_id = job.get("analysis_id")
        if not analysis_id:
            return None

        analysis_res = (
            self._client.table("analyses")
            .select("id,idea_text,go_no_go,rationale,context_used,llm_output")
            .eq("id", analysis_id)
            .limit(1)
            .execute()
        )
        if not analysis_res.data:
            return None

        row = analysis_res.data[0]
        context_used = row.get("context_used") or {}
        return {
            "analysis_id": row["id"],
            "status": job.get("status", "succeeded"),
            "summary": row.get("rationale") or "",
            "vector_results": context_used.get("vector_results", []),
            "graph_results": context_used.get("graph_results", []),
            "graph_view": context_used.get("graph_view", {"nodes": [], "edges": []}),
            "context": context_used.get(
                "context",
                {"external_context": "", "internal_context": "", "org_context": ""},
            ),
            "llm_analysis": row.get("llm_output"),
        }

    def save_success(
        self,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> str:
        analysis_id = payload["analysis_id"]
        llm_analysis = payload.get("llm_analysis") or {}
        context_used = {
            "input": payload.get("input"),
            "vector_results": payload.get("vector_results", []),
            "graph_results": payload.get("graph_results", []),
            "graph_view": payload.get("graph_view", {"nodes": [], "edges": []}),
            "context": payload.get("context", {}),
        }
        analysis_payload = {
            "id": analysis_id,
            "idea_text": payload.get("theme", ""),
            "go_no_go": self._to_go_no_go(llm_analysis.get("go_no_verdict", "")),
            "rationale": payload.get("summary", ""),
            "context_used": context_used,
            "llm_output": llm_analysis,
        }
        self._client.table("analyses").upsert(analysis_payload).execute()
        self._client.table("jobs").upsert(
            {
                "idempotency_key": idempotency_key,
                "analysis_id": analysis_id,
                "status": "succeeded",
                "error": None,
            },
            on_conflict="idempotency_key",
        ).execute()
        return analysis_id

    @staticmethod
    def _to_go_no_go(verdict: str) -> str:
        if verdict.startswith("GO"):
            return "GO"
        if verdict.startswith("NO"):
            return "NO"
        return "HOLD"
