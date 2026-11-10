import unittest
from pathlib import Path
import pandas as pd
import duckdb
from streamlit.testing.v1 import AppTest

HERE=Path(__file__).resolve().parents[1]

class DashboardTests(unittest.TestCase):
    def app(self,page='Hiệu năng'):
        at=AppTest.from_file(str(HERE/'app.py'),default_timeout=40).run()
        if page!='Hiệu năng':at.sidebar.radio[0].set_value(page).run()
        self.assertEqual(len(at.exception),0,[str(e.value) for e in at.exception])
        return at
    def test_performance_filters_and_speedup(self):
        at=self.app()
        self.assertEqual(at.metric[0].value,'15.63 giây')
        self.assertEqual(at.metric[2].value,'13.87×')
        at.selectbox[0].set_value('1m').run()
        at.selectbox[1].set_value('Q6').run()
        at.multiselect[0].set_value([]).run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('Chọn ít nhất' in item.value for item in at.info))
    def test_overview(self):
        at=self.app('Tổng quan')
        self.assertEqual(at.metric[0].value,'20,342,188')
        self.assertEqual(len(at.success),1)
    def test_extended_experiment_uses_new_baseline_and_costs(self):
        at=self.app()
        next(r for r in at.radio if r.label=='Đợt thực nghiệm').set_value('PostgreSQL bổ sung · 400 lượt').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.metric[0].value,'8.933 giây')
        self.assertEqual(at.metric[2].value,'331.24×')
        at.selectbox[1].set_value('Q2').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.metric[0].value,'41.839 giây')
        self.assertTrue(any('chỉ được đo' in x.value for x in at.info))
        at.checkbox[0].set_value(True).run()
        at.selectbox[0].set_value('1m').run()
        self.assertEqual(len(at.exception),0)
    def test_eda_filters_include_apostrophes_and_empty_period(self):
        at=self.app('Khám phá sách')
        at.selectbox[0].set_value("Children's Books").run()
        at.slider[0].set_value((2022,2023)).run()
        self.assertEqual(len(at.exception),0)
        self.assertGreater(int(at.metric[0].value.replace(',','')),0)
        at.slider[0].set_value((1997,1997)).run()
        self.assertEqual(len(at.exception),0)
    def test_cluster_selection(self):
        at=self.app('RFM & phân cụm')
        self.assertEqual(at.metric[0].value,'2')
        at.selectbox[0].set_value(1).run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.metric[4].value,'1 lượt')
    def test_preaggregated_data_and_benchmark_contract(self):
        with duckdb.connect() as con:
            row=con.execute('SELECT sum(reviews),min(year),max(year) FROM read_parquet(?)',[str(HERE/'data/review_cube.parquet')]).fetchone()
        self.assertEqual(row,(20342188,1997,2023))
        bench=pd.read_csv(HERE/'data/bang_ket_qua_144_cau_hinh.csv')
        self.assertEqual(len(bench),144)
        self.assertTrue((bench.runs==5).all())
        self.assertEqual(int(pd.read_csv(HERE/'data/cluster_profiles.csv').users.sum()),8353809)

if __name__=='__main__':unittest.main()
