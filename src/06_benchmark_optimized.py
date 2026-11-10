"""Matched end-to-end benchmarks. See BENCHMARK_OPTIMIZED.md."""
import argparse
import csv
import importlib.util
import importlib.metadata
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('baseline', ROOT / 'src/05_benchmark_baseline.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ENGINES = ['pandas_csv', 'pandas_columns', 'pandas_parquet', 'duckdb', 'postgres', 'postgres_index']
COLS = {
    'Q1': {'fact_sales': ['date_key', 'estimated_revenue'], 'dim_date': ['date_key', 'year', 'month']},
    'Q2': {'fact_sales': ['book_key'], 'dim_books': ['book_key', 'category']},
    'Q3': {'fact_sales': ['customer_key', 'sale_id', 'book_key', 'date_key'], 'dim_books': ['book_key', 'title'], 'dim_date': ['date_key', 'date']},
    'Q4': {'fact_sales': ['date_key', 'customer_key'], 'dim_date': ['date_key', 'year']},
    'Q5': {'fact_sales': ['date_key', 'estimated_revenue'], 'dim_date': ['date_key', 'date']},
    'Q6': {'fact_sales': ['customer_key', 'date_key', 'estimated_revenue'], 'dim_date': ['date_key', 'date']},
}


def sql(q, customer):
    return {
        'Q1': 'SELECT d.year,d.month,sum(f.estimated_revenue) AS revenue FROM fact_sales f JOIN dim_date d USING(date_key) GROUP BY 1,2 ORDER BY 1,2',
        'Q2': '''WITH c AS (SELECT book_key,count(*) AS n FROM fact_sales GROUP BY 1),
                   r AS (SELECT b.category,c.book_key,c.n,row_number() OVER (PARTITION BY b.category ORDER BY c.n DESC,c.book_key) AS rk FROM c JOIN dim_books b USING(book_key))
                 SELECT category,book_key,n FROM r WHERE rk<=10 ORDER BY category NULLS LAST,n DESC,book_key''',
        'Q3': f'''SELECT f.sale_id,b.title,d.date FROM fact_sales f JOIN dim_books b USING(book_key)
                  JOIN dim_date d USING(date_key) WHERE f.customer_key={int(customer)} ORDER BY f.sale_id''',
        'Q4': 'SELECT d.year,count(DISTINCT f.customer_key) AS n FROM fact_sales f JOIN dim_date d USING(date_key) GROUP BY 1 ORDER BY 1',
        'Q5': '''WITH daily AS (SELECT date_key,sum(estimated_revenue) AS revenue FROM fact_sales GROUP BY 1)
                 SELECT d.date,avg(coalesce(x.revenue,0)) OVER (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling
                 FROM dim_date d LEFT JOIN daily x USING(date_key) ORDER BY d.date''',
        'Q6': '''WITH m AS (SELECT f.customer_key,d.date,f.estimated_revenue FROM fact_sales f JOIN dim_date d USING(date_key))
                 SELECT customer_key,CAST((SELECT max(date) FROM m)-max(date) AS INTEGER) AS recency,
                 count(*) AS frequency,coalesce(sum(estimated_revenue),0) AS monetary FROM m GROUP BY 1 ORDER BY 1''',
    }[q]


def pandas_query(engine, q, folder, customer):
    import pandas as pd
    def load(table):
        columns = COLS[q][table]
        if engine == 'pandas_parquet':
            return pd.read_parquet(folder / f'{table}.parquet', columns=columns)
        options = {'usecols': columns} if engine == 'pandas_columns' else {}
        if table == 'dim_books' and engine == 'pandas_csv':
            options['dtype'] = {'isbn_13': str}
        return pd.read_csv(folder / f'{table}.csv', **options)
    f = load('fact_sales')
    if q == 'Q2':
        c = f.groupby('book_key').size().rename('n').reset_index()
        r = c.merge(load('dim_books'), on='book_key')
        return r.sort_values(['category', 'n', 'book_key'], ascending=[True, False, True]).groupby('category', dropna=False).head(10)[['category', 'book_key', 'n']].reset_index(drop=True)
    if q == 'Q3':
        r = f[f.customer_key == customer].merge(load('dim_books'), on='book_key').merge(load('dim_date'), on='date_key')
        r['date'] = pd.to_datetime(r['date'])
        return r.sort_values('sale_id')[['sale_id', 'title', 'date']].reset_index(drop=True)
    d = load('dim_date')
    if q in ['Q5', 'Q6']:
        d['date'] = pd.to_datetime(d['date'])
    r = f.merge(d, on='date_key')
    if q == 'Q1':
        return r.groupby(['year', 'month']).estimated_revenue.sum(min_count=1).rename('revenue').reset_index()
    if q == 'Q4':
        return r.groupby('year').customer_key.nunique().rename('n').reset_index()
    if q == 'Q5':
        daily = r.groupby('date').estimated_revenue.sum(min_count=1)
        values = daily.reindex(d.sort_values('date')['date']).fillna(0).rolling(7, min_periods=1).mean()
        return values.rename('rolling').rename_axis('date').reset_index()
    g = r.groupby('customer_key').agg(last_date=('date', 'max'), frequency=('customer_key', 'size'), monetary=('estimated_revenue', 'sum'))
    g['recency'] = (r.date.max() - g.last_date).dt.days
    return g.reset_index()[['customer_key', 'recency', 'frequency', 'monetary']]


def worker(engine, q, folder, customer, output, schema, timeout):
    import pandas as pd
    folder = Path(folder)
    started = time.perf_counter()
    if engine.startswith('pandas'):
        result = pandas_query(engine, q, folder, int(customer))
    elif engine == 'duckdb':
        import duckdb
        with duckdb.connect() as con:
            con.execute("SET memory_limit='2GB'")
            con.execute('SET threads=2')
            for table in COLS[q]:
                con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{folder.as_posix()}/{table}.parquet')")
            result = con.execute(sql(q, customer)).fetchdf()
    else:
        import psycopg
        with psycopg.connect(base.PG_DSN, autocommit=True) as con:
            con.execute(f'SET search_path TO {schema}')
            con.execute(f'SET statement_timeout={int(float(timeout)*1000)}')
            with con.cursor() as cur:
                cur.execute(sql(q, customer))
                result = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    elapsed = time.perf_counter() - started
    # Persist outside the timed region; compare actual rows, not aggregate fingerprints.
    result.to_parquet(output, index=False)
    print(json.dumps({'seconds': elapsed, 'rows': len(result)}))


def guarded(engine, q, folder, customer, output, schema, args):
    import psutil
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', engine, q, str(folder), str(customer), str(output), schema, str(args.timeout)]
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    handle = psutil.Process(p.pid)
    start, peak, status = time.perf_counter(), 0, 'ok'
    while p.poll() is None:
        try:
            members = [handle] + handle.children(recursive=True)
            rss = sum(x.memory_info().rss for x in members if x.is_running())
            peak = max(peak, rss)
            if rss > args.max_rss_gb * 1e9 or psutil.virtual_memory().available < args.min_free_gb * 1e9:
                status = 'memory_limit'
            elif time.perf_counter() - start > args.timeout:
                status = 'timeout'
            if status != 'ok':
                for member in reversed(members):
                    try:
                        member.kill()
                    except psutil.Error:
                        pass
                break
        except psutil.Error:
            pass
        time.sleep(.05)
    out, err = p.communicate()
    r = {'status': status, 'client_peak_gb': peak / 1e9}
    if status == 'ok':
        if p.returncode:
            r.update(status='error', error=err[-2000:])
        else:
            r.update(json.loads(out.strip().splitlines()[-1]))
    return r


def compare(reference, actual):
    import pandas as pd
    from pandas.api.types import is_numeric_dtype
    a, b = pd.read_parquet(reference), pd.read_parquet(actual)
    if list(a.columns) != list(b.columns) or a.shape != b.shape:
        raise AssertionError(f'Shape/columns differ: {a.shape} / {b.shape}')
    # SQL collation depends on the server locale. Compare rows in a common
    # client-side order, outside the timed region; do not discard duplicates.
    if 'date' in a.columns:
        a['date'] = pd.to_datetime(a['date'])
        b['date'] = pd.to_datetime(b['date'])
    keys = list(a.columns)
    a = a.sort_values(keys, kind='stable', na_position='last').reset_index(drop=True)
    b = b.sort_values(keys, kind='stable', na_position='last').reset_index(drop=True)
    for col in a:
        if is_numeric_dtype(a[col]) and is_numeric_dtype(b[col]):
            # Integers must match exactly; tolerance only for floating point aggregation.
            floating = a[col].dtype.kind == 'f' or b[col].dtype.kind == 'f'
            pd.testing.assert_series_equal(a[col], b[col], check_dtype=False, check_exact=not floating, rtol=1e-8, atol=1e-6)
        elif 'date' == col:
            pd.testing.assert_series_equal(pd.to_datetime(a[col]), pd.to_datetime(b[col]), check_dtype=False)
        else:
            pd.testing.assert_series_equal(a[col].astype('string'), b[col].astype('string'))


def prepare_parquet(folder):
    import duckdb
    records = {}
    with duckdb.connect() as con:
        for table in base.TABLES:
            source, target = folder / f'{table}.csv', folder / f'{table}.parquet'
            started = time.perf_counter()
            if not target.exists():
                # Explicit schema preserves CSV strings, including ISBN and missing categories.
                columns = ','.join(f"'{part.strip().split()[0]}':'{part.strip().split()[1]}'" for part in base.DDL[table].split(','))
                con.execute(f"COPY (SELECT * FROM read_csv('{source.as_posix()}', header=true, columns={{{columns}}})) TO '{target.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
                created = True
            else:
                created = False
            records[table] = {'created': created, 'prepare_seconds': time.perf_counter()-started, 'csv_bytes': source.stat().st_size, 'parquet_bytes': target.stat().st_size}
    return records


def setup_postgres(label):
    import psycopg
    schema = f'opt_{label}'
    with psycopg.connect(base.PG_DSN, autocommit=True) as con:
        if con.execute('SELECT 1 FROM information_schema.schemata WHERE schema_name=%s', (schema,)).fetchone():
            raise RuntimeError(f'{schema} already exists; use a fresh --tag (schema is derived from tag).')
        con.execute(f'CREATE SCHEMA {schema}')
        started = time.perf_counter()
        con.execute(f'CREATE TABLE {schema}.fact_sales AS TABLE s_{label.split("_", 1)[0]}.fact_sales')
        for table in ['dim_books', 'dim_date', 'dim_customers']:
            con.execute(f'CREATE VIEW {schema}.{table} AS SELECT * FROM s_{label.split("_", 1)[0]}.{table}')
        con.execute(f'ANALYZE {schema}.fact_sales')
        copy_seconds = time.perf_counter()-started
        started = time.perf_counter()
        con.execute(f'CREATE INDEX ON {schema}.fact_sales(customer_key)')
        con.execute(f'ANALYZE {schema}.fact_sales')
        info = {'schema': schema, 'copy_seconds': copy_seconds, 'index_build_seconds': time.perf_counter()-started,
                'index_bytes': con.execute('SELECT pg_indexes_size(%s)', (f'{schema}.fact_sales',)).fetchone()[0]}
    return schema, info


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        worker(*sys.argv[2:]); return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sizes', nargs='+', choices=base.SIZES, default=['1m'])
    p.add_argument('--engines', nargs='+', choices=ENGINES, default=ENGINES[:4])
    p.add_argument('--queries', nargs='+', choices=base.QUERIES, default=base.QUERIES)
    p.add_argument('--repeats', type=int, default=5)
    p.add_argument('--tag', required=True)
    p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--max-rss-gb', type=float, default=6)
    p.add_argument('--min-free-gb', type=float, default=1.5)
    args=p.parse_args()
    if args.repeats < 1 or not args.tag.replace('_','').isalnum() or len(args.tag)>32:
        p.error('repeats must be positive; tag must be <=32 alphanumeric/underscore characters')
    out=ROOT/'results'/args.tag
    out.mkdir(parents=True, exist_ok=False)
    versions={name:importlib.metadata.version(name) for name in ['pandas','duckdb','pyarrow','psutil']}
    summary={'machine':base.machine_info(), 'versions':versions, 'arguments':vars(args), 'timing':'Read/query + materialize full output in client; imports and result serialization excluded. RSS includes serialization; PostgreSQL server RAM excluded. OS cache uncontrolled.', 'sizes':{}}
    rng=random.Random(base.SEED)
    failed=False
    with (out/'runs.jsonl').open('w',encoding='utf-8') as log:
        for size in args.sizes:
            folder=base.prepare(size)
            params=json.loads((folder/'params.json').read_text())
            item={'parquet':prepare_parquet(folder), 'runs':[]}
            summary['sizes'][size]=item
            schema=''
            if any(e.startswith('postgres') for e in args.engines):
                item['postgres_load']=base.load_postgres(size,folder,params)
                import psycopg
                with psycopg.connect(base.PG_DSN,autocommit=True) as con:
                    item['postgres_settings']={key:con.execute('SHOW '+key).fetchone()[0] for key in ['server_version','work_mem','shared_buffers','max_parallel_workers_per_gather']}
            if 'postgres_index' in args.engines:
                schema,item['index']=setup_postgres(f'{size}_{args.tag}')
            (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            references={}
            for q in args.queries:
                reference=out/f'{size}_{q}_reference.parquet'
                check=guarded('pandas_csv',q,folder,params['customer_key'],reference,'',args)
                if check['status']!='ok':
                    raise RuntimeError(f'Reference failed {q}: {check}')
                references[q]=reference
                print(size,'reference',q,'ok',flush=True)
            # Warm every engine equally; warmup failures are recorded and fatal.
            for engine in args.engines:
                for q in args.queries:
                    target=out/f'{size}_{engine}_{q}.parquet'
                    selected=schema if engine=='postgres_index' else f's_{size}'
                    r=guarded(engine,q,folder,params['customer_key'],target,selected,args)
                    if r['status']!='ok':
                        raise RuntimeError(f'Warmup failed {engine}/{q}: {r}')
                    compare(references[q],target)
                    print(size,'warmup',engine,q,'ok',flush=True)
                    if engine.startswith('postgres'):
                        import psycopg
                        with psycopg.connect(base.PG_DSN,autocommit=True) as con:
                            con.execute(f'SET search_path TO {selected}')
                            con.execute(f'SET statement_timeout={int(args.timeout*1000)}')
                            plan=con.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql(q,params['customer_key'])).fetchone()[0]
                            (out/f'{size}_{engine}_{q}_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
            for repeat in range(1,args.repeats+1):
                jobs=[(e,q) for e in args.engines for q in args.queries]; rng.shuffle(jobs)
                for engine,q in jobs:
                    target=out/f'{size}_{engine}_{q}.parquet'
                    r=guarded(engine,q,folder,params['customer_key'],target,schema if engine=='postgres_index' else f's_{size}',args)
                    if r['status']=='ok':
                        try:
                            compare(references[q],target)
                            r['matches_reference']=True
                        except AssertionError as exc:
                            r.update(status='mismatch',matches_reference=False,error=str(exc)[:1000])
                    failed |= r['status']!='ok'
                    r.update(size=size,engine=engine,query=q,repeat=repeat)
                    item['runs'].append(r); log.write(json.dumps(r)+'\n'); log.flush()
                    print(size,engine,q,repeat,r['status'],round(r.get('seconds',0),3),flush=True)
                    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            item['medians']={}
            for engine in args.engines:
                for q in args.queries:
                    values=[r['seconds'] for r in item['runs'] if r['engine']==engine and r['query']==q and r['status']=='ok']
                    item['medians'][engine+'/'+q]=statistics.median(values) if values else None
            (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.writer(stream)
        writer.writerow(['size','query','engine','successful_runs','median_seconds','max_client_peak_gb','speedup_vs_same_engine_baseline'])
        for size,item in summary['sizes'].items():
            for engine in args.engines:
                for q in args.queries:
                    runs=[r for r in item['runs'] if r['engine']==engine and r['query']==q and r['status']=='ok']
                    median=item['medians'].get(engine+'/'+q)
                    baseline='postgres' if engine.startswith('postgres') else 'pandas_csv'
                    before=item['medians'].get(baseline+'/'+q)
                    writer.writerow([size,q,engine,len(runs),median,max((r['client_peak_gb'] for r in runs),default=None),before/median if before and median else None])
    print('Results:',out)
    if failed:
        sys.exit(1)


if __name__=='__main__':
    main()
