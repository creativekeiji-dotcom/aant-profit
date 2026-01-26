import streamlit as st
import pandas as pd
import plotly.express as px
import io
import re
import datetime

# ==========================================
# 1. 기본 설정 (수수료율 등)
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

st.set_page_config(page_title="AANT 경영 리포트", layout="wide")

# ==========================================
# 2. 데이터 처리 함수 (복잡한 로직 분리)
# ==========================================
def load_and_process_data(uploaded_files, target_year=2026):
    all_data_frames = []
    
    for file in uploaded_files:
        try:
            all_sheets = pd.read_excel(file, header=0, sheet_name=None)
            for sheet_name, raw_df in all_sheets.items():
                if len(raw_df) < 2: continue
                
                # 이카운트 양식 처리
                df_temp = raw_df.iloc[1:].copy()
                df_temp = df_temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                df_temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                if '그로스' in str(sheet_name):
                    df_temp['채널'] = '쿠팡그로스'
                
                all_data_frames.append(df_temp)
        except:
            continue
            
    if not all_data_frames: return None
    
    df = pd.concat(all_data_frames, ignore_index=True)
    
    # 날짜/숫자 변환
    def extract_date(text):
        match = re.search(r'(\d{1,2})/(\d{1,2})', str(text))
        if match:
            m, d = match.groups()
            return pd.to_datetime(f"{target_year}-{m}-{d}", format="%Y-%m-%d")
        return None

    df['일자'] = df['일자_raw'].apply(extract_date)
    df = df.dropna(subset=['일자'])
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    for col in ['수량', '판매단가', '원가단가']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    # 이익 계산
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    df['채널'] = df['채널'].astype(str).str.strip()
    df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 3. 메인 화면 구성
# ==========================================
st.title("📑 AANT CEO 경영 보고서")
st.markdown("---")

# 파일 업로드 (접이식으로 깔끔하게 숨김)
with st.expander("📂 데이터 파일 업로드 (클릭해서 열기)", expanded=True):
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_files = st.file_uploader("판매 보고서 (여러 개 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    with col_up2:
        cost_file = st.file_uploader("고정비 보고서 (선택)", type=['xlsx', 'xls'])

# 데이터가 있으면 리포트 생성
if uploaded_files:
    df = load_and_process_data(uploaded_files)
    
    if df is not None:
        # --- [1] 핵심 KPI 요약 (맨 위) ---
        total_sales = df['총판매금액'].sum()
        total_gross_profit = df['매출총이익'].sum()
        gross_margin = (total_gross_profit / total_sales * 100) if total_sales > 0 else 0
        
        # 고정비 처리
        total_fixed_cost = 0
        if cost_file:
            df_cost = pd.read_excel(cost_file)
            # 간단하게 총합만 계산 (월별 매칭은 상세에서)
            if '광고비' in df_cost.columns: total_fixed_cost += df_cost['광고비'].sum()
            if '택배비' in df_cost.columns: total_fixed_cost += df_cost['택배비'].sum()
            if '운영비' in df_cost.columns: total_fixed_cost += df_cost['운영비'].sum()
        else:
            # 파일 없으면 0원 처리 (보고서 모드에서는 수동입력 제외하고 깔끔하게)
            pass

        net_profit = total_gross_profit - total_fixed_cost
        net_margin = (net_profit / total_sales * 100) if total_sales > 0 else 0

        # KPI 카드 표시
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 총 매출액", f"{int(total_sales):,}원")
        c2.metric("📦 매출 총이익", f"{int(total_gross_profit):,}원", delta=f"{gross_margin:.1f}%")
        c3.metric("💸 고정비 합계", f"-{int(total_fixed_cost):,}원")
        c4.metric("🏆 최종 순이익", f"{int(net_profit):,}원", delta=f"{net_margin:.1f}%", delta_color="normal")
        
        st.markdown("---")

        # --- [2] 채널별 성과 분석 (Best Sales) ---
        st.header("1️⃣ 채널별 성과 분석")
        
        # 채널 데이터 집계
        channel_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
        channel_df['마진율(%)'] = (channel_df['매출총이익'] / channel_df['총판매금액'] * 100).round(1)
        channel_df = channel_df.sort_values(by='총판매금액', ascending=False) # 매출 순 정렬
        
        # 최고 매출 채널 찾기
        best_ch = channel_df.iloc[0]
        best_share = (best_ch['총판매금액'] / total_sales * 100)
        
        col_ch1, col_ch2 = st.columns([1, 2])
        
        with col_ch1:
            st.info(f"🏆 **1등 공신: {best_ch['채널']}**")
            st.write(f"- 매출 비중: **{best_share:.1f}%**")
            st.write(f"- 매출액: **{int(best_ch['총판매금액']):,}원**")
            st.write(f"- 마진율: **{best_ch['마진율(%)']:.1f}%**")
            
            # 파이차트
            fig_pie = px.pie(channel_df, values='총판매금액', names='채널', hole=0.4, title="채널별 매출 점유율")
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_ch2:
            st.subheader("📊 채널별 마진 & 마진율 비교")
            # 이중축 그래프 (막대: 마진금액, 선: 마진율)
            # Plotly 사용
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # 막대그래프 (매출이익)
            fig.add_trace(
                go.Bar(x=channel_df['채널'], y=channel_df['매출총이익'], name="매출이익(원)", marker_color='#3366CC'),
                secondary_y=False
            )

            # 꺾은선 (마진율)
            fig.add_trace(
                go.Scatter(x=channel_df['채널'], y=channel_df['마진율(%)'], name="마진율(%)", mode='lines+markers+text',
                           text=channel_df['마진율(%)'], textposition="top center", line=dict(color='#E01E5A', width=3)),
                secondary_y=True
            )

            fig.update_layout(title="채널별 수익성 분석 (막대: 이익금 / 선: 이익률)")
            st.plotly_chart(fig, use_container_width=True)

            # 표 보여주기 (깔끔하게)
            st.dataframe(
                channel_df.style.format({
                    "총판매금액": "{:,.0f}원", 
                    "매출총이익": "{:,.0f}원", 
                    "마진율(%)": "{:.1f}%"
                }), 
                use_container_width=True
            )

        st.markdown("---")

        # --- [3] 상품별 랭킹 (Top 10 Products) ---
        st.header("2️⃣ 상품별 판매 랭킹 (TOP 10)")
        
        # 상품 집계
        prod_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
        prod_df['마진율(%)'] = (prod_df['매출총이익'] / prod_df['총판매금액'] * 100).round(1)
        
        # 정렬 기준 선택 (매출순 vs 이익순)
        sort_col = st.radio("정렬 기준:", ['매출액 순', '이익금 순'], horizontal=True)
        if sort_col == '매출액 순':
            prod_df = prod_df.sort_values(by='총판매금액', ascending=False)
        else:
            prod_df = prod_df.sort_values(by='매출총이익', ascending=False)
            
        top10 = prod_df.head(10).reset_index(drop=True)
        top10.index = top10.index + 1 # 1위부터 시작하도록
        
        # Top 10 시각화 (가로 막대)
        col_p1, col_p2 = st.columns([2, 1])
        
        with col_p1:
            st.subheader("🥇 베스트 상품 10 리스트")
            st.dataframe(
                top10.style.format({
                    "수량": "{:,.0f}개",
                    "총판매금액": "{:,.0f}원",
                    "매출총이익": "{:,.0f}원",
                    "마진율(%)": "{:.1f}%"
                }).background_gradient(subset=['매출총이익'], cmap='Greens'),
                use_container_width=True
            )
            
        with col_p2:
            st.subheader("매출 상위 5개 비중")
            top5 = prod_df.head(5)
            fig_top5 = px.bar(top5, x='총판매금액', y='상품명', orientation='h', text_auto='.2s', title="매출 Top 5")
            fig_top5.update_layout(yaxis={'categoryorder':'total ascending'}) # 큰 게 위로
            st.plotly_chart(fig_top5, use_container_width=True)

        # --- [4] 엑셀 다운로드 ---
        st.divider()
        st.subheader("💾 보고서 파일 저장")
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # 시트1: 요약 보고서
            summary_sheet = pd.DataFrame({
                '구분': ['총 매출', '매출이익', '총 고정비', '최종 순이익', '순이익률'],
                '금액': [total_sales, total_gross_profit, total_fixed_cost, net_profit, f"{net_margin:.1f}%"]
            })
            summary_sheet.to_excel(writer, sheet_name='경영요약', index=False)
            
            # 시트2: 채널별 실적
            channel_df.to_excel(writer, sheet_name='채널별실적', index=False)
            
            # 시트3: 상품별 랭킹
            prod_df.to_excel(writer, sheet_name='상품별랭킹', index=False)
            
            # 시트4: 전체 로우 데이터
            df.to_excel(writer, sheet_name='상세내역', index=False)
            
        st.download_button(
            label="📥 CEO 보고용 엑셀 다운로드",
            data=buffer.getvalue(),
            file_name=f"AANT_CEO보고서_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    else:
        st.info("👆 위에서 엑셀 파일을 업로드해주세요.")
