from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError

from app.api.dependencies import get_price_update_service
from app.schemas.price_update import (
    PriceUpdateCategoriesResponse,
    PriceUpdateItem,
    PriceUpdateSearchResponse,
)
from app.services.price_update_service import PriceUpdateService, PriceUpdateTemplateError

router = APIRouter(prefix="/api/price-update", tags=["Price Update"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_ITEMS_ADAPTER = TypeAdapter(list[PriceUpdateItem])


async def _read_template_upload(upload: UploadFile) -> bytes:
    if not upload.filename:
        raise HTTPException(status_code=422, detail="Файл не выбран")
    suffix = "." + upload.filename.rsplit(".", 1)[-1].lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(
            status_code=422,
            detail=f"Файл {upload.filename} должен быть XLSX или XLSM",
        )
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail=f"Файл {upload.filename} пуст")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Файл {upload.filename} превышает 100 МБ")
    return data


@router.get("/categories", response_model=PriceUpdateCategoriesResponse)
async def list_price_update_categories(
    service: Annotated[PriceUpdateService, Depends(get_price_update_service)],
) -> PriceUpdateCategoriesResponse:
    return await run_in_threadpool(service.list_categories)


@router.post("/search", response_model=PriceUpdateSearchResponse)
async def search_price_update_products(
    service: Annotated[PriceUpdateService, Depends(get_price_update_service)],
    template_file: Annotated[UploadFile, File(...)],
    query: Annotated[str, Form()] = "",
    category: Annotated[str | None, Form()] = None,
) -> PriceUpdateSearchResponse:
    template_bytes = await _read_template_upload(template_file)
    try:
        return await run_in_threadpool(
            service.search_products, template_bytes, query, category
        )
    except PriceUpdateTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply.xlsx")
async def apply_price_update(
    service: Annotated[PriceUpdateService, Depends(get_price_update_service)],
    template_file: Annotated[UploadFile, File(...)],
    updates_json: Annotated[str, Form()],
) -> Response:
    template_bytes = await _read_template_upload(template_file)
    try:
        updates = _ITEMS_ADAPTER.validate_json(updates_json)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        content = await run_in_threadpool(service.apply_new_prices, template_bytes, updates)
    except PriceUpdateTemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="alleya_price_update.xlsx"'
        },
    )
