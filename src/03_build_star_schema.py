"""Làm sạch dữ liệu và tạo lược đồ hình sao bằng DuckDB.

Cách chạy, từ thư mục gốc của project:
    .venv\\Scripts\\python src\\03_build_star_schema.py
Kết quả: data/warehouse/*.parquet và results/build_report.json

Quy tắc làm sạch:
- Sách: mỗi parent_asin giữ một dòng (nhiều lượt đánh giá nhất).
  Giá <= 0 hoặc > MAX_PRICE_USD coi là thiếu.
- Lượt mua: chỉ giữ verified_purchase = true, đủ khóa, điểm 1-5, thời gian hợp lệ.
  Trùng (user_id, parent_asin, timestamp_ms) chỉ giữ một.
  Lượt mua không tìm thấy sách trong danh mục bị loại và được thống kê.
- quantity = 1 là giả định; estimated_revenue = quantity * giá năm 2023.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MAX_PRICE_USD = 1000
MIN_TIMESTAMP_MS = 820_454_400_000    # 1996-01-01 UTC
MAX_TIMESTAMP_MS = 1_704_067_200_000  # 2024-01-01 UTC

TABLES = ["dim_books", "dim_customers", "dim_date", "fact_sales"]


def quoted(path):
    return Path(path).as_posix().replace("'", "''")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", type=Path, default=ROOT / "data" / "parquet" / "reviews")
    parser.add_argument("--meta", type=Path, default=ROOT / "data" / "parquet" / "meta_books")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "warehouse")
    parser.add_argument("--report", type=Path, default=ROOT / "results" / "build_report.json")
    parser.add_argument("--memory", default="8GB", help="giới hạn RAM của DuckDB")
    parser.add_argument("--force", action="store_true", help="ghi đè kết quả đã có")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        sys.exit(f"Đã có {args.output}. Dùng --force nếu muốn ghi đè.")

    temp = args.output.with_name(args.output.name + ".tmp")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)

    # Dùng file tạm thay vì RAM để xử lý được dữ liệu lớn hơn bộ nhớ.
    con = duckdb.connect(str(temp / "build.duckdb"))
    con.execute(f"SET memory_limit='{args.memory}'")
    con.execute(f"SET temp_directory='{quoted(temp / 'spill')}'")
    con.execute("SET preserve_insertion_order=false")

    reviews = f"read_parquet('{quoted(args.reviews / '*.parquet')}')"
    meta = f"read_parquet('{quoted(args.meta / '*.parquet')}')"

    con.execute(f"""
        CREATE TABLE books AS
        WITH ranked AS (
            SELECT *
            FROM {meta}
            WHERE parent_asin IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY parent_asin
                                       ORDER BY rating_number DESC NULLS LAST) = 1
        )
        SELECT row_number() OVER (ORDER BY parent_asin) AS book_key,
               parent_asin,
               nullif(trim(title), '') AS title,
               nullif(trim(author), '') AS author,
               coalesce(nullif(trim(category), ''), 'Unknown') AS category,
               nullif(trim(regexp_replace(publisher_raw, '\\s*[;(].*$', '')), '') AS publisher,
               CASE WHEN length(regexp_replace(isbn_13, '[^0-9]', '', 'g')) = 13
                    THEN regexp_replace(isbn_13, '[^0-9]', '', 'g') END AS isbn_13,
               CASE WHEN try_cast(regexp_extract(publisher_raw, '(\\d{{4}})\\)\\s*$', 1) AS INT) BETWEEN 1400 AND 2024
                    THEN try_cast(regexp_extract(publisher_raw, '(\\d{{4}})\\)\\s*$', 1) AS INT) END AS publish_year,
               language,
               pages,
               CASE WHEN price_usd > 0 AND price_usd <= {MAX_PRICE_USD} THEN price_usd END AS list_price,
               average_rating,
               rating_number
        FROM ranked
    """)

    funnel = dict(zip(
        ["reviews_total", "verified", "verified_and_valid"],
        con.execute(f"""
            SELECT count(*),
                   count(*) FILTER (verified_purchase),
                   count(*) FILTER (verified_purchase
                                    AND user_id IS NOT NULL AND parent_asin IS NOT NULL
                                    AND rating BETWEEN 1 AND 5
                                    AND timestamp_ms >= {MIN_TIMESTAMP_MS}
                                    AND timestamp_ms < {MAX_TIMESTAMP_MS})
            FROM {reviews}
        """).fetchone(),
    ))

    con.execute(f"""
        CREATE TABLE purchases AS
        SELECT user_id, parent_asin, timestamp_ms,
               any_value(rating) AS rating,
               max(helpful_vote) AS helpful_vote
        FROM {reviews}
        WHERE verified_purchase
          AND user_id IS NOT NULL AND parent_asin IS NOT NULL
          AND rating BETWEEN 1 AND 5
          AND timestamp_ms >= {MIN_TIMESTAMP_MS}
          AND timestamp_ms < {MAX_TIMESTAMP_MS}
        GROUP BY user_id, parent_asin, timestamp_ms
    """)
    funnel["after_dedupe"] = con.execute("SELECT count(*) FROM purchases").fetchone()[0]

    con.execute("""
        CREATE TABLE joined AS
        SELECT p.user_id, b.book_key, b.list_price, p.rating, p.helpful_vote,
               make_timestamp(p.timestamp_ms * 1000)::DATE AS sale_date
        FROM purchases p JOIN books b USING (parent_asin)
    """)
    funnel["after_join_with_books"] = con.execute("SELECT count(*) FROM joined").fetchone()[0]
    if funnel["after_join_with_books"] == 0:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
        sys.exit("Không có lượt mua nào khớp với danh mục sách, dừng lại để kiểm tra dữ liệu.")

    con.execute("""
        CREATE TABLE dim_customers AS
        SELECT row_number() OVER (ORDER BY user_id) AS customer_key,
               user_id,
               min(sale_date) AS first_purchase_date,
               max(sale_date) AS last_purchase_date,
               count(*) AS total_purchases
        FROM joined GROUP BY user_id
    """)

    con.execute("""
        CREATE TABLE dim_date AS
        SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
               d::DATE AS date,
               day(d) AS day,
               week(d) AS week,
               month(d) AS month,
               quarter(d) AS quarter,
               year(d) AS year,
               isodow(d) >= 6 AS is_weekend
        FROM (SELECT unnest(generate_series(min(sale_date)::TIMESTAMP,
                                            max(sale_date)::TIMESTAMP,
                                            INTERVAL 1 DAY)) AS d
              FROM joined)
    """)

    con.execute("""
        CREATE TABLE fact_sales AS
        SELECT row_number() OVER () AS sale_id,
               CAST(strftime(j.sale_date, '%Y%m%d') AS INTEGER) AS date_key,
               c.customer_key,
               j.book_key,
               CAST(1 AS TINYINT) AS quantity,
               j.list_price AS price_usd,
               1 * j.list_price AS estimated_revenue,
               j.rating,
               j.helpful_vote
        FROM joined j JOIN dim_customers c USING (user_id)
    """)
    con.execute("ALTER TABLE books RENAME TO dim_books")

    def scalar(sql):
        return con.execute(sql).fetchone()[0]

    checks = {
        "fact_rows_lost_when_adding_customer": funnel["after_join_with_books"] - scalar("SELECT count(*) FROM fact_sales"),
        "duplicate_book_key": scalar("SELECT count(*) - count(DISTINCT book_key) FROM dim_books"),
        "duplicate_parent_asin": scalar("SELECT count(*) - count(DISTINCT parent_asin) FROM dim_books"),
        "duplicate_customer_key": scalar("SELECT count(*) - count(DISTINCT customer_key) FROM dim_customers"),
        "duplicate_date_key": scalar("SELECT count(*) - count(DISTINCT date_key) FROM dim_date"),
        "duplicate_sale_id": scalar("SELECT count(*) - count(DISTINCT sale_id) FROM fact_sales"),
        "orphan_book": scalar("SELECT count(*) FROM fact_sales f ANTI JOIN dim_books b USING (book_key)"),
        "orphan_customer": scalar("SELECT count(*) FROM fact_sales f ANTI JOIN dim_customers c USING (customer_key)"),
        "orphan_date": scalar("SELECT count(*) FROM fact_sales f ANTI JOIN dim_date d USING (date_key)"),
        "customer_total_mismatch": scalar("SELECT count(*) FROM fact_sales") - scalar("SELECT sum(total_purchases) FROM dim_customers"),
    }
    report = {
        "funnel": funnel,
        "row_counts": {t: scalar(f"SELECT count(*) FROM {t}") for t in TABLES},
        "fact_with_price_pct": scalar("SELECT round(100.0 * count(price_usd) / count(*), 2) FROM fact_sales"),
        "estimated_revenue_usd": scalar("SELECT round(sum(estimated_revenue), 2) FROM fact_sales"),
        "date_range": [str(v) for v in con.execute("SELECT min(date), max(date) FROM dim_date").fetchone()],
        "checks_must_be_zero": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

    failed = {name: value for name, value in checks.items() if value != 0}
    if failed:
        con.close()
        shutil.rmtree(temp, ignore_errors=True)
        sys.exit(f"Kiểm tra chất lượng thất bại, không ghi kết quả: {failed}")

    for table in TABLES:
        con.execute(f"COPY {table} TO '{quoted(temp / (table + '.parquet'))}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()

    (temp / "build.duckdb").unlink()
    shutil.rmtree(temp / "spill", ignore_errors=True)
    if args.output.exists():
        shutil.rmtree(args.output)
    temp.rename(args.output)
    print(f"Xong -> {args.output}")


if __name__ == "__main__":
    main()
