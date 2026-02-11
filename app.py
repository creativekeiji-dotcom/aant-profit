import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 판매 분석 대시보드")

# --- 사이드바: 고정비 처리 ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일을 올려주세요", type=['csv', 'xlsx'])
    
    file_fixed_sum = 0
    if fixed_file is not None:
        try:
            if fixed_file.name.endswith('.csv'):
                try: f_df = pd.read_csv(fixed_file, encoding='utf-8-sig')
                except: f_df = pd.read_csv(fixed_file, encoding='cp949')
            else: f_df = pd.read_excel(fixed_file)

            # 제목줄 자동 찾기
            if '금액' not in f_df.columns:
                for i in range(min(len(f_df), 10)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]
                        f_df = f_df.iloc[i+1:].reset_index(drop=True)
                        break

            if '금액' in f_df.columns:
                total = 0
                for _, row in f_df.iterrows():
                    val = pd.to_numeric(str(row['금액']).replace(',', '').strip(), errors='coerce') or 0
                    if '보상' in str(row.get('항목', '')): total -= abs(val)
                    else: total += abs(val)
                file_fixed_sum = total
                st.success(f"고정비 반영: {file_fixed_sum:,.0f}원")
        except: st.error("고정비 파일 형식을 확인해주세요.")

    st.write("---")
    ad_input = st.number_input("기타 지출 직접입력", value=0)
    total_fixed_cost = file_fixed_sum + ad_input
    st.metric("총 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# --- 메인: 판매 데이터 처리 (강력한 컬럼 찾기 기능 추가) ---
main_file = st.file_uploader("이카운트 판매내역 엑셀을 올려주세요", type=['xlsx', 'xls'])

if main_file is not None:
    try:
        df = pd.read_excel(main_file)
        
        # [핵심] 컬럼명 전처리 (양끝 공백 제거)
        df.columns = [str(c).strip() for c in df.columns]

        # 자동 컬럼 매핑 (이름이 조금 달라도 찾아냄)
        mapping = {}
        for c in df.columns:
            if '거래처' in c or '채널' in c: mapping[c] = '채널'
            elif '품목' in c or '상품' in c: mapping[c] = '상품명'
            elif '수량' in c: mapping[c] = '수량'
            elif '단가' in c and '입고' not in c and '원가' not in c: mapping[c] = '판매단가'
            elif '입고단가' in c or '원가' in c: mapping[c] = '원가단가'
            elif '일자' in c: mapping[c] = '일자'
        
        df.rename(columns=mapping, inplace=True)

        # 필수 컬럼 존재 확인
        required = ['수량', '판매단가']
        missing = [r for r in required if r not in df.columns]

        if not missing:
            # 숫자 변환
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            df['판매단가'] = pd.to_numeric(df['판매단가'], errors='coerce').fillna(0)
            df['원가단가'] = pd.to_numeric(df.get('원가단가', 0), errors='coerce').fillna(0)

            df['매출액'] = df['수량'] * df['판매단가']
            df['이익'] = df['매출액'] - (df['수량'] * df['원가단가']) - (df['매출액'] * 0.1) # 수수료 10% 가정

            ts, gp = df['매출액'].sum(), df['이익'].sum()
            np = gp - total_fixed_cost

            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 총 매출", f"{int(ts):,}원")
            c2.metric("📦 상품 마진", f"{int(gp):,}원")
            c3.metric("💸 총 고정비", f"-{int(total_fixed_cost):,}원")
            c4.metric("🏆 최종 순이익", f"{int(np):,}원", delta=f"{(np/ts*100):.1f}%" if ts>0 else None)
            st.divider()
            
            st.subheader("📊 채널별 매출 비중")
            fig = px.pie(df, values='매출액', names='채널')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df[['일자', '채널', '상품명', '수량', '판매단가', '매출액']])
        else:
            st.error(f"엑셀에서 다음 항목을 찾을 수 없습니다: {', '.join(missing)}")
            st.info("엑셀 제목에 '수량', '단가'라는 글자가 포함되어 있는지 확인해주세요.")

    except Exception as e:
        st.error(f"데이터 처리 에러: {e}")
