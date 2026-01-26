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
# 2. 데이터 처리 (안정성 강화)
# ==========================================
def safe_date_parse(val, target_year=2026):
    try:
        val_str = str(val)
        # 이카운트 특유의 "01/19-12" 패턴 처리
        match = re.search(r'(\d{1,2})/(\d{1,2})', val_str)
        if match:
            m, d = match.groups()
            return pd.to_datetime(f"{target_year}-{m}-{d}")
        return pd.to_datetime(val_str)
    except:
        return None

def load_data(files):
    all_dfs = []
    for file in files:
        try:
            sheets = pd.read_excel(file, header=0, sheet_name=None)
            for name, raw in sheets.items():
                if len(raw) < 2: continue
                
                # [중요] 컬럼 인덱스 매핑 (A, B, D, E, F, H)
                # 데이터가 있는 행부터 잘라내기
                temp = raw.iloc[1:].copy()
                temp = temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                if '그로스' in str(name): temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
        except:
            continue
            
    if not all_dfs: return None
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    # 날짜 및 숫자 변환
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자'])
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    for c in ['수량', '판매단가', '원가단가']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
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

with st.expander("📂 파일 업로드 열기", expanded=True):
    col1, col2 = st.columns(2)
    up_files = col1.file_uploader("판매 엑셀 파일 (다중 업로드 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    cost_file = col2.file_uploader("고정비 엑셀 (선택)", type=['xlsx', 'xls'])

if up_files:
    df = load_data(up_files)
    
    if df is not None and not df.empty:
        # KPI 계산
        sales = df['총판매금액'].sum()
        gross = df['매출총이익'].sum()
        
        fixed_cost = 0
        if cost_file:
            try:
                cdf = pd.read_excel(cost_file)
                fixed_cost = cdf[['광고비', '택배비', '운영비']].sum().sum()
            except: pass

        net = gross - fixed_cost
        margin = (net / sales * 100) if sales > 0 else 0

        # KPI 표시
        st.markdown("---")
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
            fig_pie = px.pie(ch_df, values='총판매금액', names='채널', hole=0.4, title="매출 비중")
            fig_pie.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_c2:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
            fig.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red')), secondary_y=True)
            fig.update_layout(title="이익금 vs 이익률 분석")
            st.plotly_chart(fig, use_container_width=True)

        # 2. 상품 랭킹 (오류 수정 구간)
        st.divider()
        st.subheader("2️⃣ 상품별 판매 랭킹 (Top 10)")

        # 상품명 데이터 확인
        pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
        
        # 데이터가 있는지 확인해서 메시지 출력
        if pr_df.empty:
            st.error("❌ 상품 데이터를 불러오지 못했습니다. 엑셀의 '품목명' 열을 확인해주세요.")
        else:
            st.caption(f"총 {len(pr_df):,}개의 상품이 집계되었습니다.")
            
            # 정렬 옵션
            sort_key = st.radio("정렬 기준 선택", ["매출액 높은 순", "이익금 높은 순"], horizontal=True)
            
            if "매출" in sort_key:
                top10 = pr_df.sort_values(by='총판매금액', ascending=False).head(10)
            else:
                top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)

            # 인덱스 1부터 시작 (순위 느낌)
            top10.index = range(1, len(top10) + 1)

            # [핵심 수정] 화려한 스타일링 제거 -> 기본 표로 표시 (안전빵)
            # 숫자에 콤마(,)만 찍어서 깔끔하게 보여줍니다.
            st.dataframe(
                top10.style.format({
                    "수량": "{:,.0f}",
                    "총판매금액": "{:,.0f}",
                    "매출총이익": "{:,.0f}"
                }),
                use_container_width=True
            )

    else:
        st.warning("데이터를 읽을 수 없습니다. 양식을 확인해주세요.")

else:
    st.info("👆 파일을 업로드하면 분석 결과가 나타납니다.")
