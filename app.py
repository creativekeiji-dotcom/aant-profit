import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import re
import datetime

# ==========================================
# 1. 기본 설정
# ==========================================
st.set_page_config(page_title="AANT 경영 리포트", layout="wide")

# [기본 수수료율] (파일 안 올렸을 때 비상용)
DEFAULT_FEE_RATES = {
    "쿠팡": 0.1188, "쿠팡그로스": 0.1188, "네이버": 0.06, "옥션": 0.143,
    "지마켓": 0.143, "11번가": 0.143, "오늘의집": 0.22, "카카오톡": 0.055,
    "알리": 0.11, "사업자거래": 0.0
}

# ==========================================
# 2. 데이터 처리 함수
# ==========================================
def safe_date_parse(val, target_year=2026):
    try:
        val_str = str(val)
        match = re.search(r'(\d{1,2})/(\d{1,2})', val_str)
        if match:
            m, d = match.groups()
            return pd.to_datetime(f"{target_year}-{m}-{d}")
        return pd.to_datetime(val_str)
    except:
        return None

def load_data(files, fee_dict):
    all_dfs = []
    for file in files:
        try:
            sheets = pd.read_excel(file, header=0, sheet_name=None)
            for name, raw in sheets.items():
                if len(raw) < 2: continue
                
                temp = raw.iloc[1:].copy()
                if temp.shape[1] < 8: continue 

                temp = temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                if '그로스' in str(name): temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
        except: continue
            
    if not all_dfs: return None
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자'])
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    for c in ['수량', '판매단가', '원가단가']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    df['채널'] = df['채널'].astype(str).str.strip()
    
    # [핵심] 수수료율 매핑 (업로드된 dict 우선 사용)
    # 없으면 0으로 처리하지 않고, 기본값 0.1(10%) 혹은 0으로 설정
    df['수수료율'] = df['채널'].map(fee_dict).fillna(0)
    
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 3. 메인 화면
# ==========================================
st.title("📊 AANT CEO 경영 대시보드")

# 파일 업로드 구역 확장 (3분할)
with st.expander("📂 데이터 파일 관리 (여기를 클릭하세요)", expanded=True):
    c1, c2, c3 = st.columns(3)
    
    # 1. 판매 파일
    up_files = c1.file_uploader("1️⃣ 판매 엑셀 (필수)", type=['xlsx', 'xls'], accept_multiple_files=True)
    
    # 2. 고정비 파일
    cost_file = c2.file_uploader("2️⃣ 고정비 엑셀 (선택)", type=['xlsx', 'xls'])
    
    # 3. 수수료 파일 (NEW)
    fee_file = c3.file_uploader("3️⃣ 수수료율 엑셀 (선택)", type=['xlsx', 'xls'])
    c3.caption("※ 미업로드 시 기본값(쿠팡 11.8% 등) 적용")

# 수수료율 로딩 로직
current_fee_rates = DEFAULT_FEE_RATES.copy()
if fee_file:
    try:
        fdf = pd.read_excel(fee_file)
        # 컬럼명이 '쇼핑몰명', '수수료율' 이라고 가정하거나, 첫번째 두번째 열을 사용
        # 안전하게 첫번째 열=키, 두번째 열=값으로 변환
        new_rates = dict(zip(fdf.iloc[:, 0], fdf.iloc[:, 1]))
        current_fee_rates.update(new_rates) # 기존 값에 덮어쓰기
        st.toast("✅ 새로운 수수료율이 적용되었습니다!")
    except:
        st.error("수수료 엑셀 양식을 확인해주세요 (A열:쇼핑몰명, B열:수수료율)")

# 메인 분석 로직
if up_files:
    df = load_data(up_files, current_fee_rates)
    
    if df is not None and not df.empty:
        # KPI
        sales = df['총판매금액'].sum()
        gross = df['매출총이익'].sum()
        
        fixed_cost = 0
        if cost_file:
            try:
                cdf = pd.read_excel(cost_file)
                fixed_cost = cdf.select_dtypes(include='number').sum().sum()
            except: pass

        net = gross - fixed_cost
        margin = (net / sales * 100) if sales > 0 else 0

        st.markdown("---")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 총 매출", f"{int(sales):,}원")
        k2.metric("📦 매출이익", f"{int(gross):,}원")
        k3.metric("💸 고정비", f"-{int(fixed_cost):,}원")
        k4.metric("🏆 순이익", f"{int(net):,}원", delta=f"{margin:.1f}%")
        st.markdown("---")

        # 탭 구성
        tab1, tab2, tab3 = st.tabs(["📊 채널/상품 분석", "📋 현재 수수료율 확인", "📥 보고서 다운로드"])
        
        with tab1:
            # 채널 분석
            st.subheader("채널별 성과")
            ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
            ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
            ch_df = ch_df.sort_values(by='총판매금액', ascending=False)

            cc1, cc2 = st.columns([1, 2])
            with cc1:
                st.plotly_chart(px.pie(ch_df, values='총판매금액', names='채널', hole=0.4, title="매출 비중"), use_container_width=True)
            with cc2:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
                fig.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red')), secondary_y=True)
                st.plotly_chart(fig, use_container_width=True)
            
            # 상품 분석
            st.divider()
            st.subheader("상품별 랭킹 TOP 10")
            pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
            if not pr_df.empty:
                top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)
                top10.index = range(1, len(top10)+1)
                st.dataframe(top10.style.format("{:,.0f}"), use_container_width=True)

        with tab2:
            st.subheader("📋 현재 적용된 수수료율")
            st.info("새로운 쇼핑몰이 추가되면 '수수료 엑셀'을 업로드하세요.")
            
            # 현재 적용된 수수료율을 표로 보여줌 (사용자 검증용)
            fee_df_display = pd.DataFrame(list(current_fee_rates.items()), columns=['채널명', '수수료율'])
            # 데이터에 있는 채널만 필터링해서 보여주기
            active_channels = df['채널'].unique()
            fee_df_display = fee_df_display[fee_df_display['채널명'].isin(active_channels)].reset_index(drop=True)
            fee_df_display['수수료율(%)'] = (fee_df_display['수수료율'] * 100).round(2).astype(str) + '%'
            
            st.dataframe(fee_df_display)

        with tab3:
            st.subheader("💾 최종 보고서 저장")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                pd.DataFrame({'항목':['매출','이익','고정비','순이익'], '금액':[sales,gross,fixed_cost,net]}).to_excel(writer, sheet_name='요약', index=False)
                ch_df.to_excel(writer, sheet_name='채널실적', index=False)
                df.to_excel(writer, sheet_name='상세내역', index=False)
            
            today_str = datetime.date.today().strftime("%Y%m%d")
            st.download_button("📥 CEO 보고서 다운로드", buffer.getvalue(), f"AANT_Report_{today_str}.xlsx")

    else:
        st.warning("데이터 형식을 확인해주세요.")
else:
    st.info("파일을 업로드해주세요.")
