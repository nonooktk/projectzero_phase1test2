from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.domain.prompts import (
    AXIS_NAMES,
    STAGE1_SYSTEM_PROMPT,
    STAGE1_USER_PROMPT_TEMPLATE,
    STAGE2_SYSTEM_PROMPT,
    STAGE2_TIER1_USER_PROMPT_TEMPLATE,
    STAGE2_TIER2_SYSTEM_PROMPT,
    STAGE2_TIER2_USER_PROMPT_TEMPLATE,
)
from app.ports.graph_search import AnalysisContext
from app.ports.llm import LLMAnalysis, LLMPort
from app.ports.vector_search import SearchHit


AXIS_CONTEXT_KEYS = {
    "external": "external_context",
    "internal": "internal_context",
    "org": "org_context",
}


class OpenAILLMAdapter(LLMPort):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        data_dir: Path | None = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM evaluation")
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._data_dir = data_dir or Path(__file__).resolve().parents[3] / "data"

    def evaluate(
        self,
        theme: str,
        context: AnalysisContext,
        search_results: list[SearchHit],
    ) -> LLMAnalysis:
        enriched_context = self._enrich_context(search_results, context)
        context_dict = asdict(enriched_context)
        stage1 = self._run_stage1(theme, context_dict)
        go_no_verdict = self._judge_go_no(stage1)
        stage2 = self._run_stage2(theme, stage1, context_dict, go_no_verdict)
        approver_summary = str(stage2.get("approver_summary", go_no_verdict))
        return LLMAnalysis(
            stage1=stage1,
            stage2=stage2,
            go_no_verdict=go_no_verdict,
            approver_summary=approver_summary,
        )

    def _run_stage1(self, theme: str, context: dict[str, str]) -> dict[str, Any]:
        def call_axis(axis: str) -> tuple[str, dict[str, Any]]:
            raw_context = context.get(AXIS_CONTEXT_KEYS[axis], "（情報なし）")
            prompt = STAGE1_USER_PROMPT_TEMPLATE.format(
                theme=theme,
                axis_name=AXIS_NAMES[axis],
                context=self._escape(raw_context),
            )
            return axis, self._call_json(STAGE1_SYSTEM_PROMPT, prompt)

        with ThreadPoolExecutor(max_workers=3) as executor:
            return dict(executor.map(call_axis, AXIS_CONTEXT_KEYS))

    def _run_stage2(
        self,
        theme: str,
        stage1: dict[str, Any],
        context: dict[str, str],
        go_no_verdict: str,
    ) -> dict[str, Any]:
        full_context = self._escape("\n\n".join(context.values()))
        external = stage1.get("external", {})
        internal = stage1.get("internal", {})
        org = stage1.get("org", {})

        tier1_prompt = STAGE2_TIER1_USER_PROMPT_TEMPLATE.format(
            theme=theme,
            go_no_verdict=go_no_verdict,
            external_score=external.get("score", "－"),
            external_reason=external.get("reason", ""),
            external_key_points="、".join(external.get("key_points", [])),
            internal_score=internal.get("score", "－"),
            internal_reason=internal.get("reason", ""),
            internal_key_points="、".join(internal.get("key_points", [])),
            org_score=org.get("score", "－"),
            org_reason=org.get("reason", ""),
            org_key_points="、".join(org.get("key_points", [])),
            full_context=full_context,
        )
        tier2_prompt = STAGE2_TIER2_USER_PROMPT_TEMPLATE.format(
            theme=theme,
            external_score=external.get("score", "－"),
            external_reason=external.get("reason", ""),
            internal_score=internal.get("score", "－"),
            internal_reason=internal.get("reason", ""),
            org_score=org.get("score", "－"),
            org_reason=org.get("reason", ""),
            full_context=full_context,
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            tier1_future = executor.submit(
                self._call_json,
                STAGE2_SYSTEM_PROMPT,
                tier1_prompt,
            )
            tier2_future = executor.submit(
                self._call_json,
                STAGE2_TIER2_SYSTEM_PROMPT,
                tier2_prompt,
            )
            tier1 = tier1_future.result()
            tier1["tier2"] = tier2_future.result()
            return tier1

    def _call_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _enrich_context(
        self,
        search_results: list[SearchHit],
        context: AnalysisContext,
    ) -> AnalysisContext:
        internal_path = self._data_dir / "internal.json"
        all_internal = {
            row["id"]: row
            for row in json.loads(internal_path.read_text(encoding="utf-8"))
        }

        lines: list[str] = []
        for hit in search_results:
            if hit.source != "internal":
                continue
            record = all_internal.get(hit.id)
            if not record:
                continue
            details = [f"【{record.get('name', hit.id)}】"]
            conditions = record.get("conditions_now", {})
            if conditions:
                cond_parts = [f"{k}:{v.get('status','')}" for k, v in conditions.items()]
                details.append(f"  再参入条件チェック: {' / '.join(cond_parts)}")
            if record.get("reusable_assets"):
                details.append(f"  活用可能資産: {', '.join(record['reusable_assets'])}")
            if record.get("lessons_learned"):
                details.append(f"  教訓: {record['lessons_learned']}")
            if len(details) > 1:
                lines.append("\n".join(details))

        if not lines:
            return context

        return AnalysisContext(
            external_context=context.external_context,
            internal_context=(
                context.internal_context
                + "\n\n【過去PJ詳細（GO/NO判断用）】\n"
                + "\n\n".join(lines)
            ),
            org_context=context.org_context,
        )

    @staticmethod
    def _judge_go_no(stage1: dict[str, Any]) -> str:
        internal_score = stage1.get("internal", {}).get("score", "－")
        external_score = stage1.get("external", {}).get("score", "－")
        if internal_score == "×":
            return "NO（社内適合スコアが×のため投資不可）"
        if internal_score == "△":
            return "条件付きGO（社内適合スコアが△のため、障壁解決を前提に投資検討可）"
        if external_score in ("△", "×"):
            return "条件付きGO（外部環境スコアが低いため、市場変化を確認しながら進める）"
        return "GO（全軸スコアが◎○のため即時推進可）"

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("{", "{{").replace("}", "}}")
