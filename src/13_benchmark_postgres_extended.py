"""Controlled work_mem and materialized-view experiments, measured together."""
import argparse
import csv
import importlib.util
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('optimized',ROOT/'src/06_benchmark_optimized.py')
opt=importlib.util.module_from_spec(spec);spec.loader.exec_module(opt)
CONFIGS={'postgres_4mb':4,'postgres_32mb':32,'postgres_64mb':64,'materialized_4mb':4}

def query_sql(q,customer,materialized=False):
    if not materialized:return opt.sql(q,customer)
    return {
        'Q1':'SELECT year,month,revenue FROM mv_monthly ORDER BY year,month',
        'Q5':'''SELECT d.date,avg(coalesce(m.revenue,0)) OVER
          (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS rolling
          FROM dim_date d LEFT JOIN mv_daily m USING(date_key) ORDER BY d.date''',
    }[q]

def configure(con,schema,work_mem,timeout):
    from psycopg import sql
    con.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
    con.execute("SELECT set_config('work_mem',%s,false)",(f'{work_mem}MB',))
    con.execute("SELECT set_config('statement_timeout',%s,false)",(str(int(timeout*1000)),))
    con.execute('SET max_parallel_workers_per_gather=2')

def worker(config,q,customer,schema,target,timeout,pidfile):
    import pandas as pd
    import psycopg
    started=time.perf_counter()
    with psycopg.connect(opt.base.PG_DSN,autocommit=True,application_name='books_extended_worker') as con:
        Path(pidfile).write_text(str(con.info.backend_pid),encoding='ascii')
        configure(con,schema,CONFIGS[config],float(timeout))
        with con.cursor() as cur:
            cur.execute(query_sql(q,int(customer),config=='materialized_4mb'))
            frame=pd.DataFrame(cur.fetchall(),columns=[c.name for c in cur.description])
    elapsed=time.perf_counter()-started
    frame.to_parquet(target,index=False)
    print(json.dumps({'seconds':elapsed,'rows':len(frame)}))

def guarded(config,q,customer,schema,target,args):
    import psutil
    pidfile=target.with_suffix('.pid')
    if pidfile.exists():pidfile.unlink()
    command=[sys.executable,str(Path(__file__).resolve()),'--worker',config,q,str(customer),schema,
             str(target),str(args.timeout),str(pidfile)]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
    handle=psutil.Process(proc.pid);started=time.perf_counter();peak=0;status='ok'
    while proc.poll() is None:
        if psutil.virtual_memory().available<args.min_free_gb*1e9:status='low_system_memory'
        elif time.perf_counter()-started>args.timeout+30:status='timeout'
        try:
            members=[handle]+handle.children(recursive=True)
            peak=max(peak,sum(m.memory_info().rss for m in members if m.is_running()))
        except psutil.Error:members=[]
        if status!='ok':
            # Cancel only the backend created by this worker before stopping its client.
            if pidfile.exists():
                try:
                    import psycopg
                    with psycopg.connect(opt.base.PG_DSN,autocommit=True,connect_timeout=5) as con:
                        con.execute("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE pid=%s AND application_name='books_extended_worker'",(int(pidfile.read_text()),))
                except Exception:pass
            for member in reversed(members):
                try:member.kill()
                except psutil.Error:pass
            proc.kill();break
        time.sleep(.1)
    out,err=proc.communicate()
    result={'status':status,'client_peak_gb':peak/1e9}
    if status=='ok':
        if proc.returncode:result.update(status='error',error=err[-3000:])
        else:result.update(json.loads(out.strip().splitlines()[-1]))
    return result

def setup(con,schema,size,timeout):
    from psycopg import sql
    if con.execute('SELECT 1 FROM information_schema.schemata WHERE schema_name=%s',(schema,)).fetchone():
        raise RuntimeError(f'Schema {schema} exists: use a fresh tag.')
    indexes=con.execute('SELECT indexname FROM pg_indexes WHERE schemaname=%s AND tablename=%s',(f's_{size}','fact_sales')).fetchall()
    if indexes:raise RuntimeError('Baseline fact already has indexes; use a clean benchmark baseline.')
    con.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    configure(con,schema,4,timeout)
    for table in opt.base.TABLES:
        con.execute(sql.SQL('CREATE VIEW {} AS SELECT * FROM {}.{}').format(sql.Identifier(table),sql.Identifier('s_'+size),sql.Identifier(table)))
    definitions={
      'mv_monthly':'''SELECT d.year,d.month,sum(f.estimated_revenue) AS revenue
        FROM fact_sales f JOIN dim_date d USING(date_key) GROUP BY 1,2''',
      'mv_daily':'SELECT date_key,sum(estimated_revenue) AS revenue FROM fact_sales GROUP BY 1',
    }
    info={}
    for name,query in definitions.items():
        start=time.perf_counter();con.execute(f'CREATE MATERIALIZED VIEW {name} AS {query}')
        elapsed=time.perf_counter()-start
        info[name]={'create_seconds':elapsed,'bytes':con.execute('SELECT pg_total_relation_size(%s)',(f'{schema}.{name}',)).fetchone()[0]}
        start=time.perf_counter();con.execute(f'ANALYZE {name}')
        info[name]['analyze_seconds']=time.perf_counter()-start
        info[name]['rows']=con.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
    return info

def save_summary(out,summary):
    (out/'summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(*sys.argv[2:]);return
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes',nargs='+',choices=opt.base.SIZES,default=['full'])
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--timeout',type=float,default=900)
    parser.add_argument('--min-free-gb',type=float,default=1.0)
    parser.add_argument('--queries',nargs='+',choices=opt.base.QUERIES,default=opt.base.QUERIES)
    args=parser.parse_args()
    if args.repeats<1 or not args.tag.isascii() or not args.tag.replace('_','').isalnum() or len(args.tag)>32:parser.error('Invalid tag/repeats')
    out=ROOT/'results'/args.tag;out.mkdir(exist_ok=False,parents=True)
    summary={'machine':opt.base.machine_info(),'arguments':vars(args),'configs':CONFIGS,'sizes':{},
             'timing':'Connection + per-session configuration + query + full client materialization; imports, result persistence and comparison excluded. Client RSS excludes PostgreSQL server. Warm OS cache uncontrolled.'}
    rng=random.Random(20261110);failed=False;comparison=[]
    import psycopg
    with (out/'runs.jsonl').open('w',encoding='utf-8') as log:
        for size in args.sizes:
            print('Preparing:',size,flush=True)
            folder=opt.base.prepare(size);params=json.loads((folder/'params.json').read_text())
            item={'params':params,'load':opt.base.load_postgres(size,folder,params),'runs':[],'warmups':[]}
            summary['sizes'][size]=item
            schema=f'ex_{size}_{args.tag}'
            with psycopg.connect(opt.base.PG_DSN,autocommit=True) as con:
                item['materialized_views']=setup(con,schema,size,args.timeout)
                item['settings']={k:con.execute('SHOW '+k).fetchone()[0] for k in ['server_version','work_mem','hash_mem_multiplier','shared_buffers','max_parallel_workers_per_gather','block_size']}
            save_summary(out,summary)
            references={}
            for q in args.queries:
                target=out/f'{size}_{q}_reference.parquet'
                r=guarded('postgres_4mb',q,params['customer_key'],schema,target,args)
                if r['status']!='ok':raise RuntimeError(f'Reference {q} failed: {r}')
                references[q]=target;print(size,'reference',q,'ok',flush=True)
            jobs=[(config,q) for config in CONFIGS for q in args.queries if config!='materialized_4mb' or q in ['Q1','Q5']]
            for config,q in jobs:
                target=out/f'{size}_{config}_{q}.parquet'
                r=guarded(config,q,params['customer_key'],schema,target,args)
                r.update(config=config,query=q)
                item['warmups'].append(r);save_summary(out,summary)
                if r['status']!='ok':raise RuntimeError(f'Warmup failed: {r}')
                opt.compare(references[q],target)
                print(size,'warmup',config,q,'ok',flush=True)
                with psycopg.connect(opt.base.PG_DSN,autocommit=True) as con:
                    configure(con,schema,CONFIGS[config],args.timeout)
                    plan=con.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query_sql(q,params['customer_key'],config=='materialized_4mb')).fetchone()[0]
                    (out/f'{size}_{config}_{q}_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
            for repeat in range(1,args.repeats+1):
                plan=list(jobs);rng.shuffle(plan)
                for config,q in plan:
                    target=out/f'{size}_{config}_{q}.parquet'
                    r=guarded(config,q,params['customer_key'],schema,target,args)
                    if r['status']=='ok':
                        try:opt.compare(references[q],target);r['matches_reference']=True
                        except AssertionError as exc:r.update(status='mismatch',matches_reference=False,error=str(exc)[:2000])
                    r.update(size=size,config=config,query=q,repeat=repeat)
                    item['runs'].append(r);log.write(json.dumps(r)+'\n');log.flush()
                    failed|=r['status']!='ok';save_summary(out,summary)
                    print(size,config,q,repeat,r['status'],round(r.get('seconds',0),3),flush=True)
            # Full, nonconcurrent refresh with no source mutation: measures recomputation,
            # not incremental maintenance, ingestion, or freshness under writes.
            with psycopg.connect(opt.base.PG_DSN,autocommit=True) as con:
                configure(con,schema,4,args.timeout)
                for name,info in item['materialized_views'].items():
                    values=[]
                    for _ in range(args.repeats):
                        start=time.perf_counter();con.execute(f'REFRESH MATERIALIZED VIEW {name}');values.append(time.perf_counter()-start)
                    info['refresh_seconds']=values;info['refresh_median_s']=statistics.median(values)
                    q='Q1' if name=='mv_monthly' else 'Q5'
                    with con.cursor() as cur:
                        import pandas as pd
                        cur.execute(query_sql(q,params['customer_key'],True))
                        frame=pd.DataFrame(cur.fetchall(),columns=[c.name for c in cur.description])
                    target=out/f'{size}_{name}_after_refresh.parquet';frame.to_parquet(target,index=False)
                    # Check even when Q1/Q5 were not among measured queries.
                    if q not in references:
                        reference=out/f'{size}_{q}_refresh_reference.parquet'
                        checked=guarded('postgres_4mb',q,params['customer_key'],schema,reference,args)
                        if checked['status']!='ok':raise RuntimeError(checked)
                    else:reference=references[q]
                    opt.compare(reference,target);info['refresh_matches_reference']=True
                    print(size,'refresh',name,'ok',flush=True)
            for config,q in jobs:
                rr=[r for r in item['runs'] if r['config']==config and r['query']==q and r['status']=='ok']
                baseline=[r['seconds'] for r in item['runs'] if r['config']=='postgres_4mb' and r['query']==q and r['status']=='ok']
                med=statistics.median(r['seconds'] for r in rr) if rr else None
                row={'size':size,'config':config,'query':q,'successful_runs':len(rr),'median_s':med,
                     'min_s':min((r['seconds'] for r in rr),default=None),'max_s':max((r['seconds'] for r in rr),default=None),
                     'speedup_vs_4mb':statistics.median(baseline)/med if baseline and med else None}
                if config=='materialized_4mb' and med and baseline:
                    name='mv_monthly' if q=='Q1' else 'mv_daily'
                    saving=statistics.median(baseline)-med
                    row['create_break_even_queries']=__import__('math').ceil(item['materialized_views'][name]['create_seconds']/saving) if saving>0 else None
                comparison.append(row)
            save_summary(out,summary)
            with (out/'comparison.csv').open('w',newline='',encoding='utf-8-sig') as f:
                keys=['size','config','query','successful_runs','median_s','min_s','max_s','speedup_vs_4mb','create_break_even_queries']
                writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(comparison)
    print('COMPLETE:',out,flush=True)
    if failed:raise SystemExit(1)

if __name__=='__main__':main()
