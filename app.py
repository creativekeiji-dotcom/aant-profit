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

# ==========================================
# 1. 설정
# ==========================================
st.set_page_config(page_title="AANT 경영 리포트", layout="wide")

DEFAULT_FEE_RATES = {
    "쿠팡": 0.1188, "쿠팡 주식회사": 0.1188, "쿠팡그로스": 0.1188,
    "11번가": 0.143, "11번가 주식회사": 0.143, "십일번가": 0.143, "십일번가 주식회사": 0.143,
    "지마켓": 0.13, "주식회사 지마켓": 0.13, 
    "옥션": 0.13, "주식회사 옥션": 0.13,
    "네이버": 0.0563, "네이버파이낸셜": 0.0563, "스마트스토어": 0.0563,
    "오늘의집": 0.22, "버킷플레이스": 0.22,
    "카카오톡": 0.055, "알리": 0.11, "사업자거래": 0.0
}

# ==========================================
# 2. 수수료 로직
# ==========================================
def get_fee_rate(channel_name, user_fee_dict=None):
    raw_name = str(channel_name).strip()
    clean_name = raw_name.replace(" ", "")
    
    if user_fee_dict and raw_name in user_fee_dict: return user_fee_dict[raw_name]
    if raw_name in DEFAULT_FEE_RATES: return DEFAULT_FEE_RATES[raw_name]
    if clean_name in DEFAULT_FEE_RATES: return DEFAULT_FEE_RATES[clean_name]

    if "그로스" in clean_name: return 0.1188
    if "쿠팡" in clean_name: return 0.1188
    if "11번" in clean_name or "십일번" in clean_name: return 0.143
    if "지마켓" in clean_name or "G마켓" in clean_name.upper(): return 0.13
    if "옥션" in clean_name: return 0.13
    if "네이버" in clean_name or "스마트스토어" in clean_name: return 0.0563
    if "오늘의집" in clean_name or "버킷" in clean_name: return 0.22
    if "카카오" in clean_name: return 0.055
    if "알리" in clean_name: return 0.11
    
    return 0.0

# ==========================================
# 3. PPT 생성 함수 (화이트 테마 유지)
# ==========================================
def create_ppt(sales, gross, fixed_cost, net, margin, fig_pie, fig_bar, top10_df):
    prs = Presentation()
    
    # 표지
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "AANT 월간 경영 분석"
    slide.placeholders[1].text = f"기준일: {datetime.date.today().strftime('%Y-%m-%d')}"

    # 요약
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "1. 경영 실적 요약"
    tf = slide.shapes.placeholders[1].text_frame
    def add_line(text, size, bold=False):
        p = tf.add_paragraph()
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
    add_line(f"💰 총 매출: {int(sales):,}원", 24, True)
    add_line(f"📦 이익: {int(gross):,}원 ({gross/sales*100:.1f}%)", 20)
    add_line(f"💸 고정비: {int(fixed_cost):,}원", 20)
    add_line(f"🏆 순이익: {int(net):,}원 ({margin:.1f}%)", 28, True)

    # 그래프
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "2. 채널별 성과"
    try:
        # 강제 화이트 모드 적용 (배경 흰색, 글씨 검정)
        fig_pie.update_layout(
            template="plotly_white",
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="black")
        )

        fig_bar.update_layout(
            template="plotly_white",
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(color="black")
        )
        # 축 색상도 검정으로 명시
        fig_bar.update_xaxes(showline=True, linewidth=2, linecolor='black', gridcolor='lightgray')
        fig_bar.update_yaxes(showline=True, linewidth=2, linecolor='black', gridcolor='lightgray')

        img_pie = fig_pie.to_image(format="png", width=600, height=450, scale=2)
        img_bar = fig_bar.to_image(format="png", width=600, height=450, scale=2)
        
        slide.shapes.add_picture(io.BytesIO(img_pie), Inches(0.5), Inches(2), width=Inches(4.5))
        slide.shapes.add_picture(io.BytesIO(img_bar), Inches(5.2), Inches(2), width=Inches(4.5))
    except:
        slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1)).text = "그래프 생성 실패"

    # 랭킹 표
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "3. 효자 상품 TOP 10"
    if not top10_df.empty:
        df_t = top10_df.reset_index(drop=True)
        rows, cols = df_t.shape
        table = slide.shapes.add_table(rows+1, cols, Inches(0.5), Inches(1.5), Inches(9), Inches(5)).table
        
        for c in range(cols): table.cell(0, c).text = str(df_t.columns[c])
        for r in range(rows):
            for c in range(cols):
                val = df_t.iloc[r, c]
                table.cell(r+1, c).text = f"{int(val):,}" if isinstance(val, (int, float)) else str(val)
                table.cell(r+1, c).text_frame.paragraphs[0].font.size = Pt(10)

    out = io.BytesIO()
    prs.save(out)
    out.seek(0)
    return out

# ==========================================
# 4. 데이터 로딩
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

def load_data(files, user_fees):
    all_dfs = []
    for file in files:
        sheets = read_file_force(file)
        if sheets is None: continue
        for name, raw in sheets.items():
            try:
                if len(raw) < 2 or raw.shape[1] < 8: continue
                temp = raw.iloc[:, [0, 1, 3, 4, 5, 7]].copy()
                temp.columns = ['일자_raw', '채널', '상품명', '수량', '판매단가', '원가단가']
                temp = temp[temp['일자_raw'].astype(str).str.contains(r'\d', na=False)]
                if temp.empty: continue
                
                temp['상품명'] = temp['상품명'].fillna("상품명없음").astype(str)
                temp['채널'] = temp['채널'].fillna("기타").astype(str).str.strip()
                if '그로스' in str(name) or '그로스' in file.name: temp['채널'] = '쿠팡그로스'
                
                all_dfs.append(temp)
            except: continue
            
    if not all_dfs: return None
    df = pd.concat(all_dfs, ignore_index=True)
    
    df['일자'] = df['일자_raw'].apply(lambda x: safe_date_parse(x))
    df = df.dropna(subset=['일자'])
    df['월'] = df['일자'].dt.strftime('%Y-%m')
    for c in ['수량', '판매단가', '원가단가']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['총판매금액'] = df['수량'] * df['판매단가']
    df['총원가금액'] = df['수량'] * df['원가단가']
    
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
    fee_file = c3.file_uploader("3️⃣ 수수료 파일", key="f3")

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

            st.markdown("---")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 총 매출", f"{int(sales):,}원")
            k2.metric("📦 매출이익", f"{int(gross):,}원")
            k3.metric("💸 고정비", f"-{int(fixed_cost):,}원")
            k4.metric("🏆 순이익", f"{int(net):,}원", delta=f"{margin:.1f}%")
            st.markdown("---")

            t1, t2, t3 = st.tabs(["📊 리포트", "✅ 수수료 검증", "💾 다운로드 (PPT/Excel)"])
            
            # ------------------------------------------------------------------
            # [그래프 생성 구역]
            # ------------------------------------------------------------------
            ch_df = df.groupby('채널')[['총판매금액', '매출총이익']].sum().reset_index()
            ch_df['이익률'] = (ch_df['매출총이익'] / ch_df['총판매금액'] * 100).fillna(0)
            ch_df = ch_df.sort_values(by='총판매금액', ascending=False)
            
            # 1. 파이 차트
            fig_pie = px.pie(ch_df, values='총판매금액', names='채널', hole=0.4, title="매출 비중")
            fig_pie.update_traces(textinfo='percent+label', textposition='inside')

            # 2. 바 차트 (색상 입히기!!)
            # 채널 개수만큼 색상을 준비합니다. (Plotly 기본 팔레트 사용)
            colors = px.colors.qualitative.Plotly 
            # 데이터 개수에 맞춰서 색상을 리스트로 만듦 (순환 적용)
            bar_colors = [colors[i % len(colors)] for i in range(len(ch_df))]

            fig_bar = make_subplots(specs=[[{"secondary_y": True}]])
            
            # [핵심] marker_color에 색상 리스트를 넣어주면 알록달록해집니다.
            fig_bar.add_trace(go.Bar(
                x=ch_df['채널'], 
                y=ch_df['매출총이익'], 
                name="이익금",
                marker_color=bar_colors # <--- 여기가 마법의 코드입니다!
            ), secondary_y=False)
            
            fig_bar.add_trace(go.Scatter(x=ch_df['채널'], y=ch_df['이익률'], name="이익률(%)", line=dict(color='red')), secondary_y=True)

            # ------------------------------------------------------------------

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
