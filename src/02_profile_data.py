"""Khảo sát chất lượng dữ liệu Parquet trước khi làm sạch.

Cách chạy, từ thư mục gốc của project:
    .venv\\Scripts\\python src\\02_profile_data.py
Kết quả: results/data_profile.json
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent


def parquet_glob(folder):
    return (Path(folder) / "*.parquet").as_posix().replace("'", "''")


def one_row(con, sql):
    cursor = con.execute(sql)
    names = [c[0] for c in cursor.description]
    return dict(zip(names, cursor.fetchone()))


def null_rates(con, source):
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    terms = ", ".join(f'round(100.0 * (count(*) - count("{c}")) / count(*), 2) AS "{c}"' for c in columns)
    return one_row(con, f"SELECT {terms} FROM {source}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", type=Path, default=ROOT / "data" / "parquet" / "reviews")
    parser.add_argument("--meta", type=Path, default=ROOT / "data" / "parquet" / "meta_books")
    parser.add_argument("--report", type=Path, default=ROOT / "results" / "data_profile.json")
    parser.add_argument("--memory", default="8GB", help="giới hạn RAM của DuckDB")
    args = parser.parse_args()

    reviews = f"read_parquet('{parquet_glob(args.reviews)}')"
    meta = f"read_parquet('{parquet_glob(args.meta)}')"

    with tempfile.TemporaryDirectory(dir=args.report.parent if args.report.parent.exists() else None) as spill:
        con = duckdb.connect()
        con.execute(f"SET memory_limit='{args.memory}'")
        con.execute(f"SET temp_directory='{Path(spill).as_posix()}'")

        profile = {
            "reviews_summary": one_row(con, f"""
                SELECT count(*) AS rows,
                       count(DISTINCT user_id) AS users,
                       count(DISTINCT parent_asin) AS books,
                       round(100.0 * count(*) FILTER (verified_purchase) / count(*), 2) AS verified_pct,
                       min(make_timestamp(timestamp_ms * 1000))::VARCHAR AS first_review,
                       max(make_timestamp(timestamp_ms * 1000))::VARCHAR AS last_review,
                       count(*) FILTER (rating NOT BETWEEN 1 AND 5) AS invalid_rating
                FROM {reviews}"""),
            "reviews_null_pct": null_rates(con, reviews),
            "review_duplicates": one_row(con, f"""
                SELECT count(*) - count(DISTINCT (user_id, parent_asin, timestamp_ms)) AS same_user_book_time,
                       count(*) - count(DISTINCT (user_id, parent_asin)) AS same_user_book
                FROM {reviews}"""),
            "meta_summary": one_row(con, f"""
                SELECT count(*) AS rows,
                       count(DISTINCT parent_asin) AS books,
                       count(DISTINCT category) AS categories,
                       count(*) FILTER (price_usd <= 0) AS price_not_positive,
                       count(*) FILTER (price_usd > 1000) AS price_above_1000,
                       quantile_cont(price_usd, 0.5) AS price_p50,
                       quantile_cont(price_usd, 0.99) AS price_p99,
                       max(price_usd) AS price_max
                FROM {meta}"""),
            "meta_null_pct": null_rates(con, meta),
            "join_coverage": one_row(con, f"""
                SELECT round(100.0 * count(m.parent_asin) / count(*), 2) AS verified_with_book_pct,
                       round(100.0 * count(m.price_usd) / count(*), 2) AS verified_with_price_pct
                FROM (SELECT parent_asin FROM {reviews} WHERE verified_purchase) r
                LEFT JOIN (SELECT parent_asin, any_value(price_usd) AS price_usd
                           FROM {meta} GROUP BY parent_asin) m USING (parent_asin)"""),
        }
        con.close()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(profile, indent=2, ensure_ascii=False, default=str)
    args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
