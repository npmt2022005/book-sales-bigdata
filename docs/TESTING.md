# Kiểm thử và bàn giao

Chạy từ thư mục gốc `D:\book-sales-bigdata` bằng PowerShell:

```powershell
.venv\Scripts\python run_tests.py
```

Lệnh chạy ba nhóm theo thứ tự, dừng ngay khi có nhóm thất bại:

1. `src/test_benchmark_optimized.py`: 3 kiểm thử đối chiếu kết quả, gồm NULL, thứ tự collation, và trường hợp cùng tổng nhưng khác từng dòng.
2. `tests/test_data_rules.py`: fixture cố ý làm sai khóa, liên kết, điểm, giá trị tiền, cờ mô phỏng, nhãn cụm; thêm kiểm tra mô hình lưu lại tái tạo nhãn của 150.000 người trong mẫu.
3. `src/10_validate_data.py`: kiểm tra chỉ đọc trên toàn bộ warehouse, tồn kho mô phỏng, RFM và dữ liệu gán cụm.

Nhóm unittest trong tests hiện có thêm 3 kiểm tra ngoại tuyến trong `test_extended_results.py`: xác nhận 400 lượt mới, tính speedup theo baseline mới và đối chiếu chi phí/refresh. Tổng hai nhóm nhỏ là 13 test (3 benchmark + 7 quy tắc/mô hình + 3 kết quả bổ sung), tiếp theo là 37 kiểm tra dữ liệu. Dashboard có 6 AppTest riêng, không tính gộp thành kiểm tra dữ liệu nguồn.

`src/test_postgres_extended.py` là kiểm thử tích hợp PostgreSQL online về NULL, lịch có khoảng trống, dữ liệu thay đổi trước/sau REFRESH và cấu hình work_mem theo phiên. Chạy riêng khi PostgreSQL đang bật; không yêu cầu bật server chỉ để kiểm tra các kết quả Colab đã lưu.

Chạy hai nhóm kiểm thử nhỏ mà không quét toàn bộ dữ liệu:

```powershell
.venv\Scripts\python run_tests.py --unit-only
```

Lựa chọn `--unit-only` vẫn cần mẫu huấn luyện và model hiện có cho kiểm tra mô hình. Đây không phải một bộ test hoàn toàn độc lập dữ liệu.

Chỉ chạy kiểm tra dữ liệu và lưu kết quả:

```powershell
.venv\Scripts\python src\10_validate_data.py
```

Kết quả là `results/tests/data_validation.json`. Mỗi phép kiểm tra ghi số vi phạm, trạng thái và thời gian; lỗi SQL cũng là thất bại. Mã thoát 0 chỉ khi tất cả đạt. Chạy lại sẽ ghi mới báo cáo kiểm tra, không sửa Parquet, không tái tạo nguồn và không chạy lại benchmark.

Bộ kiểm thử không yêu cầu PostgreSQL chạy vì kiểm tra warehouse/RFM trên DuckDB. Môi trường cần pandas, pyarrow, duckdb, numpy, scikit-learn, joblib, threadpoolctl. Tham khảo `results/rfm_kmeans/requirements.txt` cho phiên bản đã dùng.

## Phạm vi và giới hạn

Các phép kiểm tra gồm khóa không trùng/không thiếu, FK, ngày lịch, giá/điểm/số lượng, công thức giá trị đại diện, tổng/ngày hoạt động từng người, lượng đại diện từng sách/tháng và quy tắc giá vốn mô phỏng. RFM được đối chiếu với warehouse theo từng người; việc loại nhóm thiếu giá, giới hạn và số cụm được kiểm tra riêng.

Fixture âm giúp chứng minh kiểm tra phát hiện một số dạng dữ liệu sai. Chưa chạy lại toàn bộ ETL từ 35 GB JSONL, chưa kiểm tra tính đúng đắn ngữ nghĩa của nguồn và chưa giả lập lỗi ổ đĩa/mất điện. Các kiểm thử không thay thế phép đo hiệu năng Colab. Chạy suite trên dữ liệu lớn có thể tốn vài phút và cần dung lượng tạm cho DuckDB.

## Dashboard: đã triển khai

Đã có Streamlit + DuckDB chạy cục bộ với bốn trang: tổng quan, EDA, hiệu năng và RFM. Trang hiệu năng chọn đợt 720 hoặc 400 lượt, mỗi đợt có baseline riêng; nhóm thiếu giá và giá trị đại diện được ghi rõ. Dữ liệu phục vụ giao diện là tổng hợp sẵn.

Không cần dashboard để chạy bộ kiểm thử hoặc đọc báo cáo HTML/Word. Chưa có hosting công khai, phân quyền hoặc kiểm thử tải đa người.
