"""Offline regression checks for the verified, separately baselined Colab run."""
import json
from pathlib import Path
import unittest
import pandas as pd
import numpy as np

OUT=Path(__file__).resolve().parents[1]/'results/postgres_extended_colab'

class ExtendedResultTests(unittest.TestCase):
    def test_run_manifest(self):
        manifest=json.loads((OUT/'validation.json').read_text())
        self.assertEqual(manifest['verified_runs'],400)
        self.assertEqual(manifest['refresh_operations_verified'],40)
        self.assertEqual(manifest['total_across_two_separate_sessions'],1120)
        self.assertTrue(manifest['all_query_matches'])
    def test_each_speedup_uses_new_baseline(self):
        frame=pd.read_csv(OUT/'comparison_extended_verified.csv')
        self.assertEqual(len(frame),80)
        self.assertFalse(frame.duplicated(['size','config','query']).any())
        self.assertTrue((frame.runs==5).all())
        baseline=frame[frame.config=='postgres_4mb'][['size','query','median_s']].rename(columns={'median_s':'base'})
        merged=frame.merge(baseline,on=['size','query'],validate='many_to_one')
        np.testing.assert_allclose(merged.speedup_vs_4mb,merged.base/merged.median_s,rtol=1e-10)
        mv=frame[frame.config=='materialized_4mb']
        self.assertEqual(set(mv['query']),{'Q1','Q5'})
        self.assertEqual(len(mv),8)
    def test_refresh_costs_and_evidence(self):
        costs=pd.read_csv(OUT/'materialized_view_costs.csv')
        self.assertEqual(len(costs),8)
        self.assertFalse(costs.duplicated(['size','view']).any())
        self.assertTrue((costs[['create_seconds','refresh_median_s','bytes','rows']]>0).all().all())
        for size in ['1m','5m','10m','full']:
            item=json.loads((OUT/'evidence'/f'{size}_summary.json').read_text())['sizes'][size]
            self.assertEqual(len(item['runs']),100)
            for values in item['materialized_views'].values():
                self.assertTrue(values['refresh_matches_reference'])
                self.assertEqual(len(values['refresh_seconds']),5)
                self.assertAlmostEqual(float(np.median(values['refresh_seconds'])),values['refresh_median_s'])

if __name__=='__main__':unittest.main()
