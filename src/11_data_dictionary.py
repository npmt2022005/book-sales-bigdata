"""Generate documentation from actual Parquet schemas and curated semantics."""
import html
import json
from pathlib import Path
import duckdb
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs';OUT.mkdir(exist_ok=True)
definitions={
'dim_books':{
'book_key':'Khóa thay thế của sản phẩm; sinh khi xây warehouse, không ổn định nếu xây lại bằng quy tắc khác.',
'parent_asin':'Mã sản phẩm cha Amazon; khóa nghiệp vụ để nối metadata và đánh giá, không nhất thiết là một tác phẩm duy nhất.',
'title':'Tên sản phẩm sách từ metadata; chuỗi trống chuyển NULL.',
'author':'Tác giả từ metadata, có thể NULL.',
'category':'Nhãn danh mục nguồn; thiếu chuyển Unknown. Có thể gồm chiến dịch hoặc bộ sưu tập, chưa phải hệ thể loại chuẩn.',
'publisher':'Nhà xuất bản trích từ publisher_raw, loại phần sau dấu ; hoặc (, có thể thiếu hoặc không chính xác.',
'isbn_13':'Chuỗi 13 chữ số sau loại ký tự khác; chưa xác minh checksum ISBN.',
'publish_year':'Năm trích từ cuối publisher_raw nếu 1400–2024; không phải năm đã xác minh.',
'language':'Ngôn ngữ theo metadata, có thể thiếu.',
'pages':'Số trang theo nguồn, có thể thiếu; chưa bảo đảm mọi định dạng sản phẩm có số trang tương đương.',
'list_price':'Giá USD tại thời điểm thu thập; chỉ giữ 0 < giá ≤ 1000, ngoài ngưỡng/thiếu thành NULL.',
'average_rating':'Điểm hiển thị trong metadata, không phải điểm tính lại từ tập fact đã lọc.',
'rating_number':'Số đánh giá hiển thị trong metadata, không đồng nhất số dòng trong fact_sales.'},
'dim_customers':{
'customer_key':'Khóa thay thế của người đánh giá; không chứa tên, email hoặc địa chỉ.',
'user_id':'Mã người đánh giá nguồn Amazon; khóa nghiệp vụ, không phải mã khách hàng giao dịch đã xác thực.',
'first_purchase_date':'Ngày đánh giá đã xác minh đầu tiên trong tập sạch; tên cột cũ không có nghĩa đây là ngày mua.',
'last_purchase_date':'Ngày đánh giá đã xác minh cuối cùng trong tập sạch; không phải ngày mua thực.',
'total_purchases':'Tổng số lượt đánh giá đã xác minh của người dùng sau làm sạch; không phải tổng đơn hàng.'},
'dim_date':{
'date_key':'Khóa ngày YYYYMMDD, nối fact_sales.date_key.',
'date':'Ngày lịch UTC được suy ra từ timestamp nguồn.',
'day':'Ngày trong tháng 1–31.', 'week':'Tuần ISO 1–53; kết hợp year không phải cặp ISO-year chuẩn.',
'month':'Tháng 1–12.', 'quarter':'Quý 1–4.', 'year':'Năm lịch.', 'is_weekend':'TRUE khi thứ Bảy hoặc Chủ nhật theo ISO weekday.'},
'fact_sales':{
'sale_id':'Khóa thay thế của lượt đánh giá đã xác minh, không phải mã đơn hàng thật.',
'date_key':'FK đến dim_date.date_key, ngày viết đánh giá.',
'customer_key':'FK đến dim_customers.customer_key.', 'book_key':'FK đến dim_books.book_key.',
'quantity':'Giả định bằng 1 mỗi lượt, không có số lượng mua thực trong nguồn.',
'price_usd':'Sao chép list_price hợp lệ của sản phẩm tại thu thập, USD; có thể NULL.',
'estimated_revenue':'quantity × price_usd, chỉ là giá trị đại diện; thiếu giá thì NULL, không dùng làm doanh thu thực.',
'rating':'Điểm của đánh giá được giữ lại, 1–5.',
'helpful_vote':'Số lượt hữu ích; giữ giá trị lớn nhất khi gộp bản ghi trùng, không phải số lượt mua.'},
'fact_inventory':{
'book_key':'FK đến dim_books.book_key, chỉ các sản phẩm có hoạt động trong 09/2022–08/2023.',
'month_key':'Tháng YYYYMM từ 202209 đến 202308; khóa ghép với book_key.',
'units_sold':'Tổng quantity từ fact_sales theo sách/tháng; đặt tên cũ, thực tế là số lượt đánh giá đại diện, không phải lượng bán đo được.',
'stock_quantity':'Tồn kho mô phỏng bằng hàm băm và số lượt đại diện; số nguyên không âm, không phải tồn kho thực.',
'unit_cost':'Giá vốn mô phỏng bằng 50–80% list_price, làm tròn 2 chữ số; NULL nếu thiếu giá.',
'is_simulated':'Luôn TRUE; đánh dấu bảng lớp kinh doanh mô phỏng.'},
'rfm_all_users':{
'customer_key':'Khóa người dùng trong dim_customers.',
'recency':'Số ngày từ đánh giá cuối đến 2023-09-15; không tính đến ngày hiện tại.',
'frequency':'Số lượt đánh giá đã xác minh trong tập sạch, bằng total_purchases.',
'priced_reviews':'Số lượt có price_usd hợp lệ; từ 0 đến frequency.',
'monetary_observed':'Tổng estimated_revenue quan sát được; tất cả thiếu giữ NULL, thiếu một phần chỉ là tổng một phần.',
'price_coverage':'priced_reviews / frequency, tỷ lệ 0–1.',
'eligible':'TRUE khi mọi lượt đều có giá hợp lệ; chỉ nhóm này đưa vào K-Means.',
'frequency_stratum':'Tầng lấy mẫu theo F: 1, 2, 3-5, 6-10, 11-50, >50.'}}
definitions['rfm_with_clusters']=dict(definitions['rfm_all_users'],cluster='Nhãn K-Means 0..k-1, không có thứ hạng; -1 là thiếu giá nên không phân cụm. Mô hình hiện tại k=2.')
keys={'dim_books':'book_key (PK), parent_asin (duy nhất)', 'dim_customers':'customer_key (PK), user_id (duy nhất)',
      'dim_date':'date_key (PK)', 'fact_sales':'sale_id (PK)', 'fact_inventory':'(book_key, month_key) (PK ghép)',
      'rfm_all_users':'customer_key (PK/FK)', 'rfm_with_clusters':'customer_key (PK/FK)'}
con=duckdb.connect();schemas={};lines=['# Từ điển dữ liệu đề tài sách','',
'Nguồn gốc: Amazon Reviews 2023 – Books. Từ điển mô tả tệp Parquet thực tế trong project. Các ràng buộc dưới đây là hợp đồng logic, không phải PRIMARY KEY được cưỡng chế trong Parquet.', '',
'## Quy ước và giới hạn','',
'NULL là thiếu/không hợp lệ, không tự thay bằng 0. Giá dùng USD tại thời điểm thu thập; ngưỡng 1.000 USD là quyết định của nhóm. Lượt đánh giá có xác minh chỉ đại diện hoạt động mua; không có đơn hàng, số lượng hoặc ngày mua thực. Các khóa thay thế chỉ có ý nghĩa trong cùng lần xây warehouse.', '',
'Các cột mang tên sales/purchase/units_sold là tên kỹ thuật lịch sử; cách diễn giải phải theo mô tả bên dưới. Trong fact_inventory, units_sold được suy ra từ đánh giá; stock_quantity và unit_cost là mô phỏng. Tệp không có thông tin định danh như tên/email, nhưng user_id vẫn là mã nguồn cần quản lý phù hợp.', '',
'## Quan hệ và nguồn tạo','',
'fact_sales nối dim_books, dim_customers, dim_date qua các khóa tương ứng. fact_inventory nối dim_books và dùng month_key riêng. RFM nối dim_customers qua customer_key. Script 03 xây bốn bảng chính, script 04 tạo tồn kho mô phỏng, script 09 tạo RFM và nhãn cụm. EDA là script 08; các bảng kết quả EDA/benchmark là bảng tổng hợp dẫn xuất, không bổ sung giao dịch thật.', '']
for name,fields in definitions.items():
    path=ROOT/('results/rfm_kmeans' if name.startswith('rfm_') else 'data/warehouse')/(name+'.parquet')
    metadata=pq.ParquetFile(path).metadata
    schema=con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()
    assert set(fields)=={r[0] for r in schema},name
    schemas[name]={'path':str(path.relative_to(ROOT)),'rows':metadata.num_rows,'logical_key':keys[name],
                   'columns':[{'name':r[0],'type':r[1],'description':fields[r[0]]} for r in schema]}
    lines += [f'## {name}', '', f'Đường dẫn: `{path.relative_to(ROOT)}`. Số dòng: {metadata.num_rows:,}. Khóa logic: {keys[name]}.', '',
              '| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |','|---|---|---|']
    lines += [f'| `{r[0]}` | `{r[1]}` | {fields[r[0]]} |' for r in schema]
    lines += ['']
lines += ['## Quy tắc xây dựng và đối chiếu','',
'Đánh giá: lọc verified_purchase=true, khóa nguồn không thiếu, rating 1–5, timestamp hợp lệ 1996–2023; gộp theo (user_id, parent_asin, timestamp_ms), any_value(rating), max(helpful_vote). Quy tắc any_value có thể chọn điểm không xác định nếu bản trùng có rating khác nhau; chưa có kiểm thử tái tạo toàn bộ nguồn thô ở bộ kiểm thử này.', '',
'Sách: một parent_asin giữ dòng có rating_number lớn nhất; nhãn thiếu thành Unknown. ISBN chỉ kiểm tra đủ 13 chữ số sau chuẩn hóa. Năm xuất bản được trích bằng biểu thức chính quy nên có thể thiếu hoặc sai theo nội dung nguồn.', '',
'Ngày: lịch liên tục từ ngày đánh giá đầu đến cuối. Khách: tổng số lượt, ngày đầu/cuối đều tính từ tập sạch. RFM: chỉ phân cụm nhóm đầy đủ giá; không gán giá thiếu thành 0. Tồn kho: seed 20261109, 12 tháng 09/2022–08/2023.', '',
'Bộ kiểm thử xác minh tính toàn vẹn warehouse và RFM trên dữ liệu hiện có; không chứng minh dữ liệu nguồn đúng thực tế, không xác minh đầy đủ quyền sử dụng nguồn và không đo lại toàn bộ hiệu năng Colab.', '']
(OUT/'DATA_DICTIONARY.md').write_text('\n'.join(lines),encoding='utf-8')
(OUT/'data_dictionary.json').write_text(json.dumps(schemas,ensure_ascii=False,indent=2),encoding='utf-8')
parts=[]
for line in lines:
    if line.startswith('# '):parts.append('<h1>'+html.escape(line[2:])+'</h1>')
    elif line.startswith('## '):parts.append('<h2>'+html.escape(line[3:])+'</h2>')
    elif line:parts.append('<p style="overflow-wrap:anywhere">'+html.escape(line)+'</p>')
(OUT/'DATA_DICTIONARY.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Từ điển dữ liệu</title><style>body{font:15px/1.6 Arial;max-width:1050px;margin:35px auto;padding:0 20px}h2{margin-top:40px}</style>'+''.join(parts)+'</html>',encoding='utf-8')
print('Documented',len(schemas),'datasets,',sum(len(s['columns']) for s in schemas.values()),'columns')
