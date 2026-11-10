"""Build small read-only dashboard datasets; no web interaction scans full facts."""
from pathlib import Path
import shutil
import duckdb
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent/'data';OUT.mkdir(exist_ok=True)
con=duckdb.connect();con.execute("SET memory_limit='2GB'");con.execute('SET threads=2')
con.execute(f"SET temp_directory='{(OUT/'spill').as_posix()}'")
for table in ['fact_sales','dim_books','dim_date']:
    con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{(ROOT/'data/warehouse'/(table+'.parquet')).as_posix()}')")
con.execute(f"""COPY (SELECT d.year,d.month,b.category,f.rating,count(*) AS reviews
 FROM fact_sales f JOIN dim_date d USING(date_key) JOIN dim_books b USING(book_key)
 GROUP BY 1,2,3,4) TO '{(OUT/'review_cube.parquet').as_posix()}' (FORMAT parquet,COMPRESSION zstd)""")
con.execute(f"""COPY (WITH g AS (SELECT book_key,count(*) AS reviews,avg(rating) AS average_rating
 FROM fact_sales GROUP BY 1), r AS (SELECT b.parent_asin,b.title,b.category,g.reviews,g.average_rating,
 row_number() OVER(PARTITION BY b.category ORDER BY g.reviews DESC,b.book_key) AS rk
 FROM g JOIN dim_books b USING(book_key)) SELECT * FROM r WHERE rk<=20)
 TO '{(OUT/'top_books.parquet').as_posix()}' (FORMAT parquet,COMPRESSION zstd)""")
for relative in ['eda_sach/tables/01_tong_quan.csv','eda_sach/tables/07_thieu_thong_tin_danh_muc.csv',
 'rfm_kmeans/cluster_profiles.csv','rfm_kmeans/model_selection.csv','rfm_kmeans/run_metadata.json',
 'phan_tich_thuc_nghiem_colab/bang_ket_qua_144_cau_hinh.csv','tests/data_validation.json']:
    shutil.copy2(ROOT/'results'/relative,OUT/Path(relative).name)
assert con.execute(f"SELECT sum(reviews) FROM '{(OUT/'review_cube.parquet').as_posix()}'").fetchone()[0]==20_342_188
con.close()
for name in ['comparison_extended_verified.csv','materialized_view_costs.csv','validation.json']:
    shutil.copy2(ROOT/'results/postgres_extended_colab'/name,OUT/('extended_'+name))
print('Prepared',OUT)
