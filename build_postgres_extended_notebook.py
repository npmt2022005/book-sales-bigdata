import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PACKAGE=ROOT/'colab_upload/book-sales-colab'
source=json.loads((PACKAGE/'run_4sizes_5repeats_colab.ipynb').read_text(encoding='utf-8'))
def cell(kind,text):
    result={'cell_type':kind,'metadata':{},'source':text.splitlines(keepends=True)}
    if kind=='code':ast.parse(text);result.update(execution_count=None,outputs=[])
    return result
intro='''# Bổ sung PostgreSQL: work_mem và materialized view

Mặc định: 4 mức 1m, 5m, 10m và toàn bộ 20.342.188 dòng, mỗi mức 5 lần.
Baseline 4 MB, work_mem 32/64 MB: Q1–Q6; materialized view 4 MB: Q1 và Q5.
Tổng cộng 400 phép đo chính, thêm chi phí tạo/làm mới/dung lượng và EXPLAIN.

Chọn CPU → Run all → cho phép Drive chứa My Drive/book-sales-colab.
Mã nguồn nhúng sẵn; không cần tải script riêng. Notebook không sử dụng số liệu
cũ làm baseline và không thay đổi warehouse trên Drive. Giữ tab mở và theo dõi RAM.
Có thể sửa PLAN=['full'] ở ô đầu nếu chỉ muốn đo mức chính; baseline vẫn được đo lại.
'''
setup=''.join(source['cells'][1]['source']).replace("'optimized_4sizes_' + SESSION","'pg_extended_' + SESSION")
prepare=''.join(source['cells'][2]['source']).split("(WORK / 'src/05_benchmark_baseline.py').write_text(",1)[0]
for name in ['05_benchmark_baseline.py','06_benchmark_optimized.py','13_benchmark_postgres_extended.py','test_benchmark_optimized.py','test_postgres_extended.py']:
    text=(ROOT/'src'/name).read_text(encoding='utf-8');ast.parse(text)
    prepare+=f"(WORK / 'src/{name}').write_text({text!r}, encoding='utf-8')\n"
install=''.join(source['cells'][3]['source'])
install+='''
# Validate MV semantics and per-session work_mem in isolated temporary schemas.
tested = subprocess.run([sys.executable, str(WORK / 'src/test_postgres_extended.py')],
                        cwd=WORK, capture_output=True, text=True)
print(tested.stdout, tested.stderr)
assert tested.returncode == 0, 'Extended PostgreSQL tests failed.'
'''
run='''# 4. Measure new baseline and extended configurations in this runtime.
completed = []
for size in PLAN:
    tag = 'pgx_' + size + '_' + SESSION
    local_results = WORK / 'results' / tag
    saved_results = SESSION_DIR / tag
    saved_results.mkdir(exist_ok=False)
    command = [sys.executable, '-u', str(WORK / 'src/13_benchmark_postgres_extended.py'),
               '--sizes', size, '--repeats', str(REPEATS), '--tag', tag,
               '--min-free-gb', '1.0', '--timeout', '900']
    print('START:', size, '|', saved_results, flush=True)
    process = subprocess.Popen(command, cwd=WORK, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        with (saved_results / 'console.log').open('w', encoding='utf-8') as console:
            for line in process.stdout:
                print(line, end='', flush=True)
                console.write(line); console.flush()
                for name in ['summary.json', 'runs.jsonl']:
                    if (local_results / name).exists():
                        shutil.copy2(local_results / name, saved_results / name)
            process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        if local_results.exists():
            shutil.copytree(local_results, saved_results, dirs_exist_ok=True)
    assert process.returncode == 0, f'Incomplete {size}; inspect {saved_results}/console.log'
    summary = json.loads((saved_results / 'summary.json').read_text())
    item = summary['sizes'][size]
    runs = item['runs']
    assert len(runs) == 20 * REPEATS
    assert all(r['status'] == 'ok' and r.get('matches_reference') for r in runs)
    assert all(v['refresh_matches_reference'] for v in item['materialized_views'].values())
    completed.append({'size': size, 'tag': tag, 'measured_runs': len(runs)})
    (SESSION_DIR / 'completed.json').write_text(json.dumps(completed, indent=2))
    print('SAVED:', size, '|', len(runs), 'verified measurements', flush=True)
print('EXTENDED BENCHMARK COMPLETE:', SESSION_DIR)
'''
end='''# 5. Export query medians plus separate preparation/refresh costs.
import pandas as pd
tables = []
costs = []
for record in completed:
    path = SESSION_DIR / record['tag']
    tables.append(pd.read_csv(path / 'comparison.csv'))
    info = json.loads((path / 'summary.json').read_text())['sizes'][record['size']]
    for name, values in info['materialized_views'].items():
        costs.append({'size': record['size'], 'view': name,
                      'create_seconds': values['create_seconds'],
                      'analyze_seconds': values['analyze_seconds'],
                      'refresh_median_s': values['refresh_median_s'],
                      'bytes': values['bytes'], 'rows': values['rows']})
comparison = pd.concat(tables, ignore_index=True)
comparison.to_csv(SESSION_DIR / 'comparison_extended_all_sizes.csv', index=False, encoding='utf-8-sig')
pd.DataFrame(costs).to_csv(SESSION_DIR / 'materialized_view_costs.csv', index=False, encoding='utf-8-sig')
display(comparison[comparison['size']=='full'])
display(pd.DataFrame(costs))
print('Download results folder after completion:', SESSION_DIR)
'''
notes='''## Diễn giải đúng

- work_mem là giới hạn theo thao tác/worker, không phải tổng RAM server. Hash còn phụ thuộc hash_mem_multiplier.
- REFRESH ở đây là tính lại toàn bộ trên nguồn không thay đổi, không phải cập nhật gia tăng hay ghi đồng thời.
- View cần làm mới khi nguồn đổi; tốc độ truy vấn không miễn phí, phải báo cả thời gian tạo/refresh/dung lượng.
- Không trộn số liệu mới với benchmark cũ để tính speedup; dùng postgres_4mb cùng phiên này.
- Mốc hòa vốn chỉ tính từ chi phí tạo và thời gian tiết kiệm mỗi truy vấn, chưa tính chi phí làm mới.
- Kết quả máy cá nhân chỉ để kiểm tra; chưa đưa vào báo cáo như kết quả Colab.
'''
notebook={k:v for k,v in source.items() if k!='cells'}
notebook['cells']=[cell('markdown',intro),cell('code',setup),cell('code',prepare),cell('code',install),cell('code',run),cell('code',end),cell('markdown',notes)]
for path in [Path('D:/Bo_sung_PostgreSQL_Colab.ipynb'),PACKAGE/'Bo_sung_PostgreSQL_Colab.ipynb']:
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
    for i,c in enumerate(json.loads(path.read_text(encoding='utf-8'))['cells']):
        if c['cell_type']=='code':ast.parse(''.join(c['source']),filename=f'cell_{i}')
    print('Notebook verified:',path)
