# Chuẩn bị dữ liệu ngoài Git

## Xem sản phẩm không cần dữ liệu thô

Clone repo, cài requirements và chạy dashboard. `dashboard/data` có sẵn các tổng hợp cần thiết, không yêu cầu warehouse, PostgreSQL hoặc model. Kết quả CSV/JSON và báo cáo được chọn lọc trong repo phục vụ kiểm tra số liệu.

## Nguồn chính thức

Amazon Reviews 2023, nhóm Books, [McAuley Lab trên Hugging Face](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023): tải tệp review Books và metadata meta_Books từ liên kết nguồn. Không cần tải các nhóm sản phẩm khác.

Các tệp có thể ở dạng `.jsonl` hoặc `.jsonl.gz`; script 01 hỗ trợ cả hai. Đặt trong `external/` (được Git bỏ qua) và chỉ đường dẫn bằng `--input`. Khi dùng mặc định, script tìm `data/raw/amazon/Books.jsonl` và `meta_Books.jsonl`.

Tệp `results/source_checksums.sha256` là SHA-256 của **bản JSONL giải nén đã dùng**. Không so trực tiếp SHA-256 đó với file gzip vì khác bytes. Nếu tải bản nguồn mới, ghi lại checksum và không giả định số đếm giống bộ đã nộp.

## Warehouse cần cho kiểm thử đầy đủ

```text
data/warehouse/
  dim_books.parquet
  dim_customers.parquet
  dim_date.parquet
  fact_sales.parquet
  fact_inventory.parquet
```

Có thể tạo bằng script 01–04 theo README hoặc dùng bản warehouse đã bàn giao từ nhóm. Repo chưa cung cấp URL công khai cho warehouse đầy đủ; không có cơ chế tải ngầm. Dung lượng/đường dẫn trên máy nhóm không phải link tải cho người clone.

Để chạy kiểm tra RFM đầy đủ còn cần:

```text
results/rfm_kmeans/
  rfm_all_users.parquet
  rfm_with_clusters.parquet
  training_sample_with_clusters.parquet
  model.joblib
```

Script 09 tạo chúng từ warehouse. Model dùng joblib; chỉ nạp artifact đáng tin cậy. Tệp theo từng người dùng không nằm trong Git. Test mô hình được skip có lý do khi artifacts chưa có; kiểm tra toàn warehouse không được xem là pass chỉ từ bản clone thiếu dữ liệu.

## Thư mục Drive cho Colab

```text
My Drive/book-sales-colab/
  manifest.json
  warehouse/
    dim_books.parquet
    dim_customers.parquet
    dim_date.parquet
    fact_sales.parquet
  results/  # notebook tự lưu từng quy mô tại đây
```

Notebook không cần inventory mô phỏng cho sáu truy vấn benchmark. Manifest cần đúng byte size và SHA-256 từng tệp; không sử dụng manifest có sẵn nếu đã tạo một warehouse khác. Bản manifest của bộ đã nộp nằm trong `notebooks/warehouse_manifest.json`.

Chọn CPU và tài khoản Drive có thư mục này. Mỗi notebook tự chép dữ liệu về đĩa runtime, kiểm hash và đo lại baseline trong phiên. Nếu muốn chỉ thử mức đầy đủ, sửa PLAN=['full']; để tái lập đồ thị xu hướng giữ 4 mức. Không coi thời gian chạy nguồn mới hoặc phiên mới là số đo cũ.

## ZIP kết quả gốc

- Cơ bản: `results-20261109T144133Z-1-001.zip`, phiên `optimized_4sizes_1109_111529`.
- Bổ sung: `pg_extended_1110_132250-20261110T173019Z-1-001.zip`.

ZIP gốc không commit. Có thể đặt trong `external/` rồi truyền `--archive` cho script 07/14. Cấu trúc parser hiện dành cho các phiên này; nếu chạy mới phải cập nhật ánh xạ phiên thay vì gán số đo mới cho mã phiên cũ. Thư mục `results/postgres_extended_colab/evidence` chứa summary/EXPLAIN đã chọn lọc để kiểm tra 400 lượt mà không cần ZIP.
