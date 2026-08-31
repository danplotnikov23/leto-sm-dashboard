from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.dependencies import get_unit_economy_index_service
from app.schemas.unit_economy_index import (
    UnitEconomyIndexSummary,
    UnitEconomyLookupResponse,
)
from app.services.unit_economy_index_service import UnitEconomyIndexService


router = APIRouter(prefix="/api/unit-economy", tags=["Unit Economy Index"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.get("/summary", response_model=UnitEconomyIndexSummary)
def get_summary(
    service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
) -> UnitEconomyIndexSummary:
    return service.get_summary()


@router.get("/by-offer/{offer_id}", response_model=UnitEconomyLookupResponse)
def get_by_offer_id(
    service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
    offer_id: str,
) -> UnitEconomyLookupResponse:
    product = service.find_by_offer_id(offer_id)
    return UnitEconomyLookupResponse(found=product is not None, product=product)


@router.get("/by-sku/{sku}", response_model=UnitEconomyLookupResponse)
def get_by_sku(
    service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
    sku: str,
) -> UnitEconomyLookupResponse:
    product = service.find_by_sku(sku)
    return UnitEconomyLookupResponse(found=product is not None, product=product)


@router.post("/versions", response_model=UnitEconomyIndexSummary)
async def upload_workbook_version(
    service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
    workbook_file: Annotated[UploadFile, File(...)],
    valid_from: Annotated[date, Form(...)],
) -> UnitEconomyIndexSummary:
    if not workbook_file.filename or not workbook_file.filename.lower().endswith(
        (".xlsx", ".xlsm")
    ):
        raise HTTPException(status_code=422, detail="Файл должен быть XLSX или XLSM")
    data = await workbook_file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Файл пуст")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл превышает 100 МБ")

    try:
        return await run_in_threadpool(
            service.add_version, data, valid_from, workbook_file.filename
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Не удалось прочитать юнитку: {exc}",
        ) from exc


@router.delete("/versions/{valid_from}", response_model=UnitEconomyIndexSummary)
async def delete_workbook_version(
    service: Annotated[
        UnitEconomyIndexService,
        Depends(get_unit_economy_index_service),
    ],
    valid_from: date,
) -> UnitEconomyIndexSummary:
    try:
        return await run_in_threadpool(service.remove_version, valid_from)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

