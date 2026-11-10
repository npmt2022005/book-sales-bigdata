"""Build reproducible figures and a Vietnamese report from the verified Colab ZIP."""
import base64
import argparse
import csv
import html
import json
import statistics
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive',type=Path,default=Path.home()/'Downloads/results-20261109T144133Z-1-001.zip')
ARCHIVE=parser.parse_args().archive
PREFIX = 'results/optimized_4sizes_1109_111529/'
OUT = ROOT / 'results/phan_tich_thuc_nghiem_colab'
OUT.mkdir(exist_ok=True)
FIG = OUT / 'figures'
FIG.mkdir(exist_ok=True)
SIZES = ['1m', '5m', '10m', 'full']
X = [1, 5, 10, 20.342188]
ENGINES = ['pandas_csv', 'pandas_columns', 'pandas_parquet', 'duckdb', 'postgres', 'postgres_index']
LABELS = ['Pandas CSV', 'CSV chọn cột', 'Pandas Parquet', 'DuckDB Parquet', 'PostgreSQL', 'PostgreSQL + index']
COLORS = ['#64748b', '#ca8a04', '#0284c7', '#059669', '#9333ea', '#dc2626']
QUERIES = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6']
DESCRIPTIONS = ['Theo tháng', 'Top sách theo thể loại', 'Lịch sử người dùng', 'Số người dùng theo năm', 'Trung bình trượt 7 ngày', 'RFM đại diện']
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})

data, plans, rows = {}, {}, []
with zipfile.ZipFile(ARCHIVE) as archive:
    for size in SIZES:
        folder = f'{PREFIX}opt_{size}_1109_111529/'
        summary = json.loads(archive.read(folder + 'summary.json'))
        item = summary['sizes'][size]
        runs = item['runs']
        assert len(runs) == 180 and all(r['status'] == 'ok' and r['matches_reference'] for r in runs)
        data[size] = {'summary': summary, 'item': item, 'stats': {}}
        for engine in ENGINES:
            for q in QUERIES:
                rr = [r for r in runs if r['engine'] == engine and r['query'] == q]
                assert len(rr) == 5
                values = [r['seconds'] for r in rr]
                stat = {'size': size, 'engine': engine, 'query': q, 'runs': 5,
                        'median_s': statistics.median(values), 'min_s': min(values), 'max_s': max(values),
                        'q1_s': float(np.quantile(values, .25)), 'q3_s': float(np.quantile(values, .75)),
                        'client_peak_gb': max(r['client_peak_gb'] for r in rr)}
                data[size]['stats'][engine, q] = stat
                rows.append(stat)
        if size == 'full':
            for engine in ['postgres', 'postgres_index']:
                for q in QUERIES:
                    name = f'full_{engine}_{q}_plan.json'
                    raw = archive.read(folder + name)
                    (OUT / name).write_bytes(raw)
                    plans[engine, q] = json.loads(raw)[0]

def value(size, engine, q):
    return data[size]['stats'][engine, q]['median_s']

for r in rows:
    baseline = 'postgres' if r['engine'].startswith('postgres') else 'pandas_csv'
    r['speedup_vs_baseline'] = value(r['size'], baseline, r['query']) / r['median_s']
with (OUT / 'bang_ket_qua_144_cau_hinh.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)

def save(fig, name):
    fig.savefig(FIG / (name + '.png'), dpi=190, bbox_inches='tight')
    fig.savefig(FIG / (name + '.pdf'), bbox_inches='tight')
    plt.close(fig)

fig, axes = plt.subplots(2, 3, figsize=(16, 9))
for q, desc, ax in zip(QUERIES, DESCRIPTIONS, axes.flat):
    for e, label, color in zip(ENGINES, LABELS, COLORS):
        y = [value(s, e, q) for s in SIZES]
        ax.plot(X, y, marker='o', label=label, color=color, linewidth=1.7)
    ax.set_title(q + ' · ' + desc); ax.set_xlabel('Triệu dòng'); ax.set_ylabel('Trung vị (giây)')
    ax.set_xticks(X, ['1', '5', '10', '20,34']); ax.grid(alpha=.2)
handles, labels = axes.flat[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', ncol=3, frameon=False)
fig.suptitle('Khả năng mở rộng theo quy mô dữ liệu · Colab, 5 lần đo/cấu hình', fontsize=15)
fig.tight_layout(rect=(0, .09, 1, .95)); save(fig, '01_xu_huong_quy_mo')

fig, ax = plt.subplots(figsize=(12, 6))
positions = np.arange(6)
for i, (engine, label, color) in enumerate(zip(ENGINES[:4], LABELS[:4], COLORS[:4])):
    med = [value('full', engine, q) for q in QUERIES]
    lower = [m - data['full']['stats'][engine, q]['q1_s'] for m, q in zip(med, QUERIES)]
    upper = [data['full']['stats'][engine, q]['q3_s'] - m for m, q in zip(med, QUERIES)]
    ax.bar(positions + (i-1.5)*.2, med, width=.19, label=label, color=color,
           yerr=[lower, upper], capsize=2, error_kw={'linewidth': .7})
ax.set_xticks(positions, QUERIES); ax.set_ylabel('Giây'); ax.set_title('20,34 triệu dòng · Trung vị và khoảng tứ phân vị (5 lần)')
ax.legend(ncol=2, frameon=False); ax.grid(axis='y', alpha=.2); fig.tight_layout(); save(fig, '02_thoi_gian_full')

fig, ax = plt.subplots(figsize=(11, 5))
for i, (engine, label, color) in enumerate(zip(ENGINES[1:4], LABELS[1:4], COLORS[1:4])):
    speed = [value('full', 'pandas_csv', q)/value('full', engine, q) for q in QUERIES]
    bars = ax.bar(positions + (i-1)*.25, speed, width=.24, label=label, color=color)
    ax.bar_label(bars, fmt='%.2f', fontsize=8, padding=2)
ax.axhline(1, color='#64748b', linestyle='--', linewidth=1)
ax.set_xticks(positions, QUERIES); ax.set_ylabel('Hệ số tăng tốc so với Pandas CSV')
ax.set_title('20,34 triệu dòng · Hệ số > 1 biểu thị nhanh hơn'); ax.legend(frameon=False)
ax.set_ylim(0, 19); fig.tight_layout(); save(fig, '03_he_so_tang_toc')

fig, ax = plt.subplots(figsize=(11, 5))
for i, engine in enumerate(ENGINES[4:]):
    med = [value('full', engine, q) for q in QUERIES]
    bars = ax.bar(positions + (i-.5)*.35, med, width=.33, label=LABELS[i+4], color=COLORS[i+4])
    ax.bar_label(bars, fmt='%.2f', fontsize=8, padding=2)
ax.set_xticks(positions, QUERIES); ax.set_ylabel('Giây'); ax.set_title('B-tree trên customer_key · Không cải thiện mọi truy vấn')
ax.legend(frameon=False); ax.set_ylim(0, 108); fig.tight_layout(); save(fig, '04_postgres_index')

storage = data['full']['item']['parquet']
tables = list(storage)
fig, ax = plt.subplots(figsize=(11, 5))
for i, (key, label, color) in enumerate([('csv_bytes','CSV','#64748b'),('parquet_bytes','Parquet Zstandard','#0284c7')]):
    vals = [storage[t][key]/1e6 for t in tables]
    bars = ax.bar(np.arange(len(tables))+(i-.5)*.35, vals, width=.33, label=label, color=color)
    ax.bar_label(bars, fmt='%.1f', fontsize=9, padding=2)
ax.set_xticks(np.arange(len(tables)), tables); ax.set_ylabel('MB thập phân'); ax.set_title('Dung lượng lưu trữ · Cùng bảng và cùng số dòng')
ax.legend(frameon=False); ax.set_ylim(0, 1200); fig.tight_layout(); save(fig, '05_dung_luong')

def walk(node):
    yield node
    for child in node.get('Plans', []):
        yield from walk(child)

evidence = []
for (engine, q), plan in plans.items():
    nodes = list(walk(plan['Plan']))
    evidence.append({'engine': engine, 'query': q, 'explain_execution_ms': plan['Execution Time'],
                     'disk_sort': any(n.get('Sort Space Type') == 'Disk' for n in nodes),
                     'index_scan': any('Index' in n['Node Type'] for n in nodes),
                     'root_temp_read_blocks': plan['Plan'].get('Temp Read Blocks', 0),
                     'root_temp_written_blocks': plan['Plan'].get('Temp Written Blocks', 0)})
(OUT/'bang_chung_ke_hoach.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')

blocks = []
def heading(text): blocks.append(('heading', text))
def paragraph(text): blocks.append(('paragraph', text))
def table(headers, contents): blocks.append(('table', [headers] + contents))
def figure(name, caption): blocks.append(('figure', (name, caption)))
heading('Phân tích thực nghiệm tối ưu hiệu năng xử lý dữ liệu sách')
paragraph('Nguồn: results-20261109T144133Z-1-001.zip; chỉ sử dụng phiên optimized_4sizes_1109_111529. Loại các baseline cũ và phiên 1109_110545 bị lỗi khỏi bảng so sánh. Mức toàn bộ gồm 20.342.188 đánh giá đã xác minh mua hàng sau làm sạch; không đồng nhất với số giao dịch thực.')
heading('1. Thiết kế và xác nhận thực nghiệm')
paragraph('Thực nghiệm gồm 4 quy mô (1, 5, 10 và 20,342188 triệu dòng), 6 cấu hình và 6 truy vấn. Mỗi tổ hợp lặp 5 lần: tổng cộng 720 lượt đo, 144 tổ hợp. Đã kiểm tra đủ số lượt và tất cả đều có status=ok, matches_reference=true. Dùng trung vị; khoảng tứ phân vị mô tả dao động, không phải khoảng tin cậy thống kê.')
machine=data['full']['summary']['machine']; settings=data['full']['item']['postgres_settings']
paragraph(f"Môi trường ghi nhận: Colab Linux, {machine['logical_cpus']} CPU logic, RAM {machine['ram_gb']} GB, Python {machine['python']}; PostgreSQL {settings['server_version']}; work_mem={settings['work_mem']}, shared_buffers={settings['shared_buffers']}, max_parallel_workers_per_gather={settings['max_parallel_workers_per_gather']}. Các tag cùng mã phiên, thông số máy tương đồng; log không có mã định danh VM để chứng minh độc lập rằng phần cứng không bị thay trong suốt phiên.")
paragraph('Đo lại baseline và tối ưu trong từng mức, chạy tuần tự, xáo thứ tự trong mỗi vòng, có lượt khởi động. Thời gian gồm mở kết nối/đọc tệp, thực thi và lấy đầy đủ kết quả về DataFrame; loại import, ghi tệp và đối chiếu. Cache hệ điều hành không bị xóa. DuckDB đặt 2 luồng; các engine không được khống chế về đúng một lõi, nên đây là so sánh cấu hình hệ thống. Không dùng thời gian script 05 hoặc máy cá nhân làm mẫu số.')
table(['Mã', 'Nội dung'], list(zip(QUERIES, DESCRIPTIONS)))
heading('2. Kết quả trên toàn bộ 20,34 triệu dòng')
table(['Truy vấn']+LABELS, [[q]+[f'{value("full", e, q):.3f}' for e in ENGINES] for q in QUERIES])
paragraph('Đơn vị: giây. Cấu hình Pandas CSV là mốc của nhóm xử lý tệp; PostgreSQL chưa index là mốc của thử nghiệm chỉ mục. Không diễn giải các tỷ số là ưu thế tuyệt đối của một sản phẩm với mọi loại công việc.')
figure('02_thoi_gian_full', 'Hình 1. Thời gian xử lý tệp: trung vị và khoảng tứ phân vị.')
figure('03_he_so_tang_toc', 'Hình 2. Hệ số tăng tốc so với Pandas CSV đầy đủ.')
for e,label in zip(ENGINES[1:4],LABELS[1:4]):
    speeds=[value('full','pandas_csv',q)/value('full',e,q) for q in QUERIES]
    paragraph(f'{label}: nhanh hơn Pandas CSV từ {min(speeds):.2f} đến {max(speeds):.2f} lần. Đây là tỷ số của hai trung vị trên cùng mức dữ liệu.')
paragraph('CSV chọn cột vẫn phải phân tích cấu trúc các dòng văn bản; chủ yếu giảm chuyển đổi và vật chất hóa các cột không cần thiết. Parquet lưu theo cột, có kiểu dữ liệu và nén; cùng việc chọn cột giúp giảm chi phí đọc và phân tích. Các giải thích này phù hợp cơ chế của công cụ, nhưng thực nghiệm chưa đo I/O hay thời gian CPU riêng để phân rã đóng góp chính xác.')
paragraph('DuckDB dùng truy vấn trực tiếp trên Parquet và bộ máy thực thi phân tích. Trên mức đầy đủ, DuckDB nhanh nhất ở Q1, Q3, Q4, Q5, Q6; Pandas Parquet nhanh nhất ở Q2 trong sáu cấu hình được đo. Không có một cấu hình thắng tất cả truy vấn.')
heading('3. Khả năng mở rộng và chi phí lưu trữ')
figure('01_xu_huong_quy_mo', 'Hình 3. Xu hướng trên 4 quy mô; mỗi điểm là trung vị 5 lượt.')
paragraph('Các đường thể hiện chi phí tăng khi dữ liệu lớn hơn. Không suy diễn độ phức tạp tiệm cận hoặc khẳng định tăng tuyến tính chỉ từ bốn điểm; kích thước bảng chiều, số người dùng riêng biệt và trạng thái cache cũng thay đổi. Q3 dùng người có nhiều lượt đánh giá nhất ở mỗi mẫu, nên không phải cùng một truy vấn chọn lọc với cùng số kết quả trên mọi quy mô.')
figure('05_dung_luong', 'Hình 4. Kích thước các bảng CSV và Parquet trong mẫu đầy đủ.')
csv_total=sum(s['csv_bytes'] for s in storage.values()); pq_total=sum(s['parquet_bytes'] for s in storage.values())
paragraph(f'Tổng bốn bảng: CSV {csv_total/1e6:.2f} MB, Parquet {pq_total/1e6:.2f} MB; giảm {(1-pq_total/csv_total)*100:.2f}%. Riêng fact_sales: {storage["fact_sales"]["csv_bytes"]/1e6:.2f} → {storage["fact_sales"]["parquet_bytes"]/1e6:.2f} MB. MB ở đây là 1.000.000 byte. Không đồng nhất kích thước các bảng benchmark với toàn bộ warehouse ban đầu.')
paragraph(f'Tạo Parquet cho bốn bảng mất tổng {sum(s["prepare_seconds"] for s in storage.values()):.2f} giây; thời gian này nằm ngoài phép đo truy vấn. Chi phí chuyển đổi cần được tính nếu hệ thống chỉ chạy một lần hoặc thường xuyên làm mới dữ liệu.')
heading('4. PostgreSQL: tác dụng và giới hạn của index')
figure('04_postgres_index', 'Hình 5. PostgreSQL trước và sau B-tree trên customer_key.')
before=value('full','postgres','Q3'); after=value('full','postgres_index','Q3'); index=data['full']['item']['index']
paragraph(f'Q3 giảm từ {before:.3f} xuống {after:.3f} giây: tăng tốc {before/after:.2f} lần, giảm thời gian {(1-after/before)*100:.2f}%. Q1, Q2, Q4 chậm hơn theo trung vị; Q5 giảm nhẹ, Q6 gần như không đổi. Không quy kết sự chậm hơn là do riêng index vì hai cấu hình nằm trên hai bản sao bảng, có khác biệt bố trí vật lý/cache và dao động phiên; chỉ báo cáo mức chênh quan sát được.')
paragraph('Bằng chứng Q3: kế hoạch baseline quét tuần tự fact_sales và lọc customer_key; cấu hình tối ưu chuyển sang Index Scan trên fact_sales_customer_key_idx. Tuy nhiên cả hai vẫn quét dim_books để nối và đọc dim_date. Index giải quyết bước tìm fact nhưng chưa loại được toàn bộ chi phí nối.')
paragraph('Q2 và Q4 có Sort dùng external merge trên Disk. Q6 cũng có sắp xếp trên đĩa và ghi/đọc tệp tạm; Q2 có Hash Batches=32 tại nút hash nối. Đây là bằng chứng các thao tác không hoàn toàn nằm trong RAM ở cấu hình work_mem=4MB. B-tree customer_key không trực tiếp xử lý các nút thắt này. Hướng thử tiếp là tăng work_mem có kiểm soát, tối ưu tổng hợp, hoặc materialized view; chưa được phép kết luận mức tăng tốc của chúng khi chưa đo.')
table(['Truy vấn', 'Baseline EXPLAIN (s)', 'Có index EXPLAIN (s)', 'Sort đĩa baseline'], [[q,f'{plans["postgres",q]["Execution Time"]/1000:.3f}',f'{plans["postgres_index",q]["Execution Time"]/1000:.3f}', 'Có' if next(r for r in evidence if r['engine']=='postgres' and r['query']==q)['disk_sort'] else 'Không'] for q in QUERIES])
paragraph('EXPLAIN được thu một lượt ngoài vòng đo, có instrumentation, không lấy đầy đủ kết quả về client và có cache khác. Các thời gian EXPLAIN chỉ hỗ trợ đọc kế hoạch, không thay cho trung vị 5 lần hoặc dùng để tính tỷ số tăng tốc chung. Không cộng Actual Total Time của các nút vì thời gian cha đã chứa con và có thực thi song song.')
paragraph(f'Chi phí chuẩn bị bản index: sao chép fact và ANALYZE {index["copy_seconds"]:.2f} giây; tạo index và ANALYZE {index["index_build_seconds"]:.2f} giây; index chiếm {index["index_bytes"]/1e6:.2f} MB. Chưa đo ảnh hưởng INSERT/UPDATE/DELETE nên chưa có kết luận về chi phí ghi.')
heading('5. Giới hạn và hướng hoàn thiện')
paragraph('Bộ nhớ ghi nhận là RSS client và tiến trình con, gồm cả bước ghi kết quả; không có RAM PostgreSQL server. Không dùng chỉ số này để xếp hạng tổng RAM giữa PostgreSQL và các engine nhúng. Mẫu 5 lượt còn nhỏ, không có kiểm định ý nghĩa thống kê và không có chu kỳ khởi động lại độc lập; chênh lệch nhỏ cần diễn giải thận trọng.')
paragraph('Kiểm tra kết quả đã chuẩn hóa thứ tự tại client để tránh khác biệt collation; vẫn giữ số dòng, giá trị và dòng trùng, số thực dùng rtol=1e-8, atol=1e-6. Đó là kiểm tra tương đương giữa các engine trên dữ liệu đã chuẩn bị, không chứng minh toàn bộ quy trình xây dựng dữ liệu không có lỗi.')
paragraph('Nguồn là đánh giá có xác minh mua hàng. Thời gian là thời điểm đánh giá, giá là giá thu thập, quantity giả định bằng 1; monetary không phải chi tiêu thực. Các nhóm hoàn toàn thiếu giá có thể nhận tổng bằng 0 theo quy tắc hiện có, không được diễn giải là người dùng không chi tiêu. Báo cáo cần giữ giới hạn này khi phân tích RFM.')
paragraph('Đã có bằng chứng cho chọn cột, Parquet, DuckDB và B-tree. Tài liệu bàn giao còn liệt kê Polars, BRIN, phân vùng, materialized view, nạp dữ liệu/phân trang, xấp xỉ; các kỹ thuật này chưa nằm trong 720 lượt đo. Tiếp theo nên chọn hạng mục theo yêu cầu giảng viên, sau đó làm EDA, từ điển dữ liệu, báo cáo tổng thể và slide.')

md=[]; sections=[]
for kind,content in blocks:
    if kind=='heading':
        md.append('## '+content); sections.append('<h2>'+html.escape(content)+'</h2>')
    elif kind=='paragraph':
        md.append(content); sections.append('<p>'+html.escape(content)+'</p>')
    elif kind=='table':
        md.append('\n'.join(['| '+' | '.join(row)+' |' for row in content[:1]]+['|'+'---|'*len(content[0])]+['| '+' | '.join(row)+' |' for row in content[1:]]))
        sections.append('<table>'+''.join('<tr>'+''.join(('<th>' if i==0 else '<td>')+html.escape(c)+('</th>' if i==0 else '</td>') for c in row)+'</tr>' for i,row in enumerate(content))+'</table>')
    else:
        name,caption=content; md.append(f'![{caption}](figures/{name}.png)')
        encoded=base64.b64encode((FIG/(name+'.png')).read_bytes()).decode()
        sections.append(f'<figure><img src="data:image/png;base64,{encoded}"><figcaption>{html.escape(caption)}</figcaption></figure>')
(OUT/'Phan_tich_thuc_nghiem.md').write_text('\n\n'.join(md)+'\n',encoding='utf-8')
page='<!doctype html><html lang="vi"><meta charset="utf-8"><title>Phân tích thực nghiệm Colab</title><style>body{font:16px/1.65 Arial,sans-serif;max-width:1150px;margin:40px auto;padding:0 24px;color:#172033}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #cbd5e1;padding:8px;text-align:left}th{background:#eef2f6}img{width:100%}figure{margin:30px 0}figcaption{color:#475569}@media print{body{margin:0}figure,table{break-inside:avoid}}</style>'+''.join(sections)+'</html>'
(OUT/'Phan_tich_thuc_nghiem.html').write_text(page,encoding='utf-8')
(OUT/'report_blocks.json').write_text(json.dumps(blocks,ensure_ascii=False),encoding='utf-8')
print('Verified 720 measurements; generated 5 PNG + 5 PDF figures, CSV, Markdown and standalone HTML:', OUT)
