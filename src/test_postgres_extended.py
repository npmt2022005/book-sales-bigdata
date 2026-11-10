"""Integration test: NULL/month boundaries, work_mem sessions and MV refresh."""
import importlib.util
import tempfile
import unittest
import uuid
from pathlib import Path
import pandas as pd
import psycopg

spec=importlib.util.spec_from_file_location('extended',Path(__file__).with_name('13_benchmark_postgres_extended.py'))
ext=importlib.util.module_from_spec(spec);spec.loader.exec_module(ext)

class MaterializedViewTests(unittest.TestCase):
    def test_nulls_gaps_and_refresh(self):
        token=uuid.uuid4().hex[:10]
        size='fixture_'+token;baseline='s_'+size;schema='test_mv_'+token
        with psycopg.connect(ext.opt.base.PG_DSN,autocommit=True) as con:
            try:
                con.execute(f'CREATE SCHEMA {baseline}')
                con.execute(f'CREATE TABLE {baseline}.fact_sales(date_key INT,estimated_revenue DOUBLE PRECISION)')
                con.execute(f'CREATE TABLE {baseline}.dim_date(date_key INT,date DATE,year INT,month INT)')
                con.execute(f'CREATE TABLE {baseline}.dim_books(book_key INT)')
                con.execute(f'CREATE TABLE {baseline}.dim_customers(customer_key INT)')
                con.execute(f"INSERT INTO {baseline}.dim_date VALUES (20230101,'2023-01-01',2023,1),(20230102,'2023-01-02',2023,1),(20230103,'2023-01-03',2023,1),(20230201,'2023-02-01',2023,2)")
                con.execute(f'INSERT INTO {baseline}.fact_sales VALUES (20230101,10),(20230101,20),(20230102,NULL),(20230201,NULL)')
                info=ext.setup(con,schema,size,30)
                self.assertEqual(info['mv_monthly']['rows'],2)
                self.assertEqual(info['mv_daily']['rows'],3)
                def frame(q,mv):
                    with con.cursor() as cur:
                        cur.execute(ext.query_sql(q,1,mv))
                        return pd.DataFrame(cur.fetchall(),columns=[c.name for c in cur.description])
                with tempfile.TemporaryDirectory() as tmp:
                    a,b=Path(tmp)/'a.parquet',Path(tmp)/'b.parquet'
                    for q in ['Q1','Q5']:
                        frame(q,False).to_parquet(a,index=False);frame(q,True).to_parquet(b,index=False)
                        ext.opt.compare(a,b)
                    self.assertTrue(pd.isna(frame('Q1',True).iloc[1].revenue))
                    # A new source row does not silently update an MV.
                    con.execute(f'INSERT INTO {baseline}.fact_sales VALUES (20230103,7)')
                    self.assertEqual(frame('Q1',True).iloc[0].revenue,30)
                    for name in ['mv_monthly','mv_daily']:con.execute(f'REFRESH MATERIALIZED VIEW {name}')
                    self.assertEqual(frame('Q1',True).iloc[0].revenue,37)
                    for q in ['Q1','Q5']:
                        frame(q,False).to_parquet(a,index=False);frame(q,True).to_parquet(b,index=False)
                        ext.opt.compare(a,b)
                ext.configure(con,schema,64,30)
                self.assertEqual(con.execute('SHOW work_mem').fetchone()[0],'64MB')
                ext.configure(con,schema,4,30)
                self.assertEqual(con.execute('SHOW work_mem').fetchone()[0],'4MB')
            finally:
                # Only the two randomly named schemas created by this test are removed.
                con.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
                con.execute(f'DROP SCHEMA IF EXISTS {baseline} CASCADE')

if __name__=='__main__':unittest.main()
