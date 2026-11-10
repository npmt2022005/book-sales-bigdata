# Thực nghiệm tối ưu hiệu năng

## Phạm vi đã triển khai

`src/06_benchmark_optimized.py` chạy lại Q1–Q6 trên cùng dữ liệu:

- `pandas_csv`: đọc toàn bộ CSV, mốc so sánh trong phiên hiện tại.
- `pandas_columns`: CSV nhưng chỉ đọc các cột cần dùng.
- `pandas_parquet`: đọc cùng các cột từ Parquet Zstandard.
- `duckdb`: SQL trực tiếp trên chính các tệp Parquet đó, 2 luồng, giới hạn bộ nhớ DuckDB 2 GB.
- `postgres`: bảng mốc trong schema `s_1m`, `s_10m`... đã được script 05 nạp.
- `postgres_index`: bản sao riêng của bảng fact, có B-tree trên customer_key; dùng các bảng chiều qua view. Không thêm index vào bảng mốc.

Parquet tạo từ chính CSV của từng mẫu benchmark, không lấy một mẫu khác từ warehouse. Chi phí chuyển định dạng được lưu riêng, không cộng vào thời gian truy vấn. Các tệp Parquet đã tồn tại được tái sử dụng; xóa/di chuyển chúng theo chủ ý nếu thay dữ liệu đầu vào. Không thay CSV đầu vào giữa các lượt đo.

## Chạy trên Windows

Từ thư mục gốc project, mở PowerShell:

```powershell
.venv\Scripts\python src\pg_local.py start
.venv\Scripts\python src\06_benchmark_optimized.py --sizes 1m --engines pandas_csv pandas_columns pandas_parquet duckdb postgres postgres_index --repeats 5 --tag optimized_1m_final
```

Nếu server đã chạy thì bỏ lệnh start. Không chạy các benchmark khác đồng thời. Mỗi lần chạy dùng tag mới: kết quả và schema tối ưu đã có sẽ không bị ghi đè. Script không tự xóa schema tối ưu; chúng chiếm thêm dung lượng và được giữ để kiểm tra kế hoạch truy vấn.

Chạy ngắn để kiểm tra:

```powershell
.venv\Scripts\python src\06_benchmark_optimized.py --sizes 1m --queries Q3 --engines postgres postgres_index --repeats 1 --tag check_q3
```

## Chạy trên Colab

Bản đóng gói tại `colab_upload/book-sales-colab` đã có notebook `run_optimized_colab.ipynb`. Tải notebook đó cùng `src/06_benchmark_optimized.py` lên thư mục `My Drive/book-sales-colab` tương ứng, mở bằng Colab rồi Run all. Notebook cũ đo baseline được giữ nguyên. Notebook mới mặc định đo lại cả baseline và tối ưu trên 10 triệu dòng, 5 lần, tự lưu checkpoint và kết quả về Drive. Notebook được kiểm tra cú pháp trên Windows; chưa được thực thi trên Colab trong phiên triển khai này.

Nếu dùng phiên Colab đã thiết lập sẵn: chép script 06 vào thư mục `src`, giữ script 05 bên cạnh. Dùng runtime CPU; dữ liệu benchmark nên ở đĩa cục bộ runtime, không đọc trực tiếp từ Drive trong phép đo. Tại thư mục gốc project chạy:

```python
!pip install pandas pyarrow duckdb psutil "psycopg[binary]"
!python src/06_benchmark_optimized.py --sizes 10m --engines pandas_csv pandas_columns pandas_parquet duckdb postgres postgres_index --repeats 5 --tag optimized_10m_final
```

PostgreSQL phải được khởi động theo notebook Colab hiện có, dùng cổng 55432 và database book_sales. Không dùng pg_local.py trên Colab vì helper đó chỉ dành cho Windows. Script 06 tự nạp các bảng mốc nếu chưa có; script 05 phải đi cùng để dùng hàm chuẩn bị/nạp dữ liệu. Có thể chỉ chọn bốn engine xử lý tệp nếu PostgreSQL chưa sẵn sàng.

Sau khi mức 10 triệu thành công, dùng `--sizes full` với tag mới. Lưu toàn bộ thư mục results/<tag> về Drive. Không gộp số liệu máy cá nhân với Colab.

## Cách đo và kiểm tra

- Tham chiếu từng truy vấn được tính bằng Pandas CSV, lưu đầy đủ kết quả.
- Mọi engine chạy một lượt khởi động và kiểm tra; sau đó thứ tự engine/truy vấn được xáo ngẫu nhiên trong từng vòng đo.
- So sánh đủ cột và từng dòng đã sắp xếp. Số nguyên/chuỗi so sánh chính xác; số thực cho phép rtol=1e-8, atol=1e-6 để chấp nhận khác biệt cộng dồn dấu phẩy động.
- Thời gian gồm mở kết nối/đọc tệp, thực thi và đưa đầy đủ kết quả vào DataFrame ở client. Không gồm import thư viện, khởi động Python, ghi tệp kết quả và kiểm tra tính đúng đắn.
- Bộ nhớ là RSS đỉnh được lấy mẫu của tiến trình client và con, gồm cả bước ghi kết quả. Không bao gồm RAM của PostgreSQL server; không dùng số này để kết luận PostgreSQL dùng ít RAM hơn Pandas. Đây cũng không phải số bộ nhớ cấp phát tuyệt đối chính xác.
- Cache hệ điều hành không được xóa. Kết quả biểu diễn phiên chạy đã khởi động, không khẳng định cold-cache.
- Script 05 trả các tổng kiểm tra trong nhiều truy vấn; script 06 lấy đầy đủ kết quả nghiệp vụ để kiểm tra từng dòng. Vì vậy không tính speedup bằng thời gian script 05 chia thời gian script 06. Mốc hợp lệ là pandas_csv/postgres được script 06 đo lại ngay trong phiên đó.
- Q6 vẫn là RFM đại diện từ đánh giá đã xác minh. Không diễn giải monetary bằng doanh thu thực hoặc NULL thành chi tiêu thực bằng 0.
- B-tree customer_key chủ yếu nhắm Q3. Có thể không cải thiện Q1/Q2/Q4/Q5/Q6; cần báo cáo đúng kết quả.

## Tệp kết quả

- `runs.jsonl`: từng lượt đo, trạng thái và kết quả đối chiếu.
- `summary.json`: cấu hình máy, tham số, chi phí chuẩn bị, kích thước index và trung vị.
- `comparison.csv`: bảng so sánh và hệ số tăng tốc với mốc cùng nhóm (Pandas CSV hoặc PostgreSQL).
- `*_plan.json`: EXPLAIN ANALYZE BUFFERS trước/sau index, thu ngoài lượt đo.
- `*.parquet`: kết quả đầy đủ từng truy vấn để đối chiếu lại. Tệp theo engine giữ lượt gần nhất.

Mỗi tag là một thực nghiệm riêng. Nếu lỗi trong warmup, xem traceback; không dùng thư mục chạy dở làm kết quả hoàn chỉnh. Chỉ dùng trung vị khi đủ số lần chạy thành công và mọi kết quả đều khớp. Nếu hết bộ nhớ/thời gian, báo cáo trạng thái đó thay vì bỏ qua.

## Công việc tiếp theo

1. Đo chính trên Colab: 10 triệu dòng, 5 lần; toàn bộ nếu đủ tài nguyên.
2. Xem kế hoạch Q3; cân nhắc index bảng chiều nếu chi phí nối còn cao, thử thành cấu hình riêng.
3. Bổ sung materialized view Q1/Q5 và đo chi phí tạo/làm mới trước khi công bố hiệu quả của tính sẵn.
4. Đo chi phí ghi/cập nhật khi có index. Hiện script chỉ đo tạo index và kích thước; chưa đo write amplification.
5. Làm EDA, từ điển dữ liệu, kiểm thử quy tắc làm sạch, báo cáo và slide.

Phạm vi hiện tại chưa gồm phân vùng, BRIN, materialized view, Redis, truy vấn xấp xỉ hay dashboard.

## Kiểm thử tính đúng đắn

```powershell
.venv\Scripts\python src\test_benchmark_optimized.py
```

Bộ kiểm thử bao gồm giá bị thiếu hoàn toàn trong một tháng, thể loại trống, xếp hạng đồng lượt đánh giá, ngày không có hoạt động, RFM và trường hợp hai kết quả có cùng tổng nhưng khác từng dòng. Ngoài kiểm thử nhỏ, mọi lần đo thực đều đối chiếu kết quả đầy đủ với Pandas CSV.
