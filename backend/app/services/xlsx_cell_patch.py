"""Surgical cell-level XLSX editing shared by marketplace price-update tools.

A full openpyxl load-mutate-save round trip of a real marketplace export
(thousands of rows, data validations, inline strings) was found to silently
rewrite untouched cells into schema-invalid XML, which the marketplace's own
upload validator then rejected - even though Excel opened the result fine
(see price_update_service.apply_new_prices for the concrete case that
surfaced this with Ozon). Patching only the exact target cells' XML directly
avoids that whole class of bug: every other byte of the original export -
which the marketplace itself produced and accepts - stays untouched.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class XlsxCellPatchError(ValueError):
    pass


def resolve_sheet_xml_path(template_bytes: bytes, sheet_name: str) -> str:
    with zipfile.ZipFile(BytesIO(template_bytes)) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_id = None
    for sheet_element in workbook_root.iter(f"{{{_MAIN_NS}}}sheet"):
        if sheet_element.get("name") == sheet_name:
            rel_id = sheet_element.get(f"{{{_DOC_REL_NS}}}id")
            break
    if rel_id is None:
        raise XlsxCellPatchError(f"В файле нет листа «{sheet_name}»")

    target = None
    for rel_element in rels_root.iter(f"{{{_PKG_REL_NS}}}Relationship"):
        if rel_element.get("Id") == rel_id:
            target = rel_element.get("Target")
            break
    if target is None:
        raise XlsxCellPatchError(f"Не удалось определить расположение листа «{sheet_name}» в файле")

    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def patch_cells(
    template_bytes: bytes,
    sheet_xml_path: str,
    cell_updates: list[tuple[int, str, float]],
) -> bytes:
    """Return a copy of the workbook with only the given (row, column
    letter, value) cells replaced in ``sheet_xml_path``. Every other zip
    entry - including every other worksheet - is copied through byte for
    byte."""
    source = zipfile.ZipFile(BytesIO(template_bytes))
    try:
        sheet_xml = source.read(sheet_xml_path).decode("utf-8")

        unmatched_cells: list[str] = []
        for row_number, column_letter, value in cell_updates:
            sheet_xml, replaced = _replace_cell(sheet_xml, row_number, column_letter, value)
            if not replaced:
                unmatched_cells.append(f"{column_letter}{row_number}")
        if unmatched_cells:
            raise XlsxCellPatchError(
                "Не удалось обновить ячейки в шаблоне: " + ", ".join(unmatched_cells[:20])
            )

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target_archive:
            for item in source.infolist():
                data = (
                    sheet_xml.encode("utf-8")
                    if item.filename == sheet_xml_path
                    else source.read(item.filename)
                )
                target_archive.writestr(item, data)
        return buffer.getvalue()
    finally:
        source.close()


_ROW_CELL_REF_PATTERN = re.compile(r'<c r="([A-Z]+)\d+"')


def _column_index(column_letter: str) -> int:
    index = 0
    for char in column_letter:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _replace_cell(sheet_xml: str, row_number: int, column_letter: str, value: float) -> tuple[str, bool]:
    cell_ref = f"{column_letter}{row_number}"
    cell_pattern = re.compile(r'<c r="' + re.escape(cell_ref) + r'"([^>]*?)(?:/>|>.*?</c>)')

    def build_replacement(match: re.Match[str]) -> str:
        style_match = re.search(r'\bs="(\d+)"', match.group(1))
        style_attr = f' s="{style_match.group(1)}"' if style_match else ""
        return f'<c r="{cell_ref}"{style_attr}><v>{value}</v></c>'

    new_xml, count = cell_pattern.subn(build_replacement, sheet_xml, count=1)
    if count > 0:
        return new_xml, True

    # A genuinely blank source cell (never formatted or written to) has no
    # <c> element at all - Excel/marketplace exports omit those rather than
    # writing an empty one. Insert a new <c> into that row, in the correct
    # column-sorted position, instead of treating this as unpatchable.
    return _insert_cell(sheet_xml, row_number, column_letter, value)


def _insert_cell(sheet_xml: str, row_number: int, column_letter: str, value: float) -> tuple[str, bool]:
    row_pattern = re.compile(r'(<row r="' + str(row_number) + r'"[^>]*>)(.*?)(</row>)', re.DOTALL)
    row_match = row_pattern.search(sheet_xml)
    if row_match is None:
        return sheet_xml, False

    row_open, row_body, row_close = row_match.groups()
    new_cell_xml = f'<c r="{column_letter}{row_number}"><v>{value}</v></c>'
    target_index = _column_index(column_letter)

    insert_at = len(row_body)
    for cell_match in _ROW_CELL_REF_PATTERN.finditer(row_body):
        if _column_index(cell_match.group(1)) > target_index:
            insert_at = cell_match.start()
            break

    new_row_body = row_body[:insert_at] + new_cell_xml + row_body[insert_at:]
    new_sheet_xml = (
        sheet_xml[: row_match.start()]
        + row_open
        + new_row_body
        + row_close
        + sheet_xml[row_match.end() :]
    )
    return new_sheet_xml, True
