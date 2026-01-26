import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re  # [추가] 정규표현식 사용 (날짜 정밀 추출용)

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
# 2. 파일 업로드 구역
# ==========================================
col_up1, col_up2 = st.columns(2)

with col_up1:
    st.info("1️⃣ 판매 데이터 (이카운트 엑셀)")
    uploaded_file = st.file_uploader("판매내역 엑셀 업로드", type=['xlsx', 'xls'], key="sales")

with col_up2:
    st.info("2️⃣ 월별 고정비 데이터 (선택사항)")
    cost_file = st.file_uploader("고정비 엑셀 업로드", type=['xlsx', 'xls'], key="cost")
    
    with st.expander("❓ 고정비 파일 양식"):
        st.markdown("- 컬럼명: **월, 광고비, 택배비, 운영비**\n- 월 형식: 2026-01")

if uploaded_file is not None:
    try:
        # --- [1] 판매 데이터 로드 ---
        all_sheets = pd.read_excel(uploaded_file, header=0, sheet_name=None)
        all_data_frames = []
        
        for sheet_name, raw_df in all_sheets.items():
            try:
                if len(raw_df) < 2: continue
                
                # 이카운트 2단 헤더 처리
                df_temp = raw_df.iloc[1:].copy()
                df_temp = df_temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                df_temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                # 탭 이름에 '그로스' 있으면 채널명 변경
                if '그로스' in str(sheet_name):
                    df_temp['채널'] = '쿠팡그로스'
                
                df_temp['원본시트'] = sheet_name
                all_data_frames.append(df_temp)
            except:
                continue

        if not all_data_frames:
            st.error("데이터를 읽을 수 없습니다.")
            st.stop()
            
        df = pd.concat(all_data_frames, ignore_index=True)

        # --- [2] 날짜 변환 로직 (강화됨) ---
        # "01/19-12" -> 01월 19일 추출
        
        target_year = 2026  # [설정] 분석할 연도 (2026년으로 고정)

        def extract_date(text):
            text = str(text)
            # 정규식: 숫자 1~2개 + 슬래시(/) + 숫자 1~2개 패턴 찾기
            match = re.search(r'(\d{1,2})/(\d{1,2})', text)
            if match:
                month, day = match.groups()
                # 2026-MM-DD 형식으로 변환
                return pd.to_datetime(f"{target_year}-{month}-{day}", format="%Y-%m-%d")
            return None

        # 날짜 변환 적용
        df['일자'] = df['일자_raw'].apply(extract_date)
        
        # 날짜 인식이 안 된 행(합계 등) 제거
        df = df.dropna(subset=['일자'])
        
        # 월 컬럼 생성 (2026-01 형태)
        df['월'] = df['일자'].dt.strftime('%Y-%m')

        # --- [3] 데이터 정제 및 이익 계산 ---
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
        df['판매단가'] = pd.to_numeric(df['판매단가'], errors='coerce').fillna(0)
        df['원가단가'] = pd.to_numeric(df['원가단가'], errors='coerce').fillna(0)

        df['총판매금액'] = df['수량'] * df['판매단가']
        df['총원가금액'] = df['수량'] * df['원가단가']
        df['채널'] = df['채널'].astype(str).str.strip()
        df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
        df['수수료금액'] = df['총판매금액'] * df['수수료율']
        df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']

        # --- [4] 고정비 병합 ---
        monthly_summary = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
        
        if cost_file is not None:
            df_cost = pd.read_excel(cost_file)
            df_cost['월'] = df_cost['월'].astype(str).str.slice(0, 7)
            for col in ['광고비', '택배비', '운영비']:
                if col not in df_cost.columns: df_cost[col] = 0
            df_cost['총고정비'] = df_cost['광고비'] + df_cost['택배비'] + df_cost['운영비']
            final_summary = pd.merge(monthly_summary, df_cost[['월', '총고정비']], on='월', how='left').fillna(0)
            st.success("✅ 고정비 파일 적용 완료")
        else:
            with st.sidebar:
                st.warning("고정비 파일을 안 넣으셨네요. 아래 입력값이 적용됩니다.")
                ad_input = st.number_input("월 평균 광고비", value=0, step=10000)
                ship_input = st.number_input("월 평균 택배비", value=0, step=10000)
                oper_input = st.number_input("월 평균 운영비", value=0, step=10000)
                manual_fixed_cost = ad_input + ship_input + oper_input
            final_summary = monthly_summary.copy()
            final_summary['총고정비'] = manual_fixed_cost

        # 최종 계산
        final_summary['최종순이익'] = final_summary['매출총이익'] - final_summary['총고정비']
        final_summary['순이익률(%)'] = (final_summary['최종순이익'] / final_summary['총판매금액'] * 100).round(1)

        # 전체 합계
        grand_sales = final_summary['총판매금액'].sum()
        grand_gross = final_summary['매출총이익'].sum()
        grand_fixed = final_summary['총고정비'].sum()
        grand_net = final_summary['최종순이익'].sum()
        grand_net_margin = (grand_net / grand_sales * 100) if grand_sales > 0 else 0

        # --- 결과 화면 ---
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
            fig_line = px.line(final_summary, x='월', y='순이익률(%)', markers=True, 
                               title="순이익률 변화", text='순이익률(%)')
            fig_line.update_traces(textposition="bottom right", line_color='green')
            fig_line.add_hline(y=0, line_dash="dot", line_color="gray")
            st.plotly_chart(fig_line, use_container_width=True)

        # 상세표
        col_d1, col_d2 = st.columns([2,1])
        with col_d1:
            st.subheader("월별 손익계산서")
            st.dataframe(final_summary)
        with col_d2:
            st.subheader("채널별 매출")
            st.plotly_chart(px.pie(df, values='총판매금액', names='채널'), use_container_width=True)

        # 엑셀 다운로드 (일자 포맷 정리)
        st.divider()
        df['일자'] = df['일자'].dt.strftime('%Y-%m-%d') # 엑셀 저장 시 깔끔하게
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            final_summary.to_excel(writer, index=False, sheet_name='월별손익요약')
            df.to_excel(writer, index=False, sheet_name='판매상세내역')
        
        st.download_button("📥 최종 보고서 다운로드 (Excel)", buffer.getvalue(), "AANT_경영분석.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"오류 발생: {e}")
