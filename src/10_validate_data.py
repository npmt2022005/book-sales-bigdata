"""Read-only full-data validation with JSON evidence and nonzero failure exit."""
import argparse
import json
import time
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]

def checks():
    result=[]
    def add(name,sql):result.append((name,sql))
    for table,key in [('dim_books','book_key'),('dim_books','parent_asin'),('dim_customers','customer_key'),('dim_customers','user_id'),('dim_date','date_key'),('fact_sales','sale_id')]:
        add(f'{table}.{key}.unique_nonnull',f'SELECT count(*)-count(DISTINCT {key}) FROM {table}')
    for table,key in [('dim_books','book_key'),('dim_customers','customer_key'),('dim_date','date_key')]:
        add('fact_sales.fk_'+key,f'SELECT count(*) FROM fact_sales f ANTI JOIN {table} d USING({key})')
    add('fact_sales.required_keys','SELECT count(*) FROM fact_sales WHERE book_key IS NULL OR customer_key IS NULL OR date_key IS NULL')
    add('fact_sales.rating_range','SELECT count(*) FROM fact_sales WHERE rating IS NULL OR NOT isfinite(rating) OR rating<1 OR rating>5')
    add('fact_sales.quantity_assumption','SELECT count(*) FROM fact_sales WHERE quantity IS NULL OR quantity<>1')
    add('fact_sales.helpful_vote','SELECT count(*) FROM fact_sales WHERE helpful_vote IS NULL OR helpful_vote<0')
    add('dim_books.price_range','SELECT count(*) FROM dim_books WHERE list_price IS NOT NULL AND (NOT isfinite(list_price) OR list_price<=0 OR list_price>1000)')
    add('fact_sales.revenue_formula','''SELECT count(*) FROM fact_sales WHERE
      (price_usd IS NULL)<>(estimated_revenue IS NULL) OR
      (price_usd IS NOT NULL AND (NOT isfinite(estimated_revenue) OR abs(estimated_revenue-quantity*price_usd)>1e-8))''')
    add('fact_sales.price_matches_metadata','SELECT count(*) FROM fact_sales f JOIN dim_books b USING(book_key) WHERE f.price_usd IS DISTINCT FROM b.list_price')
    add('dim_date.calendar','''SELECT count(*) FROM dim_date WHERE date IS NULL OR date_key<>CAST(strftime(date,'%Y%m%d') AS INTEGER)
      OR day<>day(date) OR month<>month(date) OR year<>year(date) OR quarter<>quarter(date) OR week<>week(date)
      OR is_weekend IS DISTINCT FROM (isodow(date)>=6)''')
    add('dim_date.contiguous','SELECT date_diff(\'day\',min(date),max(date))+1-count(DISTINCT date) FROM dim_date')
    add('dim_customers.per_user_aggregation','''WITH expected AS (
      SELECT customer_key,count(*) AS n,min(d.date) AS first_date,max(d.date) AS last_date
      FROM fact_sales JOIN dim_date d USING(date_key) GROUP BY 1)
      SELECT count(*) FROM expected e FULL OUTER JOIN dim_customers c USING(customer_key)
      WHERE e.n IS DISTINCT FROM c.total_purchases OR e.first_date IS DISTINCT FROM c.first_purchase_date
      OR e.last_date IS DISTINCT FROM c.last_purchase_date''')
    add('fact_inventory.unique_book_month','SELECT count(*)-count(DISTINCT (book_key,month_key)) FROM fact_inventory')
    add('fact_inventory.fk_book','SELECT count(*) FROM fact_inventory i ANTI JOIN dim_books b USING(book_key)')
    add('fact_inventory.simulation_flag','SELECT count(*) FROM fact_inventory WHERE is_simulated IS DISTINCT FROM TRUE')
    add('fact_inventory.valid_values','''SELECT count(*) FROM fact_inventory WHERE book_key IS NULL OR month_key IS NULL
      OR month_key<202209 OR month_key>202308 OR month_key%100 NOT BETWEEN 1 AND 12
      OR stock_quantity IS NULL OR stock_quantity<0 OR units_sold IS NULL OR units_sold<0
      OR (unit_cost IS NOT NULL AND (NOT isfinite(unit_cost) OR unit_cost<0))''')
    add('fact_inventory.sold_by_book_month','''WITH expected AS (
      SELECT f.book_key,d.year*100+d.month AS month_key,sum(quantity) AS n FROM fact_sales f
      JOIN dim_date d USING(date_key) WHERE d.year*100+d.month BETWEEN 202209 AND 202308 GROUP BY 1,2)
      SELECT count(*) FROM expected e FULL OUTER JOIN fact_inventory i USING(book_key,month_key)
      WHERE coalesce(e.n,0) IS DISTINCT FROM i.units_sold''')
    add('fact_inventory.cost_bounds','''SELECT count(*) FROM fact_inventory i JOIN dim_books b USING(book_key)
      WHERE (i.unit_cost IS NULL)<>(b.list_price IS NULL)
      OR (i.unit_cost IS NOT NULL AND (i.unit_cost<0.5*b.list_price-0.0051 OR i.unit_cost>0.8*b.list_price+0.0051))''')
    return result

def rfm_checks():
    return [
      ('rfm.unique_user','SELECT count(*)-count(DISTINCT customer_key) FROM rfm'),
      ('rfm.population_membership','''SELECT count(*) FROM rfm r FULL OUTER JOIN dim_customers c USING(customer_key)
        WHERE r.customer_key IS NULL OR c.customer_key IS NULL'''),
      ('rfm.frequency_per_user','''SELECT count(*) FROM rfm r JOIN dim_customers c USING(customer_key)
        WHERE r.frequency IS DISTINCT FROM c.total_purchases'''),
      ('rfm.recency_per_user','''SELECT count(*) FROM rfm r JOIN dim_customers c USING(customer_key)
        WHERE r.recency IS DISTINCT FROM (SELECT max(date)+1 FROM dim_date)-c.last_purchase_date'''),
      ('rfm.coverage_and_eligibility','''SELECT count(*) FROM rfm WHERE frequency<=0 OR priced_reviews<0 OR priced_reviews>frequency
        OR price_coverage IS NULL OR abs(price_coverage-priced_reviews::DOUBLE/frequency)>1e-12
        OR eligible IS DISTINCT FROM (priced_reviews=frequency)
        OR (priced_reviews=0)<>(monetary_observed IS NULL)'''),
      ('rfm.monetary_per_user','''WITH g AS (SELECT customer_key,count(price_usd) AS priced,
        sum(estimated_revenue) AS monetary FROM fact_sales GROUP BY 1)
        SELECT count(*) FROM rfm r JOIN g USING(customer_key) WHERE r.priced_reviews IS DISTINCT FROM g.priced
        OR (r.monetary_observed IS NULL)<>(g.monetary IS NULL)
        OR abs(r.monetary_observed-g.monetary)>1e-6*greatest(1,abs(g.monetary))'''),
      ('assignments.one_per_user','SELECT count(*)-count(DISTINCT customer_key) FROM assignments'),
      ('assignments.population','''SELECT count(*) FROM assignments a FULL OUTER JOIN rfm r USING(customer_key)
        WHERE a.customer_key IS NULL OR r.customer_key IS NULL'''),
      ('assignments.preserve_rfm','''SELECT count(*) FROM assignments a JOIN rfm r USING(customer_key)
        WHERE a.recency IS DISTINCT FROM r.recency OR a.frequency IS DISTINCT FROM r.frequency
        OR a.monetary_observed IS DISTINCT FROM r.monetary_observed OR a.eligible IS DISTINCT FROM r.eligible
        OR a.priced_reviews IS DISTINCT FROM r.priced_reviews OR a.price_coverage IS DISTINCT FROM r.price_coverage'''),
      ('assignments.exclusion','SELECT count(*) FROM assignments WHERE (NOT eligible AND cluster<>-1) OR (eligible AND cluster<0) OR cluster IS NULL'),
    ]

def evaluate(con,selected):
    records=[]
    for name,sql in selected:
        start=time.perf_counter()
        try:
            violations=con.execute(sql).fetchone()[0]
            record={'name':name,'status':'pass' if violations==0 else 'fail','violations':violations}
        except Exception as exc:record={'name':name,'status':'error','error':str(exc)}
        record['seconds']=round(time.perf_counter()-start,3)
        records.append(record)
        print(record['status'],name,record.get('violations',record.get('error')),flush=True)
    return records

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--warehouse',type=Path,default=ROOT/'data/warehouse')
    p.add_argument('--rfm',type=Path,default=ROOT/'results/rfm_kmeans')
    p.add_argument('--output',type=Path,default=ROOT/'results/tests/data_validation.json')
    args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect();con.execute("SET memory_limit='2GB'");con.execute('SET threads=2')
    con.execute(f"SET temp_directory='{(args.output.parent/'spill').as_posix()}'")
    for t in ['dim_books','dim_customers','dim_date','fact_sales','fact_inventory']:
        path=(args.warehouse/(t+'.parquet')).as_posix().replace("'","''")
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{path}')")
    selected=checks()
    for name,file in [('rfm','rfm_all_users.parquet'),('assignments','rfm_with_clusters.parquet')]:
        path=(args.rfm/file).as_posix().replace("'","''")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
    selected+=rfm_checks()
    meta=json.loads((args.rfm/'run_metadata.json').read_text(encoding='utf-8'))
    k=int(meta['selected_k'])
    selected.append(('assignments.cluster_bounds',f'SELECT count(*) FROM assignments WHERE eligible AND cluster NOT BETWEEN 0 AND {k-1}'))
    selected.append(('assignments.cluster_count',f'SELECT abs(count(DISTINCT cluster)-{k}) FROM assignments WHERE eligible'))
    records=evaluate(con,selected)
    result={'warehouse':str(args.warehouse),'rfm':str(args.rfm),'checks':records,
            'passed':sum(r['status']=='pass' for r in records),'total':len(records)}
    args.output.write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    con.close()
    if result['passed']!=result['total']:raise SystemExit(1)

if __name__=='__main__':main()
