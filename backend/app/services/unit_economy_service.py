from pathlib import Path
import shutil

import pandas as pd
from fastapi import UploadFile

from app.schemas.unit_economy import (
    ExcelUploadResponse,
    HeaderDetectionResponse,
    NormalizedSheetResponse,
    SheetDataResponse,
    SheetsResponse,
)


class UnitEconomyService:
    def __init__(self, upload_dir: Path) -> None:
        self._upload_dir = upload_dir
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._current_excel_file: Path | None = None
        self._current_sheet_name: str | None = None

    async def upload_excel(self, file: UploadFile) -> ExcelUploadResponse:
        filename = Path(file.filename or "unit-economy.xlsx").name
        file_path = self._upload_dir / filename

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        self._current_excel_file = file_path
        sheets = self._read_sheet_names(file_path)
        self._current_sheet_name = sheets[0] if sheets else None

        return ExcelUploadResponse(
            status="success",
            filename=filename,
            sheets=sheets,
            current_sheet_name=self._current_sheet_name,
        )

    def get_sheets(self) -> SheetsResponse:
        file_path = self._require_excel_file()
        sheets = self._read_sheet_names(file_path)
        return SheetsResponse(sheets=sheets, current_sheet_name=self._current_sheet_name)

    def set_sheet(self, sheet_name: str) -> SheetsResponse:
        file_path = self._require_excel_file()
        sheets = self._read_sheet_names(file_path)
        if sheet_name not in sheets:
            raise ValueError("Sheet not found")

        self._current_sheet_name = sheet_name
        return SheetsResponse(sheets=sheets, current_sheet_name=self._current_sheet_name)

    def get_sheet_data(self, sheet_name: str | None = None) -> SheetDataResponse:
        selected_sheet = self._select_sheet(sheet_name)
        df = pd.read_excel(self._require_excel_file(), sheet_name=selected_sheet, header=None)
        df = df.fillna("")

        return SheetDataResponse(
            sheet_name=selected_sheet,
            columns=list(df.columns),
            rows=df.values.tolist(),
            row_count=len(df),
            column_count=len(df.columns),
        )

    def detect_header(self, sheet_name: str | None = None) -> HeaderDetectionResponse:
        selected_sheet = self._select_sheet(sheet_name)
        raw_df = self._read_raw_sheet(selected_sheet)
        header_row_index, filled_cells = self._detect_header_row(raw_df)

        return HeaderDetectionResponse(
            sheet_name=selected_sheet,
            header_row_index=header_row_index,
            filled_cells=filled_cells,
        )

    def get_normalized_sheet(
        self,
        sheet_name: str | None = None,
        header_row_index: int | None = None,
    ) -> NormalizedSheetResponse:
        selected_sheet = self._select_sheet(sheet_name)
        raw_df = self._read_raw_sheet(selected_sheet)

        if header_row_index is None:
            header_row_index, _ = self._detect_header_row(raw_df)

        headers = raw_df.iloc[header_row_index].tolist()
        clean_headers = self._build_unique_headers(headers)

        data_df = raw_df.iloc[header_row_index + 1 :].copy()
        data_df.columns = clean_headers
        data_df = data_df.fillna("")

        return NormalizedSheetResponse(
            sheet_name=selected_sheet,
            header_row_index=header_row_index,
            columns=clean_headers,
            rows=data_df.to_dict(orient="records"),
            row_count=len(data_df),
            column_count=len(data_df.columns),
        )

    def _require_excel_file(self) -> Path:
        if self._current_excel_file is None:
            raise FileNotFoundError("Excel file is not uploaded")
        return self._current_excel_file

    def _select_sheet(self, sheet_name: str | None) -> str:
        self._require_excel_file()
        if sheet_name is not None:
            self._current_sheet_name = sheet_name

        if self._current_sheet_name is None:
            raise ValueError("Sheet is not selected")

        return self._current_sheet_name

    def _read_raw_sheet(self, sheet_name: str) -> pd.DataFrame:
        return pd.read_excel(self._require_excel_file(), sheet_name=sheet_name, header=None).fillna("")

    @staticmethod
    def _read_sheet_names(file_path: Path) -> list[str]:
        excel_file = pd.ExcelFile(file_path)
        return list(excel_file.sheet_names)

    @staticmethod
    def _detect_header_row(raw_df: pd.DataFrame) -> tuple[int, int]:
        best_row_index = 0
        max_filled = 0

        for row_index, row in raw_df.iterrows():
            filled_count = sum(1 for cell in row if cell != "")
            if filled_count > max_filled:
                max_filled = filled_count
                best_row_index = int(row_index)

        return best_row_index, max_filled

    @staticmethod
    def _build_unique_headers(headers: list[object]) -> list[str]:
        clean_headers: list[str] = []
        used_headers: dict[str, int] = {}

        for index, header in enumerate(headers):
            base_name = f"column_{index}" if header == "" else str(header).strip()
            current_count = used_headers.get(base_name, 0) + 1
            used_headers[base_name] = current_count

            clean_name = base_name if current_count == 1 else f"{base_name}_{current_count}"
            clean_headers.append(clean_name)

        return clean_headers

