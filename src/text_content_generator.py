"""Tạo Text_Content cho các sản phẩm thuộc filter view "có ads"."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass

import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SOURCE_TAB = "TỔNG HỢP"
DESTINATION_TAB = "Bài viết"
PROMPT_TAB = "Promt GPT"
PROMPT_CELL = "B2"
FILTER_VIEW_TITLE = "có ads"
SOURCE_CODE_COLUMN = 3  # C
SOURCE_DESCRIPTION_COLUMN = 5  # E
DESTINATION_CODE_COLUMN = 4  # D
DESTINATION_CONTENT_COLUMN = 7  # G
FIRST_DATA_ROW = 2


@dataclass(frozen=True)
class Product:
    source_row: int
    code: str
    description: str


def normalize(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def cell(row: list[str], one_based_column: int) -> str:
    index = one_based_column - 1
    return row[index].strip() if index < len(row) else ""


def condition_matches(value: str, condition: dict) -> bool:
    """Đánh giá các điều kiện phổ biến trong Google Sheets filter view."""
    kind = condition.get("type", "")
    operands = [str(item.get("userEnteredValue", "")) for item in condition.get("values", [])]
    expected = operands[0] if operands else ""
    left, right = normalize(value), normalize(expected)
    text_checks = {
        "BLANK": not left,
        "NOT_BLANK": bool(left),
        "TEXT_EQ": left == right,
        "TEXT_NOT_EQ": left != right,
        "TEXT_CONTAINS": right in left,
        "TEXT_NOT_CONTAINS": right not in left,
        "TEXT_STARTS_WITH": left.startswith(right),
        "TEXT_ENDS_WITH": left.endswith(right),
    }
    if kind in text_checks:
        return text_checks[kind]
    try:
        number = float(re.sub(r"[^\d.-]", "", value))
        target = float(re.sub(r"[^\d.-]", "", expected))
    except ValueError:
        return True
    number_checks = {
        "NUMBER_EQ": number == target,
        "NUMBER_NOT_EQ": number != target,
        "NUMBER_GREATER": number > target,
        "NUMBER_GREATER_THAN_EQ": number >= target,
        "NUMBER_LESS": number < target,
        "NUMBER_LESS_THAN_EQ": number <= target,
    }
    return number_checks.get(kind, True)


def row_is_visible(row: list[str], criteria: dict[str, dict]) -> bool:
    for zero_based_column, criterion in criteria.items():
        index = int(zero_based_column)
        value = row[index].strip() if index < len(row) else ""
        hidden_values = {normalize(item) for item in criterion.get("hiddenValues", [])}
        if normalize(value) in hidden_values:
            return False
        condition = criterion.get("condition")
        if condition and not condition_matches(value, condition):
            return False
    return True


def open_spreadsheet() -> gspread.Spreadsheet:
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    credentials_json = os.getenv("GOOGLE_CREDENTIALS")
    missing = [name for name, value in [
        ("GOOGLE_SHEET_ID", sheet_id),
        ("GOOGLE_CREDENTIALS", credentials_json),
    ] if not value]
    if missing:
        raise EnvironmentError(f"Thiếu biến môi trường: {', '.join(missing)}")
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GOOGLE_CREDENTIALS không phải JSON hợp lệ: {exc}") from exc
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(credentials).open_by_key(sheet_id)


def find_filter_view(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet) -> dict:
    metadata = spreadsheet.fetch_sheet_metadata(
        params={"fields": "sheets(properties(sheetId,title),filterViews)"}
    )
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") != worksheet.id:
            continue
        for view in sheet.get("filterViews", []):
            if normalize(view.get("title")) == normalize(FILTER_VIEW_TITLE):
                return view
    raise ValueError(
        f"Không tìm thấy filter view '{FILTER_VIEW_TITLE}' trong tab '{SOURCE_TAB}'"
    )


def read_filtered_products(spreadsheet: gspread.Spreadsheet) -> list[Product]:
    worksheet = spreadsheet.worksheet(SOURCE_TAB)
    values = worksheet.get_all_values()
    view = find_filter_view(spreadsheet, worksheet)
    criteria = dict(view.get("criteria", {}))
    for spec in view.get("filterSpecs", []):
        column_index = spec.get("columnIndex")
        if column_index is not None and spec.get("filterCriteria"):
            criteria[str(column_index)] = spec["filterCriteria"]
    view_range = view.get("range", {})
    start_row = max(view_range.get("startRowIndex", 0) + 1, FIRST_DATA_ROW)
    end_row = min(view_range.get("endRowIndex", len(values)), len(values))
    products = []
    for row_number in range(start_row, end_row + 1):
        row = values[row_number - 1]
        if not row_is_visible(row, criteria):
            continue
        code = cell(row, SOURCE_CODE_COLUMN)
        description = cell(row, SOURCE_DESCRIPTION_COLUMN)
        if code and description:
            products.append(Product(row_number, code, description))
    return products


def generate_content(client: OpenAI, model: str, prompt: str, product: Product) -> str:
    model_input = (
        f"{prompt.strip()}\n\n"
        "Chỉ tạo nội dung cho đúng một sản phẩm dưới đây. Chỉ trả về "
        "Text_Content hoàn chỉnh, không giải thích, không Markdown và không đặt "
        "dấu ngoặc kép ở đầu hoặc cuối.\n\n"
        f"MÃ SP: {product.code}\n"
        f"THÔNG TIN SẢN PHẨM: {product.description}"
    )
    response = client.responses.create(
        model=model,
        instructions=(
            "Bạn là người viết quảng cáo thời trang tiếng Việt. Tuân thủ dữ liệu "
            "nguồn; không tự thêm chất liệu, màu sắc, kiểu dáng hoặc thông số."
        ),
        input=model_input,
        max_output_tokens=700,
        store=False,
    )
    content = re.sub(
        r'^\s*["“”]+|["“”]+\s*$', "", response.output_text.strip()
    ).strip()
    if not content:
        raise ValueError(f"AI trả về nội dung trống cho mã {product.code}")
    return content


def run(*, dry_run: bool = False, overwrite: bool = False, limit: int | None = None) -> None:
    if not dry_run and not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("Thiếu OPENAI_API_KEY")
    spreadsheet = open_spreadsheet()
    prompt = spreadsheet.worksheet(PROMPT_TAB).acell(PROMPT_CELL).value or ""
    if not prompt.strip():
        raise ValueError(f"Ô {PROMPT_TAB}!{PROMPT_CELL} đang trống")
    products = read_filtered_products(spreadsheet)
    destination = spreadsheet.worksheet(DESTINATION_TAB)
    codes = destination.col_values(DESTINATION_CODE_COLUMN)
    contents = destination.col_values(DESTINATION_CONTENT_COLUMN)
    pending = []
    for destination_row, product in enumerate(products, start=FIRST_DATA_ROW):
        old_code = codes[destination_row - 1].strip() if destination_row <= len(codes) else ""
        old_content = contents[destination_row - 1].strip() if destination_row <= len(contents) else ""
        if not overwrite and old_code == product.code and old_content:
            continue
        pending.append((destination_row, product))
    if limit is not None:
        pending = pending[:limit]
    print(f"Filter '{FILTER_VIEW_TITLE}': {len(products)} sản phẩm; xử lý {len(pending)}.")
    if dry_run:
        for row_number, product in pending:
            print(f"[DRY-RUN] Bài viết!D{row_number}/G{row_number} <- {product.code}")
        return
    client = OpenAI()
    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.4-nano")
    updates = []
    for row_number, product in pending:
        print(f"Đang viết {product.code}...")
        content = generate_content(client, model, prompt, product)
        updates.extend([
            {"range": f"D{row_number}", "values": [[product.code]]},
            {"range": f"G{row_number}", "values": [[content]]},
        ])
    if updates:
        destination.batch_update(updates, value_input_option="RAW")
    print(f"Hoàn tất: đã ghi {len(pending)} Text_Content bằng {model}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo Text_Content từ Google Sheet")
    parser.add_argument("--dry-run", action="store_true", help="Không gọi AI, không ghi Sheet")
    parser.add_argument("--overwrite", action="store_true", help="Ghi đè content đã có")
    parser.add_argument("--limit", type=int, help="Giới hạn số sản phẩm cần xử lý")
    args = parser.parse_args()
    run(dry_run=args.dry_run, overwrite=args.overwrite, limit=args.limit)


if __name__ == "__main__":
    main()
