from pathlib import Path
import json
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

HERE=Path(__file__).resolve().parent
DATA=HERE/'data'
st.set_page_config(page_title='Bookscope · Dữ liệu sách',page_icon='📚',layout='wide')
st.markdown('''<style>
.stApp {background:#f5f8fd;color:#142238}
h1,h2,h3 {font-family:Georgia,serif!important;letter-spacing:-.025em}
h1 {font-size:2.8rem!important}
[data-testid="stSidebar"] {background:#e9eff9;border-right:1px solid #d1dded}
[data-testid="stMetric"] {background:white;border-top:3px solid #244db3;padding:16px;border-radius:4px}
[data-testid="stMetricValue"] {font-size:1.85rem}
.block-container {padding-top:2rem;max-width:1450px}
</style>''',unsafe_allow_html=True)
ENGINES={'pandas_csv':'Pandas · CSV đầy đủ','pandas_columns':'Pandas · CSV chọn cột',
 'pandas_parquet':'Pandas · Parquet','duckdb':'DuckDB · Parquet',
 'postgres':'PostgreSQL · chưa index','postgres_index':'PostgreSQL · có index'}
SIZES={'1m':'1 triệu','5m':'5 triệu','10m':'10 triệu','full':'20,34 triệu'}
QUERIES={'Q1':'Theo tháng','Q2':'Top sách theo danh mục','Q3':'Lịch sử người dùng',
 'Q4':'Số người dùng theo năm','Q5':'Trung bình trượt 7 ngày','Q6':'RFM đại diện'}
PALETTE=['#65758b','#b0781a','#3478d4','#16806a','#8060b0','#bb513e']

@st.cache_data
def csv(name):return pd.read_csv(DATA/name)
@st.cache_data
def metadata(name):return json.loads((DATA/name).read_text(encoding='utf-8'))
@st.cache_data
def query_cube(first,last,category):
    with duckdb.connect() as con:
        con.execute('SET threads=2');con.execute("SET memory_limit='512MB'")
        sql="SELECT year,month,rating,sum(reviews)::BIGINT AS reviews FROM read_parquet(?) WHERE year BETWEEN ? AND ?"
        args=[str(DATA/'review_cube.parquet'),int(first),int(last)]
        if category!='Tất cả danh mục':sql+=' AND category=?';args.append(category)
        return con.execute(sql+' GROUP BY 1,2,3 ORDER BY 1,2,3',args).fetchdf()
@st.cache_data
def categories():
    with duckdb.connect() as con:
        return con.execute('SELECT DISTINCT category FROM read_parquet(?) ORDER BY category',[str(DATA/'review_cube.parquet')]).fetchdf().category.tolist()
@st.cache_data
def top_books(category):
    with duckdb.connect() as con:
        sql='SELECT title,category,reviews,average_rating FROM read_parquet(?)'
        args=[str(DATA/'top_books.parquet')]
        if category!='Tất cả danh mục':sql+=' WHERE category=?';args.append(category)
        return con.execute(sql+' ORDER BY reviews DESC,title LIMIT 15',args).fetchdf()

def plot(fig):
    fig.update_layout(template='plotly_white',font=dict(family='Arial',color='#142238'),
                      paper_bgcolor='rgba(0,0,0,0)',margin=dict(l=10,r=10,t=35,b=20),legend_title_text='')
    st.plotly_chart(fig,width='stretch')
def download(frame,name):
    st.download_button('Tải bảng CSV',frame.to_csv(index=False).encode('utf-8-sig'),name,'text/csv')
def title(kicker,heading,description):
    st.caption(kicker.upper());st.title(heading);st.write(description)

def extended_performance():
    labels={'postgres_4mb':'PostgreSQL · 4 MB','postgres_32mb':'PostgreSQL · 32 MB',
            'postgres_64mb':'PostgreSQL · 64 MB','materialized_4mb':'Materialized view · 4 MB'}
    bench=csv('extended_comparison_extended_verified.csv')
    validation=metadata('extended_validation.json')
    st.caption(f"Đợt pg_extended_1110_132250 · {validation['verified_runs']} lượt đo đã kiểm chứng. Baseline riêng: PostgreSQL 4 MB; không so thời gian trực tiếp với đợt 720 lượt.")
    a,b=st.columns(2)
    size=a.selectbox('Quy mô dữ liệu',list(SIZES),index=3,format_func=SIZES.get,key='extended_size')
    q=b.selectbox('Truy vấn',list(QUERIES),format_func=lambda x:x+' · '+QUERIES[x],key='extended_query')
    selected=bench[(bench['size']==size)&(bench['query']==q)].copy()
    baseline=float(selected.loc[selected.config=='postgres_4mb','median_s'].iloc[0])
    fastest=selected.loc[selected.median_s.idxmin()]
    cols=st.columns(3)
    cols[0].metric('Baseline PostgreSQL 4 MB',f'{baseline:.3f} giây')
    cols[1].metric('Cấu hình nhanh nhất trong đợt',f'{fastest.median_s:.3f} giây',labels[fastest.config],delta_color='off')
    cols[2].metric('Tăng tốc so với baseline mới',f'{fastest.speedup_vs_4mb:.2f}×')
    selected['Cấu hình']=selected.config.map(labels)
    selected['upper']=selected.q3_s-selected.median_s;selected['lower']=selected.median_s-selected.q1_s
    fig=px.bar(selected,x='Cấu hình',y='median_s',color='Cấu hình',error_y='upper',error_y_minus='lower',
               color_discrete_sequence=PALETTE,labels={'median_s':'Thời gian (giây)'})
    fig.update_layout(showlegend=False)
    if st.checkbox('Dùng thang log để xem chênh lệch lớn',key='extended_log'):fig.update_yaxes(type='log')
    plot(fig)
    st.caption('Trung vị và khoảng tứ phân vị của 5 lượt. work_mem không phải trần RAM server; nhiều thao tác/worker có thể dùng bộ nhớ cùng lúc.')
    if q not in ['Q1','Q5']:st.info('Materialized view chỉ được đo cho Q1 và Q5; không có kết quả view cho truy vấn đang chọn.')
    st.dataframe(selected[['Cấu hình','runs','median_s','min_s','max_s','speedup_vs_4mb']].rename(columns={
        'runs':'Số lần','median_s':'Trung vị (s)','min_s':'Nhỏ nhất (s)','max_s':'Lớn nhất (s)','speedup_vs_4mb':'Tăng tốc / 4 MB'}),hide_index=True,width='stretch')
    st.subheader('Xu hướng theo quy mô · cùng đợt bổ sung')
    trend=bench[bench['query']==q].copy()
    trend['Triệu dòng']=trend['size'].map({'1m':1,'5m':5,'10m':10,'full':20.342188})
    trend['Cấu hình']=trend.config.map(labels)
    plot(px.line(trend.sort_values('Triệu dòng'),x='Triệu dòng',y='median_s',color='Cấu hình',markers=True,
                 labels={'median_s':'Trung vị (giây)'},color_discrete_sequence=PALETTE))
    st.subheader('Chi phí tạo và làm mới materialized view')
    costs=csv('extended_materialized_view_costs.csv')
    part=costs[costs['size']==size].copy();part['KiB']=part.bytes/1024
    st.dataframe(part[['view','rows','create_seconds','analyze_seconds','refresh_median_s','KiB']].rename(columns={
        'view':'View','rows':'Số dòng','create_seconds':'Tạo (s)','analyze_seconds':'ANALYZE (s)',
        'refresh_median_s':'Refresh trung vị (s)'}),hide_index=True,width='stretch')
    st.caption('Chi phí này tách khỏi thời gian truy vấn phía trên. REFRESH tính lại toàn bộ trên nguồn không đổi; chưa đo ghi đồng thời, refresh gia tăng hay concurrent refresh. Khi nguồn thay đổi, view có thể cũ cho tới khi refresh.')
    st.write('Materialized view tăng tốc nhờ lưu kết quả trước, không phải tính lại toàn bộ fact nhanh hơn cùng tỷ lệ. Tăng work_mem chỉ cải thiện tùy truy vấn; không phải mọi mức RAM cao hơn đều tốt hơn.')
    download(bench,'postgres_bo_sung_400_luot.csv')
    st.download_button('Tải chi phí materialized view',costs.to_csv(index=False).encode('utf-8-sig'),'chi_phi_materialized_view.csv','text/csv')

required=['review_cube.parquet','top_books.parquet','01_tong_quan.csv','07_thieu_thong_tin_danh_muc.csv',
          'cluster_profiles.csv','model_selection.csv','run_metadata.json','bang_ket_qua_144_cau_hinh.csv','data_validation.json',
          'extended_comparison_extended_verified.csv','extended_materialized_view_costs.csv','extended_validation.json']
missing=[f for f in required if not (DATA/f).exists()]
if missing:
    st.error('Thiếu dữ liệu dashboard. Chạy dashboard/prepare_data.py từ project gốc trước.')
    st.write(missing);st.stop()
with st.sidebar:
    st.markdown('## Bookscope')
    st.caption('Hồ sơ dữ liệu sách · Amazon Reviews 2023')
    page=st.radio('Khám phá', ['Hiệu năng','Tổng quan','Khám phá sách','RFM & phân cụm'])
    st.divider()
    st.caption('20.342.188 đánh giá đã xác minh\n\n12/02/1997 — 14/09/2023')
    st.caption('Dữ liệu đánh giá không thay thế giao dịch bán hàng. Giá trị tiền là đại diện theo giá thu thập.')

if page=='Hiệu năng':
    title('Thực nghiệm Colab','Dữ liệu lớn, xử lý hiệu quả hơn.','Hai đợt Colab độc lập: 720 lượt cơ bản và 400 lượt bổ sung. Mỗi đợt có baseline riêng, mỗi tổ hợp đo 5 lần.')
    experiment=st.radio('Đợt thực nghiệm',['Cơ bản · 720 lượt','PostgreSQL bổ sung · 400 lượt'],horizontal=True,key='experiment')
    if experiment=='PostgreSQL bổ sung · 400 lượt':
        extended_performance()
    else:
        bench=csv('bang_ket_qua_144_cau_hinh.csv')
        c1,c2=st.columns(2)
        size=c1.selectbox('Quy mô dữ liệu',list(SIZES),index=3,format_func=SIZES.get)
        q=c2.selectbox('Truy vấn',list(QUERIES),format_func=lambda x:x+' · '+QUERIES[x])
        selected=bench[(bench['size']==size)&(bench['query']==q)].copy()
        file_rows=selected[~selected.engine.str.startswith('postgres')]
        fastest=file_rows.loc[file_rows.median_s.idxmin()]
        base=float(selected.loc[selected.engine=='pandas_csv','median_s'].iloc[0])
        cols=st.columns(3)
        cols[0].metric('Pandas CSV đầy đủ',f'{base:.2f} giây')
        cols[1].metric('Xử lý tệp nhanh nhất',f'{fastest.median_s:.2f} giây',ENGINES[fastest.engine],delta_color='off')
        cols[2].metric('Tăng tốc so với CSV đầy đủ',f'{base/fastest.median_s:.2f}×')
        selected['Cấu hình']=selected.engine.map(ENGINES)
        selected['upper']=selected.q3_s-selected.median_s;selected['lower']=selected.median_s-selected.q1_s
        fig=px.bar(selected,x='Cấu hình',y='median_s',color='Cấu hình',color_discrete_sequence=PALETTE,
                   error_y='upper',error_y_minus='lower',labels={'median_s':'Thời gian (giây)'})
        fig.update_layout(showlegend=False);plot(fig)
        st.caption('Thanh sai số: khoảng tứ phân vị của 5 lượt, không phải khoảng tin cậy. Tỷ số tăng tốc phía trên chỉ so nhóm xử lý tệp với Pandas CSV.')
        chosen=st.multiselect('Cấu hình trên biểu đồ quy mô',list(ENGINES),default=['pandas_csv','pandas_parquet','duckdb'],format_func=ENGINES.get)
        trend=bench[(bench['query']==q)&bench.engine.isin(chosen)].copy()
        trend['Triệu dòng']=trend['size'].map({'1m':1,'5m':5,'10m':10,'full':20.342188});trend['Cấu hình']=trend.engine.map(ENGINES)
        if chosen:plot(px.line(trend.sort_values('Triệu dòng'),x='Triệu dòng',y='median_s',color='Cấu hình',markers=True,labels={'median_s':'Trung vị (giây)'},color_discrete_sequence=PALETTE))
        else:st.info('Chọn ít nhất một cấu hình để xem xu hướng.')
        st.dataframe(selected[['Cấu hình','median_s','min_s','max_s','runs','speedup_vs_baseline']].rename(columns={'median_s':'Trung vị (s)','min_s':'Nhỏ nhất (s)','max_s':'Lớn nhất (s)','runs':'Số lần','speedup_vs_baseline':'Tăng tốc / mốc cùng nhóm'}),width='stretch',hide_index=True)
        st.caption('Mốc cùng nhóm: Pandas CSV cho các công cụ xử lý tệp; PostgreSQL chưa index cho thử nghiệm index. Thời gian gồm đọc/truy vấn và đưa kết quả về client. Không tính import, ghi kết quả hay đối chiếu. Cache không được xóa.')
        download(bench,'hieu_nang_4_quy_mo.csv')
elif page=='Tổng quan':
    title('Bộ sưu tập','Một bộ dữ liệu, nhiều góc nhìn.','Thông tin sách và đánh giá đã xác minh sau làm sạch. Các số liệu dưới đây mô tả tập quan sát, không phải toàn bộ thị trường sách.')
    o=csv('01_tong_quan.csv').iloc[0]
    cols=st.columns(4)
    for col,label,key in zip(cols,['Lượt đánh giá','Người đánh giá','Sản phẩm có đánh giá','Điểm trung bình'],['reviews','users','reviewed_books','average_rating']):
        col.metric(label,f'{o[key]:,.2f}' if key=='average_rating' else f'{int(o[key]):,}')
    cube=query_cube(1997,2023,'Tất cả danh mục')
    yearly=cube.groupby('year',as_index=False).reviews.sum()
    plot(px.bar(yearly,x='year',y='reviews',labels={'year':'Năm đánh giá','reviews':'Lượt đánh giá'},color_discrete_sequence=['#244db3']))
    st.caption('Năm 1997 và 2023 không đầy đủ. Dữ liệu cuối ngày 14/09/2023; thời gian là ngày viết đánh giá, không phải ngày mua.')
    left,right=st.columns(2)
    with left:
        st.subheader('Chất lượng dữ liệu')
        quality=csv('07_thieu_thong_tin_danh_muc.csv').iloc[0]
        st.metric('Lượt đánh giá thiếu giá',f'{100*o.missing_price_reviews/o.reviews:.2f}%')
        st.write(f'Danh mục có {int(quality.books):,} sản phẩm, gồm cả sản phẩm không có đánh giá trong tập sạch.')
        validation=metadata('data_validation.json')
        st.success(f"{validation['passed']}/{validation['total']} kiểm tra dữ liệu đạt trong lần kiểm chứng đã lưu.")
        st.caption('Đây là kết quả kiểm tra đã lưu, không phải kiểm tra trực tiếp mỗi lần mở dashboard.')
    with right:
        st.subheader('Phạm vi sử dụng')
        st.write('Giá là USD tại thời điểm thu thập. Quantity giả định bằng 1. Tồn kho và giá vốn mô phỏng không được dùng để kết luận về thực tế.')
        st.write('Chưa có dữ liệu đơn hàng, doanh thu, lợi nhuận hoặc tồn kho thực. Dashboard tập trung vào đánh giá, hiệu năng và phân cụm hành vi quan sát được.')
elif page=='Khám phá sách':
    title('Phân tích khám phá','Đọc những dấu vết trong dữ liệu.','Lọc thời gian và nhãn danh mục để khám phá phân phối đánh giá. Nhãn nguồn có thể là thể loại, bộ sưu tập hoặc chiến dịch.')
    left,right=st.columns([2,1])
    category=left.selectbox('Danh mục',['Tất cả danh mục']+categories())
    years=right.slider('Khoảng năm',1997,2023,(2010,2023))
    frame=query_cube(years[0],years[1],category)
    if frame.empty:st.info('Không có đánh giá trong phạm vi đã chọn. Hãy mở rộng khoảng năm hoặc đổi danh mục.')
    else:
        total=int(frame.reviews.sum());mean=float((frame.rating*frame.reviews).sum()/total)
        cols=st.columns(2);cols[0].metric('Lượt đánh giá trong bộ lọc',f'{total:,}');cols[1].metric('Điểm trung bình có trọng số',f'{mean:.2f}/5')
        monthly=frame.groupby(['year','month'],as_index=False).reviews.sum()
        # Reindex months so absent months appear as zero rather than a misleading line bridge.
        monthly['Tháng']=pd.to_datetime(dict(year=monthly.year,month=monthly.month,day=1))
        idx=pd.date_range(f'{years[0]}-01-01',min(pd.Timestamp(f'{years[1]}-12-01'),pd.Timestamp('2023-09-01')),freq='MS')
        monthly=monthly.set_index('Tháng').reindex(idx,fill_value=0).rename_axis('Tháng').reset_index()
        plot(px.line(monthly,x='Tháng',y='reviews',labels={'reviews':'Lượt đánh giá'},color_discrete_sequence=['#244db3']))
        ratings=frame.groupby('rating',as_index=False).reviews.sum().set_index('rating').reindex([1,2,3,4,5],fill_value=0).reset_index()
        plot(px.bar(ratings,x='rating',y='reviews',labels={'rating':'Điểm sao','reviews':'Lượt đánh giá'},color_discrete_sequence=['#16806a']))
        st.caption('Tháng 9/2023 chưa đầy đủ. Cả hai biểu đồ trên sử dụng khoảng năm và danh mục đã chọn.')
        download(frame,'danh_gia_theo_bo_loc.csv')
    st.subheader('Sản phẩm được đánh giá nhiều')
    st.caption('Bảng bên dưới lọc theo danh mục nhưng dùng toàn bộ 1997–2023, không áp dụng khoảng năm phía trên. Đơn vị là sản phẩm, chưa gộp mọi ấn bản thành tác phẩm.')
    top=top_books(category)
    st.dataframe(top.rename(columns={'title':'Tên sản phẩm','category':'Danh mục','reviews':'Lượt đánh giá','average_rating':'Điểm trung bình'}),hide_index=True,width='stretch')
elif page=='RFM & phân cụm':
    title('Phân nhóm người dùng','Hành vi khác nhau, hồ sơ khác nhau.','K-Means mô tả hành vi đánh giá theo RFM đại diện. Nhãn cụm không phải thứ hạng khách hàng và không chứng minh giá trị chi tiêu thực.')
    meta=metadata('run_metadata.json');profiles=csv('cluster_profiles.csv')
    cols=st.columns(3)
    cols[0].metric('Số cụm được chọn',meta['selected_k'])
    cols[1].metric('Người đủ giá được gán cụm',f"{meta['eligible_users']:,}")
    cols[2].metric('Thiếu giá, giữ riêng',f"{meta['excluded_users']:,}")
    st.info(f"Mốc R: {meta['reference_date']}. R = số ngày từ đánh giá cuối; F = số lượt đánh giá; M = tổng giá trị đại diện. Chỉ dùng người có giá đầy đủ cho tất cả lượt; không điền giá thiếu bằng 0.")
    profiles['Nhóm']=profiles.cluster.map(lambda c:'Thiếu giá · chưa phân cụm' if c==-1 else f'Cụm {c}')
    plot(px.bar(profiles,x='Nhóm',y='users',color='Nhóm',color_discrete_sequence=['#94a3b8','#244db3','#16806a'],labels={'users':'Người dùng'}))
    selected=st.selectbox('Xem hồ sơ cụm',profiles[profiles.cluster>=0].cluster.tolist(),format_func=lambda c:f'Cụm {c}')
    row=profiles[profiles.cluster==selected].iloc[0]
    cols=st.columns(3)
    cols[0].metric('R trung vị',f'{row.median_recency:,.0f} ngày')
    cols[1].metric('F trung vị',f'{row.median_frequency:,.0f} lượt')
    cols[2].metric('M đại diện trung vị',f'{row.median_monetary:,.2f} USD')
    st.caption('Các hồ sơ được tính sau gán cụm trên toàn bộ nhóm đủ giá, không chỉ mẫu huấn luyện. Nhóm thiếu giá không được so sánh Monetary như nhóm đủ giá.')
    st.subheader('Lựa chọn mô hình')
    scores=csv('model_selection.csv')
    plot(px.line(scores,x='k',y='mean_silhouette',error_y='std_silhouette',markers=True,labels={'k':'Số cụm','mean_silhouette':'Silhouette trung bình'},color_discrete_sequence=['#244db3']))
    st.caption('Mẫu phân tầng 150.000 người, log1p rồi StandardScaler; k=2–5, ba seed, n_init=10. Silhouette trên cùng 3.000 người; ARI đo ổn định giữa seed trên cùng mẫu, chưa kiểm tra qua các mẫu độc lập.')
    st.dataframe(scores,hide_index=True,width='stretch')
    download(profiles,'ho_so_cum.csv')

st.divider()
st.caption('Bookscope · Amazon Reviews 2023 / Books · Dữ liệu tổng hợp, không hiển thị mã người dùng · Kết quả Colab và phân tích đã lưu')
