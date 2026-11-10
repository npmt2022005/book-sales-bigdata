"""Package local, tested benchmark sources into a standalone Colab notebook."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / 'colab_upload/book-sales-colab'
template = json.loads((PACKAGE / 'run_full_20m_colab.ipynb').read_text(encoding='utf-8'))


def cell(kind, source):
    result = {'cell_type': kind, 'metadata': {}, 'source': source.splitlines(keepends=True)}
    if kind == 'code':
        result.update(execution_count=None, outputs=[])
        ast.parse(source)
    return result


intro = '''# Đo hiệu năng dữ liệu sách trên Google Colab

**4 quy mô: 1 triệu, 5 triệu, 10 triệu và toàn bộ 20.342.188 dòng. Mỗi quy mô đo 5 lần.**

1. Mở notebook trên Colab, chọn runtime CPU, chọn **Runtime → Run all**.
2. Đăng nhập đúng tài khoản có `My Drive/book-sales-colab/warehouse` và `manifest.json`.
3. Cho phép kết nối Drive. Không cần tải thêm script: mã nguồn đã nhúng bên trong.

Notebook đo lại cả cấu hình ban đầu và tối ưu trong cùng phiên; 20,34 triệu là mức chính.
Sáu cấu hình hiện có: Pandas CSV, CSV chọn cột, Pandas Parquet, DuckDB, PostgreSQL và PostgreSQL có B-tree trên khách hàng.
Chưa gồm Polars, BRIN, phân vùng, materialized view hoặc chi phí ghi.

Kết quả được lưu vào một thư mục phiên riêng dưới `book-sales-colab/results`.
Thời gian chạy có thể vài giờ. Nếu Colab ngắt phiên, các mức đã hoàn thành vẫn ở Drive; không gộp các mức từ máy/phiên khác nhau thành một phép so sánh cuối.
'''

setup = ''.join(template['cells'][1]['source'])
setup += '''
from datetime import datetime, timezone
SESSION = datetime.now(timezone.utc).strftime('%m%d_%H%M%S')
SESSION_DIR = DRIVE / 'results' / ('optimized_4sizes_' + SESSION)
SESSION_DIR.mkdir(exist_ok=False)
PLAN = ['1m', '5m', '10m', 'full']
REPEATS = 5
print('Results folder:', SESSION_DIR)
'''

prepare = ''.join(template['cells'][2]['source']).split("(WORK / 'src/05_benchmark_baseline.py').write_text(", 1)[0]
sources = {}
for name in ['05_benchmark_baseline.py', '06_benchmark_optimized.py', 'test_benchmark_optimized.py']:
    source = (ROOT / 'src' / name).read_text(encoding='utf-8')
    ast.parse(source)
    sources[name] = source
    prepare += f"(WORK / 'src/{name}').write_text({source!r}, encoding='utf-8')\n"

install = ''.join(template['cells'][3]['source'])
install = install.replace("(DRIVE / 'results/environment.json')", "(SESSION_DIR / 'environment.json')")
install += '''
# Run the small correctness tests before the expensive experiment.
tested = subprocess.run([sys.executable, str(WORK / 'src/test_benchmark_optimized.py')],
                        cwd=WORK, capture_output=True, text=True)
print(tested.stdout, tested.stderr)
assert tested.returncode == 0, 'Correctness tests failed; benchmark not started.'
import pyarrow.parquet as pq
rows = pq.ParquetFile(WORK / 'data/warehouse/fact_sales.parquet').metadata.num_rows
assert rows == 20_342_188, f'Unexpected full dataset size: {rows:,}'
print('Full dataset:', f'{rows:,}', 'rows')
'''

run = '''# 4. Run baseline and optimized engines together, separately for each size.
completed = []
for size in PLAN:
    tag = 'opt_' + size + '_' + SESSION
    local_results = WORK / 'results' / tag
    saved_results = SESSION_DIR / tag
    saved_results.mkdir(exist_ok=False)
    command = [sys.executable, '-u', str(WORK / 'src/06_benchmark_optimized.py'),
               '--sizes', size, '--repeats', str(REPEATS), '--tag', tag,
               '--engines', 'pandas_csv', 'pandas_columns', 'pandas_parquet',
               'duckdb', 'postgres', 'postgres_index',
               '--max-rss-gb', '8', '--min-free-gb', '1.0', '--timeout', '900']
    print('\nSTART:', size, '|', saved_results, flush=True)
    process = subprocess.Popen(command, cwd=WORK, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        with (saved_results / 'console.log').open('w', encoding='utf-8') as console:
            for line in process.stdout:
                print(line, end='', flush=True)
                console.write(line)
                console.flush()
                # Save light checkpoints during the run; full tables copied at size completion.
                for name in ['summary.json', 'runs.jsonl']:
                    source = local_results / name
                    if source.exists():
                        shutil.copy2(source, saved_results / name)
            process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if local_results.exists():
            shutil.copytree(local_results, saved_results, dirs_exist_ok=True)
    assert process.returncode == 0, f'Incomplete {size}; see {saved_results}/console.log. Do not use as final results.'
    summary = json.loads((saved_results / 'summary.json').read_text())
    runs = summary['sizes'][size]['runs']
    assert len(runs) == 6 * 6 * REPEATS
    assert all(r['status'] == 'ok' and r.get('matches_reference') for r in runs)
    completed.append({'size': size, 'tag': tag, 'measured_runs': len(runs)})
    (SESSION_DIR / 'completed.json').write_text(json.dumps(completed, indent=2))
    print('SAVED:', size, '|', len(runs), 'verified measurements', flush=True)
print('ALL FOUR SIZES COMPLETE:', SESSION_DIR)
'''
# Preserve the literal escaped newline in the generated Python source.
run = run.replace("print('\nSTART:", "print('\\nSTART:")

summary = '''# 5. Combine the verified comparison tables; preserve the full machine/environment records.
import pandas as pd
tables = []
for record in completed:
    tables.append(pd.read_csv(SESSION_DIR / record['tag'] / 'comparison.csv'))
comparison = pd.concat(tables, ignore_index=True)
comparison.to_csv(SESSION_DIR / 'comparison_all_sizes.csv', index=False, encoding='utf-8-sig')
print('Main comparison: full dataset, 20,342,188 rows')
display(comparison[comparison['size'] == 'full'])
print('Scaling comparison: median seconds')
display(comparison.pivot(index=['query', 'engine'], columns='size', values='median_seconds').reindex(columns=PLAN))
print('Results saved to:', SESSION_DIR)
'''

notes = '''## Cách sử dụng kết quả

- Mỗi mức có 180 phép đo; tổng cộng **720 phép đo**, ngoài các lượt tham chiếu, khởi động và EXPLAIN.
- Thời gian tính cả đọc/truy vấn và đưa kết quả đầy đủ về client; không tính import, ghi tệp kết quả và đối chiếu.
- Đối chiếu từng dòng; số thực có dung sai để chấp nhận khác biệt cộng dồn.
- `comparison_all_sizes.csv` dùng cho bảng báo cáo và vẽ xu hướng. Các tệp `*_plan.json` phục vụ giải thích PostgreSQL.
- Bộ nhớ ghi nhận là RSS của client và tiến trình con, không bao gồm PostgreSQL server.
- Không chia thời gian baseline cũ của script 05 cho thời gian script 06: dùng baseline được đo lại trong chính notebook này.
- Dữ liệu là đánh giá có xác minh mua hàng; giá trị tiền và RFM là đại diện, không phải doanh thu/giao dịch thực.
- Nếu một mức lỗi hoặc thiếu RAM, notebook dừng và lưu phần đã chạy. Không coi phép đo thiếu là kết quả hoàn chỉnh.
'''

notebook = {key: value for key, value in template.items() if key != 'cells'}
notebook['cells'] = [cell('markdown', intro), cell('code', setup), cell('code', prepare),
                     cell('code', install), cell('code', run), cell('code', summary), cell('markdown', notes)]
for target in [PACKAGE / 'run_4sizes_5repeats_colab.ipynb', Path('D:/Chay_de_tai_sach_Colab.ipynb')]:
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
    loaded = json.loads(target.read_text(encoding='utf-8'))
    for i, item in enumerate(loaded['cells']):
        if item['cell_type'] == 'code':
            ast.parse(''.join(item['source']), filename=f'cell_{i}')
    print('Created and syntax checked:', target)

# Check that every embedded script round-trips unchanged, without running Drive/Colab operations.
tree = ast.parse(prepare)
extracted = {}
for node in tree.body:
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == 'write_text' and call.args:
            content = ast.literal_eval(call.args[0])
            for name, source in sources.items():
                if content == source:
                    extracted[name] = content
assert extracted == sources
print('Verified all three embedded scripts match local sources exactly.')
