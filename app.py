import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import datetime

# ==========================================
# 1. 설정: 수수료율
# ==========================================
FEE_RATES = {
    "쿠팡": 0.1188,
    "쿠팡그로스": 0.1188,
    "네이버": 0.06,
    "옥션": 0.143,
    "지마켓": 0.143,
    "11번가": 0.143,
    "오늘의집": 0.22,
    "카카오톡": 0.055,
    "알리": 0.11,
    "사업자거래": 0.0
}

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 통합 경영 분석기")

# ==========================================
# 2. 파일 업로드 구역 (다중 파일 지원)
# ==========================================
col_up1, col_up2 = st.columns(2)

with col_up1:
    st.info("1️⃣ 판매 데이터 (여러 개 동시 업로드 가능)")
    # [핵심 변경] accept_multiple_files=True : 파일을 여러 개 받을 수 있게 설정
    uploaded_files = st.file_uploader("주간 보고서 파일들을 모두 드래그해서 넣으세요", 
                                      type=['xlsx', 'xls'], 
                                      accept_multiple_files=True, # 여러 개 허용
                                      key="sales")

with col_up2:
    st.info("2️⃣ 월별 고정비 데이터 (선택사항)")
    cost_file = st.file_uploader("고정비 엑셀 업로드", type=['xlsx', 'xls'], key="cost")
    with st.expander("❓ 고정비 파일 양식"):
         st.markdown("- 컬럼명: **월, 광고비, 택배비, 운영비**\n- 월 형식: 2026-01")

# ==========================================
# 3. 데이터 통합 로직
# ==========================================
if uploaded_files: # 파일이 하나라도 있으면 실행
    try:
        all_data_frames = []
        
        # [핵심] 업로드된 파일들을 하나씩 순서대로 처리
        for file in uploaded_files:
            try:
                # 엑셀의 모든 시트(탭) 읽기
                all_sheets = pd.read_excel(file, header=0, sheet_name=None)
                
                for sheet_name, raw_df in all_sheets.items():
                    if len(raw_df) < 2: continue
                    
                    # 이카운트 2단 헤더 처리
                    df_temp = raw_df.iloc[1:].copy()
                    df_temp = df_temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                    df_temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                    
                    # 탭 이름에 '그로스' 있으면 채널명 변경
                    if '그로스' in str(sheet_name):
                        df_temp['채널'] = '쿠팡그로스'
                    
                    # 어느 파일, 어느 시트에서 왔는지 기록 (나중에 검증용)
                    df_temp['출처파일'] = file.name
                    df_temp['원본시트'] = sheet_name
                    
                    all_data_frames.append(df_temp)
            except Exception as e:
                st.warning(f"파일 '{file.name}'을 읽는 중 문제가 발생하여 건너뜁니다. ({e})")
                continue

        if not all_data_frames:
            st.error("읽을 수 있는 데이터가 없습니다.")
            st.stop()
            
        # 모든 파일, 모든 시트 데이터를 하나로 합체
        df = pd.concat(all_data_frames, ignore_index=True)

        # -------------------------------------------------------
        # [데이터 정제 및 날짜 변환]
        # -------------------------------------------------------
        target_year = 2026 

        def extract_date(text):
            text = str(text)
            match = re.search(r'(\d{1,2})/(\d{1,2})', text)
            if match:
                month, day = match.groups()
                return pd.to_datetime(f"{target_year}-{month}-{day}", format="%Y-%m-%d")
            return None

        df['일자'] = df['일자_raw'].apply(extract_date)
        df = df.dropna(subset=['일자'])
        df['월'] = df['일자'].dt.strftime('%Y-%m')

        # [숫자 변환]
        for col in ['수량', '판매단가', '원가단가']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # [이익 계산]
        df['총판매금액'] = df['수량'] * df['판매단가']
        df['총원가금액'] = df['수량'] * df['원가단가']
        df['채널'] = df['채널'].astype(str).str.strip()
        df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
        df['수수료금액'] = df['총판매금액'] * df['수수료율']
        df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']

        # -------------------------------------------------------
        # [고정비 병합]
        # -------------------------------------------------------
        monthly_summary = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
        
        if cost_file is not None:
            df_cost = pd.read_excel(cost_file)
            df_cost['월'] = df_cost['월'].astype(str).str.slice(0, 7)
            for col in ['광고비', '택배비', '운영비']:
                if col not in df_cost.columns: df_cost[col] = 0
            df_cost['총고정비'] = df_cost['광고비'] + df_cost['택배비'] + df_cost['운영비']
            final_summary = pd.merge(monthly_summary, df_cost[['월', '총고정비']], on='월', how='left').fillna(0)
        else:
            with st.sidebar:
                st.warning("고정비 파일을 안 넣으셨네요. 아래 입력값이 일괄 적용됩니다.")
                ad_input = st.number_input("월 평균 광고비", value=0, step=10000)
                ship_input = st.number_input("월 평균 택배비", value=0, step=10000)
                oper_input = st.number_input("월 평균 운영비", value=0, step=10000)
                manual_fixed_cost = ad_input + ship_input + oper_input
            final_summary = monthly_summary.copy()
            final_summary['총고정비'] = manual_fixed_cost

        # [최종 지표 계산]
        final_summary['최종순이익'] = final_summary['매출총이익'] - final_summary['총고정비']
        final_summary['순이익률(%)'] = (final_summary['최종순이익'] / final_summary['총판매금액'] * 100).round(1)

        # 전체 합계
        grand_sales = final_summary['총판매금액'].sum()
        grand_gross = final_summary['매출총이익'].sum()
        grand_fixed = final_summary['총고정비'].sum()
        grand_net = final_summary['최종순이익'].sum()
        grand_net_margin = (grand_net / grand_sales * 100) if grand_sales > 0 else 0

        # ==========================================
        # 4. 결과 시각화
        # ==========================================
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 총 매출", f"{int(grand_sales):,}원")
        col2.metric("📦 매출이익", f"{int(grand_gross):,}원")
        col3.metric("💸 총 고정비", f"-{int(grand_fixed):,}원")
        col4.metric("🏆 최종 순이익", f"{int(grand_net):,}원", delta=f"{grand_net_margin:.1f}%")
        st.divider()

        # 그래프
        st.subheader("📈 월별 순이익 추세")
        tab1, tab2 = st.tabs(["순이익 금액", "순이익률(%)"])
        with tab1:
            fig_net = px.bar(final_summary, x='월', y=['매출총이익', '최종순이익'], barmode='group', 
                             title="매출이익 vs 순이익", text_auto='.2s')
            st.plotly_chart(fig_net, use_container_width=True)
        with tab2:
            fig_line = px.line(final_summary, x='월', y='순이익률(%)', markers=True, title="순이익률 변화")
            fig_line.update_traces(textposition="bottom right", line_color='green')
            fig_line.add_hline(y=0, line_dash="dot", line_color="gray")
            st.plotly_chart(fig_line, use_container_width=True)

        # 상세 데이터
        col_d1, col_d2 = st.columns([2,1])
