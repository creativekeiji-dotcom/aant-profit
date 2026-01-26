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
# 2. 데이터 처리
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

def load_data(files):
    all_dfs = []
    for file in files:
        try:
            sheets = pd.read_excel(file, header=0, sheet_name=None)
            for name, raw in sheets.items():
                if len(raw) < 2: continue
                
                temp = raw.iloc[1:].copy()
                # 컬럼 위치가 맞는지 확인 (최소 8열 이상이어야 함)
                if temp.shape[1] < 8: continue 

                temp = temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                if '그로스' in str(name): temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
        except:
            continue
            
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
    df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 3. 메인 화면
# ==========================================
st.title("📊 AANT CEO 경영 대시보드")

with st.expander("📂 데이터 파일 업로드 (여기를 클릭하세요)", expanded=True):
    col1, col2 = st.columns(2)
    up_files = col1.file_uploader("판매 엑셀 파일 (드래그해서 여러 개 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    cost_file = col2.file_uploader("고정비 엑셀 (선택사항)", type=['xlsx', 'xls'])

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

        # KPI 화면 표시
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 총 매출", f"{int(sales):,}원")
        c2.metric("📦 매출이익", f"{int(gross):,}원")
        c3.metric("💸 고정비", f"-{int(fixed_cost):,}원")
        c4.metric("🏆 순이익", f"{int(net):,}원", delta=f"{margin:.1f}%")
        st.markdown("---")

        # 1. 채널 분석
        st.subheader("1️⃣ 채널별 성과 분석")
        ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
        ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
        ch_df = ch_df.sort_values(by='총판매금액', ascending=False)

        col_c1, col_c2 = st.columns([1, 2])
        with col_c1:
            fig_pie = px.pie(ch_df, values='총판매금액', names='채널', hole=0.4, title="채널 점유율")
            fig_pie.update_traces(textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_c2:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
            fig.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red', width=3)), secondary_y=True)
            fig.update_layout(title="채널별 이익금 vs 이익률")
            st.plotly_chart(fig, use_container_width=True)

        # 2. 상품 랭킹
        st.divider()
        st.subheader("2️⃣ 상품별 판매 랭킹 (Top 10)")
        
        pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
        
        if not pr_df.empty:
            st.caption(f"분석된 전체 상품 수: {len(pr_df):,}개")
            sort_key = st.radio("정렬 기준", ["매출액 순", "이익금 순"], horizontal=True)
            
            if "매출" in sort_key:
                top10 = pr_df.sort_values(by='총판매금액', ascending=False).head(10)
            else:
                top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)
            
            top10.index = range(1, len(top10) + 1)
            
            st.dataframe(
                top10.style.format({
                    "수량": "{:,.0f}", "총판매금액": "{:,.0f}", "매출총이익": "{:,.0f}"
                }),
                use_container_width=True
            )
        else:
            st.error("상품 데이터를 불러오지 못했습니다.")

        # ==========================================
        # [핵심] 보고서 다운로드 기능 (여기를 주목하세요!)
        # ==========================================
        st.divider()
        st.subheader("💾 CEO 보고용 파일 저장")
        st.info("👇 아래 버튼을 누르면 '경영 요약'이 포함된 엑셀 보고서가 다운로드됩니다.")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # 1. 경영 요약 시트 (깔끔하게 5줄 요약)
            summary_data = {
                '구분': ['총 매출액', '매출총이익', '총 고정비', '최종 순이익', '순이익률'],
                '금액': [sales, gross, fixed_cost, net, margin]
            }
            df_sum = pd.DataFrame(summary_data)
            df_sum.to_excel(writer, sheet_name='1_경영요약', index=False)

            # 2. 채널별 실적 시트
            ch_df.to_excel(writer, sheet_name='2_채널별실적', index=False)

            # 3. 베스트 상품 시트
            if not pr_df.empty:
                top10.to_excel(writer, sheet_name='3_베스트상품TOP10')

            # 4. 전체 상세 내역 시트
            df.to_excel(writer, sheet_name='4_상세데이터', index=False)

        # 다운로드 버튼 생성
        today_str = datetime.date.today().strftime("%Y%m%d")
        st.download_button(
            label="📥 [클릭] CEO 보고서 엑셀 다운로드",
            data=buffer.getvalue(),
            file_name=f"AANT_경영보고서_{today_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.warning("데이터를 읽을 수 없습니다. 양식을 확인해주세요.")

else:
    st.info("👆 위에서 파일을 업로드해주세요.")
