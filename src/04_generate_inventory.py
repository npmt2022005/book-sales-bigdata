"""Sinh bảng fact_inventory MÔ PHỎNG cho lớp kinh doanh.

Cách chạy, từ thư mục gốc của project:
    .venv\\Scripts\\python src\\04_generate_inventory.py
Kết quả: data/warehouse/fact_inventory.parquet và results/inventory_report.json

Phạm vi: 12 tháng cuối đủ dữ liệu (2022-09 đến 2023-08), chỉ gồm sách có bán trong khoảng này.
Dữ liệu này là giả lập, mọi dòng có is_simulated = TRUE, không dùng để kết luận về thực tế.

Giả định, chạy lại cho cùng kết quả vì dùng hàm băm với SEED cố định:
- Giá vốn mỗi sách cố định, bằng 50-80% giá bán. Sách không có giá thì không có giá vốn.
- Tồn cuối tháng = số lượng bán trong tháng x hệ số từ 0 đến 2, cộng thêm 0-4 cuốn.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261109
FIRST_MONTH = 202209
LAST_MONTH = 202308


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", type=Path, default=ROOT / "data" / "warehouse")
    parser.add_argument("--report", type=Path, default=ROOT / "results" / "inventory_report.json")
    parser.add_argument("--memory", default="6GB")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = args.warehouse / "fact_inventory.parquet"
    if target.exists() and not args.force:
        sys.exit(f"Đã có {target}. Dùng --force nếu muốn ghi đè.")
    temp = target.with_suffix(".tmp.parquet")
    spill = args.warehouse.parent / "duckdb_tmp"
    wh = args.warehouse.as_posix()

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{args.memory}'")
    con.execute(f"SET temp_directory='{spill.as_posix()}'")
    con.execute(f"""
        COPY (
            WITH monthly AS (
                SELECT f.book_key, d.year * 100 + d.month AS month_key, sum(f.quantity) AS sold
                FROM '{wh}/fact_sales.parquet' f
                JOIN '{wh}/dim_date.parquet' d USING (date_key)
                WHERE d.year * 100 + d.month BETWEEN {FIRST_MONTH} AND {LAST_MONTH}
                GROUP BY 1, 2
            ),
            months AS (SELECT DISTINCT month_key FROM monthly),
            books AS (
                SELECT DISTINCT m.book_key, b.list_price
                FROM monthly m JOIN '{wh}/dim_books.parquet' b USING (book_key)
            )
            SELECT b.book_key,
                   t.month_key,
                   coalesce(s.sold, 0) AS units_sold,
                   CAST(round(coalesce(s.sold, 0) * (hash(b.book_key, t.month_key, {SEED}) % 2001) / 1000.0)
                        + hash(t.month_key, b.book_key, {SEED}) % 5 AS INTEGER) AS stock_quantity,
                   round(b.list_price * (0.5 + (hash(b.book_key, {SEED}) % 3001) / 10000.0), 2) AS unit_cost,
                   TRUE AS is_simulated
            FROM books b
            CROSS JOIN months t
            LEFT JOIN monthly s ON s.book_key = b.book_key AND s.month_key = t.month_key
        ) TO '{temp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)

    source = f"'{temp.as_posix()}'"
    row = con.execute(f"""
        SELECT count(*), count(DISTINCT book_key), count(DISTINCT month_key),
               count(*) - count(DISTINCT (book_key, month_key)),
               count(*) FILTER (stock_quantity < 0),
               sum(units_sold),
               round(100.0 * count(unit_cost) / count(*), 2),
               count(*) FILTER (NOT is_simulated)
        FROM {source}
    """).fetchone()
    expected_sold = con.execute(f"""
        SELECT sum(f.quantity)
        FROM '{wh}/fact_sales.parquet' f JOIN '{wh}/dim_date.parquet' d USING (date_key)
        WHERE d.year * 100 + d.month BETWEEN {FIRST_MONTH} AND {LAST_MONTH}
    """).fetchone()[0]
    con.close()

    report = {
        "rows": row[0], "books": row[1], "months": row[2],
        "units_sold": row[5], "with_cost_pct": row[6],
        "checks_must_be_zero": {
            "duplicate_book_month": row[3],
            "negative_stock": row[4],
            "not_marked_simulated": row[7],
            "units_sold_mismatch": int(row[5]) - int(expected_sold),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    args.report.write_text(text, encoding="utf-8")
    print(text)

    failed = {k: v for k, v in report["checks_must_be_zero"].items() if v != 0}
    if failed:
        temp.unlink()
        sys.exit(f"Kiểm tra thất bại, không ghi kết quả: {failed}")
    temp.replace(target)
    print(f"Xong -> {target}")


if __name__ == "__main__":
    main()
