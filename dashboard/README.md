# Bookscope — Dashboard dữ liệu sách

Từ thư mục gốc project:

```powershell
.venv\Scripts\python -m streamlit run dashboard\app.py --server.address 127.0.0.1 --server.port 8501
```

Mở http://localhost:8501. Dashboard chỉ phục vụ trên máy này; chưa publish lên internet.

Nếu dùng ZIP trên máy khác: giải nén, mở terminal tại thư mục dashboard và chạy:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Môi trường đã kiểm tra là Python 3.11. Cấu hình trong .streamlit tắt thu thập thống kê sử dụng. Dừng server bằng Ctrl+C trong terminal đã chạy.

Bản đóng gói có sẵn thư mục data nhỏ, không cần tải 35 GB nguồn thô hoặc nạp 20 triệu dòng vào trình duyệt. App chỉ truy vấn dữ liệu tổng hợp bằng DuckDB và cache kết quả bộ lọc. Không thay đổi warehouse hoặc huấn luyện mô hình.

Nếu cần chuẩn bị lại data từ project đầy đủ:

```powershell
.venv\Scripts\python dashboard\prepare_data.py
```

Lệnh này cần warehouse và các kết quả EDA, RFM, benchmark, kiểm thử đã có. Nó ghi lại dữ liệu dẫn xuất của dashboard. Không bấm chạy trong khi app đang có người sử dụng.

## Trang và bộ lọc

- Hiệu năng: chọn quy mô, truy vấn và các engine trên biểu đồ xu hướng. Dùng trung vị 5 lần; IQR không phải khoảng tin cậy. Speedup theo mốc cùng nhóm.
- Trang Hiệu năng có hai đợt độc lập: 720 lượt cơ bản và 400 lượt PostgreSQL bổ sung. Chọn đợt trước; không chia thời gian hai đợt cho nhau. Đợt mới có work_mem 4/32/64 MB và materialized view Q1/Q5, cùng chi phí tạo/ANALYZE/full refresh và dung lượng.
- Tổng quan: thống kê toàn bộ, ngày và kiểm tra dữ liệu đã lưu.
- Khám phá sách: danh mục và khoảng năm áp dụng biểu đồ tháng/điểm; bảng top sách theo danh mục dùng toàn bộ thời gian và được ghi rõ.
- RFM: hồ sơ cụm, nhóm thiếu giá và bằng chứng chọn k. Không hiển thị user_id.

## Giới hạn

Đây là đánh giá có xác minh mua hàng, không phải đơn hàng. Không trình bày doanh thu hay số lượng bán thực. RFM dùng giá đại diện; người thiếu giá được giữ riêng. Dữ liệu nguồn kết thúc 14/09/2023; không suy diễn xu hướng hiện tại. Có B-tree, work_mem và materialized view trong các đợt tương ứng; chưa có Polars, BRIN, partition. Tăng work_mem không giới hạn tổng RAM server; materialized view có thể cũ cho tới khi refresh.

## Kiểm tra giao diện

```powershell
.venv\Scripts\python -m unittest discover -s dashboard\tests -v
```

Kiểm tra bốn trang, thay bộ lọc, dữ liệu tổng hợp và phép tính speedup bằng Streamlit AppTest. Không thay thế việc xem trực quan trên trình duyệt.
