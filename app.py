import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import re
import datetime
import traceback
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN

# ==========================================
# 1. 설정
# ==========================================
st.set_page_config(page_title="AANT 경영 리포트", layout="wide")

# ==========================================
# 2. 핵심 로직: 수수료 키워드 매칭 (업그레이드)
# ==========================================
def get_fee_rate(channel_name, user_fee_dict=None):
    """
    채널명에 특정 단어가 포함되어 있으면 해당 수수료를 적용하는 똑똑한 함수
    """
    name = str(channel_name).replace(" ", "") # 공백 제거 후 비교
    
    # 1. 사용자가 업로드한 수수료 파일이 있으면 최우선 적용
    if user_fee_dict:
        # 사용자 파일은 정확한 매칭 우선
        if channel_name in user_fee_dict:
            return user_fee_dict[channel_name]
    
    # 2. 기본 키워드 매칭 (순서 중요: 구체적인 것부터)
    # 쿠팡
    if "그로스" in name: return 0.1188 # 로켓그로스
    if "쿠팡" in name: return 0.1188
    
    # 오픈마켓
    if "지마켓" in name or "G마켓" in name: return 0.143
    if "옥션" in name: return 0.143
    if "11번가" in name: return 0.143
    
    # 네이버
    if "네이버" in name or "스마트스토어" in name: return 0.06
    
    # 버티컬/기타
    if "오늘의집" in name or "버킷플레이스" in name: return 0.22
    if "카카오" in name: return 0.055
    if "알리" in name: return 0.11
    if "사업자" in name: return 0.0
    
    return 0.0 # 매칭 안 되면 0

# ==========================================
# 3. PPT 생성 함수 (안전성 강화)
# ==========================================
def create_ppt(sales, gross, fixed_cost, net, margin, fig_pie, fig_bar, top10_df):
    prs = Presentation()

    # [슬라이드 1] 표지
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "AANT 월간 경영 분석 보고서"
    slide.placeholders[1].text = f"기준일: {datetime.date.today().strftime('%Y-%m-%d')}\n작성: 경영지원팀"

    # [슬라이드 2] 경영 요약
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "1. 경영 실적 요약"
    tf = slide.shapes.placeholders[1].text_frame
    
    def add_line(text, size, bold=False, color=None):
        p = tf.add_paragraph()
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
        if color: p.font.color.rgb = color
        
    add_line(f"💰 총 매출액: {int(sales):,}원", 24, True)
    add_line(f"📦 매출이익: {int(gross):,}원 (이익률 {gross/sales*100:.1f}%)", 20)
    add_line(f"💸 고정비: {int(fixed_cost):,}원", 20)
    add_line(f"🏆 순이익: {int(net):,}원 (순이익률 {margin:.1f}%)", 28, True)

    # [슬라이드 3] 그래프
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "2. 채널별 성과 분석"
    try:
        img_pie = fig_pie.to_image(format="png", width=500, height=400, scale=2)
        img_bar = fig_bar.to_image(format="png", width=500, height=400, scale=2)
        slide.shapes.add_picture(io.BytesIO(img_pie), Inches(0.5), Inches(2), width=Inches(4.5))
        slide.shapes.add_picture(io.BytesIO(img_bar), Inches(5.2), Inches(2), width=Inches(4.5))
    except:
        slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1)).text = "그래프 생성 실패 (서버 설정 확인 필요)"

    # [슬라이드 4] TOP 10 (에러 수정된 부분)
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "3. 베스트 상품 TOP 10 (이익금 기준)"

    if not top10_df.empty:
        # 데이터프레임 구조 확정 (인덱스 리셋으로 안전하게)
        df_table = top10_df.reset_index(drop=True) 
        rows, cols = df_table.shape
        
        # 표 생성 (헤더 1줄 + 데이터 줄)
        table = slide.shapes.add_table(rows + 1, cols, Inches(0.5), Inches(1.5), Inches(9), Inches(5)).table
        
        # 1) 헤더 입력
        for col_idx, col_name in enumerate(df_table.columns):
            table.cell(0, col_idx).text = str(col_name)
            
        # 2) 데이터 입력 (iloc 사용으로 인덱스 에러 방지)
        for row_idx in range(rows):
            for col_idx in range(cols):
                val = df_table.iloc[row_idx, col_idx]
                
                # 숫자 포맷팅 (정수형으로 콤마)
                if isinstance(val, (int, float)):
                    table.cell(row_idx + 1, col_idx).text = f"{int(val):,}"
                else:
                    table.cell(row_idx + 1, col_idx).text = str(val)
                
                # 글자 크기
                table.cell(row_idx + 1, col_idx).text_frame.paragraphs[0].font.size = Pt(10)

    out = io.BytesIO()
    prs.save(out)
    out.seek(0)
    return out

# ==========================================
# 4. 데이터 로딩 (안전 모드)
# ==========================================
def safe_date_parse(val, target_year=2026):
    try:
        val_str = str(val).strip()
        match = re.search(r'(\d{1,2})/(\d{1,2})', val_str)
        if match:
            m, d = match.groups()
            return pd.to_datetime(f"{target_year}-{m}-{d}")
        return pd.to_datetime(val_str)
    except: return None

def read_file_force(file):
    try: return pd.read_excel(file, header=None, sheet_name=None)
    except: pass
    try: file.seek(0); return {'Sheet1': pd.read_csv(file, header=None, encoding='cp949')}
    except: pass
    try: file.seek(0); return {'Sheet1': pd.read_csv(file, header=None, encoding='utf-8')}
    except: return None

def load_data(files, user_fees=None):
    all_dfs = []
    for file in files:
        sheets = read_file_force(file)
        if sheets is None: continue
        
        for name, raw in sheets.items():
            try:
                if len(raw) < 2 or raw.shape[1] < 8: continue
                # 2단 헤더 무시하고 위치로 추출
                temp = raw.iloc[:, [0, 1, 3, 4, 5, 7]].copy()
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                
                # 날짜 있는 행만 살림
                temp = temp[temp['일자_raw'].astype(str).str.contains(r'\d', na=False)]
                if temp.empty: continue

                temp['상품명'] = temp['상품명'].fillna("상품명없음").astype(str)
                temp['채널'] = temp['채널'].fillna("기타").astype(str).str.strip()
                
                # 그로스 탭 처리
                if '그로스' in str(name) or '그로스' in file.name:
                    temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
            except: continue
            
    if not all_dfs: return None
    
    df = pd.concat(all_dfs, ignore_index=True)
    
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자'])
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    
    for c in ['수량', '판매단가', '원가단가']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    
    # [수수료 적용] 여기서 '키워드 매칭 함수'를 사용합니다
    df['수수료율'] = df['채널'].apply(lambda x: get_fee_rate(x, user_fees))
    
    df['수수료금액'] = df['총판매금액'] * df['수수료율']
    df['매출총이익'] = df['총판매금액'] - df['총원가금액'] - df['수수료금액']
    
    return df

# ==========================================
# 5. 메인 화면
# ==========================================
st.title("📊 AANT CEO 경영 대시보드")

with st.expander("📂 데이터 파일 관리", expanded=True):
    c1, c2, c3 = st.columns(3)
    up_files = c1.file_uploader("1️⃣ 판매 파일", accept_multiple_files=True, key="f1")
    cost_file = c2.file_uploader("2️⃣ 고정비 파일", key="f2")
    fee_file = c3.file_uploader("3️⃣ 수수료 파일 (필요시)", key="f3")

user_fee_rates = {}
if fee_file:
    try:
        sheets = read_file_force(fee_file)
        if sheets:
            fdf = list(sheets.values())[0]
            user_fee_rates = dict(zip(fdf.iloc[:, 0], fdf.iloc[:, 1]))
    except: pass

if up_files:
    try:
        df = load_data(up_files, user_fee_rates)
        
        if df is not None and not df.empty:
            sales = df['총판매금액'].sum()
            gross = df['매출총이익'].sum()
            fixed_cost = 0
            if cost_file:
                try:
                    sheets = read_file_force(cost_file)
                    if sheets:
                        cdf = list(sheets.values())[0]
                        fixed_cost = cdf.select_dtypes(include=['number']).sum().sum()
                except: pass
            net = gross - fixed_cost
            margin = (net / sales * 100) if sales > 0 else 0

            # --- 대시보드 ---
            st.markdown("---")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 총 매출", f"{int(sales):,}원")
            k2.metric("📦 매출이익", f"{int(gross):,}원")
            k3.metric("💸 고정비", f"-{int(fixed_cost):,}원")
            k4.metric("🏆 순이익", f"{int(net):,}원", delta=f"{margin:.1f}%")
            st.markdown("---")

            t1, t2, t3 = st.tabs(["📊 리포트", "✅ 수수료 검증", "💾 다운로드"])
            
            # 그래프
            ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
            ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
            ch_df = ch_df.sort_values(by='총판매금액', ascending=False)
            
            fig_pie = px.pie(ch_df, values='총판매금액', names='채널', hole=0.4, title="매출 비중")
            fig_bar = make_subplots(specs=[[{"secondary_y": True}]])
            fig_bar.add_trace(go.Bar(x=ch_df['채널'], y=ch_df['매출총이익'], name="이익금"), secondary_y=False)
            fig_bar.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red')), secondary_y=True)

            pr_df = df.groupby('상품명')[['수량', '총판매금액', '매출총이익']].sum().reset_index()
            pr_df = pr_df[pr_df['상품명'] != "상품명없음"]
            top10 = pd.DataFrame()
            if not pr_df.empty:
                top10 = pr_df.sort_values(by='매출총이익', ascending=False).head(10)
                top10.index = range(1, len(top10)+1)

            with t1:
                c1, c2 = st.columns([1, 2])
                with c1: st.plotly_chart(fig_pie, use_container_width=True)
                with c2: st.plotly_chart(fig_bar, use_container_width=True)
                st.divider()
                st.subheader("TOP 10 효자 상품")
                if not top10.empty:
                     st.dataframe(top10.style.format({'수량':'{:,.0f}','총판매금액':'{:,.0f}','매출총이익':'{:,.0f}'}), use_container_width=True)

            with t2:
                st.subheader("🔍 수수료율 검증")
                check_df = df.groupby('채널')[['총판매금액', '수수료금액']].sum().reset_index()
                check_df['실제적용률(%)'] = (check_df['수수료금액'] / check_df['총판매금액'] * 100).round(2)
                st.dataframe(check_df.style.format({'총판매금액':'{:,.0f}', '수수료금액':'{:,.0f}'}), use_container_width=True)

            with t3:
                st.subheader("📥 다운로드")
                
                # Excel
                buf_ex = io.BytesIO()
                with pd.ExcelWriter(buf_ex, engine='openpyxl') as writer:
                    pd.DataFrame({'구분':['매출','이익','순이익'], '금액':[sales,gross,net]}).to_excel(writer, sheet_name='요약')
                    ch_df.to_excel(writer, sheet_name='채널', index=False)
                    if not top10.empty: top10.to_excel(writer, sheet_name='랭킹', index=False)
                    df.to_excel(writer, sheet_name='전체데이터', index=False)
                
                today = datetime.date.today().strftime("%Y%m%d")
                c_d1, c_d2 = st.columns(2)
                c_d1.download_button("📥 엑셀(Excel) 받기", buf_ex.getvalue(), f"AANT_Report_{today}.xlsx")

                # PPT
                if not top10.empty:
                    top10_clean = top10[['상품명','수량','총판매금액','매출총이익']]
                else:
                    top10_clean = pd.DataFrame()

                ppt = create_ppt(sales, gross, fixed_cost, net, margin, fig_pie, fig_bar, top10_clean)
                c_d2.download_button("📥 피피티(PPT) 받기", ppt.getvalue(), f"AANT_Report_{today}.pptx")
                st.caption("※ 그래프가 안 나오면 'requirements.txt'에 'kaleido'가 있는지 확인해주세요.")

        else: st.error("❌ 데이터를 읽을 수 없습니다.")
    except Exception as e:
        st.error("⚠️ 시스템 오류 발생")
        st.code(traceback.format_exc())
