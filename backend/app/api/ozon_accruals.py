from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ozon_accruals_service
from app.schemas.ozon_accruals import OzonAccrualLookupResponse, OzonAccrualsSummary
from app.services.ozon_accruals_service import ACCOUNTING_NOTE, OzonAccrualsService


router = APIRouter(prefix="/api/ozon/accruals", tags=["Ozon Accruals"])


@router.get("/summary", response_model=OzonAccrualsSummary)
def get_summary(
    service: Annotated[OzonAccrualsService, Depends(get_ozon_accruals_service)],
) -> OzonAccrualsSummary:
    return service.get_summary()


@router.get("/by-offer/{offer_id}", response_model=OzonAccrualLookupResponse)
def get_by_offer_id(
    service: Annotated[OzonAccrualsService, Depends(get_ozon_accruals_service)],
    offer_id: str,
) -> OzonAccrualLookupResponse:
    article = service.find_by_offer_id(offer_id)
    return OzonAccrualLookupResponse(
        found=article is not None,
        article=article,
        accounting_note=ACCOUNTING_NOTE,
    )
