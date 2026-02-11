import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 경영 분석 대시보드")

# --- 사이드바: 고정비 처리 (이사님 파일 맞춤형 로직) ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일을 올려주세요", type=['csv', 'xlsx'])
    
    file_fixed_sum = 0
    if fixed_file is not None:
        try:
            # 1. 파일 읽기
            if fixed_file.name.endswith('.csv'):
                try: f_df = pd.read_csv(fixed_file, encoding='utf-8-sig')
                except: f_df = pd.read_csv(fixed_file, encoding='cp949')
            else: f_df = pd.read_excel(fixed_file)

            # 2. [핵심] 제목 줄 찾기 (빈 칸 무시하고 '금액' 글자가 있는 줄 찾기)
            if '금액' not in f_df.columns:
                for i in range(len(f_df)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]
                        f_df = f_df.iloc[i+1:].reset_index(drop=True)
                        break

            # 3. 금액 계산 (마이너스 기호를 제거하여 '비용'으로 변환)
            if '금액' in f_df.columns:
                # 콤마 제거 및 숫자로 강제 변환
                nums = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', '').str.strip(), errors='coerce').fillna(0)
                # 마이너스(-)로 적힌 지출을 플러스(+) 비용으로 변환 (보상비용은 따로 처리)
                # 이 로직은 전체의 절댓값을 합산하되, '보상' 단어가 있으면 뺍니다.
                total = 0
                for idx, row in f_df.iterrows():
                    val = pd.to_numeric(str(row['금액']).replace(',', ''), errors='coerce') or 0
                    if '보상' in str(row['항목']): # 보상비용은 수입이므로 뺌
                        total -= abs(val)
                    else:
                        total += abs(val)
                file_fixed_sum = total
                st.success(f"고정비 반영 완료: {file_fixed_sum:,.0f}원")
            else:
                st.error("'금액' 컬럼을 찾지 못했습니다.")
        except Exception as e:
            st.error(f"고정비 파일 에러: {e}")

    st.write("---")
    ad_direct = st.number_input("추가 지출 직접 입력", value=0)
    total_fixed_cost = file_fixed_sum + ad_direct
    st.metric("총 고정비", f"{total_fixed_cost:,.0f} 원")

# --- 메인: 이카운트 데이터 처리 (여기서 에러가 난다면 컬럼명 확인 필요) ---
main_file = st.file_uploader("이카운트 엑셀을 올려주세요", type=['xlsx', 'xls'])
if main_file is not None:
    try:
        m_df = pd.read_excel(main_file)
        # 이카운트 헤더 매핑
        m_df.rename(columns={'거래처명':'채널', '품목명':'상품명', '수량':'수량', '단가':'판매단가', '입고단가':'원가단가'}, inplace=True)
        
        # 매출 및 이익 계산
        m_df['매출액'] = m_df['수량'] * m_df['판매단가']
        m_df['원가'] = m_df['수량'] * m_df.get('원가단가', 0)
        # 수수료 10% 가정 (이사님 설정에 따라 수정 가능)
        m_df['이익'] = m_df['매출액'] - m_df['원가'] - (m_df['매출액'] * 0.1)
        
        total_sales = m_df['매출액'].sum()
        total_profit = m_df['이익'].sum()
        net_profit = total_profit - total_fixed_cost # 최종 계산
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("총 매출", f"{int(total_sales):,}원")
        c2.metric("총 고정비", f"-{int(total_fixed_cost):,}원")
        c3.metric("최종 순이익", f"{int(net_profit):,}원")
        st.divider()
        st.dataframe(m_df)
    except Exception as e:
        st.error(f"판매데이터 에러: {e}")
