"""Verify the new Colab archive and derive report/dashboard data without mixing sessions."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import statistics
import zipfile
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive',type=Path,default=Path.home()/'Downloads/pg_extended_1110_132250-20261110T173019Z-1-001.zip')
ARCHIVE=parser.parse_args().archive
PREFIX='pg_extended_1110_132250/'
OUT=ROOT/'results/postgres_extended_colab'
OUT.mkdir(exist_ok=True);(OUT/'figures').mkdir(exist_ok=True);(OUT/'evidence').mkdir(exist_ok=True)
SIZES={'1m':1_000_000,'5m':5_000_000,'10m':10_000_000,'full':20_342_188}
CONFIGS=['postgres_4mb','postgres_32mb','postgres_64mb','materialized_4mb']
LABELS={'postgres_4mb':'PostgreSQL · 4 MB','postgres_32mb':'PostgreSQL · 32 MB',
        'postgres_64mb':'PostgreSQL · 64 MB','materialized_4mb':'Materialized view · 4 MB'}
EXPECTED={(c,q) for c in CONFIGS for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if c!='materialized_4mb' or q in ['Q1','Q5']}
rows=[];costs=[];summaries={};plans=[]
def nodes(node):
    yield node
    for child in node.get('Plans',[]):yield from nodes(child)
with zipfile.ZipFile(ARCHIVE) as archive:
    completed=json.loads(archive.read(PREFIX+'completed.json'))
    assert {r['size'] for r in completed}==set(SIZES) and len(completed)==4
    provider=pd.read_csv(archive.open(PREFIX+'comparison_extended_all_sizes.csv'))
    assert len(provider)==80 and not provider.duplicated(['size','config','query']).any()
    for size,count in SIZES.items():
        prefix=PREFIX+f'pgx_{size}_1110_132250/'
        raw=archive.read(prefix+'summary.json');summary=json.loads(raw);summaries[size]=summary
        (OUT/'evidence'/f'{size}_summary.json').write_bytes(raw)
        item=summary['sizes'][size]
        assert item['params']['rows']['fact_sales']==count
        assert summary['arguments']['repeats']==5
        assert summary['configs']=={'postgres_4mb':4,'postgres_32mb':32,'postgres_64mb':64,'materialized_4mb':4}
        runs=item['runs'];assert len(runs)==100
        assert all(r['status']=='ok' and r['matches_reference'] is True for r in runs)
        assert {(r['config'],r['query']) for r in runs}==EXPECTED
        for config,q in sorted(EXPECTED):
            rr=[r for r in runs if r['config']==config and r['query']==q]
            assert len(rr)==5 and {r['repeat'] for r in rr}=={1,2,3,4,5}
            vals=[r['seconds'] for r in rr];assert all(math.isfinite(v) and v>0 for v in vals)
            baseline=[r['seconds'] for r in runs if r['config']=='postgres_4mb' and r['query']==q]
            median=statistics.median(vals);speed=statistics.median(baseline)/median
            original=provider[(provider['size']==size)&(provider.config==config)&(provider['query']==q)]
            assert len(original)==1 and original.iloc[0].successful_runs==5
            assert math.isclose(median,original.iloc[0].median_s,rel_tol=1e-10)
            assert math.isclose(speed,original.iloc[0].speedup_vs_4mb,rel_tol=1e-10)
            row={'size':size,'config':config,'query':q,'runs':5,'median_s':median,
                 'min_s':min(vals),'max_s':max(vals),'q1_s':float(np.quantile(vals,.25)),
                 'q3_s':float(np.quantile(vals,.75)),'speedup_vs_4mb':speed}
            rows.append(row)
            if size=='full':
                filename=f'{size}_{config}_{q}_plan.json';planraw=archive.read(prefix+filename)
                (OUT/'evidence'/filename).write_bytes(planraw)
                plan=json.loads(planraw)[0];nn=list(nodes(plan['Plan']))
                plans.append({'config':config,'query':q,'execution_ms':plan['Execution Time'],
                              'disk_sort_nodes':sum(n.get('Sort Space Type')=='Disk' for n in nn),
                              'temp_read_blocks':plan['Plan'].get('Temp Read Blocks',0),
                              'temp_written_blocks':plan['Plan'].get('Temp Written Blocks',0)})
        for name,v in item['materialized_views'].items():
            assert name in ['mv_monthly','mv_daily'] and v['refresh_matches_reference'] is True
            assert len(v['refresh_seconds'])==5 and all(x>0 and math.isfinite(x) for x in v['refresh_seconds'])
            assert math.isclose(statistics.median(v['refresh_seconds']),v['refresh_median_s'],rel_tol=1e-10)
            costs.append({'size':size,'view':name,'create_seconds':v['create_seconds'],
                          'analyze_seconds':v['analyze_seconds'],'refresh_median_s':v['refresh_median_s'],
                          'bytes':v['bytes'],'rows':v['rows']})
frame=pd.DataFrame(rows);cost=pd.DataFrame(costs);evidence=pd.DataFrame(plans)
frame.to_csv(OUT/'comparison_extended_verified.csv',index=False,encoding='utf-8-sig')
cost.to_csv(OUT/'materialized_view_costs.csv',index=False,encoding='utf-8-sig')
evidence.to_csv(OUT/'plan_evidence_full.csv',index=False,encoding='utf-8-sig')
digest=hashlib.sha256()
with ARCHIVE.open('rb') as stream:
    while part:=stream.read(1024*1024):digest.update(part)
validation={'archive':str(ARCHIVE),'sha256':digest.hexdigest(),'session':'pg_extended_1110_132250',
 'verified_runs':400,'verified_combinations':80,'repeats':5,'verified_sizes':SIZES,
 'baseline':'postgres_4mb within the same session','all_query_matches':True,'refresh_views_verified':8,
 'refresh_operations_verified':40,'provider_csv_matches_recomputed_medians':True,
 'old_session_runs':720,'total_across_two_separate_sessions':1120}
(OUT/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
def full(config,q):return frame[(frame['size']=='full')&(frame.config==config)&(frame['query']==q)].iloc[0]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
    fig.tight_layout();fig.savefig(OUT/'figures'/(name+'.png'),dpi=180,bbox_inches='tight')
    fig.savefig(OUT/'figures'/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
fig,axes=plt.subplots(2,3,figsize=(13,8))
for q,ax in zip(['Q1','Q2','Q3','Q4','Q5','Q6'],axes.flat):
    rr=[full(c,q) for c in CONFIGS[:3]]
    ax.bar(['4 MB','32 MB','64 MB'],[r.median_s for r in rr],color=['#64748b','#3478d4','#16806a'])
    ax.set_title(q);ax.set_ylabel('Trung vị (giây)');ax.grid(axis='y',alpha=.15)
fig.suptitle('Điều chỉnh work_mem · 20,34 triệu dòng · 5 lần đo / cấu hình');fig.subplots_adjust(top=.9)
save(fig,'01_work_mem_full')
fig,axes=plt.subplots(1,2,figsize=(11,5))
for q,ax in zip(['Q1','Q5'],axes):
    rr=[full('postgres_4mb',q),full('materialized_4mb',q)]
    bars=ax.bar(['Tính lại từ fact','Materialized view'],[r.median_s for r in rr],color=['#64748b','#16806a'])
    ax.bar_label(bars,fmt='%.3f',padding=3);ax.set_ylim(0,max(r.median_s for r in rr)*1.2)
    ax.set_title(q+f' · tăng tốc {rr[1].speedup_vs_4mb:.2f}×');ax.set_ylabel('Trung vị (giây)')
save(fig,'02_materialized_query')
fc=cost[cost['size']=='full'];fig,ax=plt.subplots(figsize=(10,5));pos=np.arange(2)
ax.bar(pos-.18,fc.create_seconds,width=.35,label='Tạo view',color='#3478d4')
ax.bar(pos+.18,fc.refresh_median_s,width=.35,label='Refresh đầy đủ (trung vị)',color='#b0781a')
ax.set_xticks(pos,fc['view']);ax.set_ylabel('Giây');ax.set_title('Chi phí chuẩn bị và duy trì · tách khỏi thời gian truy vấn');ax.legend()
save(fig,'03_materialized_cost')
blocks=[]
def h(t):blocks.append(('heading',t))
def p(t):blocks.append(('paragraph',t))
def table(headers,rr):blocks.append(('table',[headers]+rr))
def image(name,text):blocks.append(('figure',(name,text)))
h('Thực nghiệm PostgreSQL bổ sung: work_mem và materialized view')
p('Nguồn là pg_extended_1110_132250, thu trong đợt Colab riêng với 720 phép đo trước. Đã xác minh đủ 400 lượt mới: 4 quy mô, 20 tổ hợp/mức, 5 lần/tổ hợp. Toàn bộ kết quả khớp baseline; 8 view qua 40 lượt refresh và đối chiếu sau refresh đều đạt. Tổng hồ sơ có 1.120 lượt đo chính qua hai đợt; không dùng baseline cũ làm mẫu số cho kết quả mới.')
h('Thiết kế đối chứng và phạm vi đo')
p('Ba cấu hình PostgreSQL 4, 32, 64 MB dùng cùng nguồn và SQL Q1–Q6, max_parallel_workers_per_gather=2. Cấu hình materialized_4mb chỉ áp dụng Q1/Q5 và giữ work_mem=4 MB. Thời gian gồm kết nối, thiết lập phiên, truy vấn và nhận toàn bộ kết quả, không gồm ghi tệp/đối chiếu; baseline 4 MB được đo lại trong chính đợt bổ sung. Mỗi cấu hình có warm-up, thứ tự chạy xáo và trung vị 5 lần. Các view tạo từ snapshot nguồn, không đổi fact.')
p('work_mem là giới hạn theo thao tác, có thể nhân lên theo worker và phép hash; không phải trần RAM server. Không có đo tổng bộ nhớ PostgreSQL để kết luận 64 MB là cấu hình tối ưu tài nguyên. EXPLAIN là lượt riêng có instrumentation, không thay cho trung vị chính.')
h('Kết quả work_mem trên toàn bộ dữ liệu')
table(['Truy vấn','4 MB (s)','32 MB (s)','64 MB (s)','4 MB / 64 MB'],[[q]+[f'{full(c,q).median_s:.3f}' for c in CONFIGS[:3]]+[f'{full("postgres_64mb",q).speedup_vs_4mb:.3f}×'] for q in ['Q1','Q2','Q3','Q4','Q5','Q6']])
image('01_work_mem_full','Thời gian theo work_mem trên cùng đợt Colab mới.')
p('Q2 tăng tốc khoảng 1,13 lần ở 64 MB; Q5 khoảng 1,28 lần ở 32 MB. Q1 chậm hơn baseline, Q3 không cải thiện, Q4/Q6 chênh lệch nhỏ. Không có bằng chứng tăng work_mem luôn làm nhanh hơn; các chênh lệch nhỏ chưa được kiểm định ý nghĩa thống kê.')
for q in ['Q2','Q4','Q6']:
    a=evidence[(evidence.config=='postgres_4mb')&(evidence['query']==q)].iloc[0]
    b=evidence[(evidence.config=='postgres_64mb')&(evidence['query']==q)].iloc[0]
    p(f'{q}: trong lượt EXPLAIN riêng, số block tạm ghi ở nút gốc giảm từ {int(a.temp_written_blocks):,} xuống {int(b.temp_written_blocks):,} khi tăng 4 → 64 MB; vẫn có {int(b.disk_sort_nodes)} nút sắp xếp dùng đĩa. Số block ở gốc được dùng trực tiếp, không cộng các nút cha/con vì sẽ đếm trùng.')
h('Materialized view: tốc độ truy vấn và đánh đổi')
table(['Truy vấn','Baseline mới (s)','Đọc view (s)','Tăng tốc'],[[q,f'{full("postgres_4mb",q).median_s:.3f}',f'{full("materialized_4mb",q).median_s:.3f}',f'{full("materialized_4mb",q).speedup_vs_4mb:.2f}×'] for q in ['Q1','Q5']])
image('02_materialized_query','Tăng tốc nhờ đọc kết quả tổng hợp trước, không phải tăng tốc tính lại toàn bộ fact.')
table(['View','Số dòng','Tạo (s)','ANALYZE (s)','Refresh TB vị (s)','Dung lượng (KiB)'],[[r.view,str(int(r.rows)),f'{r.create_seconds:.3f}',f'{r.analyze_seconds:.4f}',f'{r.refresh_median_s:.3f}',f'{r.bytes/1024:.0f}'] for r in fc.itertuples()])
image('03_materialized_cost','Tạo và refresh được đo riêng, không cộng lẫn vào thời gian đọc view.')
p('Q1 nhanh khoảng 331,24 lần, Q5 khoảng 128,17 lần khi đọc tổng hợp đã lưu. mv_monthly có 317 dòng, mv_daily có 9.487 dòng thay vì quét 20.342.188 dòng fact. Chi phí là tạo, dung lượng, làm mới và nguy cơ dữ liệu cũ. Refresh ở đây tính lại đầy đủ trên nguồn không thay đổi; chưa đo concurrent refresh, cập nhật nguồn hay bảo trì gia tăng.')
p('Với tỷ số trung vị quan sát, chi phí tạo riêng mv_monthly được bù sau khoảng 2 truy vấn Q1, mv_daily khoảng 1 truy vấn Q5. Đây chỉ là ước lượng ceil(create_time / saving_per_query), không bao gồm ANALYZE, refresh, lưu trữ hoặc tải đồng thời. Không cam kết hòa vốn tương tự trong vận hành thực tế.')
h('Kết luận bổ sung và khả năng tái lập')
p('Hai kỹ thuật đã có mã, kết quả Colab và bằng chứng đối chiếu. work_mem phù hợp thử giảm I/O tạm nhưng cần đo theo truy vấn; materialized view phù hợp thống kê lặp lại trên snapshot hoặc có lịch refresh rõ. Để cập nhật kết quả, chạy src/14_analyze_postgres_extended.py trên ZIP gốc; CSV đã kiểm chứng dùng cho dashboard và report_blocks dùng cho báo cáo. Không cần xây lại EDA hay huấn luyện lại K-Means.')
(OUT/'report_blocks.json').write_text(json.dumps(blocks,ensure_ascii=False,indent=2),encoding='utf-8')
md=[]
for kind,c in blocks:
    if kind=='heading':md.append('## '+c)
    elif kind=='paragraph':md.append(c)
    elif kind=='figure':md.append(f'![{c[1]}](figures/{c[0]}.png)')
    else:md.append('\n'.join(['| '+' | '.join(c[0])+' |','|'+'---|'*len(c[0])]+['| '+' | '.join(r)+' |' for r in c[1:]]))
(OUT/'Phan_tich_PostgreSQL_bo_sung.md').write_text('\n\n'.join(md),encoding='utf-8')
dashboard=ROOT/'dashboard/data'
for name in ['comparison_extended_verified.csv','materialized_view_costs.csv','validation.json']:
    (dashboard/('extended_'+name)).write_bytes((OUT/name).read_bytes())
print('Verified 400 runs, 80 combinations, 40 refresh operations; report and dashboard data generated.')
