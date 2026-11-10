"""Đo hệ thống mốc so sánh CHƯA TỐI ƯU trên 6 truy vấn Q1-Q6.

Hai hệ thống mốc:
- pandas_csv: mỗi lần chạy đọc lại CSV, đủ mọi cột, kiểu dữ liệu mặc định.
- postgres: cấu hình mặc định, không có khóa chính, index hay partition.

Cách chạy, từ thư mục gốc (server PostgreSQL phải đang chạy, xem pg_local.py):
    .venv\\Scripts\\python src\\05_benchmark_baseline.py --sizes 1m 10m full --repeats 5

Cách đo:
- Thứ tự truy vấn được xáo ngẫu nhiên trong mỗi vòng, có seed cố định.
- PostgreSQL chạy một lần khởi động trước khi đo. Vì vậy số đo là trạng thái cache nóng.
- PostgreSQL đo thời gian thực thi trên server, không tính truyền toàn bộ kết quả về client.
- pandas được theo dõi RAM đỉnh và bị dừng nếu vượt giới hạn, để không ảnh hưởng ứng dụng khác.
- Mỗi truy vấn tạo một "dấu kết quả" để đối chiếu giữa hai hệ thống.
"""
import argparse
import os
import csv
import json
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE = ROOT / "data" / "warehouse"
BENCH = ROOT / "data" / "benchmark"
SEED = 20261109
SIZES = {"1m": 1_000_000, "5m": 5_000_000, "10m": 10_000_000, "full": None}
QUERIES = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
TABLES = ["dim_books", "dim_customers", "dim_date", "fact_sales"]
PG_DSN = os.environ.get('BOOK_SALES_PG_DSN', "host=127.0.0.1 port=55432 user=postgres dbname=book_sales")

DDL = {
    "dim_books": """book_key BIGINT, parent_asin TEXT, title TEXT, author TEXT, category TEXT, publisher TEXT,
                    isbn_13 TEXT, publish_year INT, language TEXT, pages INT, list_price DOUBLE PRECISION,
                    average_rating REAL, rating_number INT""",
    "dim_customers": """customer_key BIGINT, user_id TEXT, first_purchase_date DATE, last_purchase_date DATE,
                        total_purchases BIGINT""",
    "dim_date": """date_key INT, date DATE, day INT, week INT, month INT, quarter INT, year INT, is_weekend BOOLEAN""",
    "fact_sales": """sale_id BIGINT, date_key INT, customer_key BIGINT, book_key BIGINT, quantity SMALLINT,
                     price_usd DOUBLE PRECISION, estimated_revenue DOUBLE PRECISION, rating REAL, helpful_vote INT""",
}


def sql_for(query, customer):
    return {
        "Q1": """SELECT count(*), sum(r) FROM (
                     SELECT d.year, d.month, sum(f.estimated_revenue) AS r
                     FROM fact_sales f JOIN dim_date d USING (date_key) GROUP BY 1, 2) s""",
        "Q2": """WITH c AS (SELECT book_key, count(*) AS n FROM fact_sales GROUP BY 1),
                      r AS (SELECT c.book_key, c.n,
                                   row_number() OVER (PARTITION BY b.category ORDER BY c.n DESC, c.book_key) AS rk
                            FROM c JOIN dim_books b USING (book_key))
                 SELECT count(*), sum(n), sum(book_key) FROM r WHERE rk <= 10""",
        "Q3": f"""SELECT count(*), sum(sale_id) FROM (
                      SELECT f.sale_id, b.title, d.date
                      FROM fact_sales f JOIN dim_books b USING (book_key) JOIN dim_date d USING (date_key)
                      WHERE f.customer_key = {int(customer)} ORDER BY f.sale_id) s""",
        "Q4": """SELECT count(*), sum(n) FROM (
                     SELECT d.year, count(DISTINCT f.customer_key) AS n
                     FROM fact_sales f JOIN dim_date d USING (date_key) GROUP BY 1) s""",
        "Q5": """WITH daily AS (SELECT date_key, sum(estimated_revenue) AS r FROM fact_sales GROUP BY 1),
                      s AS (SELECT avg(coalesce(x.r, 0)) OVER (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS a
                            FROM dim_date d LEFT JOIN daily x USING (date_key))
                 SELECT count(*), sum(a) FROM s""",
        "Q6": """WITH m AS (SELECT f.customer_key, d.date, f.estimated_revenue
                            FROM fact_sales f JOIN dim_date d USING (date_key)),
                      g AS (SELECT customer_key, max(date) AS last_date, count(*) AS frequency,
                                   coalesce(sum(estimated_revenue), 0) AS monetary
                            FROM m GROUP BY 1)
                 SELECT count(*), sum(frequency), sum(monetary),
                        sum((SELECT max(date) FROM m) - last_date) FROM g""",
    }[query]


def run_pandas(query, folder, customer):
    """Cách làm thông thường, chưa tối ưu: đọc lại CSV đầy đủ mỗi lần chạy."""
    import pandas as pd

    def load(name, **options):
        return pd.read_csv(folder / f"{name}.csv", **options)

    fact = load("fact_sales")
    if query == "Q1":
        merged = fact.merge(load("dim_date"), on="date_key")
        result = merged.groupby(["year", "month"])["estimated_revenue"].sum()
        return [len(result), float(result.sum())]
    if query == "Q2":
        counts = fact.groupby("book_key").size().rename("n").reset_index()
        merged = counts.merge(load("dim_books", dtype={"isbn_13": str}), on="book_key")
        merged = merged.sort_values(["category", "n", "book_key"], ascending=[True, False, True])
        top = merged.groupby("category", dropna=False).head(10)
        return [len(top), int(top["n"].sum()), int(top["book_key"].sum())]
    if query == "Q3":
        rows = fact[fact["customer_key"] == customer]
        rows = rows.merge(load("dim_books", dtype={"isbn_13": str}), on="book_key")
        rows = rows.merge(load("dim_date"), on="date_key").sort_values("sale_id")
        return [len(rows), int(rows["sale_id"].sum())]
    if query == "Q4":
        merged = fact.merge(load("dim_date"), on="date_key")
        result = merged.groupby("year")["customer_key"].nunique()
        return [len(result), int(result.sum())]
    dates = load("dim_date", parse_dates=["date"])
    merged = fact.merge(dates, on="date_key")
    if query == "Q5":
        daily = merged.groupby("date")["estimated_revenue"].sum()
        daily = daily.reindex(dates.sort_values("date")["date"], fill_value=0)
        rolling = daily.rolling(7, min_periods=1).mean()
        return [len(rolling), float(rolling.sum())]
    if query == "Q6":
        grouped = merged.groupby("customer_key").agg(
            last_date=("date", "max"), frequency=("sale_id", "count"), monetary=("estimated_revenue", "sum"))
        recency = (merged["date"].max() - grouped["last_date"]).dt.days
        return [len(grouped), int(grouped["frequency"].sum()), float(grouped["monetary"].sum()), int(recency.sum())]
    raise ValueError(query)


def worker(query, folder, customer):
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.perf_counter()
    fingerprint = run_pandas(query, Path(folder), int(customer))
    print(json.dumps({"seconds": time.perf_counter() - started, "fingerprint": fingerprint}))


def prepare(label):
    """Xuất CSV cho một quy mô. Bảng chiều chỉ giữ các dòng được bảng sự kiện dùng tới."""
    import duckdb

    target = BENCH / label
    if (target / "params.json").exists():
        return target
    temp = BENCH / (label + ".tmp")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    wh = WAREHOUSE.as_posix()
    out = temp.as_posix()
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute(f"SET temp_directory='{(BENCH / 'spill').as_posix()}'")
    limit = SIZES[label]
    if limit is None:
        con.execute(f"CREATE VIEW fact AS SELECT * FROM '{wh}/fact_sales.parquet'")
    else:
        con.execute(f"""CREATE TABLE fact AS SELECT * FROM '{wh}/fact_sales.parquet'
                        ORDER BY hash(sale_id, {SEED}), sale_id LIMIT {limit}""")
    copies = {
        "fact_sales": "SELECT * FROM fact",
        "dim_date": f"SELECT * FROM '{wh}/dim_date.parquet'",
        "dim_books": f"SELECT * FROM '{wh}/dim_books.parquet' b SEMI JOIN (SELECT DISTINCT book_key FROM fact) f USING (book_key)",
        "dim_customers": f"SELECT * FROM '{wh}/dim_customers.parquet' c SEMI JOIN (SELECT DISTINCT customer_key FROM fact) f USING (customer_key)",
    }
    for table, query in copies.items():
        con.execute(f"COPY ({query}) TO '{out}/{table}.csv' (FORMAT csv, HEADER)")
    customer, purchases = con.execute(
        "SELECT customer_key, count(*) n FROM fact GROUP BY 1 ORDER BY n DESC, customer_key LIMIT 1").fetchone()
    rows = {t: con.execute(f"SELECT count(*) FROM read_csv('{out}/{t}.csv', all_varchar=true, quote='\"')").fetchone()[0]
            for t in TABLES}
    con.close()
    params = {"customer_key": int(customer), "customer_purchases": int(purchases), "rows": rows,
              "csv_mb": {t: round((temp / f"{t}.csv").stat().st_size / 1e6, 1) for t in TABLES}}
    (temp / "params.json").write_text(json.dumps(params, indent=2), encoding="utf-8")
    if target.exists():
        shutil.rmtree(target)
    temp.rename(target)
    return target


def load_postgres(label, folder, params):
    import psycopg

    schema = f"s_{label}"
    with psycopg.connect(PG_DSN, autocommit=True) as con:
        done = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=%s", (schema,)).fetchone()[0]
        if done == len(TABLES):
            info_path = folder / "postgres_load.json"
            if info_path.exists():
                return json.loads(info_path.read_text(encoding="utf-8"))
        con.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        con.execute(f"CREATE SCHEMA {schema}")
        seconds = {}
        for table in TABLES:
            con.execute(f"CREATE TABLE {schema}.{table} ({DDL[table]})")
            started = time.perf_counter()
            with con.cursor() as cur, open(folder / f"{table}.csv", "rb") as source:
                with cur.copy(f"COPY {schema}.{table} FROM STDIN (FORMAT csv, HEADER true, NULL '')") as copy:
                    while chunk := source.read(1024 * 1024):
                        copy.write(chunk)
            seconds[table] = round(time.perf_counter() - started, 3)
            count = con.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
            if count != params["rows"][table]:
                sys.exit(f"Nạp thiếu {table}: {count} so với {params['rows'][table]}")
            con.execute(f"ANALYZE {schema}.{table}")
        size = {t: con.execute("SELECT pg_total_relation_size(%s)", (f"{schema}.{t}",)).fetchone()[0] for t in TABLES}
    info = {"copy_seconds": seconds, "table_mb": {t: round(v / 1e6, 1) for t, v in size.items()}}
    (folder / "postgres_load.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def run_postgres(label, query, customer, timeout):
    import psycopg

    with psycopg.connect(PG_DSN, autocommit=True) as con:
        con.execute(f"SET search_path TO s_{label}")
        con.execute(f"SET statement_timeout = {int(timeout * 1000)}")
        started = time.perf_counter()
        try:
            row = con.execute(sql_for(query, customer)).fetchone()
        except psycopg.errors.QueryCanceled:
            return {"status": "timeout", "seconds": time.perf_counter() - started}
        seconds = time.perf_counter() - started
    return {"status": "ok", "seconds": seconds, "fingerprint": [float(v) if v is not None else None for v in row]}


def run_pandas_guarded(query, folder, customer, args):
    """Chạy pandas trong tiến trình con, dừng nếu vượt RAM, thời gian hoặc máy sắp hết bộ nhớ."""
    import psutil

    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--worker", query, str(folder), str(customer)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
    )
    handle = psutil.Process(process.pid)

    def family():
        # Python trong venv trên Windows là tiến trình trung gian, tiến trình thật là tiến trình con của nó.
        try:
            return [handle] + handle.children(recursive=True)
        except psutil.Error:
            return []

    def total_rss(processes):
        total = 0
        for item in processes:
            try:
                total += item.memory_info().rss
            except psutil.Error:
                pass
        return total

    started = time.perf_counter()
    peak, status = 0, "ok"
    members = []
    while process.poll() is None:
        members = family() or members
        peak = max(peak, total_rss(members))
        if peak > args.max_rss_gb * 1e9:
            status = "exceeded_ram_limit"
        elif psutil.virtual_memory().available < args.min_free_gb * 1e9:
            status = "stopped_low_system_memory"
        elif time.perf_counter() - started > args.timeout:
            status = "timeout"
        if status != "ok":
            for item in reversed(members):
                try:
                    item.kill()
                except psutil.Error:
                    pass
            process.kill()
            break
        time.sleep(0.05)
    out, err = process.communicate()
    result = {"status": status, "peak_gb": round(peak / 1e9, 3), "seconds": time.perf_counter() - started}
    if status == "ok":
        if process.returncode != 0:
            result["status"] = "error"
            result["error"] = err.strip()[-600:]
        else:
            result.update(json.loads(out.strip().splitlines()[-1]))
    return result


def same(left, right):
    if left is None or right is None or len(left) != len(right):
        return False
    return all(abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(a))) for a, b in zip(left, right))


def machine_info():
    import psutil

    return {
        "cpu": platform.processor(), "logical_cpus": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "available_ram_gb_at_start": round(psutil.virtual_memory().available / 1e9, 1),
        "cpu_percent_at_start": psutil.cpu_percent(interval=1),
        "python": platform.python_version(), "os": platform.platform(),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(*sys.argv[2:5])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", choices=SIZES, default=["1m"])
    parser.add_argument("--engines", nargs="+", choices=["pandas_csv", "postgres"], default=["pandas_csv", "postgres"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--tag", default="baseline")
    parser.add_argument("--max-rss-gb", type=float, default=10)
    parser.add_argument("--min-free-gb", type=float, default=1.5)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()

    out_dir = ROOT / "results" / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"machine": machine_info(), "sizes": {}}
    rng = random.Random(SEED)
    with open(out_dir / "runs.csv", "w", newline="", encoding="utf-8") as raw:
        writer = csv.writer(raw)
        writer.writerow(["size", "engine", "query", "repeat", "status", "seconds", "peak_gb", "fingerprint"])
        for label in args.sizes:
            folder = prepare(label)
            params = json.loads((folder / "params.json").read_text(encoding="utf-8"))
            customer = params["customer_key"]
            info = {"params": params}
            if "postgres" in args.engines:
                info["postgres_load"] = load_postgres(label, folder, params)
                for query in QUERIES:  # lượt khởi động, không tính vào kết quả
                    run_postgres(label, query, customer, args.timeout)
            stopped, prints, seconds, statuses, peaks = set(), {}, {}, {}, {}
            for repeat in range(1, args.repeats + 1):
                plan = [(e, q) for e in args.engines for q in QUERIES]
                rng.shuffle(plan)
                for engine, query in plan:
                    key = (engine, query)
                    if key in stopped:
                        continue
                    if engine == "postgres":
                        result = run_postgres(label, query, customer, args.timeout)
                    else:
                        result = run_pandas_guarded(query, folder, customer, args)
                    status = result["status"]
                    statuses[key] = status
                    writer.writerow([label, engine, query, repeat, status, round(result["seconds"], 4),
                                     result.get("peak_gb", ""), json.dumps(result.get("fingerprint"))])
                    raw.flush()
                    print(label, engine, query, repeat, status, round(result["seconds"], 2), result.get("peak_gb", ""),
                          result.get("error", ""), flush=True)
                    if status != "ok":
                        stopped.add(key)
                        continue
                    seconds.setdefault(key, []).append(result["seconds"])
                    prints.setdefault(key, result["fingerprint"])
                    if "peak_gb" in result:
                        peaks[key] = max(peaks.get(key, 0), result["peak_gb"])
            table = {}
            for engine, query in [(e, q) for e in args.engines for q in QUERIES]:
                key = (engine, query)
                values = seconds.get(key, [])
                table[f"{engine}/{query}"] = {
                    "status": statuses.get(key), "runs": len(values),
                    "median_s": round(statistics.median(values), 4) if values else None,
                    "min_s": round(min(values), 4) if values else None,
                    "max_s": round(max(values), 4) if values else None,
                    "peak_gb": peaks.get(key),
                }
            info["results"] = table
            if len(args.engines) == 2:
                info["fingerprints_match"] = {
                    q: same(prints.get(("pandas_csv", q)), prints.get(("postgres", q)))
                    if ("pandas_csv", q) in prints and ("postgres", q) in prints else None
                    for q in QUERIES
                }
            summary["sizes"][label] = info
            (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v.get("fingerprints_match") for k, v in summary["sizes"].items()}, indent=2))
    print(f"Xong -> {out_dir}")


if __name__ == "__main__":
    main()
