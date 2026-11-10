"""Refresh handover and editable docs after verified extended Colab results."""
import json
import shutil
from pathlib import Path
from docx import Document
from docx.shared import Pt

ROOT=Path(__file__).resolve().parents[1]
def document():
    d=Document();d.styles['Normal'].font.name='Times New Roman';d.styles['Normal'].font.size=Pt(12)
    return d
def add_table(d,headers,rows):
    t=d.add_table(rows=1,cols=len(headers));t.style='Table Grid'
    for i,v in enumerate(headers):t.rows[0].cells[i].text=v
    for row in rows:
        cells=t.add_row().cells
        for i,v in enumerate(row):cells[i].text=str(v)
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                for r in p.runs:r.font.size=Pt(10)
    return t
def markdown_doc(files,target):
    d=document()
    for index,file in enumerate(files):
        if index:d.add_page_break()
        lines=file.read_text(encoding='utf-8').splitlines();i=0
        while i<len(lines):
            line=lines[i]
            if line.startswith('|'):
                rows=[]
                while i<len(lines) and lines[i].startswith('|'):
                    cells=[v.strip().replace('`','') for v in lines[i].strip('|').split('|')]
                    if not all(set(v)<=set('-: ') for v in cells):rows.append(cells)
                    i+=1
                add_table(d,rows[0],rows[1:]);continue
            if line.startswith('# '):d.add_heading(line[2:],0)
            elif line.startswith('## '):d.add_heading(line[3:],1)
            elif line and not line.startswith('```'):d.add_paragraph(line.replace('`',''))
            i+=1
    d.save(target)

validation=json.loads((ROOT/'results/postgres_extended_colab/validation.json').read_text())
data_checks=json.loads((ROOT/'results/tests/data_validation.json').read_text())
assert validation['verified_runs']==400 and data_checks['passed']==37
d=document();d.add_heading('TÀI LIỆU BÀN GIAO ĐỀ TÀI — CẬP NHẬT',0)
d.add_paragraph('Xây dựng bộ dữ liệu về kinh doanh sách và thực hiện các phương pháp tối ưu hiệu năng cho hệ thống khi dữ liệu quá lớn')
d.add_paragraph('Ngày cập nhật: 11/11/2026. Học phần: Nhập môn Khoa học dữ liệu.')
d.add_paragraph('Thành viên: Nguyễn Phạm Minh Thức — N23DCCN129; Nguyễn Thành Nam — N23DCCN108. Giảng viên hướng dẫn: ThS. Nguyễn Ngọc Duy.')
d.add_heading('1. Hiện trạng và phạm vi',1)
add_table(d,['Hạng mục','Trạng thái và sản phẩm'],[
 ['Dữ liệu','20.342.188 đánh giá đã xác minh sau làm sạch; warehouse và nguồn có checksum.'],
 ['Tối ưu cơ bản','Đã kiểm chứng 720 lượt: Pandas CSV/chọn cột/Parquet, DuckDB, PostgreSQL trước/sau B-tree.'],
 ['Tối ưu PostgreSQL bổ sung','Đã kiểm chứng 400 lượt: work_mem 4/32/64 MB và materialized view Q1/Q5; 40 lần refresh.'],
 ['EDA, RFM, K-Means','Đã có: 8 biểu đồ EDA; RFM 8.353.809 người; K-Means k=2 cho 5.821.888 người đủ giá.'],
 ['Từ điển và kiểm thử','7 bộ dữ liệu, 58 cột; 13 test project + 37 kiểm tra dữ liệu thật đạt.'],
 ['Dashboard','Đã có Streamlit + DuckDB, 4 trang; trang hiệu năng tách hai đợt, 6 AppTest đạt.'],
 ['Báo cáo','Word/PDF 6 chương, đã cập nhật work_mem/MV và thông tin thành viên.'],
 ['Chưa triển khai','Polars, BRIN, partition, ghi nguồn đồng thời, phân trang, xấp xỉ, Redis. Chỉ làm thêm nếu yêu cầu.'],
 ['Chuẩn bị bảo vệ','Slide, demo, rà định dạng và xác nhận phạm vi với giảng viên chưa được coi là hoàn tất.']])
d.add_heading('2. Hai đợt thực nghiệm phải giữ riêng',1)
d.add_paragraph('Đợt optimized_4sizes_1109_111529: 720 lượt, 4 quy mô × 6 engine × 6 truy vấn × 5 lần. Đợt pg_extended_1110_132250: 400 lượt, 4 quy mô × (3 mức work_mem × 6 truy vấn + 2 truy vấn materialized view) × 5 lần. Tổng 1.120 lượt chính ở hai đợt độc lập; 40 lần refresh được lưu như chi phí duy trì, không tính vào 1.120. Không tính speedup bằng cách chia thời gian từ hai đợt.')
d.add_paragraph('Đợt bổ sung có baseline postgres_4mb mới, max_parallel_workers_per_gather=2. Trên mức đầy đủ: Q2 64 MB nhanh khoảng 1,13 lần; Q5 32 MB khoảng 1,28 lần. MV Q1 khoảng 331,24 lần, MV Q5 khoảng 128,17 lần. Tạo MV tháng/ngày lần lượt 9,844/6,080 giây; refresh trung vị 9,709/4,848 giây. Không suy diễn tăng work_mem luôn nhanh hơn.')
d.add_heading('3. Ý nghĩa dữ liệu và giới hạn',1)
d.add_paragraph('Đánh giá xác minh là đại diện hoạt động mua, không phải giao dịch thật. Quantity=1 là giả định, ngày là ngày đánh giá, giá là giá thu thập. Tồn kho và giá vốn mô phỏng có cờ. Không dùng estimated_revenue để khẳng định doanh thu. RFM neo 2023-09-15, nhóm thiếu bất kỳ giá nào không đưa vào K-Means; -1 là nhãn loại do thiếu giá, không phải một cụm huấn luyện.')
d.add_paragraph('MV đọc kết quả lưu sẵn, có thể cũ khi nguồn thay đổi. Refresh được đo đầy đủ trên nguồn không đổi, không có ghi đồng thời hoặc incremental refresh. work_mem là theo thao tác/worker; chưa đo tổng RAM server PostgreSQL. Cache và dao động Colab vẫn giới hạn phép so sánh.')
d.add_heading('4. Vị trí tài nguyên',1)
add_table(d,['Nội dung','Đường dẫn'],[
 ['Project',str(ROOT)],['Warehouse',str(ROOT/'data/warehouse')],
 ['Báo cáo',str(ROOT/'reports/Bao_cao_kinh_doanh_sach.docx')],
 ['Hiệu năng cơ bản',str(ROOT/'results/phan_tich_thuc_nghiem_colab')],
 ['Hiệu năng bổ sung',str(ROOT/'results/postgres_extended_colab')],
 ['EDA / RFM',str(ROOT/'results/eda_sach')+'; '+str(ROOT/'results/rfm_kmeans')],
 ['Kiểm thử / từ điển',str(ROOT/'results/tests')+'; '+str(ROOT/'docs')],
 ['Dashboard',str(ROOT/'dashboard/app.py')+' — http://localhost:8501 khi server chạy'],
 ['Notebook bổ sung','D:\\Bo_sung_PostgreSQL_Colab.ipynb'],
 ['Drive','My Drive/book-sales-colab/results/pg_extended_1110_132250 (tài khoản người dùng tự quản lý)']])
d.add_heading('5. Chạy lại và kiểm tra',1)
for text in ['.venv\\Scripts\\python run_tests.py',
 '.venv\\Scripts\\python -m unittest discover -s dashboard\\tests -v',
 '.venv\\Scripts\\python src\\14_analyze_postgres_extended.py',
 '.venv\\Scripts\\python -m streamlit run dashboard\\app.py --server.address 127.0.0.1 --server.port 8501',
 'python src\\12_build_final_report.py (dùng Python hệ thống có python-docx, PyMuPDF và ReportLab)']:
    d.add_paragraph(text)
d.add_paragraph('Phân tích mới không chạy lại Colab; script 14 đọc ZIP gốc tại Downloads, kiểm chứng và tạo dữ liệu dẫn xuất. Giữ ZIP gốc hoặc sửa ARCHIVE khi chuyển máy. Mỗi notebook chạy lại cần tag mới; không ghi đè các bộ dữ liệu đã có tùy tiện. Dashboard chỉ đọc tổng hợp, không cần bật PostgreSQL.')
d.add_heading('6. Việc tiếp theo trước khi nộp',1)
d.add_paragraph('Rà báo cáo và cập nhật mục lục trong Word, chuẩn bị slide/demo, tự giải thích quy trình và thống nhất phạm vi với giảng viên. Báo cáo đã ghi rõ AI hỗ trợ mã và tài liệu. Không tự đánh dấu mọi mục mở rộng trong kế hoạch cũ là đã làm.')
target=Path('D:/Ban_giao_de_tai_kinh_doanh_sach.docx')
backup=ROOT/'docs/archive/Ban_giao_truoc_cap_nhat_20261111.docx'
backup.parent.mkdir(exist_ok=True,parents=True)
if target.exists() and not backup.exists():shutil.copy2(target,backup)
d.save(target);d.save(ROOT/'docs/Ban_giao_cap_nhat.docx')
markdown_doc([ROOT/'docs/DATA_DICTIONARY.md',ROOT/'docs/TESTING.md'],ROOT/'docs/Tu_dien_du_lieu_va_kiem_thu.docx')
markdown_doc([ROOT/'docs/POSTGRES_EXTENDED.md'],ROOT/'docs/POSTGRES_EXTENDED.docx')
test_summary={'unit_tests_passed':13,'data_checks_passed':37,'data_checks_total':37,'dashboard_tests_passed':6,
 'verified_basic_runs':720,'verified_extended_runs':400,'verified_refresh_operations':40,
 'dictionary_datasets':7,'dictionary_columns':58,'dashboard':'implemented locally; two experiment sessions kept separate'}
(ROOT/'results/tests/handover_summary.json').write_text(json.dumps(test_summary,indent=2),encoding='utf-8')
(ROOT/'dashboard/test_results.json').write_text(json.dumps({'tests':6,'passed':6,'visual_browser_inspection':False,
 'scope':'all 4 pages; both experiment sessions; new baseline and MV costs'},indent=2),encoding='utf-8')
print('Updated handover, editable documentation and test summaries.')
