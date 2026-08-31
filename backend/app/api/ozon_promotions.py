from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.ozon_promotions import OzonPromotionAnalyzeResponse
from app.services.ozon_promotions_service import OzonPromotionsService


router = APIRouter(prefix="/api/ozon/promotions", tags=["Ozon Promotions"])


@router.post("/analyze", response_model=OzonPromotionAnalyzeResponse)
async def analyze_ozon_promotions(
    unit_file: Annotated[UploadFile, File()],
    sales_file: Annotated[UploadFile, File()],
    promotions_file: Annotated[UploadFile, File()],
) -> OzonPromotionAnalyzeResponse:
    try:
        unit_content = await unit_file.read()
        sales_content = await sales_file.read()
        promotions_content = await promotions_file.read()
        return OzonPromotionsService().analyze(
            unit_file.filename or "unit.xlsx",
            unit_content,
            sales_file.filename or "sales.xlsx",
            sales_content,
            promotions_file.filename or "promotions.xlsx",
            promotions_content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
