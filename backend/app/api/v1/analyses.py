from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from app.domain.analysis_service import AnalysisInput, AnalysisService
from app.infra.di import get_analysis_service

router = APIRouter()


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
    draft = service.start(
        AnalysisInput(
            target_market=request.target_market,
            assets=request.assets,
            idea_detail=request.idea_detail,
        ),
        idempotency_key=idempotency_key,
    )
    return AnalysisResponse(**draft.to_dict())
