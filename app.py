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

DEFAULT_FEE_RATES = {
    "쿠팡": 0.1188, "쿠팡그로스": 0.1188, "네이버": 0.06, "옥션": 0.143,
    "지마켓": 0.143, "11번가": 0.143, "오늘의집": 0.22, "카카오톡": 0.055,
    "알리": 0.11, "사업자거래": 0.0
}

# ==========================================
# 2. 강력한 데이터 로더 (여기가 핵심 수정됨!)
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

def read_file_robust(file):
    """
    어떤 파일이든(엑셀, CSV, 한글CSV) 죽지 않고 읽어내는 함수
    """
    filename = file.name.lower()
    
    # 1. 엑셀(.xlsx) 시도
    if filename.endswith('.xlsx') or filename.endswith('.xls'):
        try:
            return pd.read_excel(file, header=0, sheet_name=None)
        except:
            pass # 실패하면 CSV로 넘어감

    # 2. CSV 시도 (UTF-8: 일반적인 경우)
    try:
        file.seek(0)
        df = pd.read_csv(file, header=0)
        return {'Sheet1': df}
    except:
        pass
        
    # 3. CSV 시도 (CP949: 한국 엑셀/공공기관 데이터 필수)
    try:
        file.seek(0)
        df = pd.read_csv(file, header=0, encoding='cp949')
        return {'Sheet1': df}
    except:
        pass
        
    # 4. CSV 시도 (EUC-KR: 옛날 한글 코드)
    try:
        file.seek(0)
        df = pd.read_csv(file, header=0, encoding='euc-kr')
        return {'Sheet1': df}
    except:
        return None # 진짜 읽을 수 없는 파일

def load_data(files, fee_dict):
    all_dfs = []
    
    for file in files:
        sheets = read_file_robust(file)
        
        if sheets is None:
            st.toast(f"⚠️ 파일 '{file.name}'을 읽지 못했습니다. (패스)", icon="❌")
            continue

        for name, raw in sheets.items():
            try:
                # 데이터가 너무 적으면 패스
                if len(raw) < 2: continue
                
                # [이카운트 양식 파싱]
                # 2번째 줄부터 데이터라고 가정하고 자름
                temp = raw.iloc[1:].copy()
                
                # 컬럼 개수가 부족하면 패스 (최소 8개 열은 있어야 함)
                if temp.shape[1] < 8: 
                    continue
                
                # 필요한 열만 추출 (일자, 거래처, 품목명, 수량, 판매단가, 원가단가)
                # 위치: A(0), B(1), D(3), E(4), F(5), H(7)
                temp = temp.iloc[:, [0, 1, 3, 4, 5, 7]]
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                # 상품명/채널 강제 문자 변환 (NaN 방지)
                temp['상품명'] = temp['상품명'].fillna("상품명없음").astype(str)
                temp['채널'] = temp['채널'].fillna("").astype(str)
                
                # 그로스 체크
                if '그로스' in str(name) or '그로스' in file.name:
                    temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
                
            except Exception as e:
                continue
            
    if not all_dfs: return None
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    # 데이터 전처리
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자']) # 날짜 없는 행 삭제
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    for c in ['수량', '판매단가', '원가단가']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    df['채널'] = df['채널'].str.strip()
    
    df['수수료율'] = df['채널'].map(fee_dict).fillna(0)
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 3. 메인 화면
# ==========================================
st.title("📊 AANT CEO 경영 대시보드")

with st.expander("📂 데이터 파일 관리", expanded=True):
    c1, c2, c3 = st.columns(3)
    up_files = c1.file_uploader("1️⃣ 판매 파일 (필수)", accept_multiple_files=True)
    cost_file = c2.file_uploader("2️⃣ 고정비 파일 (선택)")
    fee_file = c3.file_uploader("3️⃣ 수수료율 파일 (선택)")

# 수수료율 로딩
current_fee_rates = DEFAULT_FEE_RATES.copy()
if fee_file:
    try:
        sheets = read_file_robust(fee_file)
        if sheets:
            # 첫 번째 시트 사용
            fdf = list(sheets.values())[0]
            new_rates = dict(zip(fdf.iloc[:, 0], fdf.iloc[:, 1]))
            current_fee_rates.update(new_rates)
    except: pass

if up_files:
    # 데이터 로드 시도
    df = load_data(up_files, current_fee_rates)
    
    if df is not None and not df.empty:
        # ------------------------------------------------
        # [데이터 정상] 분석 화면 출력
        # ------------------------------------------------
        sales = df['총판매금액'].sum()
        gross = df['매출총이익'].sum()
        
        fixed_cost = 0
        if cost_file:
            try:
                sheets = read_file_robust(cost_file)
                if sheets:
                    cdf = list(sheets.values())[0]
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

        tab1, tab2, tab3 = st.tabs(["📊 분석 리포트", "📋 수수료율", "📥 파일 다운로드"])
        
        with tab1:
            # 1. 채널 분석
            st.subheader("1️⃣ 채널별 성과")
            ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
            ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
            ch_df = ch_df.sort_values(by='총판매금액', ascending=False)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.plotly_chart(px.pie(ch_df, values='총판매금액', names='채널', hole=0.4), use_container_width=True)
            with col2:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                fig.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
                fig.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red')), secondary_y=True)
                st.plotly_chart(fig, use_container_width=True)
            
            # 2. 랭킹 (문제 해결 구간)
            st.divider()
            st.subheader("2️⃣ 상품별 판매 랭킹 (Top 10)")
            
            # 상품명 그룹핑
            pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
            
            # 혹시 상품명이 없거나 빈값인 경우 제거
            pr_df = pr_df[pr_df['상품명'] != "상품명없음"]
            
            if not pr_df.empty:
                top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)
                top10.index = range(1, len(top10)+1)
                st.dataframe(top10.style.format("{:,.0f}"), use_container_width=True)
            else:
                st.warning("상품 데이터가 없습니다. 원본 데이터의 [품목명] 컬럼을 확인해주세요.")

        with tab2:
            st.subheader("📋 적용 수수료율")
            f_disp = pd.DataFrame(list(current_fee_rates.items()), columns=['채널', '요율'])
            f_disp = f_disp[f_disp['채널'].isin(df['채널'].unique())]
            st.dataframe(f_disp)

        with tab3:
            st.subheader("💾 보고서 다운로드")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                pd.DataFrame({'구분':['매출','이익','고정비','순이익'], '금액':[sales,gross,fixed_cost,net]}).to_excel(writer, sheet_name='요약', index=False)
                ch_df.to_excel(writer, sheet_name='채널실적', index=False)
                if not pr_df.empty: pr_df.to_excel(writer, sheet_name='상품랭킹', index=False)
                df.to_excel(writer, sheet_name='상세내역', index=False)
            
            today_str = datetime.date.today().strftime("%Y%m%d")
            st.download_button("📥 CEO 보고서 엑셀 받기", buffer.getvalue(), f"AANT_Report_{today_str}.xlsx")

    else:
        # ------------------------------------------------
        # [데이터 읽기 실패 시] 진단 메시지 출력
        # ------------------------------------------------
        st.error("❌ 데이터를 읽을 수 없습니다.")
        st.info("💡 힌트: 파일이 CSV형식일 경우, '한글 인코딩(cp949)' 문제일 수 있는데 이번 코드에서 해결했습니다. 그래도 안 된다면 파일 내용을 캡처해서 보여주세요.")
else:
    st.info("파일을 업로드해주세요.")
