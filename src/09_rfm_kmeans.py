"""Full-population RFM, stratified KMeans evaluation and batched assignments.

Monetary is a metadata-price proxy, not transaction revenue. Users with any
missing price remain in the output with cluster=-1 and are not imputed as zero.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import base64
import hashlib
import html
import json
from pathlib import Path

import duckdb
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/rfm_kmeans'
OUT.mkdir(exist_ok=True)
(OUT/'figures').mkdir(exist_ok=True)
con=duckdb.connect()
con.execute("SET memory_limit='2GB'")
con.execute('SET threads=2')
con.execute(f"SET temp_directory='{(OUT/'spill').as_posix()}'")
wh=(ROOT/'data/warehouse').as_posix()
rfm_path=OUT/'rfm_all_users.parquet'
if rfm_path.exists():
    raise SystemExit('Output already exists. Preserve this run or use a fresh output directory.')

con.execute(f"CREATE VIEW fact AS SELECT * FROM read_parquet('{wh}/fact_sales.parquet')")
reference=con.execute(f"SELECT max(date)+1 FROM read_parquet('{wh}/dim_date.parquet')").fetchone()[0]
print('Reference date:',reference,flush=True)
con.execute(f"""COPY (
 WITH g AS (SELECT customer_key,max(date_key) AS last_key,count(*) AS frequency,
 count(price_usd) AS priced_reviews,sum(estimated_revenue) AS monetary_observed
 FROM fact GROUP BY 1)
 SELECT customer_key,DATE '{reference}'-strptime(CAST(last_key AS VARCHAR),'%Y%m%d')::DATE AS recency,
 frequency,priced_reviews,monetary_observed,
 priced_reviews::DOUBLE/frequency AS price_coverage,
 priced_reviews=frequency AS eligible,
 CASE WHEN frequency=1 THEN '1' WHEN frequency=2 THEN '2' WHEN frequency<=5 THEN '3-5'
 WHEN frequency<=10 THEN '6-10' WHEN frequency<=50 THEN '11-50' ELSE '>50' END AS frequency_stratum
 FROM g) TO '{rfm_path.as_posix()}' (FORMAT parquet,COMPRESSION zstd)""")
con.execute(f"CREATE VIEW rfm AS SELECT * FROM read_parquet('{rfm_path.as_posix()}')")
overview=con.execute('''SELECT count(*) AS users,sum(frequency)::BIGINT AS reviews,
 count(*) FILTER(WHERE eligible) AS eligible_users,count(*) FILTER(WHERE priced_reviews=0) AS no_price_users,
 count(*) FILTER(WHERE priced_reviews>0 AND NOT eligible) AS partial_price_users,
 min(recency) AS min_recency,max(recency) AS max_recency FROM rfm''').fetchdf()
overview.to_csv(OUT/'population.csv',index=False,encoding='utf-8-sig')
assert int(overview.iloc[0].users)==8_353_809 and int(overview.iloc[0].reviews)==20_342_188
assert int(overview.iloc[0].min_recency)>=1
print('Population:',overview.to_dict('records'),flush=True)

strata=con.execute('SELECT frequency_stratum,count(*) AS users FROM rfm WHERE eligible GROUP BY 1 ORDER BY 1').fetchdf()
target=min(150_000,int(strata.users.sum()))
quotas=target*strata.users/strata.users.sum()
strata['sample_n']=np.floor(quotas).astype(int)
remaining=target-int(strata.sample_n.sum())
for i in np.argsort(-(quotas-np.floor(quotas)).to_numpy(),kind='stable')[:remaining]:
    strata.loc[i,'sample_n']+=1
con.register('quotas',strata)
sample=con.execute('''SELECT customer_key,recency,frequency,monetary_observed,frequency_stratum
 FROM (SELECT *,row_number() OVER(PARTITION BY frequency_stratum ORDER BY hash(customer_key,20261109),customer_key) AS rn
       FROM rfm WHERE eligible) r JOIN quotas q USING(frequency_stratum)
 WHERE rn<=q.sample_n ORDER BY customer_key''').fetchdf()
assert len(sample)==target and sample.customer_key.is_unique
observed=sample.groupby('frequency_stratum').size().to_dict()
assert all(observed.get(r.frequency_stratum,0)==r.sample_n for r in strata.itertuples())
strata.to_csv(OUT/'sampling_strata.csv',index=False,encoding='utf-8-sig')
sample.to_parquet(OUT/'training_sample.parquet',index=False)
features=['recency','frequency','monetary_observed']
raw=sample[features].to_numpy(dtype=float)
assert np.isfinite(raw).all() and (raw>=0).all()
scaler=StandardScaler()
x=scaler.fit_transform(np.log1p(raw))
evaluation_indices=np.random.default_rng(20261109).choice(len(x),min(3000,len(x)),replace=False)
scores=[]; labels_by_k={};models={}
with threadpool_limits(limits=2):
    for k in range(2,6):
        labels_by_k[k]={}
        for seed in [42,2026,1109]:
            model=KMeans(n_clusters=k,random_state=seed,n_init=10,max_iter=300)
            labels=model.fit_predict(x)
            assert len(np.unique(labels))==k
            score=float(silhouette_score(x[evaluation_indices],labels[evaluation_indices]))
            scores.append({'k':k,'seed':seed,'silhouette':score,'inertia':float(model.inertia_),
                           'iterations':int(model.n_iter_),'min_cluster_pct':100*np.bincount(labels).min()/len(labels)})
            labels_by_k[k][seed]=labels
            models[k,seed]=model
            print('Model:',k,seed,'silhouette:',round(score,4),flush=True)
metrics=pd.DataFrame(scores)
metrics.to_csv(OUT/'kmeans_metrics.csv',index=False,encoding='utf-8-sig')
stability=[]
for k in range(2,6):
    for left,right in [(42,2026),(42,1109),(2026,1109)]:
        stability.append({'k':k,'seed_left':left,'seed_right':right,
                          'adjusted_rand_index':adjusted_rand_score(labels_by_k[k][left],labels_by_k[k][right])})
stability=pd.DataFrame(stability)
stability.to_csv(OUT/'seed_stability.csv',index=False,encoding='utf-8-sig')
summary=metrics.groupby('k').agg(mean_silhouette=('silhouette','mean'),std_silhouette=('silhouette','std'),
                               mean_inertia=('inertia','mean'),min_cluster_pct=('min_cluster_pct','min')).reset_index()
summary=summary.merge(stability.groupby('k').adjusted_rand_index.mean().rename('mean_ari'),on='k')
summary.to_csv(OUT/'model_selection.csv',index=False,encoding='utf-8-sig')
best_k=int(summary.sort_values(['mean_silhouette','k'],ascending=[False,True]).iloc[0].k)
best_seed=int(metrics[metrics.k==best_k].sort_values(['silhouette','seed'],ascending=[False,True]).iloc[0].seed)
best=models[best_k,best_seed]
joblib.dump({'scaler':scaler,'model':best,'features':features,'transform':'log1p',
             'reference_date':str(reference),'eligibility':'all reviews have valid prices'},OUT/'model.joblib')

# Predict all eligible users, not just the training sample. Keep excluded users explicit.
assignment=OUT/'rfm_with_clusters.parquet'
writer=None
predicted=0; excluded=0
try:
    with threadpool_limits(limits=2):
        for batch in pq.ParquetFile(rfm_path).iter_batches(batch_size=100_000):
            frame=batch.to_pandas()
            eligible=frame.eligible.to_numpy(dtype=bool)
            clusters=np.full(len(frame),-1,dtype=np.int32)
            if eligible.any():
                transformed=scaler.transform(np.log1p(frame.loc[eligible,features].to_numpy(dtype=float)))
                clusters[eligible]=best.predict(transformed)
            predicted+=int(eligible.sum());excluded+=int((~eligible).sum())
            table=pa.Table.from_pandas(frame,preserve_index=False).append_column('cluster',pa.array(clusters))
            if writer is None:writer=pq.ParquetWriter(assignment,table.schema,compression='zstd')
            writer.write_table(table)
finally:
    if writer is not None:writer.close()
assert predicted==int(overview.iloc[0].eligible_users)
assert predicted+excluded==int(overview.iloc[0].users)
con.execute(f"CREATE VIEW assignments AS SELECT * FROM read_parquet('{assignment.as_posix()}')")
profiles=con.execute('''SELECT cluster,count(*) AS users,median(recency) AS median_recency,
 median(frequency) AS median_frequency,median(monetary_observed) AS median_monetary,
 avg(recency) AS mean_recency,avg(frequency) AS mean_frequency,avg(monetary_observed) AS mean_monetary
 FROM assignments GROUP BY 1 ORDER BY 1''').fetchdf()
profiles['population_pct']=100*profiles.users/int(overview.iloc[0].users)
profiles.to_csv(OUT/'cluster_profiles.csv',index=False,encoding='utf-8-sig')
assert int(profiles.users.sum())==8_353_809
sample['cluster']=labels_by_k[best_k][best_seed]
sample.to_parquet(OUT/'training_sample_with_clusters.parquet',index=False)
metadata={'reference_date':str(reference),'training_users':len(sample),'eligible_users':predicted,
          'excluded_users':excluded,'selected_k':best_k,'selected_seed':best_seed,
          'silhouette_eval_users':len(evaluation_indices),'sampling_seed':20261109,
          'selection_rule':'maximize mean silhouette over 3 seeds; choose seed with highest silhouette',
          'mean_ari':float(summary.loc[summary.k==best_k,'mean_ari'].iloc[0]),
          'training_sample_sha256':hashlib.sha256((OUT/'training_sample.parquet').read_bytes()).hexdigest()}
(OUT/'run_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
def save(name):
    plt.tight_layout();plt.savefig(OUT/'figures'/(name+'.png'),dpi=180,bbox_inches='tight')
    plt.savefig(OUT/'figures'/(name+'.pdf'),bbox_inches='tight');plt.close()
fig,axes=plt.subplots(1,2,figsize=(11,4))
axes[0].errorbar(summary.k,summary.mean_silhouette,yerr=summary.std_silhouette,marker='o',capsize=4)
axes[0].set(title='Silhouette · trung bình ± SD của 3 seed',xlabel='Số cụm k',ylabel='Silhouette')
axes[1].plot(summary.k,summary.mean_inertia,marker='o');axes[1].set(title='Inertia sau log1p và chuẩn hóa',xlabel='Số cụm k',ylabel='Inertia')
for ax in axes:ax.set_xticks(range(2,6));ax.grid(alpha=.2)
save('01_chon_k')
plt.figure(figsize=(8,4));plt.bar(summary.k,summary.mean_ari,color='#059669');plt.ylim(0,1.05)
plt.xticks(range(2,6));plt.xlabel('Số cụm k');plt.ylabel('ARI trung bình giữa các seed');plt.title('Độ ổn định trên cùng mẫu huấn luyện');save('02_do_on_dinh')
included=profiles[profiles.cluster>=0]
plt.figure(figsize=(9,4));plt.bar(profiles.cluster.astype(str),profiles.population_pct,color=['#94a3b8' if c==-1 else '#0284c7' for c in profiles.cluster])
plt.xlabel('Cụm (-1: thiếu giá, không đưa vào K-Means)');plt.ylabel('% toàn bộ người dùng');plt.title('Phân bổ sau dự đoán toàn bộ người dùng đủ giá');save('03_quy_mo_cum')
fig,axes=plt.subplots(1,3,figsize=(12,4))
for ax,col,label in zip(axes,['median_recency','median_frequency','median_monetary'],['Recency (ngày)','Frequency (lượt đánh giá)','Monetary đại diện (USD)']):
    ax.bar(included.cluster.astype(str),included[col],color='#0284c7');ax.set_title(label);ax.set_xlabel('Cụm')
save('04_ho_so_cum')
plt.figure(figsize=(8,6));chosen=np.random.default_rng(42).choice(len(sample),min(12_000,len(sample)),replace=False)
plt.scatter(sample.iloc[chosen].recency,sample.iloc[chosen].frequency,c=sample.iloc[chosen].cluster,cmap='tab10',s=5,alpha=.35)
plt.xscale('log');plt.yscale('log');plt.xlabel('Recency (ngày, thang log)');plt.ylabel('Frequency (thang log)')
plt.title('12.000 người từ mẫu huấn luyện · Màu là cụm');save('05_phan_bo_RF')

blocks=[]
def h(s):blocks.append(('heading',s))
def p(s):blocks.append(('paragraph',s))
def table(headers,rows):blocks.append(('table',[headers]+rows))
def image(name,caption):blocks.append(('figure',(name,caption)))
h('Hoàn thiện EDA, RFM và phân cụm K-Means')
p('EDA đã hoàn thành riêng tại results/eda_sach: 8 biểu đồ và 11 bảng. Phần này bổ sung RFM toàn bộ người dùng, lựa chọn K-Means trên mẫu phân tầng và suy luận trên tất cả người dùng đủ giá. Nguồn là đánh giá đã xác minh mua hàng, không phải sổ giao dịch.')
h('1. Định nghĩa RFM và xử lý dữ liệu thiếu')
table(['Biến','Định nghĩa'],[['R — Recency',f'Số ngày từ đánh giá cuối đến {reference}; giá trị nhỏ là gần mốc dữ liệu hơn.'],['F — Frequency','Số lượt đánh giá đã xác minh sau làm sạch, không phải số đơn hàng.'],['M — Monetary','Tổng giá trị đại diện theo estimated_revenue; dùng giá thu thập, không phải số tiền đã thanh toán.'],['price_coverage','Số lượt có giá hợp lệ / tổng lượt đánh giá của người dùng.']])
p(f'Tính RFM cho 8.353.809 người dùng trên 20.342.188 dòng. Mốc {reference} là ngày sau đánh giá cuối, không phải ngày hiện tại. M giữ NULL nếu tất cả giá thiếu; tổng quan sát một phần không được coi là tổng chi tiêu đầy đủ. Có {predicted:,} người đủ giá toàn bộ ({100*predicted/8_353_809:.2f}%) được phân cụm, {excluded:,} người không đủ giá được giữ trong đầu ra với cluster=-1, không gán M=0 để ép vào K-Means.')
p('Loại nhóm thiếu giá khỏi mô hình tạo thiên lệch chọn mẫu. Phân cụm chỉ đại diện nhóm đủ giá và không được suy rộng cho toàn bộ khách hàng. price_coverage và số lượt có giá được giữ để kiểm tra; có thể nghiên cứu mô hình RF riêng cho nhóm thiếu giá nhưng chưa triển khai trong phần này.')
h('2. Lấy mẫu và biến đổi')
p(f'Mẫu {len(sample):,} người lấy từ tập đủ giá, phân tầng theo F: 1, 2, 3–5, 6–10, 11–50, >50; phân bổ gần tỷ lệ số người từng tầng. Trong tầng chọn bằng hash xác định của customer_key với seed 20261109, không lấy ngẫu nhiên lượt đánh giá vì sẽ làm người hoạt động nhiều dễ được chọn hơn. Đã kiểm tra kích thước, khóa duy nhất và đúng quota từng tầng.')
p('Biến đổi log1p(R), log1p(F), log1p(M) để giảm lệch, sau đó StandardScaler để các biến có thang đo tương đương. Scaler chỉ fit trên mẫu huấn luyện và được dùng lại khi dự đoán toàn bộ. Không sử dụng nhãn thật, nên không có độ chính xác phân loại hoặc kiểm tra dự đoán hành vi tương lai.')
h('3. Chọn k và kiểm tra seed')
p('Thử k=2,3,4,5; mỗi k với seed 42, 2026, 1109; mỗi mô hình n_init=10, max_iter=300. Silhouette dùng cùng 3.000 người lấy ngẫu nhiên từ mẫu để kiểm soát chi phí khoảng cách. Chọn k có silhouette trung bình cao nhất qua ba seed, sau đó chọn seed có silhouette cao nhất tại k đó. Đây là tiêu chí mô tả trên mẫu, chưa kiểm tra ổn định qua các mẫu độc lập.')
table(['k','Silhouette TB','SD','ARI TB','Cụm nhỏ nhất (%)'],[[str(int(r.k)),f'{r.mean_silhouette:.4f}',f'{r.std_silhouette:.4f}',f'{r.mean_ari:.4f}',f'{r.min_cluster_pct:.2f}'] for r in summary.itertuples()])
p(f'Chọn k={best_k}, seed={best_seed}; ARI trung bình {metadata["mean_ari"]:.4f}. ARI so độ nhất quán giữa nhãn của ba seed trên cùng 150.000 người, không phụ thuộc việc hoán đổi số thứ tự cụm. Kết quả không chứng minh đây là số nhóm khách hàng thật trong thị trường.')
image('01_chon_k','Hình 1. Silhouette và inertia khi thử k=2–5.')
image('02_do_on_dinh','Hình 2. Độ ổn định giữa các seed trên cùng mẫu.')
h('4. Hồ sơ cụm trên toàn bộ nhóm đủ giá')
table(['Cụm','Số người','% toàn bộ','R trung vị','F trung vị','M trung vị'],[[str(int(r.cluster)),f'{int(r.users):,}',f'{r.population_pct:.2f}',f'{r.median_recency:.0f}',f'{r.median_frequency:.0f}',f'{r.median_monetary:.2f}'] for r in profiles.itertuples()])
image('03_quy_mo_cum','Hình 3. Quy mô cụm, gồm nhóm không được phân cụm do thiếu giá.')
image('04_ho_so_cum','Hình 4. RFM trung vị trong từng cụm được suy luận.')
for r in included.itertuples():
    p(f'Cụm {int(r.cluster)}: {int(r.users):,} người; đánh giá cuối cách mốc {r.median_recency:.0f} ngày (trung vị), F trung vị {r.median_frequency:.0f}, M đại diện trung vị {r.median_monetary:.2f} USD. Cần đối chiếu ba biến đồng thời để mô tả mức hoạt động, không gọi nhóm này là khách hàng lợi nhuận cao hay có nguy cơ rời bỏ chỉ từ mô hình hiện tại.')
image('05_phan_bo_RF','Hình 5. Hai chiều R–F trên mẫu; mô hình thực tế dùng cả ba biến.')
p('Số thứ tự cụm là nhãn kỹ thuật và không có thứ hạng tốt/xấu. Biểu đồ hai chiều chỉ là phép chiếu: các điểm trùng trên R–F vẫn có thể khác cụm do M. Mô hình được dự đoán theo batch 100.000 dòng để không phải nạp toàn bộ hơn 8 triệu người vào RAM cùng lúc.')
h('5. Kiểm chứng và tệp bàn giao')
p('Đã xác nhận số người và tổng lượt RFM khớp warehouse, R>=1, biến mô hình hữu hạn/không âm, sample không trùng khóa, mỗi k sinh đủ k cụm. Đã kiểm tra số người dự đoán cộng nhóm loại bằng 8.353.809 và tổng hồ sơ cụm khớp toàn bộ. Chưa có đánh giá tính hữu ích bằng nhãn kinh doanh độc lập.')
p('rfm_all_users.parquet: RFM gốc cho toàn bộ người; rfm_with_clusters.parquet: toàn bộ RFM kèm cluster, -1 nghĩa là loại do thiếu giá; cluster_profiles.csv: hồ sơ cụm; model_selection.csv, kmeans_metrics.csv và seed_stability.csv: bằng chứng chọn mô hình; training_sample*.parquet: mẫu tái lập; model.joblib: scaler và mô hình, chỉ nạp từ nguồn tin cậy; run_metadata.json: mốc, seed và checksum mẫu. Mã nguồn src/09_rfm_kmeans.py.')
p('Hạng mục EDA–RFM–K-Means đã có sản phẩm và kết quả. Chưa hoàn thành báo cáo tổng thể, từ điển dữ liệu hoặc các kỹ thuật tối ưu mở rộng. Các kết quả phân cụm cần trình bày là phân nhóm hành vi đánh giá theo giá đại diện, không phải phân khúc mua hàng đã xác thực.')

md=[];body=[]
for kind,c in blocks:
    if kind=='heading':md.append('## '+c);body.append('<h2>'+html.escape(c)+'</h2>')
    elif kind=='paragraph':md.append(c);body.append('<p>'+html.escape(c)+'</p>')
    elif kind=='table':
        md.append('\n'.join(['| '+' | '.join(c[0])+' |','|'+'---|'*len(c[0])]+['| '+' | '.join(r)+' |' for r in c[1:]]))
        body.append('<table>'+''.join('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in r)+'</tr>' for r in c)+'</table>')
    else:
        name,caption=c;md.append(f'![{caption}](figures/{name}.png)')
        encoded=base64.b64encode((OUT/'figures'/(name+'.png')).read_bytes()).decode()
        body.append(f'<figure><img src="data:image/png;base64,{encoded}"><figcaption>{html.escape(caption)}</figcaption></figure>')
(OUT/'RFM_KMeans.md').write_text('\n\n'.join(md),encoding='utf-8')
(OUT/'RFM_KMeans.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><title>RFM và K-Means</title><style>body{font:16px/1.65 Arial;max-width:1100px;margin:35px auto;padding:0 20px;color:#172033}img{width:100%}figure{margin:28px 0}table{border-collapse:collapse;width:100%;font-size:14px}td{border:1px solid #cbd5e1;padding:8px}tr:first-child{background:#eef2f6;font-weight:bold}@media print{figure,table{break-inside:avoid}}</style>'+''.join(body)+'</html>',encoding='utf-8')
(OUT/'report_blocks.json').write_text(json.dumps(blocks,ensure_ascii=False),encoding='utf-8')
con.close()
print('Complete:',metadata,flush=True)
