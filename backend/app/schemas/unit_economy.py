from pydantic import BaseModel


class ExcelUploadResponse(BaseModel):
    status: str
    filename: str
    sheets: list[str]
    current_sheet_name: str | None


class SheetsResponse(BaseModel):
    sheets: list[str]
    current_sheet_name: str | None


class SheetDataResponse(BaseModel):
    sheet_name: str
    columns: list[str | int]
    rows: list[list[object]]
    row_count: int
    column_count: int


class HeaderDetectionResponse(BaseModel):
    sheet_name: str
    header_row_index: int
    filled_cells: int


class NormalizedSheetResponse(BaseModel):
    sheet_name: str
    header_row_index: int
    columns: list[str]
    rows: list[dict[str, object]]
    row_count: int
    column_count: int

