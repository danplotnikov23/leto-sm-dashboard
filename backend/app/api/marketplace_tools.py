from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError

from app.api.dependencies import get_marketplace_tools_service
from app.integrations.ozon_elastic_boosting.config import CategoryOverride
from app.schemas.marketplace_tools import (
    ArtifactLink,
    MarketplaceToolResult,
    PromoCategoriesResponse,
    PromoCategoryOption,
    PromoCategoryOverrideInput,
)
from app.services.marketplace_tools_service import (
    MarketplaceToolsService,
    ToolRunResult,
)

_CATEGORY_OVERRIDES_ADAPTER = TypeAdapter(list[PromoCategoryOverrideInput])
_EXCLUDED_IDENTIFIERS_ADAPTER = TypeAdapter(list[str])


router = APIRouter(prefix="/api/tools", tags=["Marketplace Tools"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


async def _read_excel_upload(upload: UploadFile, *, required: bool = True) -> bytes | None:
    if not upload.filename:
        if required:
            raise HTTPException(status_code=422, detail="Файл не выбран")
        return None
    suffix = "." + upload.filename.rsplit(".", 1)[-1].lower()
    if suffix not in ALLOWED_EXCEL_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail=f"Файл {upload.filename} должен быть XLSX или XLSM",
        )
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail=f"Файл {upload.filename} пуст")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл {upload.filename} превышает 100 МБ",
        )
    return data


def _response_from_result(result: ToolRunResult) -> MarketplaceToolResult:
    return MarketplaceToolResult(
        tool=result.tool,
        stats=result.stats,
        preview=result.preview,
        artifacts=[
            ArtifactLink(
                filename=artifact.filename,
                media_type=artifact.media_type,
                download_url=(
                    f"/api/tools/artifacts/{result.artifact_id}/{artifact.filename}"
                ),
            )
            for artifact in result.artifacts
        ],
        warnings=list(result.warnings),
    )


@router.post("/ozon-elastic-boosting/categories", response_model=PromoCategoriesResponse)
async def list_ozon_elastic_boosting_categories(
    service: Annotated[
        MarketplaceToolsService,
        Depends(get_marketplace_tools_service),
    ],
    promo_file: Annotated[UploadFile, File(...)],
) -> PromoCategoriesResponse:
    promo_bytes = await _read_excel_upload(promo_file)
    try:
        categories = await run_in_threadpool(
            service.list_ozon_elastic_boosting_categories,
            promo_bytes=promo_bytes,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PromoCategoriesResponse(
        categories=[
            PromoCategoryOption(category=category, product_count=count)
            for category, count in categories
        ]
    )


@router.post("/ozon-elastic-boosting", response_model=MarketplaceToolResult)
async def process_ozon_elastic_boosting(
    service: Annotated[
        MarketplaceToolsService,
        Depends(get_marketplace_tools_service),
    ],
    promo_file: Annotated[UploadFile, File(...)],
    ads_file: Annotated[UploadFile, File(...)],
    min_discount: Annotated[float, Form()] = 0.1,
    max_discount: Annotated[float, Form()] = 11.0,
    exclude_direct_ads: Annotated[bool, Form()] = True,
    strict_union_exclusion: Annotated[bool, Form()] = True,
    zero_discount_for_negative: Annotated[bool, Form()] = False,
    target_discount_percent: Annotated[float | None, Form()] = None,
    category_overrides_json: Annotated[str, Form()] = "[]",
    excluded_identifiers_json: Annotated[str, Form()] = "[]",
) -> MarketplaceToolResult:
    promo_bytes = await _read_excel_upload(promo_file)
    ads_bytes = await _read_excel_upload(ads_file)
    try:
        overrides_input = _CATEGORY_OVERRIDES_ADAPTER.validate_json(category_overrides_json)
        excluded_identifiers = _EXCLUDED_IDENTIFIERS_ADAPTER.validate_json(
            excluded_identifiers_json
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    category_overrides = [
        CategoryOverride(
            category=item.category,
            min_discount=item.min_discount,
            max_discount=item.max_discount,
            exclude=item.exclude,
        )
        for item in overrides_input
    ]
    try:
        result = await run_in_threadpool(
            service.process_ozon_elastic_boosting,
            promo_bytes=promo_bytes,
            ads_bytes=ads_bytes,
            min_discount=min_discount,
            max_discount=max_discount,
            exclude_direct_ads=exclude_direct_ads,
            strict_union_exclusion=strict_union_exclusion,
            zero_discount_for_negative=zero_discount_for_negative,
            target_discount_percent=target_discount_percent,
            excluded_identifiers=excluded_identifiers,
            category_overrides=category_overrides,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response_from_result(result)


@router.get("/artifacts/{artifact_id}/{filename}")
def download_artifact(
    artifact_id: str,
    filename: str,
    service: Annotated[
        MarketplaceToolsService,
        Depends(get_marketplace_tools_service),
    ],
) -> FileResponse:
    try:
        path = service.resolve_artifact(artifact_id, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Файл результата не найден") from exc
    return FileResponse(path=path, filename=path.name)
