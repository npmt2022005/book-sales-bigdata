# Bổ sung PostgreSQL: work_mem và materialized view

## Các cấu hình

- `postgres_4mb`: baseline đo lại, work_mem=4 MB.
- `postgres_32mb`: cùng dữ liệu và SQL, work_mem=32 MB.
- `postgres_64mb`: cùng dữ liệu và SQL, work_mem=64 MB.
- `materialized_4mb`: work_mem=4 MB, Q1 đọc mv_monthly, Q5 đọc mv_daily rồi tính trung bình trượt trên lịch đầy đủ.

Giữ max_parallel_workers_per_gather=2 ở mọi cấu hình. Không đổi work_mem toàn server. PostgreSQL có thể cấp work_mem cho nhiều nút, worker và phép hash (theo hash_mem_multiplier); không hiểu 64 MB là trần RAM toàn tiến trình. Chạy tuần tự, hủy backend riêng của worker nếu RAM trống xuống ngưỡng, có statement_timeout. Theo dõi RAM thực tế trên Colab.

Baseline fact phải chưa có index. Các materialized view ở schema mới và chỉ đọc bảng baseline; không sửa dữ liệu nguồn. Chi phí tạo view, ANALYZE, dung lượng và full REFRESH được lưu riêng. Chưa đo cập nhật nguồn/ghi đồng thời, refresh concurrent hay refresh gia tăng.

## Thiết kế đo

Đo lại baseline trong cùng phiên, cùng SQL và số dòng. Mỗi tổ hợp lặp 5 lần sau lượt khởi động, thứ tự xáo ngẫu nhiên. Đối chiếu toàn bộ kết quả; chuẩn hóa thứ tự chữ ở client. Các cấu hình work_mem chạy Q1–Q6; materialized view chỉ Q1/Q5, không giả định có kết quả cho các truy vấn khác.

Mỗi mức có (3 × 6 + 2) × 5 = 100 lượt đo chính. Bốn mức có 400 lượt, ngoài tham chiếu/warmup/EXPLAIN và refresh. Thời gian đo gồm kết nối, thiết lập phiên, thực thi và nhận đầy đủ kết quả. Không ghép trực tiếp thời gian notebook cũ với phép đo mới để tính speedup; dùng postgres_4mb mới.

Mỗi view được REFRESH đầy đủ 5 lần sau vòng đo, không thay đổi dữ liệu nguồn; giá trị được đối chiếu lại sau refresh. Thời gian tạo và refresh không nằm trong thời gian query. `create_break_even_queries` là ceil(create_time / saving_per_query), chỉ là ước tính từ trung vị, chưa gồm lưu trữ, làm mới, cập nhật hoặc tải đồng thời.

## Chạy cục bộ

```powershell
.venv\Scripts\python src\pg_local.py start
.venv\Scripts\python src\test_postgres_extended.py
.venv\Scripts\python src\13_benchmark_postgres_extended.py --sizes 1m --repeats 2 --tag extended_local_check
```

Dùng tag mới cho lần chạy mới; không ghi đè kết quả. Schema bổ sung được giữ lại để kiểm tra. Kiểm thử fixture xóa đúng hai schema ngẫu nhiên do nó tạo, không xóa baseline của project.

## Chạy Colab

Dùng notebook `Bo_sung_PostgreSQL_Colab.ipynb`, tải lên tài khoản có My Drive/book-sales-colab. Notebook nhúng script, kết nối Drive và chép dữ liệu về runtime. Mặc định 4 mức (1m,5m,10m,full), 5 lần. Có thể đổi PLAN=['full'] để chỉ đo mức chính, nhưng phải giữ đủ baseline mới trong cùng phiên.

Kết quả nằm trong `book-sales-colab/results/pg_extended_<phiên>`. Mỗi mức có summary.json, runs.jsonl, comparison.csv, EXPLAIN JSON và kết quả từng dòng. Console và checkpoint nhẹ được lưu trong quá trình chạy; sao lưu toàn bộ sau mỗi mức. Khi lỗi, dừng và giữ kết quả dở để chẩn đoán; không dùng làm số liệu cuối.

## Trạng thái báo cáo

Đã hoàn thành đợt Colab `pg_extended_1110_132250`: 400 lượt đo chính, đủ 4 quy mô, 5 lần/tổ hợp; mọi kết quả khớp baseline. Đã xác minh 40 lần refresh trên 8 view và kết quả sau refresh. Hồ sơ kiểm chứng trong `results/postgres_extended_colab/validation.json`; script 14 tính lại trung vị từ lượt gốc và đối chiếu CSV nguồn.

Báo cáo Word/PDF có mục 5.4 riêng; dashboard có bộ chọn đợt cơ bản (720 lượt) và đợt bổ sung (400 lượt). Tổng 1.120 lượt ở hai đợt độc lập, không phải tất cả cấu hình trên cùng một CPU. Baseline của đợt bổ sung là postgres_4mb mới. Kết quả máy cá nhân vẫn giữ riêng.

Trên toàn bộ dữ liệu: 64 MB giúp Q2 khoảng 1,13 lần, 32 MB giúp Q5 khoảng 1,28 lần; không cải thiện mọi truy vấn. Materialized view giúp Q1 khoảng 331,24 lần và Q5 khoảng 128,17 lần. Đọc view không bao gồm tạo/refresh; nguồn thay đổi phải làm mới. Chưa đo ghi nguồn đồng thời hay concurrent refresh.
