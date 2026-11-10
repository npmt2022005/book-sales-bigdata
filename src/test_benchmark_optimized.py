"""Correctness on edge cases that aggregate fingerprints can miss."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('optimized', Path(__file__).with_name('06_benchmark_optimized.py'))
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)


class QueryTests(unittest.TestCase):
    def test_collation_order_does_not_change_row_equality(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            left, right = Path(tmp) / 'left.parquet', Path(tmp) / 'right.parquet'
            rows = pd.DataFrame({'category': ['#Booktok', 'ASINs for HQP', 'Arts & Photography', None],
                                 'book_key': [1, 2, 3, 4], 'n': [2, 3, 4, 5]})
            rows.to_parquet(left, index=False)
            rows.iloc[[2, 1, 3, 0]].to_parquet(right, index=False)
            opt.compare(left, right)
            rows.loc[1, 'book_key'] = 99
            rows.to_parquet(right, index=False)
            with self.assertRaises(AssertionError):
                opt.compare(left, right)

    def test_cross_engine_nulls_ties_dates_and_rfm(self):
        import pandas as pd
        import duckdb
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = {
                'fact_sales': pd.DataFrame([
                    [1, 20230101, 1, 1, 1, 10., 10., 5., 0],
                    [2, 20230101, 1, 2, 1, None, None, 4., 0],
                    [3, 20230103, 2, 3, 1, None, None, 3., 0],
                    [4, 20230201, 3, 3, 1, None, None, 3., 0],
                ], columns=[p.strip().split()[0] for p in opt.base.DDL['fact_sales'].split(',')]),
                'dim_books': pd.DataFrame([
                    [1, 'a', 'A', 'Author', 'Fiction', '', '001', 2020, 'en', 100, 10., 5., 1],
                    [2, 'b', 'B', 'Author', 'Fiction', '', '002', 2020, 'en', 100, None, 4., 1],
                    [3, 'c', 'C', 'Author', None, '', '003', 2020, 'en', 100, None, 3., 2],
                ], columns=[p.strip().split()[0] for p in opt.base.DDL['dim_books'].split(',')]),
                'dim_date': pd.DataFrame([
                    [20230101, '2023-01-01', 1, 1, 1, 1, 2023, True],
                    [20230102, '2023-01-02', 2, 1, 1, 1, 2023, False],
                    [20230103, '2023-01-03', 3, 1, 1, 1, 2023, False],
                    [20230201, '2023-02-01', 1, 5, 2, 1, 2023, False],
                ], columns=[p.strip().split()[0] for p in opt.base.DDL['dim_date'].split(',')]),
            }
            for table, df in data.items():
                df.to_csv(folder / f'{table}.csv', index=False)
                df.to_parquet(folder / f'{table}.parquet', index=False)
            with duckdb.connect() as con:
                for table in data:
                    con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_csv('{folder.as_posix()}/{table}.csv',header=true)")
                for q in opt.base.QUERIES:
                    reference = folder / 'reference.parquet'
                    result = opt.pandas_query('pandas_csv', q, folder, 1)
                    result.to_parquet(reference, index=False)
                    for engine in ['pandas_columns', 'pandas_parquet']:
                        actual = folder / 'actual.parquet'
                        opt.pandas_query(engine, q, folder, 1).to_parquet(actual, index=False)
                        opt.compare(reference, actual)
                    actual = folder / 'sql.parquet'
                    con.execute(opt.sql(q, 1)).fetchdf().to_parquet(actual, index=False)
                    opt.compare(reference, actual)
            q1 = opt.pandas_query('pandas_csv', 'Q1', folder, 1)
            self.assertTrue(pd.isna(q1.loc[q1.month == 2, 'revenue'].iloc[0]))
            q6 = opt.pandas_query('pandas_csv', 'Q6', folder, 1)
            self.assertEqual(q6.loc[q6.customer_key == 2, 'monetary'].iloc[0], 0)
            # An empty customer history must also have matching output columns.
            a = opt.pandas_query('pandas_csv', 'Q3', folder, 999)
            self.assertEqual(len(a), 0)

    def test_row_comparison_detects_same_sum_different_rows(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            left, right = Path(tmp) / 'left.parquet', Path(tmp) / 'right.parquet'
            pd.DataFrame({'value': [1, 4]}).to_parquet(left)
            pd.DataFrame({'value': [2, 3]}).to_parquet(right)
            with self.assertRaises(AssertionError):
                opt.compare(left, right)


if __name__ == '__main__':
    unittest.main()
