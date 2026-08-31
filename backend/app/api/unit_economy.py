from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import get_unit_economy_service
from app.schemas.unit_economy import (
    ExcelUploadResponse,
    HeaderDetectionResponse,
    NormalizedSheetResponse,
    SheetDataResponse,
    SheetsResponse,
)
from app.services.unit_economy_service import UnitEconomyService


router = APIRouter(tags=["Unit Economy"])


@router.post("/upload-excel", response_model=ExcelUploadResponse)
async def upload_excel(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
    file: UploadFile = File(...),
) -> ExcelUploadResponse:
    return await service.upload_excel(file)


@router.get("/sheets", response_model=SheetsResponse)
def get_sheets(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
) -> SheetsResponse:
    try:
        return service.get_sheets()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/set-sheet", response_model=SheetsResponse)
def set_sheet(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
    sheet_name: str,
) -> SheetsResponse:
    try:
        return service.set_sheet(sheet_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sheet-data", response_model=SheetDataResponse)
def get_sheet_data(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
    sheet_name: str | None = None,
) -> SheetDataResponse:
    try:
        return service.get_sheet_data(sheet_name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/detect-header", response_model=HeaderDetectionResponse)
def detect_header(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
    sheet_name: str | None = None,
) -> HeaderDetectionResponse:
    try:
        return service.detect_header(sheet_name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/normalized-sheet", response_model=NormalizedSheetResponse)
def get_normalized_sheet(
    service: Annotated[UnitEconomyService, Depends(get_unit_economy_service)],
    sheet_name: str | None = None,
    header_row_index: int | None = None,
) -> NormalizedSheetResponse:
    try:
        return service.get_normalized_sheet(sheet_name, header_row_index)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

