import streamlit as st
import pandas as pd
import plotly.express as px
import io

# ==========================================
# 1. 설정: 채널별 수수료율 (필요시 수정하세요)
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

# 이카운트 엑셀 컬럼 매핑 (이사님 엑셀 양식에 맞춤)
COLUMN_MAP = {
    '일자': '일자',       
    '채널': '거래처명',
    '상품명': '품목명',
    '수량': '수량',
    '판매단가': '단가',
    '원가단가': '입고단가'
}

# ==========================================
# 2. 화면 구성 및 사이드바 (고정비 설정)
# ==========================================
st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 경영 분석 대시보드")

with st.sidebar:
    st.header("💸 월간 고정비 설정")
    st.info("파일을 업로드하거나 직접 금액을 입력하세요.")
    
    # [기능 추가] 고정비 파일 업로드
    st.subheader("📁 1. 파일로 자동 입력")
    fixed_file = st.file_uploader("고정비 CSV/엑셀 업로드", type=['csv', 'xlsx'])
    
    file_fixed_cost = 0
    if fixed_file is not None:
        try:
            if fixed_file.name.endswith('.csv'):
                try:
                    f_df = pd.read_csv(fixed_file, encoding='utf-8-sig')
                except:
                    f_df = pd.read_csv(fixed_file, encoding='cp949')
            else:
                f_df = pd.read_excel(fixed_file)
            
            if '금액' in f_df.columns:
                # 콤마 제거 및 숫자로 변환
                f_df['금액'] = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                file_fixed_cost = f_df['금액'].sum()
                st.success(f"파일 반영: {file_fixed_cost:,.0f}원")
            else:
                st.error("'금액' 컬럼이 없습니다. 양식을 확인해주세요.")
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")

    st.write("---")

    # 수동 입력 (파일 외 추가 비용)
    st.subheader("⌨️ 2. 추가/수동 입력")
    ad_cost = st.number_input("광고비 직접입력", value=0, step=10000)
    shipping_cost = st.number_input("물류비 직접입력", value=0, step=10000)
    etc_cost = st.number_input("기타 직접입력", value=0, step=10000)
    
    # 최종 고정비 합산
    total_fixed_cost = file_fixed_cost + ad_cost + shipping_cost + etc_cost
    st.metric("최종 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# ==========================================
# 3. 메인 로직: 판매 데이터 처리
# ==========================================
uploaded_file = st.file_uploader("이카운트 판매내역 엑셀을 업로드하세요", type=['xlsx', 'xls'])

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        # 컬럼명 변경
        rename_dict = {v: k for k, v in COLUMN_MAP.items() if v in df.columns}
        df.rename(columns=rename_dict, inplace=True)

        if '수량' not in df.columns or '판매단가' not in df.columns:
            st.error("필수 컬럼(수량, 단가)을 찾을 수 없습니다. 이카운트 양식을 확인해주세요.")
        else:
            # 기본 계산 로직
            if '일자' in df.columns:
                df['일자'] = pd.to_datetime(df['일자'])
                df['월'] = df['일자'].dt.strftime('%Y-%m')

            df['총판매금액'] = df['수량'] * df['판매단가']
            df['원가단가'] = df.get('원가단가', 0)
            df['총원가금액'] = df['수량'] * df['원가단가']
            
            df['채널'] = df['채널'].astype(str).str.strip()
            df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
            df['수수료금액'] = df['총판매금액'] * df['수수료율']
            
            df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
            
            # 합계 데이터 계산
            total_sales = df['총판매금액'].sum()
            gross_profit = df['매출총이익'].sum()
            net_profit = gross_profit - total_fixed_cost # 고정비 반영
            
            gross_margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
            net_margin = (net_profit / total_sales * 100) if total_sales > 0 else 0

            # 결과 지표 출력 (대시보드 상단 카드)
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 총 매출", f"{int(total_sales):,}원")
            c2.metric("📦 상품 마진 (GP)", f"{int(gross_profit):,}원", f"{gross_margin:.1f}%")
            c3.metric("💸 고정비 (파일+수동)", f"-{total_fixed_cost:,.0f}원")
            c4.metric("🏆 최종 순이익 (NP)", f"{int(net_profit):,}원", f"{net_margin:.1f}%")
            st.divider()

            # 시각화 영역
            tab1, tab2 = st.tabs(["채널별 분석", "월별 추세"])
            with tab1:
                col_a, col_b = st.columns(2)
                fig1 = px.pie(df, values='총판매금액', names='채널', title='채널별 매출 비중')
                col_a.plotly_chart(fig1, use_container_width=True)
                
                channel_grp = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
                fig2 = px.bar(channel_grp, x='채널', y='매출총이익', title='채널별 이익액')
                col_b.plotly_chart(fig2, use_container_width=True)
            
            with tab2:
                if '월' in df.columns:
                    monthly = df.groupby('월')[['총판매금액', '매출총이익']].sum().reset_index()
                    fig3 = px.line(monthly, x='월', y='총판매금액', markers=True, title='월별 매출액 추이')
                    st.plotly_chart(fig3, use_container_width=True)

            # 결과 다운로드 버튼
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='상세데이터')
            st.download_button("📥 분석 결과 엑셀 다운로드", buffer.getvalue(), "AANT_결산_리포트.xlsx")

    except Exception as e:
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
