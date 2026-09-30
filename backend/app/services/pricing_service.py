import math
import re
from typing import List, Dict, Any
from app.config import settings


def parse_and_validate_page_range(page_range_str: str, total_pages: int) -> List[int]:
    """
    Parse a page range string (e.g. 'all', '1-3, 5, 7-9') and validate it against total_pages.
    
    Rules:
    - Page numbers cannot be less than 1.
    - Page numbers cannot exceed total_pages.
    - Invalid syntax is rejected.
    - Duplicate pages are deduplicated.
    - Returns sorted list of unique 1-indexed page numbers.
    """
    if not page_range_str or not page_range_str.strip():
        raise ValueError("Page range cannot be empty.")

    cleaned = page_range_str.strip()

    # Handle 'all' case
    if cleaned.lower() == "all":
        if total_pages < 1:
            raise ValueError("Document has 0 pages.")
        return list(range(1, total_pages + 1))

    # Reject leading/trailing comma or consecutive commas
    if cleaned.startswith(",") or cleaned.endswith(",") or re.search(r",\s*,", cleaned):
        raise ValueError("Invalid page range format. Commas must separate page numbers or ranges.")

    parts = [p.strip() for p in cleaned.split(",")]
    if not parts:
        raise ValueError("Invalid page range format.")

    selected_pages = set()

    for part in parts:
        if not part:
            raise ValueError("Invalid page range format.")

        # Check for range syntax 'X-Y'
        if "-" in part:
            range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
            if not range_match:
                raise ValueError(f"Invalid range format '{part}'. Expected format like '1-3'.")
            start = int(range_match.group(1))
            end = int(range_match.group(2))

            if start < 1:
                raise ValueError(f"Page numbers must be 1 or greater. Got '{start}'.")
            if end < start:
                raise ValueError(f"Range start ({start}) cannot be greater than range end ({end}).")
            if end > total_pages:
                raise ValueError(f"Page range '{part}' exceeds total document pages ({total_pages}).")

            for page in range(start, end + 1):
                selected_pages.add(page)
        else:
            # Single page number
            if not part.isdigit():
                raise ValueError(f"Invalid page number '{part}'. Must be numeric.")
            page_num = int(part)
            if page_num < 1:
                raise ValueError(f"Page numbers must be 1 or greater. Got '{page_num}'.")
            if page_num > total_pages:
                raise ValueError(f"Page {page_num} exceeds total document pages ({total_pages}).")
            selected_pages.add(page_num)

    if not selected_pages:
        raise ValueError("No pages were selected.")

    return sorted(list(selected_pages))


def calculate_physical_sheets(selected_page_count: int, copies: int, duplex: bool) -> int:
    """
    Calculate the number of physical paper sheets required.
    - Single side: 1 page = 1 sheet per copy.
    - Double side: 2 pages = 1 sheet (rounded up) per copy.
    """
    if selected_page_count <= 0 or copies <= 0:
        return 0

    if not duplex:
        return selected_page_count * copies

    sheets_per_copy = math.ceil(selected_page_count / 2.0)
    return int(sheets_per_copy * copies)


def calculate_pricing(
    selected_page_count: int,
    copies: int,
    color_mode: str,
    duplex: bool,
) -> Dict[str, Any]:
    """
    Authoritatively calculate print job pricing based on centralized settings.
    
    Formula:
    - price_per_page = BW_PRICE_PER_PAGE if color_mode == 'bw' else COLOR_PRICE_PER_PAGE
    - total_amount = selected_page_count * copies * price_per_page
    - physical_sheet_count = calculate_physical_sheets(selected_page_count, copies, duplex)
    """
    if selected_page_count <= 0:
        raise ValueError("Selected page count must be greater than 0.")

    if copies < 1 or copies > 100:
        raise ValueError("Copies must be between 1 and 100.")

    mode = color_mode.strip().lower()
    if mode not in ["bw", "color"]:
        raise ValueError(f"Invalid color mode '{color_mode}'. Must be 'bw' or 'color'.")

    price_per_page = (
        settings.BW_PRICE_PER_PAGE if mode == "bw" else settings.COLOR_PRICE_PER_PAGE
    )
    total_amount = round(selected_page_count * copies * price_per_page, 2)
    physical_sheet_count = calculate_physical_sheets(selected_page_count, copies, duplex)

    return {
        "selected_page_count": selected_page_count,
        "copies": copies,
        "color_mode": mode,
        "duplex": duplex,
        "physical_sheet_count": physical_sheet_count,
        "price_per_page": price_per_page,
        "total_amount": total_amount,
        "currency": settings.CURRENCY,
    }
