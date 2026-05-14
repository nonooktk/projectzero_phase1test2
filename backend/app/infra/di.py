from functools import lru_cache

from app.adapters.chroma_vector_search import ChromaVectorSearchAdapter
from app.adapters.networkx_graph_search import NetworkXGraphSearchAdapter
from app.adapters.openai_llm import OpenAILLMAdapter
from app.adapters.simple_vector_search import SimpleVectorSearchAdapter
from app.adapters.supabase_repository import SupabaseAnalysisRepository
from app.domain.analysis_service import AnalysisService
from app.infra.settings import get_settings
from app.ports.vector_search import VectorSearchPort


def _get_vector_search(backend: str) -> VectorSearchPort:
    if backend == "chroma":
        return ChromaVectorSearchAdapter()
    return SimpleVectorSearchAdapter()


@lru_cache
def get_analysis_service() -> AnalysisService:
    settings = get_settings()
    return AnalysisService(
        vector_search=_get_vector_search(settings.vector_search_backend),
        graph_search=NetworkXGraphSearchAdapter(),
        llm=OpenAILLMAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        ),
        repository=(
            SupabaseAnalysisRepository(
                url=settings.supabase_url,
                service_role_key=settings.supabase_service_role_key,
            )
            if settings.enable_supabase_save or settings.enable_idempotency
            else None
        ),
        enable_idempotency=settings.enable_idempotency,
        enable_repository_save=settings.enable_supabase_save,
        enable_llm_fallback=settings.enable_llm_fallback,
    )
