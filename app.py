import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="AANT 월간 결산", layout="wide")
st.title("📊 AANT(안트) 판매 분석 대시보드")

# --- 1. 사이드바: 고정비 설정 ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일을 올려주세요", type=['csv', 'xlsx'])
    file_fixed_sum = 0
    if fixed_file is not None:
        try:
            f_df = pd.read_csv(fixed_file, encoding='utf-8-sig') if fixed_file.name.endswith('.csv') else pd.read_excel(fixed_file)
            if '금액' not in f_df.columns:
                for i in range(len(f_df)):
                    if '금액' in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]; f_df = f_df.iloc[i+1:].reset_index(drop=True); break
            if '금액' in f_df.columns:
                f_df['amt'] = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', '').str.strip(), errors='coerce').fillna(0)
                total = 0
                for _, row in f_df.iterrows():
                    v = abs(row['amt'])
                    if '보상' in str(row.values): total -= v
                    else: total += v
                file_fixed_sum = total
                st.success(f"고정비 반영: {file_fixed_sum:,.0f}원")
        except: st.error("고정비 파일을 확인해주세요.")
    st.write("---")
    total_fixed_cost = file_fixed_sum + st.number_input("기타 직접입력", value=0)
    st.metric("총 고정비 합계", f"{total_fixed_cost:,.0f} 원")

# --- 2. 메인: 판매 데이터 처리 (중복 합계 필터링 추가) ---
main_file = st.file_uploader("이카운트 매출 엑셀을 올려주세요", type=['xlsx', 'xls', 'csv'])

if main_file is not None:
    try:
        raw = pd.read_excel(main_file) if not main_file.name.endswith('.csv') else pd.read_csv(main_file)
        
        h_idx = -1
        for i in range(len(raw)):
            if '거래처명' in [str(v) for v in raw.iloc[i].values]:
                h_idx = i; break
        
        if h_idx != -1:
            h1 = raw.iloc[h_idx].values.tolist()
            h2 = raw.iloc[h_idx + 1].values.tolist()
            h1_filled = []
            curr = ""
            for v in h1:
                if pd.notna(v) and str(v).strip() != "": curr = str(v).strip()
                h1_filled.append(curr)
            
            new_cols = []
            for p1, p2 in zip(h1_filled, h2):
                p1, p2 = str(p1).strip(), str(p2).strip() if pd.notna(p2) else ""
                new_cols.append(f"{p1}_{p2}" if p1 and p2 else (p1 or p2 or "Unnamed"))
            
            df = raw.iloc[h_idx + 2:].copy()
            df.columns = new_cols
            
            # [수정] '계'나 '합계'가 들어간 중복 행 제거 (범인 검거!)
            df = df[~df.iloc[:, 0].astype(str).str.contains('계|합계', na=False)]
            df = df[~df.iloc[:, 1].astype(str).str.contains('계|합계', na=False)]
            
            col_map = {}
            for c in df.columns:
                if '거래처명' in c: col_map[c] = '채널'
                elif '품목명' in c: col_map[c] = '상품명'
                elif '판매_수량' in c: col_map[c] = '수량'
                elif '판매_금액' in c: col_map[c] = '매출액'
                elif '원가_금액' in c: col_map[c] = '매입원가'
                elif '일자' in c: col_map[c] = '일자'
            
            df.rename(columns=col_map, inplace=True)
            
            for col in ['수량', '매출액', '매입원가']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
            if '매출액' in df.columns:
                ts = df['매출액'].sum()
                # 매입원가가 0이면 이익을 0으로 잡지 않도록 수정
                cost_sum = df['매입원가'].sum()
                gp = ts - cost_sum - (ts * 0.1) # 수수료 10% 가정
                np = gp - total_fixed_cost
                
                # 순이익률 계산
                net_margin = (np / ts * 100) if ts > 0 else 0
                
                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("💰 실 매출액", f"{int(ts):,}원")
                c2.metric("📦 상품 마진", f"{int(gp):,}원")
                c3.metric("💸 총 고정비", f"-{int(total_fixed_cost):,}원")
                c4.metric("🏆 최종 순이익", f"{int(np):,}원", delta=f"{net_margin:.1f}%", delta_color="normal")
                st.divider()
                
                st.plotly_chart(px.pie(df, values='매출액', names='채널', title='채널별 매출 비중'))
                st.dataframe(df[['일자', '채널', '상품명', '수량', '매출액']])
            else: st.error("파일에서 '판매_금액' 항목을 찾을 수 없습니다.")
        else: st.error("엑셀 양식을 인식할 수 없습니다.")
    except Exception as e: st.error(f"에러 발생: {e}")
