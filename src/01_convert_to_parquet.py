"""Chuyển file JSONL thô của Amazon Reviews 2023 sang Parquet.

Đọc theo luồng nên không nạp toàn bộ vào RAM.
Bỏ các cột nặng (nội dung đánh giá, ảnh, video, mô tả).

Cách chạy, từ thư mục gốc của project:
    .venv\\Scripts\\python src\\01_convert_to_parquet.py reviews
    .venv\\Scripts\\python src\\01_convert_to_parquet.py meta
Tùy chọn: --limit N để chạy thử, --force để ghi đè kết quả cũ.
"""
import argparse
import gzip
import json
import re
import shutil
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
BATCH_SIZE = 500_000

REVIEW_SCHEMA = pa.schema([
    ("parent_asin", pa.string()),
    ("asin", pa.string()),
    ("user_id", pa.string()),
    ("timestamp_ms", pa.int64()),
    ("rating", pa.float32()),
    ("helpful_vote", pa.int32()),
    ("verified_purchase", pa.bool_()),
])

META_SCHEMA = pa.schema([
    ("parent_asin", pa.string()),
    ("title", pa.string()),
    ("author", pa.string()),
    ("main_category", pa.string()),
    ("category", pa.string()),
    ("category_path", pa.string()),
    ("publisher_raw", pa.string()),
    ("language", pa.string()),
    ("isbn_13", pa.string()),
    ("pages", pa.int32()),
    ("price_usd", pa.float64()),
    ("price_raw", pa.string()),
    ("average_rating", pa.float32()),
    ("rating_number", pa.int32()),
])

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
PAGES = re.compile(r"(\d[\d,]*)\s*pages?", re.IGNORECASE)
INT32_MAX = 2_147_483_647


def to_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = NUMBER.search(str(value))
    return float(match.group().replace(",", "")) if match else None


def to_int32(value):
    number = to_float(value)
    if number is None or not 0 <= number <= INT32_MAX:
        return None
    return int(number)


def to_text(value):
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)


def parse_review(rec):
    return {
        "parent_asin": to_text(rec.get("parent_asin")),
        "asin": to_text(rec.get("asin")),
        "user_id": to_text(rec.get("user_id")),
        "timestamp_ms": int(rec["timestamp"]) if rec.get("timestamp") is not None else None,
        "rating": to_float(rec.get("rating")),
        "helpful_vote": to_int32(rec.get("helpful_vote")),
        "verified_purchase": rec.get("verified_purchase") if isinstance(rec.get("verified_purchase"), bool) else None,
    }


def parse_pages(details):
    for key in ("Print length", "Paperback", "Hardcover", "Mass Market Paperback", "Spiral-bound"):
        match = PAGES.search(str(details.get(key, "")))
        if match:
            return to_int32(match.group(1))
    return None


def parse_meta(rec):
    details = rec.get("details") if isinstance(rec.get("details"), dict) else {}
    author = rec.get("author") if isinstance(rec.get("author"), dict) else {}
    categories = rec.get("categories") if isinstance(rec.get("categories"), list) else []
    categories = [str(c) for c in categories]
    raw_price = rec.get("price")
    return {
        "parent_asin": to_text(rec.get("parent_asin")),
        "title": to_text(rec.get("title")),
        "author": to_text(author.get("name")),
        "main_category": to_text(rec.get("main_category")),
        # categories[0] thường là "Books", cấp thực sự có ý nghĩa là cấp kế tiếp.
        "category": categories[1] if len(categories) > 1 else None,
        "category_path": " > ".join(categories) or None,
        "publisher_raw": to_text(details.get("Publisher")),
        "language": to_text(details.get("Language")),
        "isbn_13": to_text(details.get("ISBN 13")),
        "pages": parse_pages(details),
        "price_usd": to_float(raw_price),
        "price_raw": to_text(raw_price),
        "average_rating": to_float(rec.get("average_rating")),
        "rating_number": to_int32(rec.get("rating_number")),
    }


JOBS = {
    "reviews": ("Books.jsonl", parse_review, REVIEW_SCHEMA, "reviews"),
    "meta": ("meta_Books.jsonl", parse_meta, META_SCHEMA, "meta_books"),
}


def open_lines(path):
    """Đọc được cả file .jsonl và .jsonl.gz."""
    opener = gzip.open if path.suffix == ".gz" else open
    return opener(path, "rt", encoding="utf-8")


def write_part(rows, schema, out_dir, part):
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, out_dir / f"part-{part:05d}.parquet", compression="zstd")


def main():
    # Console Windows mặc định không in được tiếng Việt.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=JOBS)
    parser.add_argument("--input", type=Path, help="mặc định: data/raw/amazon/<file của job>")
    parser.add_argument("--output", type=Path, help="mặc định: data/parquet/<job>")
    parser.add_argument("--limit", type=int, help="chỉ đọc N dòng đầu để chạy thử")
    parser.add_argument("--force", action="store_true", help="ghi đè thư mục kết quả đã có")
    args = parser.parse_args()

    file_name, parse, schema, out_name = JOBS[args.job]
    source = args.input or ROOT / "data" / "raw" / "amazon" / file_name
    target = args.output or ROOT / "data" / "parquet" / out_name
    temp = target.with_name(target.name + ".tmp")

    if target.exists() and not args.force:
        sys.exit(f"Đã có {target}. Dùng --force nếu muốn ghi đè.")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)

    started = time.perf_counter()
    rows, part, total, bad = [], 0, 0, 0
    with open_lines(source) as lines:
        for line in lines:
            if args.limit is not None and total + bad >= args.limit:
                break
            try:
                rows.append(parse(json.loads(line)))
                total += 1
            except (ValueError, TypeError, KeyError, OverflowError):
                bad += 1
                continue
            if len(rows) >= BATCH_SIZE:
                write_part(rows, schema, temp, part)
                part += 1
                rows = []
                print(f"{total:,} dòng, {time.perf_counter() - started:.0f} giây", flush=True)
    if rows:
        write_part(rows, schema, temp, part)

    if target.exists():
        shutil.rmtree(target)
    temp.rename(target)
    print(f"Xong {args.job}: {total:,} dòng hợp lệ, {bad:,} dòng lỗi, "
          f"{time.perf_counter() - started:.0f} giây -> {target}")


if __name__ == "__main__":
    main()
