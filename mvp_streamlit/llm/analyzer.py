"""
analyzer.py — GPT-4o-mini を使った Stage1・Stage2 分析モジュール

担当: Aさん（データ＆AI担当）

【このファイルの役割】
- Stage1: 3軸（外部・内部・組織）を個別に分析し、◎○△×スコアを生成する
- Stage2: Stage1の結果を統合し、事業案3つ＋承認者サマリーを生成する
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from config import OPENAI_API_KEY
from llm.prompts import (
    STAGE1_SYSTEM_PROMPT,
    STAGE1_USER_PROMPT_TEMPLATE,
    STAGE2_SYSTEM_PROMPT,
    STAGE2_TIER1_USER_PROMPT_TEMPLATE,
    STAGE2_TIER2_SYSTEM_PROMPT,
    STAGE2_TIER2_USER_PROMPT_TEMPLATE,
    AXIS_NAMES,
)

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "gpt-4o-mini"

# 軸名とcontextキーのマッピング
AXIS_CONTEXT_KEYS = {
    "external": "external_context",
    "internal": "internal_context",
    "org": "org_context",
}


def run_stage1(theme: str, context: dict) -> dict:
    """
    Stage1: 3軸を個別に分析してスコアを生成する。

    Args:
        theme (str): ユーザーが入力したテーマ
        context (dict): build_context() が返す3軸のコンテキスト
                        {"external_context": "...", "internal_context": "...", "org_context": "..."}

    Returns:
        dict: 3軸のスコアと根拠
        例:
        {
          "external": {"score": "◎", "reason": "...", "key_points": [...]},
          "internal": {"score": "○", "reason": "...", "key_points": [...]},
          "org":      {"score": "△", "reason": "...", "key_points": [...]}
        }
    """

    def call_gpt(axis: str) -> tuple[str, dict]:
        t_start = time.perf_counter()
        raw_context = context.get(AXIS_CONTEXT_KEYS[axis], "（情報なし）")
        escaped_context = raw_context.replace("{", "{{").replace("}", "}}")
        prompt = STAGE1_USER_PROMPT_TEMPLATE.format(
            theme=theme,
            axis_name=AXIS_NAMES[axis],
            context=escaped_context,
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        print(
            f"[TIMER]   Stage1/{axis}: {time.perf_counter() - t_start:.2f}s", flush=True
        )
        return axis, json.loads(response.choices[0].message.content)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(call_gpt, axis) for axis in AXIS_CONTEXT_KEYS]
        results = dict(f.result() for f in futures)

    return results


def _call_stage2_tier1(
    theme: str, stage1_results: dict, full_context_escaped: str, go_no_verdict: str
) -> dict:
    """proposals + approver_summary を生成する（Tier1）"""
    t_start = time.perf_counter()
    external = stage1_results.get("external", {})
    internal = stage1_results.get("internal", {})
    org = stage1_results.get("org", {})

    prompt = STAGE2_TIER1_USER_PROMPT_TEMPLATE.format(
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
        full_context=full_context_escaped,
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    print(f"[TIMER]   Stage2/Tier1: {time.perf_counter() - t_start:.2f}s", flush=True)
    return json.loads(response.choices[0].message.content)


def _call_stage2_tier2(
    theme: str, stage1_results: dict, full_context_escaped: str
) -> dict:
    """3C分析（Customer/Competitor/Company）を単独で深く生成する（Tier2）"""
    t_start = time.perf_counter()
    external = stage1_results.get("external", {})
    internal = stage1_results.get("internal", {})
    org = stage1_results.get("org", {})

    prompt = STAGE2_TIER2_USER_PROMPT_TEMPLATE.format(
        theme=theme,
        external_score=external.get("score", "－"),
        external_reason=external.get("reason", ""),
        internal_score=internal.get("score", "－"),
        internal_reason=internal.get("reason", ""),
        org_score=org.get("score", "－"),
        org_reason=org.get("reason", ""),
        full_context=full_context_escaped,
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": STAGE2_TIER2_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    print(f"[TIMER]   Stage2/Tier2: {time.perf_counter() - t_start:.2f}s", flush=True)
    return json.loads(response.choices[0].message.content)


def run_stage2(theme: str, stage1_results: dict, context: dict) -> dict:
    """
    Stage2: Tier1（proposals + approver_summary）とTier2（3C分析）を
    並列で生成して統合する。

    Returns:
        dict: {
          "proposals": [...],
          "approver_summary": "...",
          "tier2": {"customer": {...}, "competitor": {...}, "company": {...}}
        }
    """
    internal = stage1_results.get("internal", {})
    external = stage1_results.get("external", {})

    # Stage1スコアからルールベースでGO/NO判定（LLMに委ねず固定する）
    internal_score = internal.get("score", "－")
    external_score_val = external.get("score", "－")
    if internal_score == "×":
        go_no_verdict = "NO（社内適合スコアが×のため投資不可）"
    elif internal_score == "△":
        go_no_verdict = (
            "条件付きGO（社内適合スコアが△のため、障壁解決を前提に投資検討可）"
        )
    elif external_score_val in ("△", "×"):
        go_no_verdict = (
            "条件付きGO（外部環境スコアが低いため、市場変化を確認しながら進める）"
        )
    else:
        go_no_verdict = "GO（全軸スコアが◎○のため即時推進可）"

    full_context = "\n\n".join(
        [
            context.get("external_context", ""),
            context.get("internal_context", ""),
            context.get("org_context", ""),
        ]
    )
    full_context_escaped = full_context.replace("{", "{{").replace("}", "}}")

    # Tier1とTier2を並列実行
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_tier1 = executor.submit(
            _call_stage2_tier1,
            theme,
            stage1_results,
            full_context_escaped,
            go_no_verdict,
        )
        f_tier2 = executor.submit(
            _call_stage2_tier2, theme, stage1_results, full_context_escaped
        )
        tier1 = f_tier1.result()
        tier2 = f_tier2.result()

    tier1["tier2"] = tier2
    return tier1


def _enrich_context_with_full_records(search_results: list, context: dict) -> dict:
    """
    検索結果のIDに基づいてinternal.jsonから conditions_now / reusable_assets /
    lessons_learned を取得し、internal_context に追記する。
    ChromaDB の content フィールドには含まれないGO/NO判断情報をLLMに渡すための処理。
    """
    internal_path = os.path.join(os.path.dirname(__file__), "../data/internal.json")
    with open(internal_path, encoding="utf-8") as f:
        all_internal = {r["id"]: r for r in json.load(f)}

    enrichment_lines = []
    for r in search_results:
        if r.get("source") != "internal":
            continue
        record = all_internal.get(r["id"])
        if not record:
            continue

        lines = [f"【{record.get('name', r['id'])}】"]

        conditions = record.get("conditions_now", {})
        if conditions:
            cond_parts = [f"{k}:{v.get('status','')}" for k, v in conditions.items()]
            lines.append(f"  再参入条件チェック: {' / '.join(cond_parts)}")

        assets = record.get("reusable_assets", [])
        if assets:
            lines.append(f"  活用可能資産: {', '.join(assets)}")

        lessons = record.get("lessons_learned", "")
        if lessons:
            lines.append(f"  教訓: {lessons}")

        if len(lines) > 1:
            enrichment_lines.append("\n".join(lines))

    if enrichment_lines:
        enrichment = "\n\n".join(enrichment_lines)
        existing = context.get("internal_context", "")
        context = dict(context)
        context["internal_context"] = (
            existing + "\n\n【過去PJ詳細（GO/NO判断用）】\n" + enrichment
        )

    return context


def analyze(theme: str, context: dict, search_results: list = None) -> dict:
    """
    Stage1 と Stage2 を順番に実行し、最終結果を返す。
    app.py から呼び出すメイン関数。

    Args:
        theme (str): ユーザーが入力したテーマ
        context (dict): build_context() が返す3軸のコンテキスト
        search_results (list, optional): search() の返り値。渡すと conditions_now 等を
                                         context に自動追記してGO/NO判断精度を上げる。

    Returns:
        dict: {
          "stage1": Stage1の結果,
          "stage2": Stage2の結果
        }
    """
    t0 = time.perf_counter()

    if search_results:
        context = _enrich_context_with_full_records(search_results, context)
    t_enrich = time.perf_counter()
    print(f"[TIMER] enrich_context: {t_enrich - t0:.2f}s", flush=True)

    stage1 = run_stage1(theme, context)
    t_stage1 = time.perf_counter()
    print(f"[TIMER] Stage1 (3並列GPT): {t_stage1 - t_enrich:.2f}s", flush=True)

    stage2 = run_stage2(theme, stage1, context)
    t_stage2 = time.perf_counter()
    print(f"[TIMER] Stage2 (2並列GPT): {t_stage2 - t_stage1:.2f}s", flush=True)

    print(f"[TIMER] 合計: {t_stage2 - t0:.2f}s", flush=True)
    return {"stage1": stage1, "stage2": stage2}
