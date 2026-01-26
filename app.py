import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import re
import datetime

# ==========================================
# 1. 설정
# ==========================================
st.set_page_config(page_title="AANT 경영 리포트", layout="wide")

FEE_RATES = {
    "쿠팡": 0.1188, "쿠팡그로스": 0.1188, "네이버": 0.06, "옥션": 0.143,
    "지마켓": 0.143, "11번가": 0.143, "오늘의집": 0.22, "카카오톡": 0.055,
    "알리": 0.11, "사업자거래": 0.0
}

# ==========================================
# 2. 강력한 데이터 처리 함수 (수정됨)
# ==========================================
def safe_date_parse(val, target_year=2026):
    """어떤 날짜 형식이 들어와도 찰떡같이 2026년 날짜로 변환"""
    try:
        # 1. 이미 날짜 형식이면 바로 반환
        if isinstance(val, (pd.Timestamp, datetime.date, datetime.datetime)):
            return pd.to_datetime(val)
        
        val_str = str(val)
        
        # 2. "01/19-12" 같은 이카운트 특유의 패턴 찾기
        match = re.search(r'(\d{1,2})/(\d{1,2})', val_str)
        if match:
            m, d = match.groups()
            return pd.to_datetime(f"{target_year}-{m}-{d}")
            
        # 3. "2026-01-19" 같은 표준 패턴 시도
        return pd.to_datetime(val_str)
    except:
        return None

def load_data(files):
    all_dfs = []
    
    for file in files:
        try:
            # 모든 시트 읽기
            sheets = pd.read_excel(file, header=0, sheet_name=None)
            for name, raw in sheets.items():
                if len(raw) < 2: continue # 데이터 너무 적으면 패스
                
                # [안전 장치] 컬럼이 충분한지 확인
                if raw.shape[1] < 8: 
                    continue 

                # 이카운트 양식 (2단 헤더 고려, 2번째 줄부터 데이터로 간주)
                # 만약 헤더가 1줄 뿐이라면 데이터가 1줄 빠질 수 있으나, 안전을 위해 유지
                temp = raw.iloc[1:].copy()
                
                # 필요한 열만 쏙 (A, B, D, E, F, H)
                temp = temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                # 채널명 보정
                if '그로스' in str(name): temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
        except Exception as e:
            st.error(f"⚠️ '{file.name}' 파일을 읽는 중 문제가 생겼습니다: {e}")
            continue
            
    if not all_dfs: return None
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    # 날짜 변환 (강화된 함수 사용)
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자']) # 날짜 없는 행(합계 등) 제거
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    # 숫자 변환
    for c in ['수량', '판매단가', '원가단가']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
    # 이익 계산
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    df['채널'] = df['채널'].astype(str).str.strip()
    df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 3. 메인 화면
# ==========================================
st.title("📊 AANT CEO 경영 대시보드")

with st.expander("📂 파일 업로드 열기/접기", expanded=True):
    col1, col2 = st.columns(2)
    up_files = col1.file_uploader("판매 엑셀 파일 (여러 개 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    cost_file = col2.file_uploader("고정비 엑셀 (선택)", type=['xlsx', 'xls'])

if up_files:
    df = load_data(up_files)
    
    if df is not None and not df.empty:
        # KPI 계산
        sales = df['총판매금액'].sum()
        gross = df['매출총이익'].sum()
        
        # 고정비 계산
        fixed_cost = 0
        if cost_file:
            try:
                cdf = pd.read_excel(cost_file)
                fixed_cost = cdf[['광고비', '택배비', '운영비']].sum().sum()
            except:
                st.warning("고정비 파일 형식을 확인해주세요.")

        net = gross - fixed_cost
        margin = (net / sales * 100) if sales > 0 else 0

        st.markdown("---")
        # KPI 카드
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 총 매출", f"{int(sales):,}원")
        c2.metric("📦 매출이익", f"{int(gross):,}원")
        c3.metric("💸 고정비", f"-{int(fixed_cost):,}원")
        c4.metric("🏆 순이익", f"{int(net):,}원", delta=f"{margin:.1f}%")
        st.markdown("---")

        # 1. 채널 분석
        st.subheader("1️⃣ 채널별 성과")
        ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
        ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
        ch_df = ch_df.sort_values(by='총판매금액', ascending=False)

        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            st.caption("매출 점유율")
            fig_pie = px.pie(ch_df, values='총판매금액', names='채널', hole=0.4)
            fig_pie.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_c2:
            st.caption("수익성 비교 (막대: 이익금 / 선: 이익률)")
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
            fig.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", mode='lines+markers', line=dict(color='red', width=3)), secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

        # 2. 상품 랭킹
        st.divider()
        st.subheader("2️⃣ 상품별 판매 랭킹 (Top 10)")
        
        pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
        pr_df['마진율'] = (pr_df['매출총이익'] / pr_df['총판매금액'] * 100).fillna(0)
        
        sort_key = st.radio("정렬 기준", ["매출액 높은 순", "이익금 높은 순"], horizontal=True)
        if "매출" in sort_key:
            top10 = pr_df.sort_values(by='총판매금액', ascending=False).head(10)
        else:
            top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)
            
        # 스타일링된 데이터프레임 (배경색 그라데이션)
        st.dataframe(
            top10.style.format({
                "수량": "{:,.0f}", "총판매금액": "{:,.0f}", "매출총이익": "{:,.0f}", "마진율": "{:.1f}%"
            }).background_gradient(subset=['매출총이익'], cmap='Greens'),
            use_container_width=True
        )

        # 3. 엑셀 다운로드
        st.divider()
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            ch_df.to_excel(writer, sheet_name='채널별분석')
            pr_df.to_excel(writer, sheet_name='상품별전체')
            df.to_excel(writer, sheet_name='상세내역', index=False)
            
        st.download_button("📥 통합 보고서 엑셀 다운로드", buffer.getvalue(), "AANT_CEO_Report.xlsx")

    else:
        st.warning("데이터를 읽을 수 없습니다. 엑셀 파일 형식을 확인해주세요.")

else:
    st.info("👆 위에서 엑셀 파일을 업로드해주세요.")
