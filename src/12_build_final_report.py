"""Compose project report using Group 7's structure, not its research content."""
import copy
import os
import csv
import json
import re
import shutil
from pathlib import Path
import pymupdf
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.platypus import BaseDocTemplate,PageTemplate,Frame,Paragraph,Spacer,PageBreak,Table,TableStyle,Image,NextPageTemplate,KeepTogether,CondPageBreak
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_JUSTIFY,TA_CENTER
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports';OUT.mkdir(exist_ok=True)
REPORT_SUFFIX=os.environ.get('BOOK_REPORT_SUFFIX','')
ASSETS=ROOT/'docs/template_nhom7'
if not list(ASSETS.glob('logo.*')) or not list(ASSETS.glob('border.*')):
    template=pymupdf.open(r'C:\Users\ACER\Downloads\Nhom7_NhapMonKhoaHocDuLieu.pdf')
    for xref,name in [(9,'border'),(23,'logo')]:
        item=template.extract_image(xref)
        (ASSETS/(name+'.'+item['ext'])).write_bytes(item['image'])
logo=next(ASSETS.glob('logo.*'));border=next(ASSETS.glob('border.*'))
TITLE='Xây dựng bộ dữ liệu về kinh doanh sách và thực hiện các phương pháp tối ưu hiệu năng cho hệ thống khi dữ liệu quá lớn'
SUPERVISOR='ThS. Nguyễn Ngọc Duy'
MEMBERS=['Nguyễn Phạm Minh Thức — N23DCCN129','Nguyễn Thành Nam — N23DCCN108']
CHAPTERS=['Giới thiệu đề tài','Cơ sở lý thuyết và nền tảng kỹ thuật','Phân tích và thiết kế ứng dụng','Hiện thực hệ thống','Vận hành và kết quả thực nghiệm','Kết luận và đánh giá khả năng ứng dụng']
blocks=[]
def h(t):blocks.append(('heading',t))
def p(t):blocks.append(('paragraph',t))
def table(headers,rows):blocks.append(('table',[headers]+rows))
def chapter(n):blocks.append(('chapter',f'Chương {n} {CHAPTERS[n-1]}'))
chapter(1)
h('1.1. Bối cảnh và vấn đề nghiên cứu')
p('Dữ liệu về sách trên thương mại điện tử có nhiều dạng: danh mục sản phẩm, đánh giá của người dùng và giao dịch bán hàng. Khi số bản ghi tăng lên hàng chục triệu, thao tác đọc tệp, ghép bảng, đếm phân biệt và tổng hợp có thể mất nhiều thời gian. Đề tài xây dựng một quy trình chuẩn bị dữ liệu có thể chạy lại và đánh giá các cấu hình xử lý bằng số đo thực tế, thay vì chỉ mô tả ưu điểm lý thuyết của công nghệ.')
p('Nguồn được chọn là Amazon Reviews 2023, nhóm Books, do McAuley Lab công bố [1]. Đơn vị quan sát của dữ liệu cuối là một lượt đánh giá đã xác minh mua hàng sau làm sạch, không phải đơn hàng. Sự phân biệt này quyết định cách đặt tên biểu đồ, tính RFM và giới hạn kết luận kinh doanh. Tên bảng fact_sales được giữ theo mã nguồn lịch sử nhưng không được xem là sổ doanh thu.')
h('1.2. Mục tiêu và câu hỏi')
p('Mục tiêu là xây dựng kho dữ liệu thông tin sách và đánh giá, thực nghiệm tối ưu truy vấn theo quy mô, phân tích mô tả, phân nhóm người dùng và cung cấp dashboard để tra cứu kết quả. Đề tài không đề xuất thuật toán mới; đóng góp là quy trình có dữ liệu, mã thực thi, kết quả và kiểm chứng đi kèm.')
table(['Câu hỏi','Bằng chứng trả lời'],[['Dữ liệu sau xử lý có cấu trúc và chất lượng ra sao?','Lược đồ hình sao, từ điển 58 cột, báo cáo làm sạch và 37 kiểm tra dữ liệu.'],['Khi tăng từ 1 lên 20,34 triệu dòng, thời gian thay đổi thế nào?','720 phép đo trong cùng mã phiên Colab, trung vị 5 lần/tổ hợp.'],['Chọn cột, Parquet, DuckDB và index có hiệu quả ra sao?','So sánh baseline đo lại trong phiên và kế hoạch PostgreSQL.'],['Dữ liệu thể hiện đặc điểm đánh giá và cấu trúc nhóm nào?','EDA, RFM toàn bộ người dùng và K-Means trên mẫu phân tầng.']])
h('1.3. Phạm vi ứng dụng')
table(['Thành phần','Phạm vi','Giới hạn'],[['Nguồn','Books: review và metadata','Không có giao dịch bán hàng công khai đi kèm.'],['Thời gian','12/02/1997–14/09/2023 trong tập sạch','Không đại diện hành vi hiện tại.'],['Giá','Giá thu thập, USD, 0 < giá ≤ 1.000','Không có giá lịch sử tại từng lần mua.'],['Tồn kho và giá vốn','Bổ sung mô phỏng, có cờ','Không kết luận tồn kho hoặc lợi nhuận thực.'],['Triển khai','Dashboard cục bộ Streamlit + DuckDB','Chưa có phân quyền hay kiểm thử tải đa người.']])
p('Khái niệm dữ liệu quá lớn được hiểu theo thời gian phản hồi, không khẳng định Pandas không chạy được. Đã thử chọn cột, Parquet, DuckDB, B-tree, work_mem và materialized view. Đợt cơ bản có 720 lượt đo; đợt PostgreSQL bổ sung có 400 lượt. Hai đợt có baseline riêng, không trộn thời gian để tính mức tăng tốc. Polars, BRIN, phân vùng, chi phí ghi/phân trang và xấp xỉ còn là hướng phát triển.')
chapter(2)
h('2.1. Chuẩn bị dữ liệu và lược đồ phân tích')
p('Quy trình dữ liệu gồm lưu nguồn, chuyển đổi định dạng, khảo sát chất lượng, chuẩn hóa, liên kết và kiểm tra bất biến. Phân biệt kiểm tra cú pháp với kiểm tra ngữ nghĩa: một ISBN có 13 chữ số chưa chứng minh checksum hợp lệ; mã người đánh giá không chứng minh lịch sử giao dịch đầy đủ. Kho dữ liệu dùng bảng sự kiện và bảng chiều để biểu diễn đơn vị quan sát cùng thông tin mô tả.')
p('Lược đồ hình sao gồm fact_sales liên kết dim_books, dim_customers và dim_date. Ưu điểm thiết kế là tách thông tin mô tả khỏi sự kiện và hỗ trợ tổng hợp theo thời gian/sản phẩm/người dùng. Thực nghiệm hiện không so sánh hình sao với mọi lược đồ khác, nên không có kết luận định lượng riêng về lợi ích của lược đồ.')
h('2.2. Định dạng cột và hệ thống xử lý')
p('CSV biểu diễn dữ liệu văn bản; chọn cột giúp giảm chuyển đổi và vật chất hóa cột không dùng. Parquet lưu theo cột và có nén, phù hợp truy vấn đọc một phần thuộc tính. DuckDB có thể truy vấn trực tiếp Parquet và đẩy việc chọn cột xuống bước đọc [2]. Các đặc điểm này là cơ sở đặt giả thuyết tối ưu, còn mức cải thiện phải dựa trên Chương 5.')
h('2.3. Chỉ mục và kế hoạch thực thi')
p('B-tree hỗ trợ các điều kiện bằng hoặc khoảng trên giá trị có thứ tự [3]. Truy vấn Q3 lọc customer_key là ứng viên sử dụng index, trong khi truy vấn tổng hợp toàn bộ dữ liệu có thể vẫn chọn quét tuần tự. EXPLAIN ANALYZE cung cấp kế hoạch có số đo; thời gian tại nút cha chứa công việc nút con, nên không cộng đơn giản để tính tổng.')
h('2.4. RFM, K-Means và đánh giá cụm')
p('RFM biểu diễn thời gian từ hoạt động cuối, số lần hoạt động và giá trị tiền quan sát. Trong đề tài này, cả ba đều xuất phát từ đánh giá và giá metadata, nên được gọi là RFM đại diện. Nhóm có bất kỳ lượt thiếu giá không được gán tổng quan sát thành chi tiêu đầy đủ hoặc điền bằng 0.')
p('K-Means tối thiểu hóa tổng bình phương khoảng cách đến tâm cụm trong không gian đặc trưng [4]. Sử dụng log1p rồi StandardScaler để giảm lệch và cân bằng thang đo. Silhouette hỗ trợ so sánh độ tách cụm; ARI so độ nhất quán nhãn giữa seed. Đây là đánh giá nội tại, không thay thế xác nhận phân khúc bằng nhãn kinh doanh độc lập.')
h('2.5. Nguyên tắc đo hiệu năng')
p('Một so sánh có ý nghĩa cần giữ cùng tập dữ liệu, truy vấn, quy mô, phạm vi thời gian đo và môi trường. Baseline cũ từ phiên Colab khác chỉ là tham khảo. Trong notebook hiện hành, baseline và cấu hình tối ưu được đo lại tuần tự, xáo thứ tự, chạy 5 lần rồi lấy trung vị. Khoảng tứ phân vị mô tả dao động nhưng không phải khoảng tin cậy thống kê.')
h('2.6. Bộ nhớ thao tác và lưu kết quả tính trước')
p('work_mem giới hạn bộ nhớ cho từng thao tác như sắp xếp hoặc bảng băm; nhiều worker và toán tử có thể sử dụng đồng thời, nên không phải trần RAM toàn server [6]. Thực nghiệm chỉ thay giá trị trong phiên kết nối, không đổi cấu hình server chung. Materialized view lưu kết quả truy vấn để đọc lại; khi nguồn đổi cần REFRESH [7]. Phải báo cả chi phí tạo, làm mới và dung lượng, không coi tốc độ đọc là tốc độ tính lại toàn bộ dữ liệu.')
chapter(3)
h('3.1. Nguồn và luồng xử lý')
table(['Bước','Đầu vào','Đầu ra'],[['Thu thập','Books review và metadata','Khoảng 34,8 GB JSONL, checksum nguồn.'],['Chuẩn hóa định dạng','JSONL','Parquet trung gian; bỏ nội dung nặng không phục vụ truy vấn.'],['Khảo sát/làm sạch','Parquet trung gian','Lọc verified, khóa/điểm/thời gian, gộp trùng và chuẩn hóa giá.'],['Xây warehouse','Đánh giá và sách đã xử lý','Bốn bảng chính, bổ sung fact_inventory mô phỏng.'],['Phân tích','Warehouse','Benchmark Colab; EDA; RFM; K-Means.'],['Truyền đạt','Bảng tổng hợp đã lưu','Dashboard, biểu đồ, báo cáo và kiểm thử.']])
h('3.2. Quy tắc chất lượng và truy nguyên')
p('Đánh giá được lọc verified_purchase=true, khóa nguồn không thiếu, điểm 1–5 và timestamp trong khoảng xử lý 1996–2023. Gộp theo (user_id, parent_asin, timestamp_ms), giữ any_value(rating) và helpful_vote lớn nhất. any_value không bảo đảm chọn điểm xác định nếu các bản trùng có điểm khác nhau; đây là giới hạn cần giữ trong hồ sơ quy tắc.')
p('Mỗi parent_asin của metadata giữ một dòng ưu tiên rating_number lớn hơn. Giá không dương hoặc trên 1.000 USD được đổi NULL theo ngưỡng do nhóm đặt. Thiếu category thành Unknown; publisher/năm xuất bản trích bằng quy tắc chuỗi. Nguồn được giữ và có checksum, nhưng bảng fact cuối không lưu đầy đủ dòng JSONL gốc theo mỗi bản ghi; truy nguyên dựa vào mã sản phẩm, mã người dùng, thời gian và script xử lý.')
h('3.3. Thiết kế bảng và khóa')
dictionary=json.loads((ROOT/'docs/data_dictionary.json').read_text(encoding='utf-8'))
table(['Bảng','Số dòng','Khóa logic'],[[name,f'{info["rows"]:,}',info['logical_key']] for name,info in dictionary.items()])
p('Parquet không cưỡng chế PRIMARY KEY/FOREIGN KEY như hệ quản trị quan hệ. Bộ kiểm tra xác minh tính duy nhất, không thiếu và liên kết trên dữ liệu thực. Khóa thay thế có ý nghĩa trong lần xây warehouse hiện tại; không dùng làm định danh bền vững xuyên các lần tái tạo nếu quy tắc sinh thay đổi. Phụ lục cung cấp từ điển cột và liên kết tệp chi tiết.')
h('3.4. Thiết kế phân tích và dashboard')
p('EDA đọc tập sạch và tính các bảng theo năm, tháng, điểm, sản phẩm, nhãn danh mục, giá và hoạt động người dùng. Đối với top sách, đơn vị là parent_asin chứ chưa hợp nhất mọi ấn bản thành một tác phẩm. Phân cụm huấn luyện từ mẫu người dùng, không lấy mẫu lượt đánh giá để tránh tăng xác suất chọn người hoạt động nhiều.')
p('Dashboard có bốn trang: Hiệu năng, Tổng quan, Khám phá sách, RFM & phân cụm. Một cube tổng hợp theo năm, tháng, danh mục, điểm phục vụ bộ lọc; top sản phẩm được tính trước. Các nhãn phạm vi chỉ rõ bộ lọc năm không áp dụng bảng top toàn kỳ. Dashboard không chạy lại benchmark hoặc mô hình khi tương tác.')
chapter(4)
h('4.1. Tổ chức mã nguồn')
table(['Mô-đun','Trách nhiệm'],[['01_convert_to_parquet.py','Đọc JSONL theo luồng, ghi Parquet.'],['02_profile_data.py','Khảo sát thiếu, trùng và giá bất thường.'],['03_build_star_schema.py','Làm sạch, ghép và xây bốn bảng.'],['04_generate_inventory.py','Mô phỏng tồn kho và giá vốn.'],['05_benchmark_baseline.py','Đo mốc tham khảo; cung cấp helper chuẩn bị mẫu/nạp PostgreSQL.'],['06_benchmark_optimized.py','Đo lại baseline và tối ưu, đối chiếu kết quả từng dòng.'],['07_analyze_benchmark.py','Biểu đồ và phân tích kết quả Colab.'],['08_eda.py / 09_rfm_kmeans.py','EDA và phân cụm, suy luận theo lô.'],['10_validate_data.py / 11_data_dictionary.py','Kiểm tra dữ liệu và sinh từ điển.'],['dashboard/app.py','Giao diện Streamlit đọc bảng tổng hợp.']])
h('4.2. Hiện thực tối ưu và tính đúng đắn')
p('Sáu cấu hình gồm pandas_csv, pandas_columns, pandas_parquet, duckdb, postgres và postgres_index. Parquet từng quy mô được tạo từ đúng CSV của mẫu đó. PostgreSQL có index dùng bản sao fact và view bảng chiều để giữ baseline không có index. Chi phí sao chép, tạo index và dung lượng được ghi riêng.')
p('Mỗi engine trả đầy đủ kết quả và chuẩn hóa thứ tự ở client trước đối chiếu nhằm tránh khác biệt collation giữa PostgreSQL Linux và Pandas. Không bỏ dòng trùng. Số nguyên/chuỗi so chính xác; số thực cho dung sai rtol=1e-8, atol=1e-6. Sửa lỗi thứ tự không đồng nghĩa bỏ qua kiểm tra giá trị. RSS là phía client và tiến trình con, chưa gồm PostgreSQL server.')
h('4.3. Bộ kiểm thử và tài liệu dữ liệu')
p('run_tests.py chạy 3 kiểm thử benchmark, 7 kiểm thử quy tắc/mô hình, 3 kiểm thử kết quả PostgreSQL bổ sung và 37 phép kiểm tra dữ liệu thật. Fixture âm kiểm tra khóa, liên kết, điểm, NULL tiền và nhãn cụm. Mô hình lưu được nạp lại để đối chiếu 150.000 nhãn mẫu. Dashboard có 6 kiểm thử AppTest, gồm chọn đợt mới và baseline tương ứng. Kiểm thử PostgreSQL online về NULL/refresh/work_mem được chạy riêng khi server hoạt động.')
p('src/13_benchmark_postgres_extended.py đo work_mem 4/32/64 MB và materialized_4mb cho Q1/Q5; src/14_analyze_postgres_extended.py kiểm chứng ZIP, tính lại trung vị và tạo bảng/biểu đồ. View tổng hợp tạo trong schema riêng, không sửa fact. Baseline 4 MB được đo lại trong đợt bổ sung. Mỗi view refresh đầy đủ 5 lần, không đo ghi nguồn đồng thời hoặc incremental refresh.')
p('Từ điển sinh từ schema Parquet thực tế kết hợp diễn giải được viết theo quy tắc xử lý: 7 bộ dữ liệu, 58 cột. Bộ kiểm thử chưa tái chạy toàn bộ ETL 35 GB từ đầu, chưa kiểm tra sự thật kinh doanh của nguồn và chưa giả lập lỗi mất điện; kết quả pass cần được hiểu trong phạm vi được kiểm.')
h('4.4. Triển khai và vận hành')
table(['Mục đích','Lệnh / tệp'],[['Kiểm thử project','.venv\\Scripts\\python run_tests.py'],['Sinh EDA','.venv\\Scripts\\python src\\08_eda.py'],['RFM/K-Means','.venv\\Scripts\\python src\\09_rfm_kmeans.py (từ chối ghi đè nếu đã có RFM)'],['Dashboard','.venv\\Scripts\\python -m streamlit run dashboard\\app.py --server.address 127.0.0.1'],['Colab','run_4sizes_5repeats_colab.ipynb; Drive book-sales-colab; CPU runtime.']])
p('Dashboard cục bộ được kiểm tra phản hồi HTTP và AppTest. Chưa có kiểm tra tải đa người, phân quyền hoặc public hosting. Dữ liệu đóng gói của dashboard chỉ là tổng hợp, không chứa user_id. Tài liệu hướng dẫn đi kèm ghi phiên bản thư viện và đường dẫn kết quả.')
chapter(5)
# Reuse the project's own verified analyses. Keep enough figures for a readable report.
sources=[('phan_tich_thuc_nghiem_colab','5.1','Thực nghiệm hiệu năng',{'01_xu_huong_quy_mo','03_he_so_tang_toc','04_postgres_index','05_dung_luong'}),
         ('eda_sach','5.2','Phân tích khám phá dữ liệu',{'01_theo_nam','03_diem_danh_gia','04_top_sach','06_thieu_du_lieu'}),
         ('rfm_kmeans','5.3','RFM và K-Means',{'01_chon_k','03_quy_mo_cum','04_ho_so_cum'})]
for folder,prefix,name,keep in sources:
    h(prefix+'. '+name)
    source=json.loads((ROOT/'results'/folder/'report_blocks.json').read_text(encoding='utf-8'))
    subsection=0
    for i,(kind,c) in enumerate(source):
        if i==0:continue
        if kind=='heading':
            subsection+=1;blocks.append(('subheading',f'{prefix}.{subsection}. '+re.sub(r'^\d+\.\s*','',c)))
        elif kind=='figure':
            fig,caption=c
            if fig in keep:blocks.append(('figure',(str(ROOT/'results'/folder/'figures'/(fig+'.png')),re.sub(r'^Hình \d+\.\s*','',caption))))
        else:blocks.append((kind,c))
h('5.4. Thực nghiệm PostgreSQL bổ sung · đợt độc lập')
extended=json.loads((ROOT/'results/postgres_extended_colab/report_blocks.json').read_text(encoding='utf-8'))
for i,(kind,c) in enumerate(extended):
    if i==0:continue
    if kind=='heading':blocks.append(('subheading',c))
    elif kind=='figure':
        name,caption=c
        blocks.append(('figure',(str(ROOT/'results/postgres_extended_colab/figures'/(name+'.png')),caption)))
    else:blocks.append((kind,c))
chapter(6)
h('6.1. Mức đáp ứng mục tiêu')
table(['Mục tiêu','Kết quả và bằng chứng','Trạng thái'],[['Xây dữ liệu','20.342.188 đánh giá; lược đồ, nguồn, profile và kiểm tra.','Đã có sản phẩm.'],['Tối ưu hiệu năng','720 lượt đo, 4 quy mô, 6 cấu hình, đúng kết quả.','Hoàn thành nhóm kỹ thuật đã triển khai.'],['EDA và phân nhóm','8 biểu đồ EDA; RFM 8.353.809 người; K-Means k=2.','Đã có phân tích, kèm giới hạn.'],['Triển khai','Dashboard 4 trang, dữ liệu tổng hợp, 5 kiểm thử AppTest.','Chạy cục bộ.'],['Tài liệu/kiểm thử','Từ điển 58 cột; 10 test project và 37 kiểm tra dữ liệu.','Đã có tài liệu và bằng chứng.'],['Tối ưu mở rộng','Polars, BRIN, partition, materialized view, ghi/phân trang/xấp xỉ.','Chưa triển khai, không tính là kết quả.']])
p('Đợt cơ bản cho thấy chọn cột, Parquet và DuckDB cải thiện xử lý tệp; B-tree giúp Q3. Đợt bổ sung cho thấy work_mem 64 MB giúp Q2 khoảng 1,13 lần, 32 MB giúp Q5 khoảng 1,28 lần nhưng không cải thiện mọi truy vấn. Materialized view tăng tốc đọc Q1 khoảng 331,24 lần và Q5 khoảng 128,17 lần so với baseline mới, đổi lại chi phí tạo và refresh. Đây là 1.120 lượt đo chính ở hai đợt độc lập, không phải một thí nghiệm với mọi cấu hình trên cùng CPU.')
h('6.2. Khả năng ứng dụng và hạn chế')
p('Sản phẩm phù hợp học tập, phân tích chất lượng, khám phá đánh giá và minh họa đo hiệu năng có kiểm chứng. Chưa phù hợp quyết định nhập hàng, tối ưu lợi nhuận hay định giá thực tế vì thiếu giao dịch, giá lịch sử và tồn kho thật. Nhãn danh mục nguồn chưa đồng nhất; mẫu verified và nhóm đủ giá có thiên lệch chọn mẫu. Kết quả k=2 không chứng minh thị trường có đúng hai nhóm khách hàng.')
p('Về đo lường, số lần lặp còn nhỏ; cache không được kiểm soát hoàn toàn; số luồng các engine không được đưa về một lõi; RAM server PostgreSQL chưa được đo. Cấu hình có index là bản sao bảng nên khác biệt vật lý/cache có thể ảnh hưởng thời gian. Mã phiên chung và thông số máy tương đồng chưa phải mã định danh phần cứng xuyên phiên.')
h('6.3. Hướng phát triển')
p('Đã bổ sung work_mem và materialized view với chi phí tạo, dung lượng và refresh đầy đủ. Hướng tiếp theo gồm index bảng chiều, đo ghi nguồn/refresh đồng thời, Polars, BRIN và phân vùng nếu cần. Có thể kiểm tra cụm qua mẫu độc lập, thử RF cho nhóm thiếu giá và chuẩn hóa danh mục. Dashboard cần đánh giá tải và độ trễ nếu triển khai nhiều người dùng; chưa có công bố hosting.')
blocks.append(('chapter','Tài liệu tham khảo'))
for s in ['[1] McAuley Lab. Amazon Reviews 2023, dataset card và data fields. https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023 (truy cập 10/11/2026).',
 '[2] DuckDB. Reading and Writing Parquet Files. https://duckdb.org/docs/stable/data/parquet/overview (truy cập 10/11/2026).',
 '[3] PostgreSQL Global Development Group. PostgreSQL 16, 11.2 Index Types. https://www.postgresql.org/docs/16/indexes-types.html (truy cập 10/11/2026).',
 '[4] scikit-learn developers. Clustering: K-Means, silhouette và adjusted Rand index. https://scikit-learn.org/stable/modules/clustering.html (truy cập 10/11/2026).',
 '[5] Hồ sơ thực nghiệm: results-20261109T144133Z-1-001.zip (720 lượt), pg_extended_1110_132250-20261110T173019Z-1-001.zip (400 lượt). Hai đợt được kiểm chứng và trình bày riêng trong project book-sales-bigdata.',
 '[6] PostgreSQL 16. Resource Consumption: work_mem và hash_mem_multiplier. https://www.postgresql.org/docs/16/runtime-config-resource.html (truy cập 11/11/2026).',
 '[7] PostgreSQL 16. Materialized Views; REFRESH MATERIALIZED VIEW. https://www.postgresql.org/docs/16/rules-materializedviews.html ; https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html (truy cập 11/11/2026).']:p(s)
blocks.append(('chapter','Phụ lục tái lập và nguồn minh chứng'))
h('A. Bản đồ tệp kết quả')
table(['Nội dung','Vị trí tương đối'],[['Dữ liệu sạch','data/warehouse/*.parquet'],['Hiệu năng gốc','results/colab_verified_1109_111529'],['Phân tích hiệu năng','results/phan_tich_thuc_nghiem_colab'],['EDA','results/eda_sach/tables và figures'],['RFM/nhãn cụm/mô hình','results/rfm_kmeans'],['Kiểm thử dữ liệu','results/tests/data_validation.json'],['Từ điển','docs/data_dictionary.json; DATA_DICTIONARY.md'],['Dashboard','dashboard/app.py; data; README.md']])
h('B. Từ điển dữ liệu rút gọn theo schema thực tế')
for name,info in dictionary.items():
    blocks.append(('subheading',name+' — '+info['logical_key']))
    table(['Cột','Kiểu','Diễn giải'],[[c['name'],c['type'],c['description']] for c in info['columns']])
h('C. Thông tin cần xác nhận trước khi nộp')
p('Thông tin thành viên và giảng viên đã được điền theo xác nhận của nhóm. Trước khi nộp, cần xác nhận việc chấp nhận nguồn đánh giá làm đại diện kinh doanh và chốt các kỹ thuật mở rộng bắt buộc. Cập nhật mục lục và số trang trong Word sau chỉnh sửa.')

h('D. Minh chứng đợt PostgreSQL bổ sung')
p('Nguồn kiểm chứng: results/postgres_extended_colab/validation.json; bảng comparison_extended_verified.csv và materialized_view_costs.csv; kế hoạch EXPLAIN và summary gốc trong evidence. Dùng Bo_sung_PostgreSQL_Colab.ipynb để tái đo. Các baseline của hai đợt phải giữ riêng; không chia thời gian đợt trước cho thời gian đợt sau để tính tăng tốc.')
replacements={
 '720 phép đo trong cùng mã phiên Colab, trung vị 5 lần/tổ hợp.':'720 lượt cơ bản và 400 lượt bổ sung ở hai đợt độc lập; mỗi tổ hợp 5 lần.',
 '720 lượt đo, 4 quy mô, 6 cấu hình, đúng kết quả.':'720 lượt cơ bản + 400 lượt PostgreSQL bổ sung; baseline riêng từng đợt.',
 'Dashboard 4 trang, dữ liệu tổng hợp, 5 kiểm thử AppTest.':'Dashboard 4 trang, chọn hai đợt thực nghiệm, 6 kiểm thử AppTest.',
 'Từ điển 58 cột; 10 test project và 37 kiểm tra dữ liệu.':'Từ điển 58 cột; 13 test project và 37 kiểm tra dữ liệu.',
 'Polars, BRIN, partition, materialized view, ghi/phân trang/xấp xỉ.':'Polars, BRIN, partition, ghi nguồn đồng thời/phân trang/xấp xỉ.',
 'Hướng thử tiếp là tăng work_mem có kiểm soát, tối ưu tổng hợp, hoặc materialized view; chưa được phép kết luận mức tăng tốc của chúng khi chưa đo.':'Trong đợt cơ bản, work_mem và materialized view chưa được đo; kết quả của đợt bổ sung trình bày riêng ở mục 5.4.',
 'Đã có bằng chứng cho chọn cột, Parquet, DuckDB và B-tree. Tài liệu bàn giao còn liệt kê Polars, BRIN, phân vùng, materialized view, nạp dữ liệu/phân trang, xấp xỉ; các kỹ thuật này chưa nằm trong 720 lượt đo.':'Đợt cơ bản có bằng chứng cho chọn cột, Parquet, DuckDB và B-tree. Work_mem và materialized view được đo trong đợt bổ sung riêng (mục 5.4); Polars, BRIN, phân vùng, nạp dữ liệu/phân trang và xấp xỉ chưa triển khai.',
 'Hạng mục EDA–RFM–K-Means đã có sản phẩm và kết quả. Chưa hoàn thành báo cáo tổng thể, từ điển dữ liệu hoặc các kỹ thuật tối ưu mở rộng.':'Hạng mục EDA–RFM–K-Means đã có sản phẩm, báo cáo và từ điển dữ liệu. Hai kỹ thuật tối ưu bổ sung work_mem/materialized view được kiểm chứng riêng ở mục 5.4.',
}
def updated(value):
    if isinstance(value,str):
        for old,new in replacements.items():value=value.replace(old,new)
        return value
    if isinstance(value,(list,tuple)):return [updated(v) for v in value]
    return value
blocks=updated(blocks)

front=[('LỜI CẢM ƠN','Chúng em xin cảm ơn giảng viên học phần Nhập môn Khoa học dữ liệu đã cung cấp kiến thức nền tảng để thực hiện quy trình chuẩn bị, phân tích và đánh giá hệ thống dữ liệu. Đề tài là cơ hội thực hành xử lý dữ liệu quy mô lớn, đo hiệu năng và trình bày kết quả có kiểm chứng. Chúng em mong nhận được góp ý về lựa chọn nguồn, phạm vi diễn giải và thiết kế thực nghiệm để tiếp tục hoàn thiện sản phẩm.'),
 ('TÓM TẮT','Đề tài xây dựng kho dữ liệu từ Amazon Reviews 2023 – Books, giữ 20.342.188 đánh giá đã xác minh sau làm sạch. Thực nghiệm gồm 720 lượt đo trên bốn quy mô và sáu cấu hình, mỗi tổ hợp lặp năm lần. Trên 20,34 triệu dòng, DuckDB Parquet tăng tốc khoảng 2,29–16,07 lần so với Pandas CSV theo truy vấn; B-tree trên customer_key giúp Q3 khoảng 1,25 lần. EDA mô tả đánh giá và chất lượng dữ liệu; RFM được tính cho 8.353.809 người, trong đó 5.821.888 người đủ giá được gán hai cụm từ mô hình chọn trên mẫu phân tầng 150.000 người. Sản phẩm có dashboard Streamlit, từ điển và kiểm thử. Các giá trị tiền là đại diện theo metadata, không phải doanh thu thực. Từ khóa: dữ liệu sách; đánh giá đã xác minh; Parquet; DuckDB; B-tree; RFM; K-Means.')]

front[1]=('TÓM TẮT','Đề tài xây dựng kho dữ liệu từ Amazon Reviews 2023 – Books, giữ 20.342.188 đánh giá đã xác minh sau làm sạch. Hai đợt Colab độc lập cung cấp 720 lượt đo cơ bản và 400 lượt PostgreSQL bổ sung; mỗi tổ hợp lặp năm lần và đối chiếu kết quả. Đợt cơ bản: DuckDB Parquet tăng tốc khoảng 2,29–16,07 lần so với Pandas CSV, B-tree giúp Q3 khoảng 1,25 lần. Đợt bổ sung: tăng work_mem cải thiện tùy truy vấn; materialized view giúp Q1 khoảng 331,24 lần, Q5 khoảng 128,17 lần so với baseline mới, đổi lại thời gian tạo/refresh và nguy cơ dữ liệu cũ. EDA và RFM mô tả 8.353.809 người; 5.821.888 người đủ giá được gán hai cụm từ mẫu phân tầng 150.000 người. Sản phẩm có dashboard, từ điển và kiểm thử. Các giá trị tiền là đại diện theo metadata, không phải doanh thu thực. Từ khóa: đánh giá sách; Parquet; DuckDB; B-tree; work_mem; materialized view; RFM; K-Means.')

def field(paragraph,instruction):
    r=paragraph.add_run();start=OxmlElement('w:fldChar');start.set(qn('w:fldCharType'),'begin')
    text=OxmlElement('w:instrText');text.set(qn('xml:space'),'preserve');text.text=instruction
    end=OxmlElement('w:fldChar');end.set(qn('w:fldCharType'),'end')
    r._r.extend([start,text,end])
def configure(doc):
    sec=doc.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11)
    sec.left_margin=Inches(.98);sec.right_margin=Inches(.75);sec.top_margin=sec.bottom_margin=Inches(.75)
    for name in ['Normal','Heading 1','Heading 2','Heading 3','Caption']:
        s=doc.styles[name];s.font.name='Times New Roman';s.font.size=Pt(12 if name!='Caption' else 11);s.font.color.rgb=RGBColor(0,0,0)
    doc.styles['Normal'].paragraph_format.line_spacing=1.15
    doc.styles['Normal'].paragraph_format.space_after=Pt(6)
    for name in ['Heading 1','Heading 2','Heading 3']:doc.styles[name].paragraph_format.keep_with_next=True
    sec.different_first_page_header_footer=True
    hp=sec.header.paragraphs[0];hp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    hp.add_run('NHẬP MÔN KHOA HỌC DỮ LIỆU | DỮ LIỆU KINH DOANH SÁCH').font.size=Pt(9)
    fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.CENTER;field(fp,' PAGE ')
    upd=OxmlElement('w:updateFields');upd.set(qn('w:val'),'true');doc.settings.element.append(upd)
def cover(doc,blank=False):
    para=doc.add_paragraph();para.alignment=WD_ALIGN_PARAGRAPH.CENTER
    para.add_run('HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG').bold=True
    para=doc.add_paragraph();para.alignment=WD_ALIGN_PARAGRAPH.CENTER;para.add_run().add_picture(str(logo),width=Inches(1.25))
    identity=[('Giảng viên hướng dẫn: [Cần điền]',False),('Nhóm thực hiện: [Cần điền]',True),('[Họ tên thành viên — Mã sinh viên]',False),('[Lớp — Nhóm]',False)] if blank else [('Giảng viên hướng dẫn: '+SUPERVISOR,False),('Nhóm thực hiện',True)]+[(member,False) for member in MEMBERS]
    for s,bold in [('BÁO CÁO TIỂU LUẬN',True),('Học phần Nhập môn khoa học dữ liệu',False),('[TÊN ĐỀ TÀI]' if blank else TITLE,True)]+identity+[('Tháng 11 năm 2026',False)]:
        para=doc.add_paragraph();para.alignment=WD_ALIGN_PARAGRAPH.CENTER;para.paragraph_format.space_after=Pt(16);para.add_run(s).bold=bold
def build_docx(path,blank=False):
    d=Document();configure(d);cover(d,blank)
    for i,(name,content) in enumerate(front):
        if i==0:
            front_sec=d.add_section(WD_SECTION_START.NEW_PAGE)
            front_sec.different_first_page_header_footer=False
            front_num=OxmlElement('w:pgNumType');front_num.set(qn('w:start'),'1');front_num.set(qn('w:fmt'),'lowerRoman');front_sec._sectPr.append(front_num)
        else:d.add_page_break()
        d.add_heading(name,1);d.add_paragraph('[Nội dung]' if blank else content)
    for name,code in [('MỤC LỤC',' TOC \\o "1-3" \\h \\z \\u '),('DANH MỤC HÌNH',' TOC \\h \\z \\t "Caption,1" '),('DANH MỤC BẢNG',' TOC \\h \\z \\t "TableCaption,1" ')]:
        d.add_page_break();d.add_heading(name,1);field(d.add_paragraph(),code)
        d.add_paragraph('Cập nhật trường mục lục trong Word sau khi hoàn thiện nội dung.').italic=True
    sec=d.add_section(WD_SECTION_START.NEW_PAGE)
    sec.different_first_page_header_footer=False
    num=OxmlElement('w:pgNumType');num.set(qn('w:start'),'1');num.set(qn('w:fmt'),'decimal');sec._sectPr.append(num)
    if 'TableCaption' not in d.styles:
        style=d.styles.add_style('TableCaption',1);style.base_style=d.styles['Caption']
    d.styles['TableCaption'].paragraph_format.keep_with_next=True
    fig_count=table_count=0
    chosen=[('chapter',f'Chương {i+1} {c}') for i,c in enumerate(CHAPTERS)] if blank else blocks
    for kind,c in chosen:
        if kind=='chapter':
            if blank and c!=chosen[0][1]:d.add_page_break()
            heading=d.add_heading(c,1)
            heading.paragraph_format.space_before=Pt(20)
            if blank:d.add_paragraph('[Nội dung chương]')
        elif kind in ['heading','subheading']:d.add_heading(c,2 if kind=='heading' else 3)
        elif kind=='paragraph':
            para=d.add_paragraph(c);para.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
        elif kind=='table':
            table_count+=1;d.add_paragraph(f'Bảng {table_count}. '+(' / '.join(c[0])),style='TableCaption')
            t=d.add_table(rows=1,cols=len(c[0]));t.style='Table Grid'
            for j,v in enumerate(c[0]):t.rows[0].cells[j].text=v
            repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
            for row in c[1:]:
                cells=t.add_row().cells
                for j,v in enumerate(row):cells[j].text=str(v)
            for row in t.rows:
                for cell in row.cells:
                    for p0 in cell.paragraphs:
                        for r in p0.runs:r.font.size=Pt(9)
        elif kind=='figure':
            fig_count+=1;name,caption=c
            from docx.image.image import Image as DocxImage
            dimensions=DocxImage.from_file(name)
            width=min(6.65,4.1*dimensions.px_width/dimensions.px_height)
            picture=d.add_paragraph();picture.alignment=WD_ALIGN_PARAGRAPH.CENTER
            picture.paragraph_format.keep_with_next=True
            picture.add_run().add_picture(name,width=Inches(width))
            d.add_paragraph(f'Hình {fig_count}. {caption}',style='Caption')
    d.save(path)
    print('DOCX',path,'figures',fig_count,'tables',table_count)
build_docx(OUT/('Bao_cao_kinh_doanh_sach'+REPORT_SUFFIX+'.docx'))
build_docx(OUT/'Template_nhom7_co_the_chinh_sua.docx',blank=True)

# Generate a paginated companion PDF without requiring installed Microsoft Word.
fontdir=Path('C:/Windows/Fonts')
for name,file in [('TNR','times.ttf'),('TNRB','timesbd.ttf'),('TNRI','timesi.ttf')]:pdfmetrics.registerFont(TTFont(name,str(fontdir/file)))
pdfmetrics.registerFontFamily('TNR',normal='TNR',bold='TNRB',italic='TNRI',boldItalic='TNRB')
styles={'body':ParagraphStyle('body',fontName='TNR',fontSize=12,leading=15,alignment=TA_JUSTIFY,spaceAfter=7),
        'h1':ParagraphStyle('h1',fontName='TNRB',fontSize=12,leading=16,spaceAfter=12,keepWithNext=True),
        'h2':ParagraphStyle('h2',fontName='TNRB',fontSize=12,leading=15,spaceBefore=10,spaceAfter=7,keepWithNext=True),
        'h3':ParagraphStyle('h3',fontName='TNRB',fontSize=11,leading=14,spaceBefore=8,spaceAfter=6,keepWithNext=True),
        'cell':ParagraphStyle('cell',fontName='TNR',fontSize=9,leading=11),
        'caption':ParagraphStyle('caption',fontName='TNRB',fontSize=10,leading=12,alignment=TA_CENTER,spaceBefore=5,spaceAfter=8),
        'center':ParagraphStyle('center',fontName='TNR',fontSize=12,leading=16,alignment=TA_CENTER,spaceAfter=15)}
WIDTH=612-70.8-54
class ReportDoc(BaseDocTemplate):
    def beforeDocument(self):
        self.body_start=getattr(self,'known_body_start',None)
        self.heading_id=0
    def __init__(self,path):
        super().__init__(str(path),pagesize=(612,792),leftMargin=70.8,rightMargin=54,topMargin=56,bottomMargin=48)
        self.body_start=None;self.heading_id=0
        frame=lambda:Frame(70.8,48,WIDTH,688,id='normal',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates([PageTemplate(id='cover',frames=frame(),onPage=self.on_cover),PageTemplate(id='normal',frames=frame(),onPage=self.on_normal)])
    def on_cover(self,canvas,doc):
        canvas.drawImage(str(border),2,-8,width=607.5,height=815,mask='auto')
    def on_normal(self,canvas,doc):
        canvas.saveState();canvas.setFont('TNR',9)
        canvas.drawCentredString(306,763,'NHẬP MÔN KHOA HỌC DỮ LIỆU | DỮ LIỆU KINH DOANH SÁCH')
        if self.body_start is not None and doc.page>=self.body_start:label=str(doc.page-self.body_start+1)
        else:label=['','i','ii','iii','iv','v','vi','vii','viii','ix'][min(doc.page-1,9)]
        canvas.drawCentredString(306,29,label);canvas.restoreState()
    def afterFlowable(self,flow):
        if isinstance(flow,Paragraph) and getattr(flow,'report_heading',False):
            if flow.getPlainText().startswith('Chương 1 '):self.body_start=self.page;self.known_body_start=self.page
            self.heading_id+=1;key=f'h{self.heading_id}'
            self.canv.bookmarkPage(key)
            level=getattr(flow,'toc_level',0)
            self.notify('TOCEntry',(level,flow.getPlainText(),self.page-self.body_start+1 if self.body_start else self.page,key))
        if isinstance(flow,Paragraph) and hasattr(flow,'figure_caption'):
            self.notify('FigureEntry',(0,flow.getPlainText(),self.page-self.body_start+1 if self.body_start else self.page))
        if isinstance(flow,Paragraph) and hasattr(flow,'table_caption'):
            self.notify('TableEntry',(0,flow.getPlainText(),self.page-self.body_start+1 if self.body_start else self.page))
class IndexTOC(TableOfContents):
    def __init__(self,event):super().__init__();self.event=event
    def notify(self,kind,stuff):
        if kind==self.event:self.addEntry(*stuff)

story=[]
def para(text,style='body'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
story+=[Spacer(1,6),para('HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG','center'),Spacer(1,15),Image(str(logo),width=94,height=95),Spacer(1,22),para('BÁO CÁO TIỂU LUẬN','center'),para('Học phần Nhập môn khoa học dữ liệu','center'),Spacer(1,12),para(TITLE,'center'),Spacer(1,18),para('Giảng viên hướng dẫn: '+SUPERVISOR,'center'),para('Nhóm thực hiện','center')]+[para(member,'center') for member in MEMBERS]+[Spacer(1,22),para('Tháng 11 năm 2026','center'),NextPageTemplate('normal'),PageBreak()]
for name,content in front:story+=[para(name,'h1'),para(content),PageBreak()]
for name,event in [('MỤC LỤC','TOCEntry'),('DANH MỤC HÌNH','FigureEntry'),('DANH MỤC BẢNG','TableEntry')]:
    toc=IndexTOC(event);toc.levelStyles=[ParagraphStyle('toc0',fontName='TNR',fontSize=11,leading=14,spaceAfter=6),ParagraphStyle('toc1',fontName='TNR',fontSize=10,leading=13,leftIndent=12,spaceAfter=4)]
    story += [para(name,'h1'),toc,PageBreak()]
fig_no=tab_no=0
for idx,(kind,c) in enumerate(blocks):
    if kind in ['chapter','heading','subheading']:
        if kind=='chapter' and idx:
            story.extend([CondPageBreak(100),Spacer(1,14)])
        item=para(c,'h1' if kind=='chapter' else 'h2' if kind=='heading' else 'h3')
        if kind!='subheading':item.report_heading=True;item.toc_level=0 if kind=='chapter' else 1
        story.append(item)
    elif kind=='paragraph':story.append(para(c))
    elif kind=='table':
        tab_no+=1;cap=para(f'Bảng {tab_no}. '+(' / '.join(c[0])),'caption');cap.table_caption=True;cap.keepWithNext=True;story.append(cap)
        rows=[[para(v,'cell') for v in row] for row in c]
        weights=[1]*len(c[0])
        if c[0]==['Cột','Kiểu','Diễn giải']:weights=[1.5,1,3.5]
        widths=[WIDTH*w/sum(weights) for w in weights]
        t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,'#8a8a8a'),('BACKGROUND',(0,0),(-1,0),'#eeeeee'),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story += [t,Spacer(1,8)]
    elif kind=='figure':
        name,caption=c;fig_no+=1
        image=Image(name);scale=min(WIDTH/image.imageWidth,295/image.imageHeight)
        image.drawWidth=image.imageWidth*scale;image.drawHeight=image.imageHeight*scale
        cap=para(f'Hình {fig_no}. {caption}','caption');cap.figure_caption=True
        story += [KeepTogether([Spacer(1,6),image,cap])]
pdf_path=OUT/('Bao_cao_kinh_doanh_sach'+REPORT_SUFFIX+'.pdf')
ReportDoc(pdf_path).multiBuild(story)
pdf=pymupdf.open(pdf_path)
assert len(pdf)>15
fulltext=''.join(page.get_text() for page in pdf)
assert 'Chương 6' in fulltext and '20.342.188' in fulltext
for i in [0,6,len(pdf)-1]:pdf[i].get_pixmap(matrix=pymupdf.Matrix(1,1)).save(str(OUT/f'preview_{i+1}.png'))
print('PDF:',pdf_path,'pages:',len(pdf))
(OUT/'report_content.json').write_text(json.dumps(blocks,ensure_ascii=False,indent=2),encoding='utf-8')
submission=OUT/'submission';submission.mkdir(exist_ok=True)
shutil.copy2(pdf_path,submission/'Bao_cao_kinh_doanh_sach.pdf')
shutil.copy2(OUT/('Bao_cao_kinh_doanh_sach'+REPORT_SUFFIX+'.docx'),submission/'Bao_cao_kinh_doanh_sach.docx')
