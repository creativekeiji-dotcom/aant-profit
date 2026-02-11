import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 판매 분석 대시보드")

# --- 1. 사이드바: 고정비 처리 (기존 로직 유지) ---
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
            if '금액' not in f_df.columns:
                for i in range(min(len(f_df), 10)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]; f_df = f_df.iloc[i+1:].reset_index(drop=True); break
            if '금액' in f_df.columns:
                f_df['금액_숫자'] = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                file_fixed_sum = f_df['금액_숫자'].sum()
                st.success(f"고정비 반영: {file_fixed_sum:,.0f}원")
        except: st.error("고정비 파일 형식을 확인해주세요.")
    st.write("---")
    total_fixed_cost = file_fixed_sum + st.number_input("기타 지출 직접입력", value=0)
    st.metric("총 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# --- 2. 메인: 판매 데이터 처리 (이사님 파일 맞춤형) ---
main_file = st.file_uploader("이카운트 판매내역 엑셀을 올려주세요", type=['xlsx', 'xls', 'csv'])

if main_file is not None:
    try:
        # 파일 읽기 (이사님 파일 특성상 2번째 줄부터 제목일 확률이 높음)
        if main_file.name.endswith('.csv'):
            try: df = pd.read_csv(main_file, encoding='utf-8-sig')
            except: df = pd.read_csv(main_file, encoding='cp949')
        else:
            df = pd.read_excel(main_file)

        # [중요] 이사님 파일에서 제목 줄 강제로 찾기
        # '수량'이나 '금액'이 포함된 행을 찾아서 헤더로 지정
        if not ('수량' in df.columns or '금액' in df.columns):
            for i in range(min(len(df), 10)):
                row_values = [str(v) for v in df.iloc[i].values]
                if any('수량' in v or '금액' in v for v in row_values):
                    df.columns = df.iloc[i]
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break

        # 컬럼명 공백 제거
        df.columns = [str(c).strip() for c in df.columns]

        # 이사님 파일에 존재하는 실제 컬럼명 매핑
        col_map = {}
        for c in df.columns:
            if '거래처' in c or '채널' in c: col_map[c] = '채널'
            elif '수량' in c: col_map[c] = '수량'
            elif '금액' in c and '판매' in c: col_map[c] = '매출액'
            elif '금액' in c and ('매입' in c or '원가' in c): col_map[c] = '매입원가'
            elif '이익' in c: col_map[c] = '매출이익'
            elif '품목' in c or '상품' in c: col_map[c] = '상품명'

        df.rename(columns=col_map, inplace=True)

        # 필수 데이터가 숫자형인지 확인 및 변환
        for target in ['수량', '매출액', '매출이익']:
            if target in df.columns:
                df[target] = pd.to_numeric(df[target].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

        if '매출액' in df.columns:
            ts = df['매출액'].sum()
            # 이사님 파일에 '매출이익'이 이미 계산되어 있다면 그것을 사용
            gp = df['매출이익'].sum() if '매출이익' in df.columns else (ts * 0.3) # 없으면 30% 가정
            np = gp - total_fixed_cost

            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 총 매출", f"{int(ts):,}원")
            c2.metric("📦 상품 마진(GP)", f"{int(gp):,}원")
            c3.metric("💸 총 고정비", f"-{int(total_fixed_cost):,}원")
            c4.metric("🏆 최종 순이익(NP)", f"{int(np):,}원", delta=f"{(np/ts*100):.1f}%" if ts>0 else None)
            st.divider()
            
            # 시각화
            if '채널' in df.columns:
                fig = px.pie(df, values='매출액', names='채널', title='채널별 매출 비중')
                st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("📋 분석 데이터 미리보기")
            st.dataframe(df)
        else:
            st.error("파일에서 '금액' 또는 '매출' 관련 컬럼을 찾을 수 없습니다. 엑셀 제목을 확인해주세요.")

    except Exception as e:
        st.error(f"데이터 처리 에러: {e}")
