from fastapi import APIRouter

from app.infra.settings import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/openai")
def openai_health() -> dict[str, object]:
    settings = get_settings()
    key = settings.openai_api_key.strip()
    result: dict[str, object] = {
        "configured": bool(key),
        "key_prefix": key[:7] if key else "",
        "key_length": len(key),
        "model": settings.openai_model,
    }
    if not key:
        return {**result, "ok": False, "error_type": "MissingOpenAIKey"}

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=key,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "{\"status\":\"ok\"} と返してください。"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=20,
        )
        return {
            **result,
            "ok": True,
            "response": response.choices[0].message.content,
        }
    except Exception as exc:
        return {
            **result,
            "ok": False,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
