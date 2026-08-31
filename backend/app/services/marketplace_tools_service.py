from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app.integrations.ozon_elastic_boosting.config import CategoryOverride, ProcessingConfig
from app.integrations.ozon_elastic_boosting.processor import (
    ProcessingError,
    create_processing_report,
    list_promo_categories,
    load_workbook_file,
    process_promo_workbook,
    save_result,
)


PREVIEW_LIMIT = 20_000
SAFE_FILENAME_PATTERN = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._() -]+")


@dataclass(frozen=True)
class ArtifactFile:
    filename: str
    media_type: str


@dataclass(frozen=True)
class ToolRunResult:
    artifact_id: str
    tool: str
    stats: dict[str, str | int | float | bool | None]
    preview: list[dict[str, str | int | float | bool | None]]
    artifacts: tuple[ArtifactFile, ...]
    warnings: tuple[str, ...] = ()


class MarketplaceToolsService:
    def __init__(self, artifacts_dir: Path) -> None:
        self._artifacts_dir = artifacts_dir.resolve()
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    def list_ozon_elastic_boosting_categories(
        self,
        *,
        promo_bytes: bytes,
    ) -> list[tuple[str, int]]:
        promo_values_workbook = load_workbook_file(BytesIO(promo_bytes), data_only=True)
        try:
            return list_promo_categories(promo_values_workbook)
        except ProcessingError as exc:
            raise ValueError(str(exc)) from exc
        finally:
            promo_values_workbook.close()

    def process_ozon_elastic_boosting(
        self,
        *,
        promo_bytes: bytes,
        ads_bytes: bytes,
        min_discount: float,
        max_discount: float,
        exclude_direct_ads: bool,
        strict_union_exclusion: bool,
        zero_discount_for_negative: bool = False,
        target_discount_percent: float | None = None,
        excluded_identifiers: list[str] | None = None,
        category_overrides: list[CategoryOverride] | None = None,
    ) -> ToolRunResult:
        promo_workbook = load_workbook_file(BytesIO(promo_bytes), data_only=False)
        promo_values_workbook = load_workbook_file(BytesIO(promo_bytes), data_only=True)
        ads_workbook = load_workbook_file(BytesIO(ads_bytes), data_only=True)
        try:
            try:
                result = process_promo_workbook(
                    promo_workbook,
                    promo_values_workbook,
                    ads_workbook,
                    ProcessingConfig(
                        min_discount=min_discount,
                        max_discount=max_discount,
                        exclude_direct_ads=exclude_direct_ads,
                        strict_union_exclusion=strict_union_exclusion,
                        zero_discount_for_negative=zero_discount_for_negative,
                        target_discount_percent=target_discount_percent,
                        excluded_identifiers=frozenset(excluded_identifiers or ()),
                        category_overrides=tuple(category_overrides or ()),
                    ),
                )
                xlsx_bytes, _ = save_result(result)
            except ProcessingError as exc:
                raise ValueError(str(exc)) from exc
            csv_bytes = create_processing_report(result.report_rows).encode("utf-8-sig")
            artifact_id, output_dir = self._create_output_dir()
            xlsx_name = self._write_artifact(output_dir, result.output_filename, xlsx_bytes)
            csv_name = self._write_artifact(output_dir, result.csv_filename, csv_bytes)
            preview = [
                self._normalize_mapping(asdict(row))
                for row in result.report_rows[:PREVIEW_LIMIT]
            ]
            return ToolRunResult(
                artifact_id=artifact_id,
                tool="ozon_elastic_boosting",
                stats=self._normalize_mapping(asdict(result.summary)),
                preview=preview,
                artifacts=(
                    ArtifactFile(
                        filename=xlsx_name,
                        media_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                    ),
                    ArtifactFile(filename=csv_name, media_type="text/csv; charset=utf-8"),
                ),
            )
        finally:
            promo_workbook.close()
            promo_values_workbook.close()
            ads_workbook.close()

    def resolve_artifact(self, artifact_id: str, filename: str) -> Path:
        safe_id = self._safe_identifier(artifact_id)
        safe_filename = self._safe_filename(filename)
        path = (self._artifacts_dir / safe_id / safe_filename).resolve()
        if self._artifacts_dir not in path.parents or not path.is_file():
            raise FileNotFoundError(filename)
        return path

    def _create_output_dir(self) -> tuple[str, Path]:
        artifact_id = uuid4().hex
        output_dir = self._artifacts_dir / artifact_id
        output_dir.mkdir(parents=True, exist_ok=False)
        return artifact_id, output_dir

    def _write_artifact(self, output_dir: Path, filename: str, data: bytes) -> str:
        safe_filename = self._safe_filename(filename)
        (output_dir / safe_filename).write_bytes(data)
        return safe_filename

    @staticmethod
    def _safe_filename(filename: str) -> str:
        clean = SAFE_FILENAME_PATTERN.sub("_", Path(filename).name).strip(" .")
        if not clean:
            raise ValueError("Некорректное имя итогового файла")
        return clean

    @staticmethod
    def _safe_identifier(value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise FileNotFoundError(value)
        return value

    @staticmethod
    def _normalize_mapping(
        values: dict[str, object],
    ) -> dict[str, str | int | float | bool | None]:
        normalized: dict[str, str | int | float | bool | None] = {}
        for key, value in values.items():
            if value is None or isinstance(value, (str, int, float, bool)):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        return normalized
