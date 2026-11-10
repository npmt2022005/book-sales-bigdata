# Từ điển dữ liệu đề tài sách

Nguồn gốc: Amazon Reviews 2023 – Books. Từ điển mô tả tệp Parquet thực tế trong project. Các ràng buộc dưới đây là hợp đồng logic, không phải PRIMARY KEY được cưỡng chế trong Parquet.

## Quy ước và giới hạn

NULL là thiếu/không hợp lệ, không tự thay bằng 0. Giá dùng USD tại thời điểm thu thập; ngưỡng 1.000 USD là quyết định của nhóm. Lượt đánh giá có xác minh chỉ đại diện hoạt động mua; không có đơn hàng, số lượng hoặc ngày mua thực. Các khóa thay thế chỉ có ý nghĩa trong cùng lần xây warehouse.

Các cột mang tên sales/purchase/units_sold là tên kỹ thuật lịch sử; cách diễn giải phải theo mô tả bên dưới. Trong fact_inventory, units_sold được suy ra từ đánh giá; stock_quantity và unit_cost là mô phỏng. Tệp không có thông tin định danh như tên/email, nhưng user_id vẫn là mã nguồn cần quản lý phù hợp.

## Quan hệ và nguồn tạo

fact_sales nối dim_books, dim_customers, dim_date qua các khóa tương ứng. fact_inventory nối dim_books và dùng month_key riêng. RFM nối dim_customers qua customer_key. Script 03 xây bốn bảng chính, script 04 tạo tồn kho mô phỏng, script 09 tạo RFM và nhãn cụm. EDA là script 08; các bảng kết quả EDA/benchmark là bảng tổng hợp dẫn xuất, không bổ sung giao dịch thật.

## dim_books

Đường dẫn: `data\warehouse\dim_books.parquet`. Số dòng: 4,448,181. Khóa logic: book_key (PK), parent_asin (duy nhất).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `book_key` | `BIGINT` | Khóa thay thế của sản phẩm; sinh khi xây warehouse, không ổn định nếu xây lại bằng quy tắc khác. |
| `parent_asin` | `VARCHAR` | Mã sản phẩm cha Amazon; khóa nghiệp vụ để nối metadata và đánh giá, không nhất thiết là một tác phẩm duy nhất. |
| `title` | `VARCHAR` | Tên sản phẩm sách từ metadata; chuỗi trống chuyển NULL. |
| `author` | `VARCHAR` | Tác giả từ metadata, có thể NULL. |
| `category` | `VARCHAR` | Nhãn danh mục nguồn; thiếu chuyển Unknown. Có thể gồm chiến dịch hoặc bộ sưu tập, chưa phải hệ thể loại chuẩn. |
| `publisher` | `VARCHAR` | Nhà xuất bản trích từ publisher_raw, loại phần sau dấu ; hoặc (, có thể thiếu hoặc không chính xác. |
| `isbn_13` | `VARCHAR` | Chuỗi 13 chữ số sau loại ký tự khác; chưa xác minh checksum ISBN. |
| `publish_year` | `INTEGER` | Năm trích từ cuối publisher_raw nếu 1400–2024; không phải năm đã xác minh. |
| `language` | `VARCHAR` | Ngôn ngữ theo metadata, có thể thiếu. |
| `pages` | `INTEGER` | Số trang theo nguồn, có thể thiếu; chưa bảo đảm mọi định dạng sản phẩm có số trang tương đương. |
| `list_price` | `DOUBLE` | Giá USD tại thời điểm thu thập; chỉ giữ 0 < giá ≤ 1000, ngoài ngưỡng/thiếu thành NULL. |
| `average_rating` | `FLOAT` | Điểm hiển thị trong metadata, không phải điểm tính lại từ tập fact đã lọc. |
| `rating_number` | `INTEGER` | Số đánh giá hiển thị trong metadata, không đồng nhất số dòng trong fact_sales. |

## dim_customers

Đường dẫn: `data\warehouse\dim_customers.parquet`. Số dòng: 8,353,809. Khóa logic: customer_key (PK), user_id (duy nhất).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `customer_key` | `BIGINT` | Khóa thay thế của người đánh giá; không chứa tên, email hoặc địa chỉ. |
| `user_id` | `VARCHAR` | Mã người đánh giá nguồn Amazon; khóa nghiệp vụ, không phải mã khách hàng giao dịch đã xác thực. |
| `first_purchase_date` | `DATE` | Ngày đánh giá đã xác minh đầu tiên trong tập sạch; tên cột cũ không có nghĩa đây là ngày mua. |
| `last_purchase_date` | `DATE` | Ngày đánh giá đã xác minh cuối cùng trong tập sạch; không phải ngày mua thực. |
| `total_purchases` | `BIGINT` | Tổng số lượt đánh giá đã xác minh của người dùng sau làm sạch; không phải tổng đơn hàng. |

## dim_date

Đường dẫn: `data\warehouse\dim_date.parquet`. Số dòng: 9,711. Khóa logic: date_key (PK).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `date_key` | `INTEGER` | Khóa ngày YYYYMMDD, nối fact_sales.date_key. |
| `date` | `DATE` | Ngày lịch UTC được suy ra từ timestamp nguồn. |
| `day` | `BIGINT` | Ngày trong tháng 1–31. |
| `week` | `BIGINT` | Tuần ISO 1–53; kết hợp year không phải cặp ISO-year chuẩn. |
| `month` | `BIGINT` | Tháng 1–12. |
| `quarter` | `BIGINT` | Quý 1–4. |
| `year` | `BIGINT` | Năm lịch. |
| `is_weekend` | `BOOLEAN` | TRUE khi thứ Bảy hoặc Chủ nhật theo ISO weekday. |

## fact_sales

Đường dẫn: `data\warehouse\fact_sales.parquet`. Số dòng: 20,342,188. Khóa logic: sale_id (PK).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `sale_id` | `BIGINT` | Khóa thay thế của lượt đánh giá đã xác minh, không phải mã đơn hàng thật. |
| `date_key` | `INTEGER` | FK đến dim_date.date_key, ngày viết đánh giá. |
| `customer_key` | `BIGINT` | FK đến dim_customers.customer_key. |
| `book_key` | `BIGINT` | FK đến dim_books.book_key. |
| `quantity` | `TINYINT` | Giả định bằng 1 mỗi lượt, không có số lượng mua thực trong nguồn. |
| `price_usd` | `DOUBLE` | Sao chép list_price hợp lệ của sản phẩm tại thu thập, USD; có thể NULL. |
| `estimated_revenue` | `DOUBLE` | quantity × price_usd, chỉ là giá trị đại diện; thiếu giá thì NULL, không dùng làm doanh thu thực. |
| `rating` | `FLOAT` | Điểm của đánh giá được giữ lại, 1–5. |
| `helpful_vote` | `INTEGER` | Số lượt hữu ích; giữ giá trị lớn nhất khi gộp bản ghi trùng, không phải số lượt mua. |

## fact_inventory

Đường dẫn: `data\warehouse\fact_inventory.parquet`. Số dòng: 4,347,336. Khóa logic: (book_key, month_key) (PK ghép).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `book_key` | `BIGINT` | FK đến dim_books.book_key, chỉ các sản phẩm có hoạt động trong 09/2022–08/2023. |
| `month_key` | `BIGINT` | Tháng YYYYMM từ 202209 đến 202308; khóa ghép với book_key. |
| `units_sold` | `DOUBLE` | Tổng quantity từ fact_sales theo sách/tháng; đặt tên cũ, thực tế là số lượt đánh giá đại diện, không phải lượng bán đo được. |
| `stock_quantity` | `INTEGER` | Tồn kho mô phỏng bằng hàm băm và số lượt đại diện; số nguyên không âm, không phải tồn kho thực. |
| `unit_cost` | `DOUBLE` | Giá vốn mô phỏng bằng 50–80% list_price, làm tròn 2 chữ số; NULL nếu thiếu giá. |
| `is_simulated` | `BOOLEAN` | Luôn TRUE; đánh dấu bảng lớp kinh doanh mô phỏng. |

## rfm_all_users

Đường dẫn: `results\rfm_kmeans\rfm_all_users.parquet`. Số dòng: 8,353,809. Khóa logic: customer_key (PK/FK).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `customer_key` | `BIGINT` | Khóa người dùng trong dim_customers. |
| `recency` | `BIGINT` | Số ngày từ đánh giá cuối đến 2023-09-15; không tính đến ngày hiện tại. |
| `frequency` | `BIGINT` | Số lượt đánh giá đã xác minh trong tập sạch, bằng total_purchases. |
| `priced_reviews` | `BIGINT` | Số lượt có price_usd hợp lệ; từ 0 đến frequency. |
| `monetary_observed` | `DOUBLE` | Tổng estimated_revenue quan sát được; tất cả thiếu giữ NULL, thiếu một phần chỉ là tổng một phần. |
| `price_coverage` | `DOUBLE` | priced_reviews / frequency, tỷ lệ 0–1. |
| `eligible` | `BOOLEAN` | TRUE khi mọi lượt đều có giá hợp lệ; chỉ nhóm này đưa vào K-Means. |
| `frequency_stratum` | `VARCHAR` | Tầng lấy mẫu theo F: 1, 2, 3-5, 6-10, 11-50, >50. |

## rfm_with_clusters

Đường dẫn: `results\rfm_kmeans\rfm_with_clusters.parquet`. Số dòng: 8,353,809. Khóa logic: customer_key (PK/FK).

| Cột | Kiểu DuckDB quan sát | Ý nghĩa và quy tắc |
|---|---|---|
| `customer_key` | `BIGINT` | Khóa người dùng trong dim_customers. |
| `recency` | `BIGINT` | Số ngày từ đánh giá cuối đến 2023-09-15; không tính đến ngày hiện tại. |
| `frequency` | `BIGINT` | Số lượt đánh giá đã xác minh trong tập sạch, bằng total_purchases. |
| `priced_reviews` | `BIGINT` | Số lượt có price_usd hợp lệ; từ 0 đến frequency. |
| `monetary_observed` | `DOUBLE` | Tổng estimated_revenue quan sát được; tất cả thiếu giữ NULL, thiếu một phần chỉ là tổng một phần. |
| `price_coverage` | `DOUBLE` | priced_reviews / frequency, tỷ lệ 0–1. |
| `eligible` | `BOOLEAN` | TRUE khi mọi lượt đều có giá hợp lệ; chỉ nhóm này đưa vào K-Means. |
| `frequency_stratum` | `VARCHAR` | Tầng lấy mẫu theo F: 1, 2, 3-5, 6-10, 11-50, >50. |
| `cluster` | `INTEGER` | Nhãn K-Means 0..k-1, không có thứ hạng; -1 là thiếu giá nên không phân cụm. Mô hình hiện tại k=2. |

## Quy tắc xây dựng và đối chiếu

Đánh giá: lọc verified_purchase=true, khóa nguồn không thiếu, rating 1–5, timestamp hợp lệ 1996–2023; gộp theo (user_id, parent_asin, timestamp_ms), any_value(rating), max(helpful_vote). Quy tắc any_value có thể chọn điểm không xác định nếu bản trùng có rating khác nhau; chưa có kiểm thử tái tạo toàn bộ nguồn thô ở bộ kiểm thử này.

Sách: một parent_asin giữ dòng có rating_number lớn nhất; nhãn thiếu thành Unknown. ISBN chỉ kiểm tra đủ 13 chữ số sau chuẩn hóa. Năm xuất bản được trích bằng biểu thức chính quy nên có thể thiếu hoặc sai theo nội dung nguồn.

Ngày: lịch liên tục từ ngày đánh giá đầu đến cuối. Khách: tổng số lượt, ngày đầu/cuối đều tính từ tập sạch. RFM: chỉ phân cụm nhóm đầy đủ giá; không gán giá thiếu thành 0. Tồn kho: seed 20261109, 12 tháng 09/2022–08/2023.

Bộ kiểm thử xác minh tính toàn vẹn warehouse và RFM trên dữ liệu hiện có; không chứng minh dữ liệu nguồn đúng thực tế, không xác minh đầy đủ quyền sử dụng nguồn và không đo lại toàn bộ hiệu năng Colab.
