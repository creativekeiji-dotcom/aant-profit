import streamlit as st
import pandas as pd
import plotly.express as px
import io # 파일 다운로드를 위한 기능

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

COLUMN_MAP = {
    '일자': '일자',       
    '채널': '거래처명',
    '상품명': '품목명',
    '수량': '수량',
    '판매단가': '단가',
    '원가단가': '입고단가'
}

# ==========================================
# 2. 화면 구성
# ==========================================
st.set_page_config(page_title="AANT 월간 결산", layout="wide")

st.title("📊 AANT(안트) 경영 분석 대시보드")

# --- 사이드바: 고정비 입력 ---
with st.sidebar:
    st.header("💸 월간 고정비 입력")
    st.info("순이익 계산을 위해 이번 달 총 비용을 입력하세요.")
    
    ad_cost = st.number_input("광고비 총액 (원)", value=0, step=10000, format="%d")
    shipping_cost = st.number_input("택배비/물류비 (원)", value=0, step=10000, format="%d")
    etc_cost = st.number_input("기타 운영비 (원)", value=0, step=10000, format="%d")
    
    total_fixed_cost = ad_cost + shipping_cost + etc_cost
    st.write("---")
    st.metric("총 고정비 합계", f"{total_fixed_cost:,} 원")

# --- 메인 화면 ---
uploaded_file = st.file_uploader("이카운트 엑셀 파일을 업로드하세요 (판매내역)", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        rename_dict = {v: k for k, v in COLUMN_MAP.items() if v in df.columns}
        df.rename(columns=rename_dict, inplace=True)

        if '수량' not in df.columns or '판매단가' not in df.columns:
            st.error("필수 컬럼(수량, 단가 등)을 찾을 수 없습니다.")
        else:
            # 날짜 변환 (추세 그래프용)
            if '일자' in df.columns:
                df['일자'] = pd.to_datetime(df['일자'])
                df['월'] = df['일자'].dt.strftime('%Y-%m') # 월별 그룹핑을 위해 컬럼 생성
            
            # 1. 기본 이익 계산
            df['총판매금액'] = df['수량'] * df['판매단가']
            if '원가단가' not in df.columns: df['원가단가'] = 0
            df['총원가금액'] = df['수량'] * df['원가단가']
            
            df['채널'] = df['채널'].astype(str).str.strip()
            df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
            df['수수료금액'] = df['총판매금액'] * df['수수료율']
            
            df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
            
            # 마진율 (개별 건)
            df['마진율'] = df.apply(lambda x: x['매출총이익'] / x['총판매금액'] if x['총판매금액'] > 0 else 0, axis=1)

            # 2. 전체 합계 계산
            total_sales = df['총판매금액'].sum()
            gross_profit = df['매출총이익'].sum()
            
            # 3. 최종 순이익 (고정비 차감)
            net_profit = gross_profit - total_fixed_cost
            
            gross_margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            net_margin = (net_profit / total_sales * 100) if total_sales > 0 else 0

            # --- 결과 보여주기 ---
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 총 매출", f"{int(total_sales):,}원")
            col2.metric("📦 매출이익 (상품마진)", f"{int(gross_profit):,}원", delta=f"{gross_margin:.1f}%")
            col3.metric("💸 고정비 지출", f"-{total_fixed_cost:,}원")
            col4.metric("🏆 최종 순이익", f"{int(net_profit):,}원", delta=f"{net_margin:.1f}%", delta_color="normal")
            st.divider()

            # --- [추가 기능 1] 월별 추세 그래프 (꺾은선) ---
            if '월' in df.columns:
                st.subheader("📈 월별 매출 및 이익율 추이")
                # 월별로 데이터 묶기
                monthly_trend = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
                monthly_trend['이익률(%)'] = (monthly_trend['매출총이익'] / monthly_trend['총판매금액'] * 100).round(1)
                
                # 그래프 그리기 (이중축: 막대는 매출, 선은 이익률)
                # 직관적으로 보기 위해 콤보 차트 대신 라인 차트 2개로 분리하거나, plotly 기능을 활용
                
                tab1, tab2 = st.tabs(["이익률 변화", "매출 변화"])
                
                with tab1:
                    fig_line = px.line(monthly_trend, x='월', y='이익률(%)', markers=True, 
                                       title="월별 상품 마진율 변화 (%)", text='이익률(%)')
                    fig_line.update_traces(textposition="bottom right", line_color='#E01E5A')
                    st.plotly_chart(fig_line, use_container_width=True)
                    
                with tab2:
                    fig_bar = px.bar(monthly_trend, x='월', y='총판매금액', 
                                     title="월별 매출액 변화", text_auto='.2s')
                    st.plotly_chart(fig_bar, use_container_width=True)

            # --- [기존 기능] 채널별 분석 ---
            st.subheader("채널별 상세 분석")
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                fig_pie = px.pie(df, values='총판매금액', names='채널', title='채널 점유율')
                st.plotly_chart(fig_pie, use_container_width=True)
            with col_chart2:
                channel_group = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
                fig_bar = px.bar(channel_group, x='채널', y='매출총이익', text_auto='.2s', title='채널별 이익금액')
                st.plotly_chart(fig_bar, use_container_width=True)

            # --- [추가 기능 2] 엑셀 다운로드 ---
            st.divider()
            st.subheader("💾 데이터 다운로드")
            
            # 엑셀 파일 생성 로직
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='상세내역')
                # 월별 요약 시트도 추가
                if '월' in df.columns:
                    monthly_trend.to_excel(writer, index=False, sheet_name='월별요약')
            
            # 다운로드 버튼
            st.download_button(
                label="📥 분석 결과 엑셀로 받기",
                data=buffer.getvalue(),
                file_name="AANT_결산분석결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            with st.expander("📄 원본 데이터 미리보기"):
                st.dataframe(df)

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
