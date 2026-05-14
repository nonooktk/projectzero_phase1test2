import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.domain.analysis_service import AnalysisInput, AnalysisService
from app.infra.di import get_analysis_service

router = APIRouter()
logger = logging.getLogger(__name__)


class AnalysisRequest(BaseModel):
    target_market: str = Field(default="", max_length=500)
    assets: str = Field(default="", max_length=500)
    idea_detail: str = Field(min_length=1, max_length=4000)


class AnalysisResponse(BaseModel):
    analysis_id: str
    status: str
    summary: str
    vector_results: list[dict]
    graph_results: list[dict]
    graph_view: dict
    context: dict
    llm_analysis: dict | None


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis(
    request: AnalysisRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResponse:
    _ = idempotency_key
    try:
        draft = service.start(
            AnalysisInput(
                target_market=request.target_market,
                assets=request.assets,
                idea_detail=request.idea_detail,
            ),
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        logger.exception("Analysis request failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {exc.__class__.__name__}: {exc}",
        ) from exc
    return AnalysisResponse(**draft.to_dict())
