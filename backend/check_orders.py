from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT id, file_id, copies, color_mode, duplex, page_range, selected_page_count, physical_sheet_count, price_per_page, total_amount, currency, status FROM orders ORDER BY created_at DESC LIMIT 5")).fetchall()
    print(f"Total retrieved: {len(rows)}")
    for r in rows:
        print("Order:", r)
