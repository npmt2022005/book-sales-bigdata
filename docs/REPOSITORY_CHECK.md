# Kiểm tra bản chuẩn bị nộp GitHub

Ngày: 11/11/2026.

## Đã thực hiện

- Khởi tạo branch `main`, gắn remote `https://github.com/npmt2022005/book-sales-bigdata.git` trên tài khoản npmt2022005. Repository riêng tư.
- README mô tả mục tiêu, thành viên, dữ liệu, cách cài/chạy, hai đợt đo, kết quả, EDA/RFM, tests và giới hạn.
- Có requirements runtime/report và hướng dẫn dữ liệu ngoài Git.
- Đưa hai notebook Colab vào notebooks; giữ bản cuối của PDF/Word trong reports/submission.
- Bỏ qua môi trường ảo, data thô/warehouse/PG, ZIP, log, spill, model và artifacts từng người.
- Chỉ giữ hai Parquet tổng hợp của dashboard, có chủ ý.
- Thêm GitHub Actions cho tests ngoại tuyến và Streamlit AppTest. Workflow chưa được GitHub thực thi vì chưa push.

## Kiểm tra bản sao giống bản clone

Tạo bản sao chỉ chứa các tệp Git không bỏ qua, dùng môi trường Python đã cài dependencies để chạy:

```text
python run_tests.py --unit-only
python -m unittest discover -s dashboard/tests -v
```

Kết quả: **12 test project đạt, 1 test model skip đúng lý do; 6 test dashboard đạt**. Mẫu/model không thuộc Git nên test round-trip không thể chạy từ bản clone. Trên máy nhóm có đủ artifacts, bộ project đã đạt 13 test và 37 kiểm tra dữ liệu.

Đã kiểm tra các liên kết tệp trong README tồn tại trong bản sao, toàn bộ mã Python parse được và pip check không báo dependency hỏng. Đây không phải một lần cài mới hoàn toàn trên máy khác: dùng interpreter/dependencies đang có. CI cấu hình cài mới trên Ubuntu/Python 3.11 để tiếp tục kiểm chứng khi repository được push.

## Truy cập bài nộp

URL: https://github.com/npmt2022005/book-sales-bigdata . Với repository riêng tư, giảng viên cần được cấp quyền hoặc nhóm phải chuyển quyền truy cập theo yêu cầu môn. Bản local không bao gồm dữ liệu lớn bị Git bỏ qua; phần dữ liệu tổng hợp và báo cáo đủ để xem sản phẩm.
