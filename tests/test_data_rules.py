"""Negative fixtures prove validation detects corruption, not just happy paths."""
import importlib.util
from pathlib import Path
import unittest
import duckdb
import numpy as np
import pandas as pd
import joblib

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('validator',ROOT/'src/10_validate_data.py')
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)

class DataRuleTests(unittest.TestCase):
    def setUp(self):self.con=duckdb.connect();self.rules=dict(validator.checks()+validator.rfm_checks())
    def tearDown(self):self.con.close()
    def value(self,name):return self.con.execute(self.rules[name]).fetchone()[0]
    def test_duplicate_and_null_primary_key(self):
        self.con.execute('CREATE TABLE dim_books(book_key BIGINT)');self.con.execute('INSERT INTO dim_books VALUES (1),(2)')
        self.assertEqual(self.value('dim_books.book_key.unique_nonnull'),0)
        self.con.execute('INSERT INTO dim_books VALUES (1),(NULL)')
        self.assertEqual(self.value('dim_books.book_key.unique_nonnull'),2)
    def test_orphan_including_null_fk(self):
        self.con.execute('CREATE TABLE dim_books AS SELECT 1 AS book_key')
        self.con.execute('CREATE TABLE fact_sales AS SELECT 1 AS book_key')
        self.assertEqual(self.value('fact_sales.fk_book_key'),0)
        self.con.execute('INSERT INTO fact_sales VALUES (2),(NULL)')
        self.assertEqual(self.value('fact_sales.fk_book_key'),2)
    def test_ratings_invalid_and_missing(self):
        self.con.execute('CREATE TABLE fact_sales(rating DOUBLE)');self.con.execute('INSERT INTO fact_sales VALUES (1),(5)')
        self.assertEqual(self.value('fact_sales.rating_range'),0)
        self.con.execute("INSERT INTO fact_sales VALUES (0),(6),(NULL),('NaN')")
        self.assertEqual(self.value('fact_sales.rating_range'),4)
    def test_missing_revenue_is_not_zero(self):
        self.con.execute('CREATE TABLE fact_sales(price_usd DOUBLE,estimated_revenue DOUBLE,quantity INT)')
        self.con.execute('INSERT INTO fact_sales VALUES (10,10,1),(NULL,NULL,1)')
        self.assertEqual(self.value('fact_sales.revenue_formula'),0)
        self.con.execute('INSERT INTO fact_sales VALUES (NULL,0,1),(10,12,1)')
        self.assertEqual(self.value('fact_sales.revenue_formula'),2)
    def test_simulation_flag_requires_true(self):
        self.con.execute('CREATE TABLE fact_inventory(is_simulated BOOLEAN)')
        self.con.execute('INSERT INTO fact_inventory VALUES (true),(false),(NULL)')
        self.assertEqual(self.value('fact_inventory.simulation_flag'),2)
    def test_cluster_exclusion(self):
        self.con.execute('CREATE TABLE assignments(eligible BOOLEAN,cluster INT)')
        self.con.execute('INSERT INTO assignments VALUES (true,0),(false,-1)')
        self.assertEqual(self.value('assignments.exclusion'),0)
        self.con.execute('INSERT INTO assignments VALUES (true,-1),(false,1),(true,NULL)')
        self.assertEqual(self.value('assignments.exclusion'),3)
    def test_model_roundtrip_matches_saved_training_labels(self):
        from threadpoolctl import threadpool_limits
        folder=ROOT/'results/rfm_kmeans'
        if not (folder/'model.joblib').exists() or not (folder/'training_sample_with_clusters.parquet').exists():
            self.skipTest('Full RFM/model artifacts are intentionally excluded from Git; generate them with src/09_rfm_kmeans.py.')
        model=joblib.load(folder/'model.joblib')
        frame=pd.read_parquet(folder/'training_sample_with_clusters.parquet')
        with threadpool_limits(limits=2):
            predicted=model['model'].predict(model['scaler'].transform(np.log1p(frame[model['features']].to_numpy(float))))
        np.testing.assert_array_equal(predicted,frame.cluster.to_numpy())

if __name__=='__main__':unittest.main()
