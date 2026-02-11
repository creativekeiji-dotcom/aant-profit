import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 수수료율 설정
FEE_RATES = {
    "쿠팡": 0.1188, "쿠팡그로스": 0.1188, "네이버": 0.06,
    "옥션": 0.143, "지마켓": 0.143, "11번가": 0.143,
    "오늘의집": 0.22, "카카오톡": 0.055, "알리": 0.11, "사업자거래": 0.0
}

# 2. 화면 설정
st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 경영 분석 대시보드")

# --- 사이드바: 고정비 처리 ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일을 올려주세요", type=['csv', 'xlsx'])
    
    file_fixed_cost = 0
    if fixed_file is not None:
        try:
            # 파일 읽기
            if fixed_file.name.endswith('.csv'):
                try: f_df = pd.read_csv(fixed_file, encoding='utf-8-sig')
                except: f_df = pd.read_csv(fixed_file, encoding='cp949')
            else:
                f_df = pd.read_excel(fixed_file)

            # [핵심] 제목이 밀려있을 경우 '금액'이라는 단어를 찾아 헤더로 강제 지정
            if '금액' not in f_df.columns:
                for i in range(min(len(f_df), 5)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]
                        f_df = f_df.iloc[i+1:].reset_index(drop=True)
                        break

            # 금액 계산 (콤마 제거, 숫자 변환)
            if '금액' in f_df.columns:
                f_df['금액_숫자'] = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', '').str.strip(), errors='coerce').fillna(0)
                file_fixed_cost = f_df['금액_숫자'].sum()
                st.success(f"파일 반영: {file_fixed_cost:,.0f}원")
            else:
                st.error("'금액' 컬럼을 찾을 수 없습니다. 양식을 확인해주세요.")
        except Exception as e:
            st.error(f"고정비 파일 에러: {e}")

    st.write("---")
    ad_cost = st.number_input("추가 광고비 직접입력", value=0)
    etc_cost = st.number_input("기타 운영비 직접입력", value=0)
    total_fixed_cost = file_fixed_cost + ad_cost + etc_cost
    st.metric("최종 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# --- 메인: 판매 데이터 처리 ---
main_file = st.file_uploader("이카운트 판매내역 엑셀을 올려주세요", type=['xlsx', 'xls'])

if main_file is not None:
    try:
        df = pd.read_excel(main_file)
        # 이카운트 양식의 제목을 표준 제목으로 강제 매핑
        col_map = {'일자':'일자', '거래처명':'채널', '품목명':'상품명', '수량':'수량', '단가':'판매단가', '입고단가':'원가단가'}
        df.rename(columns=col_map, inplace=True)

        if '수량' in df.columns and '판매단가' in df.columns:
            # 계산 로직
            df['총판매금액'] = df['수량'] * df['판매단가']
            df['원가단가'] = df.get('원가단가', 0)
            df['총원가금액'] = df['수량'] * df['원가단가']
            df['채널'] = df['채널'].astype(str).str.strip()
            df['수수료율'] = df['채널'].map(FEE_RATES).fillna(0)
            df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - (df['총판매금액'] * df['수수료율'])

            # 결과 집계
            ts, gp = df['총판매금액'].sum(), df['매출총이익'].sum()
            np = gp - total_fixed_cost
            
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 총 매출", f"{int(ts):,}원")
            c2.metric("📦 상품 마진", f"{int(gp):,}원", f"{(gp/ts*100):.1f}%" if ts>0 else "0%")
            c3.metric("💸 총 고정비", f"-{total_fixed_cost:,.0f}원")
            c4.metric("🏆 최종 순이익", f"{int(np):,}원", f"{(np/ts*100):.1f}%" if ts>0 else "0%")
            st.divider()

            # 그래프
            fig = px.pie(df, values='총판매금액', names='채널', title='채널별 매출 비중')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("판매내역 파일의 컬럼명이 '수량', '단가' 인지 확인해주세요.")
    except Exception as e:
        st.error(f"메인 데이터 에러: {e}")
