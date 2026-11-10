"""EDA of cleaned verified book reviews; no simulated inventory or revenue claims."""
import base64
import csv
import html
import json
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/eda_sach'
OUT.mkdir(exist_ok=True)
FIG = OUT / 'figures'
FIG.mkdir(exist_ok=True)
TABLES = OUT / 'tables'
TABLES.mkdir(exist_ok=True)
con = duckdb.connect()
con.execute("SET memory_limit='2GB'")
con.execute('SET threads=2')
con.execute(f"SET temp_directory='{(OUT/'spill').as_posix()}'")
for table in ['fact_sales', 'dim_books', 'dim_customers', 'dim_date']:
    path=(ROOT/'data/warehouse'/f'{table}.parquet').as_posix().replace("'", "''")
    con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path}')")

def query(name, sql):
    frame=con.execute(sql).fetchdf()
    frame.to_csv(TABLES/(name+'.csv'),index=False,encoding='utf-8-sig')
    print('Saved:',name,flush=True)
    return frame

overview=query('01_tong_quan', '''SELECT count(*) AS reviews, count(DISTINCT customer_key) AS users,
 count(DISTINCT book_key) AS reviewed_books, min(d.date) AS first_date, max(d.date) AS last_date,
 avg(rating) AS average_rating, count(*) FILTER(WHERE price_usd IS NULL) AS missing_price_reviews,
 count(*) FILTER(WHERE rating<1 OR rating>5 OR rating IS NULL) AS invalid_rating,
 count(*) FILTER(WHERE quantity<>1 OR quantity IS NULL) AS unexpected_quantity
 FROM fact_sales JOIN dim_date d USING(date_key)''')
o=overview.iloc[0]
catalog=con.execute('SELECT count(*) FROM dim_books').fetchone()[0]
assert int(o.reviews)==20_342_188
assert int(o.invalid_rating)==0 and int(o.unexpected_quantity)==0
yearly=query('02_theo_nam', '''SELECT d.year,count(*) AS reviews,avg(f.rating) AS average_rating,
 count(*) FILTER(WHERE f.price_usd IS NULL) AS missing_price_reviews
 FROM fact_sales f JOIN dim_date d USING(date_key) GROUP BY 1 ORDER BY 1''')
monthly=query('03_theo_thang', '''SELECT date_trunc('month',d.date)::DATE AS month,count(*) AS reviews,
 avg(f.rating) AS average_rating FROM fact_sales f JOIN dim_date d USING(date_key) GROUP BY 1 ORDER BY 1''')
ratings=query('04_phan_phoi_diem', 'SELECT rating,count(*) AS reviews FROM fact_sales GROUP BY 1 ORDER BY 1')
assert int(yearly.reviews.sum())==int(monthly.reviews.sum())==int(ratings.reviews.sum())==int(o.reviews)

# Aggregate before joining wide book metadata, using a bounded-memory SQL engine.
con.execute('''CREATE TEMP TABLE book_activity AS SELECT book_key,count(*) AS reviews,
 sum(rating) AS rating_sum,avg(rating) AS average_rating,
 count(*) FILTER(WHERE price_usd IS NULL) AS missing_price_reviews
 FROM fact_sales GROUP BY 1''')
topbooks=query('05_top_sach', '''SELECT b.parent_asin,b.title,b.category,a.reviews,a.average_rating,b.list_price
 FROM book_activity a JOIN dim_books b USING(book_key) ORDER BY a.reviews DESC,a.book_key LIMIT 20''')
categories=query('06_the_loai', '''SELECT b.category,sum(a.reviews)::BIGINT AS reviews,count(*) AS reviewed_books,
 sum(a.rating_sum)/sum(a.reviews) AS average_rating,
 sum(a.missing_price_reviews)::BIGINT AS missing_price_reviews
 FROM book_activity a JOIN dim_books b USING(book_key) GROUP BY 1 ORDER BY reviews DESC,category''')
categories['missing_price_pct']=100*categories.missing_price_reviews/categories.reviews
categories.to_csv(TABLES/'06_the_loai.csv',index=False,encoding='utf-8-sig')
assert int(categories.reviews.sum())==int(o.reviews)
missing=query('07_thieu_thong_tin_danh_muc', '''SELECT count(*) AS books,
 count(*) FILTER(WHERE list_price IS NULL) AS missing_price,
 count(*) FILTER(WHERE author IS NULL OR trim(author)='') AS missing_author,
 count(*) FILTER(WHERE category IS NULL OR trim(category)='' OR category='Unknown') AS unknown_category,
 count(*) FILTER(WHERE publisher IS NULL OR trim(publisher)='') AS missing_publisher,
 count(*) FILTER(WHERE isbn_13 IS NULL OR trim(isbn_13)='') AS missing_isbn,
 count(*) FILTER(WHERE pages IS NULL) AS missing_pages,
 count(*) FILTER(WHERE publish_year IS NULL) AS missing_publish_year,
 count(*) FILTER(WHERE list_price IS NOT NULL AND (list_price<=0 OR list_price>1000)) AS invalid_clean_price
 FROM dim_books''')
assert int(missing.iloc[0].invalid_clean_price)==0
price=query('08_gia_sach', '''SELECT count(list_price) AS valid_price_books,min(list_price) AS min_price,
 quantile_cont(list_price,.25) AS p25,median(list_price) AS median_price,
 quantile_cont(list_price,.75) AS p75,quantile_cont(list_price,.95) AS p95,max(list_price) AS max_price
 FROM dim_books''')
pricebins=query('09_nhom_gia', '''SELECT CASE WHEN list_price<=10 THEN '0–10' WHEN list_price<=20 THEN '10–20'
 WHEN list_price<=50 THEN '20–50' WHEN list_price<=100 THEN '50–100' ELSE '100–1.000' END AS price_band,
 count(*) AS books,min(list_price) AS lower_sort FROM dim_books WHERE list_price IS NOT NULL
 GROUP BY 1 ORDER BY lower_sort''')
activity=query('10_tan_suat_nguoi_dung', '''SELECT CASE WHEN total_purchases=1 THEN '1' WHEN total_purchases=2 THEN '2'
 WHEN total_purchases<=5 THEN '3–5' WHEN total_purchases<=10 THEN '6–10' WHEN total_purchases<=50 THEN '11–50'
 ELSE '>50' END AS review_band,count(*) AS users,sum(total_purchases)::BIGINT AS reviews,min(total_purchases) AS lower_sort
 FROM dim_customers GROUP BY 1 ORDER BY lower_sort''')
users=query('11_tong_quan_nguoi_dung', '''SELECT count(*) AS users,sum(total_purchases)::BIGINT AS reviews,
 median(total_purchases) AS median_reviews,max(total_purchases) AS max_reviews,
 count(*) FILTER(WHERE total_purchases=1) AS one_review_users FROM dim_customers''')
assert int(users.iloc[0].users)==int(o.users) and int(users.iloc[0].reviews)==int(o.reviews)
assert int(activity.users.sum())==int(o.users)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
def save(name):
    plt.tight_layout()
    plt.savefig(FIG/(name+'.png'),dpi=190,bbox_inches='tight')
    plt.savefig(FIG/(name+'.pdf'),bbox_inches='tight')
    plt.close()

plt.figure(figsize=(11,5)); colors=['#0284c7' if y not in [1997,2023] else '#d97706' for y in yearly.year]
plt.bar(yearly.year,yearly.reviews/1e6,color=colors);plt.xlabel('Năm đánh giá');plt.ylabel('Triệu lượt đánh giá')
plt.title('Lượt đánh giá đã xác minh theo năm · 1997 và 2023 là năm không đầy đủ');save('01_theo_nam')
plt.figure(figsize=(12,5));plt.plot(monthly.month,monthly.reviews/1000,color='#0284c7',linewidth=1.3)
plt.axvspan(monthly.month.iloc[-1],o.last_date,color='#d97706',alpha=.2)
plt.xlabel('Tháng đánh giá');plt.ylabel('Nghìn lượt');plt.title('Lượt đánh giá theo tháng · Tháng 9/2023 chưa đầy đủ');save('02_theo_thang')
plt.figure(figsize=(8,5));bars=plt.bar(ratings.rating.astype(str),100*ratings.reviews/o.reviews,color='#059669')
plt.bar_label(bars,fmt='%.1f%%',padding=3);plt.ylim(0,100);plt.xlabel('Điểm sao');plt.ylabel('Tỷ lệ lượt đánh giá (%)')
plt.title('Phân phối điểm trong các đánh giá đã xác minh');save('03_diem_danh_gia')
top=topbooks.head(15).iloc[::-1];plt.figure(figsize=(12,8))
labels=[str(t) if len(str(t))<=64 else str(t)[:61]+'…' for t in top.title]
plt.barh(range(len(top)),top.reviews/1000,color='#0284c7');plt.yticks(range(len(top)),labels,fontsize=8)
plt.xlabel('Nghìn lượt đánh giá');plt.title('15 sản phẩm sách được đánh giá đã xác minh nhiều nhất');save('04_top_sach')
cat=categories.head(15).iloc[::-1];plt.figure(figsize=(11,7))
plt.barh(cat.category,cat.reviews/1e6,color='#059669');plt.xlabel('Triệu lượt đánh giá')
plt.title('15 nhãn danh mục có nhiều đánh giá nhất · Nhãn lấy từ nguồn Amazon');save('05_the_loai')
mr=missing.iloc[0]; fields=['missing_price','missing_author','unknown_category','missing_publisher','missing_isbn','missing_pages','missing_publish_year']
labels=['Giá hợp lệ','Tác giả','Thể loại','Nhà xuất bản','ISBN-13','Số trang','Năm xuất bản']
plt.figure(figsize=(10,5));bars=plt.barh(labels[::-1],[100*mr[f]/catalog for f in fields][::-1],color='#d97706')
plt.bar_label(bars,fmt='%.1f%%',padding=3);plt.xlim(0,110);plt.xlabel('Tỷ lệ thiếu / Unknown (%) trên toàn bộ danh mục')
plt.title('Thông tin thiếu sau làm sạch · Không phải chỉ trên sách có đánh giá');save('06_thieu_du_lieu')
plt.figure(figsize=(9,5));plt.bar(pricebins.price_band,pricebins.books/1000,color='#0284c7')
plt.xlabel('Khoảng giá USD: cận dưới mở, cận trên đóng');plt.ylabel('Nghìn sản phẩm sách')
plt.title('Giá tại thời điểm thu thập · Chỉ lấy 0 < giá ≤ 1.000 USD');save('07_phan_phoi_gia')
plt.figure(figsize=(9,5));bars=plt.bar(activity.review_band,100*activity.users/o.users,color='#059669')
plt.bar_label(bars,fmt='%.1f%%',padding=3);plt.ylim(0,100);plt.xlabel('Số lượt đánh giá đã xác minh của một người dùng')
plt.ylabel('Tỷ lệ người dùng (%)');plt.title('Mức độ hoạt động đánh giá · Không phải tần suất mua hàng');save('08_nguoi_dung')

blocks=[]
def h(t):blocks.append(('heading',t))
def p(t):blocks.append(('paragraph',t))
def fig(n,t):blocks.append(('figure',(n,t)))
def table(headers,rows):blocks.append(('table',[headers]+rows))
def number(v):return f'{int(v):,}'.replace(',','.')
h('Phân tích khám phá dữ liệu sách và đánh giá khách hàng')
p('EDA trên các bảng đã làm sạch trong data/warehouse. Chỉ dùng đánh giá có verified_purchase=true sau kiểm tra hợp lệ, gộp trùng và nối danh mục. Không dùng tồn kho, giá vốn mô phỏng hoặc suy ra doanh thu thực. Phạm vi này khác bộ đánh giá Amazon thô ban đầu.')
h('1. Tổng quan và kiểm tra tính nhất quán')
table(['Chỉ tiêu','Kết quả'],[['Lượt đánh giá',number(o.reviews)],['Người đánh giá',number(o.users)],['Sản phẩm có đánh giá trong tập sạch',number(o.reviewed_books)],['Toàn bộ danh mục sách',number(catalog)],['Ngày đầu',str(o.first_date.date())],['Ngày cuối',str(o.last_date.date())],['Điểm trung bình',f'{o.average_rating:.3f} / 5']])
p('Đã kiểm tra tổng lượt theo năm, tháng, điểm và danh mục đều khớp fact_sales; tổng hoạt động từ dim_customers khớp số dòng fact. Điểm nằm trong 1–5, quantity bằng 1 theo giả định xây dựng dữ liệu; giá không thiếu nằm trong (0, 1.000] USD. Các kiểm tra này không thay thế toàn bộ kiểm thử nguồn thô và không chứng minh không có thiên lệch chọn mẫu.')
h('2. Xu hướng thời gian')
fig('01_theo_nam','Hình 1. Lượt đánh giá theo năm; các năm biên không đầy đủ.')
fig('02_theo_thang','Hình 2. Chuỗi thời gian số đánh giá theo tháng.')
complete=yearly[(yearly.year>o.first_date.year)&(yearly.year<o.last_date.year)]
peak=complete.loc[complete.reviews.idxmax()]
p(f'Trong các năm lịch nằm hoàn toàn trong khoảng quan sát, năm {int(peak.year)} có nhiều đánh giá nhất: {number(peak.reviews)} lượt. Năm {o.first_date.year} bắt đầu từ {o.first_date.date()}, năm {o.last_date.year} kết thúc ngày {o.last_date.date()}; tháng cuối cũng chưa đầy đủ. Không so trực tiếp tổng 2023 với năm đầy đủ để kết luận giảm nhu cầu.')
p('Các mốc này là thời gian viết đánh giá, không phải thời gian mua. Biến động có thể do hành vi đánh giá, độ phủ thu thập hoặc thay đổi danh mục; chưa có dữ liệu để quy kết cho doanh số, mùa vụ mua hay chiến dịch khuyến mãi.')
h('3. Phân phối điểm đánh giá')
fig('03_diem_danh_gia','Hình 3. Tỷ lệ đánh giá theo số sao.')
five=int(ratings.loc[ratings.rating==5,'reviews'].sum()); low=int(ratings.loc[ratings.rating<=2,'reviews'].sum())
p(f'Điểm trung bình {o.average_rating:.3f}/5; đánh giá 5 sao chiếm {100*five/o.reviews:.2f}%, điểm 1–2 sao chiếm {100*low/o.reviews:.2f}%. Đây là phân phối của người có đánh giá đã xác minh được giữ lại, không đại diện tự động cho toàn bộ người mua. Không dùng điểm trung bình đơn lẻ để kết luận chất lượng hoặc mức hài lòng toàn thị trường.')
h('4. Sách và nhãn danh mục được quan tâm')
fig('04_top_sach','Hình 4. Top 15 theo số lượt đánh giá, không phải số sách bán.')
table(['Tên sản phẩm','Lượt đánh giá','Điểm TB'],[[str(r.title)[:85],number(r.reviews),f'{r.average_rating:.2f}'] for r in topbooks.head(10).itertuples()])
p('Đơn vị xếp hạng là sản phẩm theo parent_asin, chưa hợp nhất tất cả ấn bản thành một tác phẩm. Một sản phẩm nhiều lượt đánh giá không đồng nghĩa số bản bán cao hơn theo đúng tỷ lệ. Điểm ở đây tính từ tập sạch, có thể khác average_rating trong metadata.')
fig('05_the_loai','Hình 5. Các nhãn danh mục nhiều đánh giá nhất.')
table(['Danh mục','Lượt đánh giá','Điểm TB','Thiếu giá (%)'],[[str(r.category),number(r.reviews),f'{r.average_rating:.2f}',f'{r.missing_price_pct:.2f}'] for r in categories.head(10).itertuples()])
p('Các nhãn lấy từ metadata Amazon, có thể trộn thể loại nội dung, bộ sưu tập, chiến dịch hoặc định dạng. Vì vậy chưa thể coi đây là hệ phân loại thể loại sách chuẩn. Điểm trung bình theo danh mục được tính có trọng số theo từng lượt đánh giá, không lấy trung bình đơn giản của điểm từng sách.')
h('5. Dữ liệu thiếu và giá sách')
fig('06_thieu_du_lieu','Hình 6. Tỷ lệ thiếu trên toàn bộ danh mục, kể cả sản phẩm không có đánh giá trong tập sạch.')
p(f'Thiếu giá hợp lệ ở {number(mr.missing_price)} sản phẩm, chiếm {100*mr.missing_price/catalog:.2f}% danh mục. Theo trọng số lượt đánh giá, có {number(o.missing_price_reviews)} lượt thiếu giá, chiếm {100*o.missing_price_reviews/o.reviews:.2f}%. Hai tỷ lệ có mẫu số khác nhau. Giá bị loại do ngoài ngưỡng đã trở thành NULL nên không phân biệt được nguyên nhân chỉ từ warehouse; cần bảng profile nguồn khi phân tích nguyên nhân.')
fig('07_phan_phoi_gia','Hình 7. Phân bố giá hợp lệ ở thời điểm thu thập, theo sản phẩm.')
pr=price.iloc[0]
p(f'Trong các sách có giá hợp lệ: trung vị {pr.median_price:.2f} USD, tứ phân vị thứ nhất {pr.p25:.2f} USD, tứ phân vị thứ ba {pr.p75:.2f} USD, phân vị 95% {pr.p95:.2f} USD. Đây là giá thu thập, không phải giá giao dịch lịch sử; không nhân giá với số đánh giá để gọi là doanh thu thực. Không điền giá thiếu bằng 0 cho phân tích chi tiêu.')
h('6. Hoạt động người dùng')
fig('08_nguoi_dung','Hình 8. Nhóm người dùng theo số lượt đánh giá trong tập sạch.')
u=users.iloc[0]
p(f'Có {number(u.one_review_users)} người chỉ có một lượt đánh giá, chiếm {100*u.one_review_users/o.users:.2f}%. Trung vị số đánh giá/người là {u.median_reviews:.0f}; cao nhất {number(u.max_reviews)}. Đây là mức độ hoạt động đánh giá quan sát được, không phải toàn bộ lịch sử mua. Nếu làm RFM/K-Means, cần log hóa biến lệch và kiểm tra nhóm ít hoạt động; chưa thể đặt tên nhóm khách hàng giá trị cao bằng chi tiêu thực.')
h('7. Kết luận và giới hạn')
p('EDA cung cấp mô tả dữ liệu sau làm sạch, xu hướng thời gian, phân phối điểm, mức quan tâm tới sản phẩm/danh mục, giá và hoạt động đánh giá. Các biểu đồ không chứng minh quan hệ nhân quả. Giá thiếu, nhãn danh mục không chuẩn, thời gian đánh giá thay thời gian mua và lọc verified_purchase đều ảnh hưởng diễn giải.')
p('Các bảng CSV được lưu trong tables, biểu đồ PNG/PDF trong figures. Script 08_eda.py có thể chạy lại từ thư mục gốc bằng .venv\\Scripts\\python src\\08_eda.py. Cần thống nhất với giảng viên phạm vi dùng đánh giá làm đại diện trước khi kết luận về kinh doanh. Bước tiếp theo là từ điển dữ liệu và tích hợp EDA với báo cáo hiệu năng; phân cụm là phần mở rộng.')

md=[]; body=[]
for kind,content in blocks:
    if kind=='heading':md.append('## '+content);body.append('<h2>'+html.escape(content)+'</h2>')
    elif kind=='paragraph':md.append(content);body.append('<p>'+html.escape(content)+'</p>')
    elif kind=='table':
        md.append('\n'.join(['| '+' | '.join(content[0])+' |','|'+'---|'*len(content[0])]+['| '+' | '.join(r)+' |' for r in content[1:]]))
        body.append('<table>'+''.join('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in row)+'</tr>' for row in content)+'</table>')
    else:
        name,caption=content;md.append(f'![{caption}](figures/{name}.png)')
        encoded=base64.b64encode((FIG/(name+'.png')).read_bytes()).decode()
        body.append(f'<figure><img src="data:image/png;base64,{encoded}"><figcaption>{html.escape(caption)}</figcaption></figure>')
(OUT/'EDA_sach.md').write_text('\n\n'.join(md),encoding='utf-8')
(OUT/'EDA_sach.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><title>EDA sách</title><style>body{font:16px/1.65 Arial;max-width:1100px;margin:35px auto;padding:0 20px;color:#172033}img{width:100%}figure{margin:28px 0}table{border-collapse:collapse;width:100%;font-size:14px}td{border:1px solid #cbd5e1;padding:8px}tr:first-child{background:#eef2f6;font-weight:bold}@media print{figure,table{break-inside:avoid}}</style>'+''.join(body)+'</html>',encoding='utf-8')
(OUT/'report_blocks.json').write_text(json.dumps(blocks,ensure_ascii=False),encoding='utf-8')
con.close()
print('EDA complete:',OUT,flush=True)
