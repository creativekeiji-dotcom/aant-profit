import streamlit as st
import pandas as pd
import plotly.express as px
import io
import datetime

# ==========================================
# 1. 설정: 수수료율 (기존 동일)
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
uploaded_file = st.file_uploader("이카운트 '판매이익현황' 엑셀 파일을 그대로 업로드하세요", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # 1. 데이터 불러오기 (헤더가 2줄이므로 header=0으로 읽고 처리)
        raw_df = pd.read_excel(uploaded_file, header=0)
        
        # 2. 데이터 전처리 (이카운트 양식 맞춤형)
        # 엑셀의 특정 위치(열)를 강제로 지정해서 가져옵니다.
        # A열(0): 일자, B열(1): 거래처명, D열(3): 품목명, E열(4): 수량, F열(5): 판매단가, H열(7): 원가단가
        try:
            # 실제 데이터는 2행(인덱스 1)부터 시작하므로 슬라이싱
            # 주의: 업로드된 파일 구조에 따라 행 위치가 약간 다를 수 있어 유효한 데이터만 필터링
            df = raw_df.iloc[1:].copy()
            
            # 필요한 열만 쏙 뽑아내기 (iloc 사용)
            df = df.iloc[:, [0, 1, 3, 4, 5, 7]]
            
            # 컬럼 이름 새로 붙이기
            df.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
            
            # 3. 데이터 정제 (빈 값 제거 및 숫자 변환)
            df = df.dropna(subset=['일자_raw']) # 날짜 없는 행 삭제 (합계 라인 등)
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            df['판매단가'] = pd.to_numeric(df['판매단가'], errors='coerce').fillna(0)
            df['원가단가'] = pd.to_numeric(df['원가단가'], errors='coerce').fillna(0)
            
            # 날짜 변환 로직 (예: "01/19-1" -> "2026-01-19")
            current_year = datetime.datetime.now().year
            
            def clean_date(date_str):
                try:
                    # "01/19-1" 형태에서 앞부분 "01/19"만 가져옴
                    clean_str = str(date_str).split('-')[0]
                    return pd.to_datetime(f"{current_year}/{clean_str}", format="%Y/%m/%d")
                except:
                    return None

            df['일자'] = df['일자_raw'].apply(clean_date)
            df['월'] = df['일자'].dt.strftime('%Y-%m')

        except Exception as e:
            st.error(f"데이터 구조 해석 중 오류 발생: {e}")
            st.stop()

        # 4. 수익 계산 로직
        df['총판매금액'] = df['수량'] * df['판매단가']
        df['총원가금액'] = df['수량'] * df['원가단가']
        
        df['채널'] = df['채널'].astype(str).str.strip()
        df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
        df['수수료금액'] = df['총판매금액'] * df['수수료율']
        
        df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
        
        # 5. 전체 합계 계산
        total_sales = df['총판매금액'].sum()
        gross_profit = df['매출총이익'].sum()
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

        # 그래프 (월별 추이)
        if df['월'].notnull().any():
            st.subheader("📈 월별 매출 및 이익율 추이")
            monthly_trend = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
            monthly_trend['이익률(%)'] = (monthly_trend['매출총이익'] / monthly_trend['총판매금액'] * 100).round(1)
            
            tab1, tab2 = st.tabs(["이익률 변화", "매출 변화"])
            with tab1:
                fig_line = px.line(monthly_trend, x='월', y='이익률(%)', markers=True, title="월별 마진율 변화 (%)", text='이익률(%)')
                fig_line.update_traces(textposition="bottom right", line_color='#E01E5A')
                st.plotly_chart(fig_line, use_container_width=True)
            with tab2:
                fig_bar = px.bar(monthly_trend, x='월', y='총판매금액', title="월별 매출액 변화", text_auto='.2s')
                st.plotly_chart(fig_bar, use_container_width=True)

        # 채널별 분석
        st.subheader("채널별 상세 분석")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            fig_pie = px.pie(df, values='총판매금액', names='채널', title='채널 점유율')
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_chart2:
            channel_group = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
            fig_bar = px.bar(channel_group, x='채널', y='매출총이익', text_auto='.2s', title='채널별 이익금액')
            st.plotly_chart(fig_bar, use_container_width=True)

        # 엑셀 다운로드
        st.divider()
        st.subheader("💾 데이터 다운로드")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            save_cols = ['일자', '채널', '상품명', '수량', '판매단가', '원가단가', '총판매금액', '수수료금액', '매출총이익']
            df[save_cols].to_excel(writer, index=False, sheet_name='상세내역')
            if '월' in df.columns:
                monthly_trend.to_excel(writer, index=False, sheet_name='월별요약')
        
        st.download_button(
            label="📥 분석 결과 엑셀로 받기",
            data=buffer.getvalue(),
            file_name="AANT_결산분석결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        with st.expander("📄 원본 데이터 미리보기"):
            st.dataframe(df)

    except Exception as e:
        st.error(f"파일을 읽는 중 오류가 발생했습니다. 양식을 확인해주세요: {e}")
