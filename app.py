import streamlit as st
import pandas as pd
import plotly.express as px
import io
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

# ==========================================
# 2. 화면 구성
# ==========================================
st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 통합 경영 분석기")

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
uploaded_file = st.file_uploader("이카운트 엑셀 파일을 업로드하세요 (모든 탭 자동 통합)", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        # [핵심 변경] sheet_name=None : 모든 시트를 다 읽어옴 (딕셔너리 형태)
        all_sheets = pd.read_excel(uploaded_file, header=0, sheet_name=None)
        
        all_data_frames = []
        
        # 각 시트(탭)를 하나씩 꺼내서 처리
        for sheet_name, raw_df in all_sheets.items():
            try:
                # 데이터가 너무 적으면(빈 시트 등) 패스
                if len(raw_df) < 2:
                    continue

                # 이카운트 2단 헤더 처리 (2번째 줄부터 데이터로 인식)
                # 구조가 동일하다고 가정하고 처리
                df_temp = raw_df.iloc[1:].copy()
                
                # 필수 컬럼 위치 가져오기 (A, B, D, E, F, H 열)
                # 만약 시트마다 양식이 조금 다르다면 에러가 날 수 있으니 try-except로 방어
                df_temp = df_temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                df_temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                # 어느 탭에서 왔는지 기록 (나중에 확인용)
                df_temp['원본시트'] = sheet_name
                
                # 리스트에 추가
                all_data_frames.append(df_temp)
                
            except Exception as e:
                # 특정 시트 형식이 다르면 건너뜀 (안내 메시지 없이 조용히 처리)
                continue

        # 모든 시트 데이터를 하나로 합치기
        if not all_data_frames:
            st.error("데이터를 읽을 수 없습니다. 엑셀 양식을 확인해주세요.")
            st.stop()
            
        df = pd.concat(all_data_frames, ignore_index=True)

        # -------------------------------------------------------
        # 이후 로직은 기존과 동일 (데이터 정제 및 계산)
        # -------------------------------------------------------
        
        # 3. 데이터 정제
        df = df.dropna(subset=['일자_raw']) 
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
        df['판매단가'] = pd.to_numeric(df['판매단가'], errors='coerce').fillna(0)
        df['원가단가'] = pd.to_numeric(df['원가단가'], errors='coerce').fillna(0)
        
        # 날짜 변환
        current_year = datetime.datetime.now().year
        def clean_date(date_str):
            try:
                clean_str = str(date_str).split('-')[0] # "01/19-1" -> "01/19"
                return pd.to_datetime(f"{current_year}/{clean_str}", format="%Y/%m/%d")
            except:
                return None

        df['일자'] = df['일자_raw'].apply(clean_date)
        df['월'] = df['일자'].dt.strftime('%Y-%m')

        # 4. 수익 계산
        df['총판매금액'] = df['수량'] * df['판매단가']
        df['총원가금액'] = df['수량'] * df['원가단가']
        
        df['채널'] = df['채널'].astype(str).str.strip()
        df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
        df['수수료금액'] = df['총판매금액'] * df['수수료율']
        
        df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
        
        # 5. 합계 계산
        total_sales = df['총판매금액'].sum()
        gross_profit = df['매출총이익'].sum()
        net_profit = gross_profit - total_fixed_cost
        
        gross_margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
        net_margin = (net_profit / total_sales * 100) if total_sales > 0 else 0

        # --- 결과 보여주기 ---
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 통합 총 매출", f"{int(total_sales):,}원")
        col2.metric("📦 통합 매출이익", f"{int(gross_profit):,}원", delta=f"{gross_margin:.1f}%")
        col3.metric("💸 고정비 지출", f"-{total_fixed_cost:,}원")
        col4.metric("🏆 최종 순이익", f"{int(net_profit):,}원", delta=f"{net_margin:.1f}%", delta_color="normal")
        st.divider()

        # 그래프 (월별)
        if df['월'].notnull().any():
            st.subheader("📈 통합 월별 추이 (그로스 포함)")
            monthly_trend = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
            monthly_trend['이익률(%)'] = (monthly_trend['매출총이익'] / monthly_trend['총판매금액'] * 100).round(1)
            
            tab1, tab2 = st.tabs(["이익률", "매출액"])
            with tab1:
                fig_line = px.line(monthly_trend, x='월', y='이익률(%)', markers=True, text='이익률(%)')
                fig_line.update_traces(textposition="bottom right", line_color='#E01E5A')
                st.plotly_chart(fig_line, use_container_width=True)
            with tab2:
                fig_bar = px.bar(monthly_trend, x='월', y='총판매금액', text_auto='.2s')
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
        st.subheader("💾 통합 데이터 다운로드")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            save_cols = ['일자', '원본시트', '채널', '상품명', '수량', '판매단가', '원가단가', '총판매금액', '수수료금액', '매출총이익']
            df[save_cols].to_excel(writer, index=False, sheet_name='전체통합내역')
            if '월' in df.columns:
                monthly_trend.to_excel(writer, index=False, sheet_name='월별요약')
        
        st.download_button(
            label="📥 통합 결과 엑셀로 받기",
            data=buffer.getvalue(),
            file_name="AANT_통합결산결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        with st.expander("📄 원본 데이터 미리보기 (상위 100개)"):
            st.dataframe(df.head(100))

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
