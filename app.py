import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 판매 분석 대시보드")

# --- 1. 사이드바: 고정비 처리 (이사님 파일 맞춤형) ---
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
            
            # '금액' 컬럼 찾기
            target_col = [c for c in f_df.columns if '금액' in str(c)]
            if not target_col:
                for i in range(len(f_df)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]; f_df = f_df.iloc[i+1:].reset_index(drop=True)
                        target_col = ['금액']; break
            
            if target_col:
                f_df['amt'] = pd.to_numeric(f_df[target_col[0]].astype(str).str.replace(',', '').str.strip(), errors='coerce').fillna(0)
                # 보상은 빼고 지출은 더함
                total = 0
                for _, row in f_df.iterrows():
                    v = abs(row['amt'])
                    if '보상' in str(row.values): total -= v
                    else: total += v
                file_fixed_sum = total
                st.success(f"고정비 반영: {file_fixed_sum:,.0f}원")
        except: st.error("고정비 파일 형식을 확인해주세요.")
    
    st.write("---")
    etc_val = st.number_input("기타 지출 직접입력", value=0)
    total_fixed_cost = file_fixed_sum + etc_val
    st.metric("총 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# --- 2. 메인: 판매 데이터 처리 (이중 헤더 완벽 대응) ---
main_file = st.file_uploader("이카운트 판매내역 엑셀을 올려주세요", type=['xlsx', 'xls', 'csv'])

if main_file is not None:
    try:
        # 이카운트 특성상 상단 빈 행 무시하고 데이터만 추출
        df_raw = pd.read_excel(main_file) if not main_file.name.endswith('.csv') else pd.read_csv(main_file)
        
        # '거래처명'이 있는 행을 찾아서 제목줄로 설정
        header_idx = -1
        for i in range(len(df_raw)):
            if '거래처명' in [str(v) for v in df_raw.iloc[i].values]:
                header_idx = i
                break
        
        if header_idx != -1:
            # 제목줄과 바로 아래 수량/단가 줄을 합침
            headers = df_raw.iloc[header_idx].fillna('').astype(str).values
            sub_headers = df_raw.iloc[header_idx + 1].fillna('').astype(str).values
            
            new_cols = []
            for h, s in zip(headers, sub_headers):
                combined = (h + "_" + s).strip("_")
                new_cols.append(combined)
            
            df = df_raw.iloc[header_idx + 2:].copy()
            df.columns = new_cols
            df.reset_index(drop=True, inplace=True)
            
            # 이사님 파일 전용 컬럼 찾기 로직
            col_map = {}
            for c in df.columns:
                if '거래처명' in c: col_map[c] = '채널'
                elif '품목명' in c: col_map[c] = '상품명'
                elif '판매_수량' in c or ('판매' in c and '수량' in c): col_map[c] = '수량'
                elif '판매_금액' in c or ('판매' in c and '금액' in c): col_map[c] = '매출액'
                elif '원가_금액' in c or ('원가' in c and '금액' in c): col_map[c] = '매입원가'
                elif '일자' in c: col_map[c] = '일자'
            
            df.rename(columns=col_map, inplace=True)
            
            # 숫자 변환
            for col in ['수량', '매출액', '매입원가']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            if '매출액' in df.columns:
                ts = df['매출액'].sum()
                cost = df['매입원가'].sum() if '매입원가' in df.columns else 0
                gp = ts - cost - (ts * 0.1) # 수수료 10% 가정
                np = gp - total_fixed_cost
                
                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("💰 총 매출", f"{int(ts):,}원")
                c2.metric("📦 상품 마진(GP)", f"{int(gp):,}원")
                c3.metric("💸 총 고정비", f"-{int(total_fixed_cost):,}원")
                c4.metric("🏆 최종 순이익(NP)", f"{int(np):,}원", delta=f"{(np/ts*100):.1f}%" if ts>0 else None)
                st.divider()
                
                # 채널별 비중 그래프
                if '채널' in df.columns:
                    fig = px.pie(df, values='매출액', names='채널', title='채널별 매출 비중')
                    st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📋 분석 데이터 미리보기")
                st.dataframe(df)
            else:
                st.error("파일에서 '판매 금액' 데이터를 찾을 수 없습니다.")
        else:
            st.error("이카운트 양식의 '거래처명' 제목줄을 찾을 수 없습니다.")
            
    except Exception as e:
        st.error(f"데이터 처리 에러: {e}")
