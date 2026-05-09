import os
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

# =========================================================
# 온라인 월간 리포트 - 단순 안정형 / 디자인 개선 버전
# 기능 추가 없음: 단일 월 매출 엑셀 + 고정비 + KPI + 표 + 그래프 + PDF
# =========================================================

FEE_RATES = {
    "쿠팡그로스": 0.1188,
    "쿠팡": 0.1188,
    "네이버파이낸셜": 0.06,
    "네이버": 0.06,
    "안트": 0.0,
    "옥션": 0.143,
    "지마켓": 0.143,
    "11번가": 0.143,
    "십일번가": 0.143,
    "오늘의집": 0.22,
    "버킷플레이스": 0.22,
    "카카오톡": 0.055,
    "AliExpress": 0.11,
    "알리": 0.11,
    "사업자거래": 0.0,
    "온라인 소비자": 0.0,
}

COLOR_MAP = {
    "매출액": "#2563EB",
    "상품마진": "#16A34A",
    "고정비": "#F97316",
    "순이익": "#7C3AED",
}

st.set_page_config(page_title="온라인 월간 리포트", layout="wide")

st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem; max-width: 1280px; }
    .report-title { font-size: 34px; font-weight: 850; color: #0f172a; margin-bottom: 4px; }
    .report-subtitle { color: #64748b; font-size: 15px; margin-bottom: 22px; }
    div[data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #e5e7eb; padding: 18px;
        border-radius: 16px; box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
    }
    div[data-testid="stMetricLabel"] { font-size: 0.9rem; color: #64748b; }
    div[data-testid="stMetricValue"] { font-size: 1.65rem; font-weight: 850; color: #0f172a; }
    .section-label { font-size: 20px; font-weight: 800; color: #111827; margin-top: 24px; margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="report-title">온라인 월간 리포트</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="report-subtitle">매출, 상품마진, 고정비, 순이익, 채널별 비중, TOP10 상품을 한 화면에서 정리합니다.</div>',
    unsafe_allow_html=True,
)


def clean_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce",
    ).fillna(0)


def format_won(value: float) -> str:
    return f"{int(round(value)):,.0f}원"


def short_text(value, max_len: int = 30) -> str:
    text = str(value)
    return text if len(text) <= max_len else text[:max_len] + "..."


def get_fee_rate(channel: str) -> float:
    text = str(channel)
    for key, rate in FEE_RATES.items():
        if key in text:
            return rate
    return 0.10


def read_any_file(uploaded_file, header=None):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, header=header, encoding="utf-8-sig")
    return pd.read_excel(uploaded_file, header=header)


def calculate_fixed_cost(fixed_file, manual_cost: float) -> float:
    file_fixed_sum = 0

    if fixed_file is not None:
        try:
            f_df = read_any_file(fixed_file, header=0)

            if "금액" not in [str(c).strip() for c in f_df.columns]:
                raw = read_any_file(fixed_file, header=None)
                for i in range(len(raw)):
                    row_values = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[i].values]
                    if "금액" in row_values:
                        f_df = raw.iloc[i + 1 :].copy()
                        f_df.columns = [str(x).strip() for x in raw.iloc[i].values]
                        break

            amount_col = None
            for col in f_df.columns:
                if "금액" in str(col):
                    amount_col = col
                    break

            if amount_col is None:
                st.sidebar.error("고정비 파일에서 '금액' 컬럼을 찾지 못했습니다.")
                return manual_cost

            f_df["amt"] = clean_number(f_df[amount_col])

            total = 0
            for _, row in f_df.iterrows():
                value = abs(row["amt"])
                row_text = " ".join([str(x) for x in row.values])
                if any(word in row_text for word in ["보상", "환급", "환불", "취소"]):
                    total -= value
                else:
                    total += value

            file_fixed_sum = total
            st.sidebar.success(f"고정비 파일 반영: {format_won(file_fixed_sum)}")

        except Exception as e:
            st.sidebar.error(f"고정비 파일 확인 중 오류: {e}")

    return file_fixed_sum + manual_cost


def parse_sales_file(main_file) -> pd.DataFrame:
    raw = read_any_file(main_file, header=None)

    h_idx = -1
    for i in range(len(raw)):
        row_values = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[i].values]
        if "거래처명" in row_values:
            h_idx = i
            break

    if h_idx == -1:
        raise ValueError("엑셀에서 헤더 행의 '거래처명'을 찾지 못했습니다.")

    h1 = raw.iloc[h_idx].values.tolist()
    h2 = raw.iloc[h_idx + 1].values.tolist()

    h1_filled = []
    current = ""
    for value in h1:
        if pd.notna(value) and str(value).strip() != "":
            current = str(value).strip()
        h1_filled.append(current)

    new_cols = []
    for p1, p2 in zip(h1_filled, h2):
        p1 = str(p1).strip() if pd.notna(p1) else ""
        p2 = str(p2).strip() if pd.notna(p2) else ""
        if p1 and p2:
            new_cols.append(f"{p1}_{p2}")
        elif p1:
            new_cols.append(p1)
        elif p2:
            new_cols.append(p2)
        else:
            new_cols.append("Unnamed")

    df = raw.iloc[h_idx + 2 :].copy()
    df.columns = new_cols
    df = df[~df.iloc[:, 0].astype(str).str.contains("계|합계", na=False)]

    col_map = {
        "거래처명": "채널",
        "품목명": "상품명",
        "판매_수량": "수량",
        "판매_금액": "매출액",
        "원가_금액": "매입원가",
    }

    rename_map = {}
    for col in df.columns:
        col_text = str(col)
        for key, new_name in col_map.items():
            if key in col_text:
                rename_map[col] = new_name
                break
    df.rename(columns=rename_map, inplace=True)

    required_cols = ["채널", "상품명", "수량", "매출액", "매입원가"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"필수 컬럼이 없습니다: {missing_cols}")

    df = df[required_cols].copy()
    df["채널"] = df["채널"].fillna("").astype(str).str.strip()
    df["상품명"] = df["상품명"].fillna("").astype(str).str.strip()

    for col in ["수량", "매출액", "매입원가"]:
        df[col] = clean_number(df[col])

    df = df[(df["매출액"] != 0) | (df["수량"] != 0)].copy()

    df["수수료율"] = df["채널"].apply(get_fee_rate)
    df["수수료"] = df["매출액"] * df["수수료율"]
    df["이익액"] = df["매출액"] - df["매입원가"] - df["수수료"]
    df["마진율(%)"] = (df["이익액"] / df["매출액"].replace(0, pd.NA) * 100).fillna(0)
    return df


def build_channel_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("채널", as_index=False)
        .agg(매출액=("매출액", "sum"), 이익액=("이익액", "sum"), 수량=("수량", "sum"))
        .sort_values("매출액", ascending=False)
    )
    summary["마진율(%)"] = (summary["이익액"] / summary["매출액"].replace(0, pd.NA) * 100).fillna(0)
    summary["매출비중(%)"] = (summary["매출액"] / summary["매출액"].sum() * 100).fillna(0)
    return summary


def build_top10(df: pd.DataFrame) -> pd.DataFrame:
    top10 = (
        df.groupby("상품명", as_index=False)
        .agg(매출액=("매출액", "sum"), 이익액=("이익액", "sum"), 수량=("수량", "sum"))
        .sort_values("매출액", ascending=False)
        .head(10)
    )
    top10["마진율(%)"] = (top10["이익액"] / top10["매출액"].replace(0, pd.NA) * 100).fillna(0)
    top10["매출비중(%)"] = (top10["매출액"] / df["매출액"].sum() * 100).fillna(0)
    return top10


class ReportPDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 22, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Nanum", "", 16)
        self.cell(0, 14, "온라인 월간 리포트", ln=True, align="C")
        self.ln(6)

    def footer(self):
        self.set_y(-12)
        self.set_font("Nanum", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")


def make_pdf(ts, gp, total_fixed_cost, net_profit, net_margin, channel_summary, top10) -> bytes:
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        raise RuntimeError("PDF 생성을 위해 NanumGothic.ttf 파일이 GitHub 루트에 필요합니다.")

    pdf = ReportPDF()
    pdf.add_font("Nanum", "", font_path)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Nanum", "", 13)
    pdf.cell(0, 8, "Executive Summary", ln=True)
    pdf.ln(2)

    kpis = [
        ("총 매출액", format_won(ts), (37, 99, 235)),
        ("상품 마진", format_won(gp), (22, 163, 74)),
        ("총 고정비", format_won(total_fixed_cost), (249, 115, 22)),
        ("최종 순이익", format_won(net_profit), (124, 58, 237)),
    ]

    x0 = 10
    y0 = pdf.get_y()
    box_w = 46
    box_h = 24
    gap = 2.5

    for i, (label, value, color) in enumerate(kpis):
        x = x0 + i * (box_w + gap)
        pdf.set_xy(x, y0)
        pdf.set_fill_color(*color)
        pdf.rect(x, y0, box_w, box_h, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Nanum", "", 8)
        pdf.set_xy(x + 3, y0 + 4)
        pdf.cell(box_w - 6, 5, label, ln=True)
        pdf.set_font("Nanum", "", 11)
        pdf.set_xy(x + 3, y0 + 12)
        pdf.cell(box_w - 6, 6, value, ln=True)

    pdf.set_y(y0 + box_h + 8)
    pdf.set_text_color(80, 80, 80)
    pdf.set_font("Nanum", "", 10)
    pdf.cell(0, 7, f"순이익률: {net_margin:.1f}% / 상품마진율: {(gp / ts * 100) if ts else 0:.1f}%", ln=True)

    pdf.ln(6)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Nanum", "", 13)
    pdf.cell(0, 8, "채널별 매출 요약", ln=True)

    pdf.set_font("Nanum", "", 8.5)
    pdf.set_fill_color(241, 245, 249)
    headers = [("채널", 44), ("매출액", 38), ("이익액", 38), ("수량", 24), ("마진율", 22), ("비중", 22)]
    for h, w in headers:
        pdf.cell(w, 8, h, border=1, align="C", fill=True)
    pdf.ln()

    for idx, row in channel_summary.iterrows():
        fill = idx % 2 == 0
        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(44, 8, short_text(row["채널"], 13), border=1, fill=fill)
        pdf.cell(38, 8, f"{int(row['매출액']):,}", border=1, align="R", fill=fill)
        pdf.cell(38, 8, f"{int(row['이익액']):,}", border=1, align="R", fill=fill)
        pdf.cell(24, 8, f"{int(row['수량']):,}", border=1, align="R", fill=fill)
        pdf.cell(22, 8, f"{row['마진율(%)']:.1f}%", border=1, align="R", fill=fill)
        pdf.cell(22, 8, f"{row['매출비중(%)']:.1f}%", border=1, ln=True, align="R", fill=fill)

    pdf.ln(6)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Nanum", "", 13)
    pdf.cell(0, 8, "TOP 10 판매 상품", ln=True)

    pdf.set_font("Nanum", "", 8.2)
    pdf.set_fill_color(241, 245, 249)
    headers = [("순위", 14), ("상품명", 78), ("매출액", 34), ("이익액", 34), ("수량", 18), ("마진", 16)]
    for h, w in headers:
        pdf.cell(w, 8, h, border=1, align="C", fill=True)
    pdf.ln()

    for idx, row in top10.reset_index(drop=True).iterrows():
        fill = idx % 2 == 0
        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(14, 8, str(idx + 1), border=1, align="C", fill=fill)
        pdf.cell(78, 8, short_text(row["상품명"], 28), border=1, fill=fill)
        pdf.cell(34, 8, f"{int(row['매출액']):,}", border=1, align="R", fill=fill)
        pdf.cell(34, 8, f"{int(row['이익액']):,}", border=1, align="R", fill=fill)
        pdf.cell(18, 8, f"{int(row['수량']):,}", border=1, align="R", fill=fill)
        pdf.cell(16, 8, f"{row['마진율(%)']:.1f}%", border=1, ln=True, align="R", fill=fill)

    pdf_output_raw = pdf.output(dest="S")
    if isinstance(pdf_output_raw, bytearray):
        return bytes(pdf_output_raw)
    if isinstance(pdf_output_raw, bytes):
        return pdf_output_raw
    return pdf_output_raw.encode("latin-1")


with st.sidebar:
    st.header("① 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일 업로드", type=["csv", "xlsx", "xls"])
    manual_fixed_cost = st.number_input("기타 고정비 직접입력", min_value=0, value=0, step=10000)
    st.divider()
    st.header("② 매출 파일")
    main_file = st.file_uploader("이카운트 매출 엑셀 업로드", type=["xlsx", "xls", "csv"])
    st.divider()
    st.caption("복잡한 월별 누적 기능 없이, 한 달 리포트만 깔끔하게 생성합니다.")


total_fixed_cost = calculate_fixed_cost(fixed_file, manual_fixed_cost)

if main_file is None:
    st.info("좌측 사이드바에서 이카운트 매출 엑셀을 업로드하세요.")
    st.stop()

try:
    df = parse_sales_file(main_file)

    ts = df["매출액"].sum()
    gp = df["이익액"].sum()
    net_profit = gp - total_fixed_cost
    net_margin = (net_profit / ts * 100) if ts > 0 else 0

    channel_summary = build_channel_summary(df)
    top10 = build_top10(df)

    st.markdown('<div class="section-label">핵심 요약</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매출액", format_won(ts))
    c2.metric("상품 마진", format_won(gp), delta=f"마진율 {(gp / ts * 100) if ts else 0:.1f}%")
    c3.metric("총 고정비", f"-{format_won(total_fixed_cost)}")
    c4.metric("최종 순이익", format_won(net_profit), delta=f"순이익률 {net_margin:.1f}%")

    st.markdown('<div class="section-label">도표 요약</div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1])

    with left:
        profit_df = pd.DataFrame({"항목": ["매출액", "상품마진", "고정비", "순이익"], "금액": [ts, gp, total_fixed_cost, net_profit]})
        fig_profit = px.bar(profit_df, x="항목", y="금액", text="금액", title="이익 계산 구조", color="항목", color_discrete_map=COLOR_MAP)
        fig_profit.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig_profit.update_layout(yaxis_tickformat=",", height=430, showlegend=False, plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=20, r=20, t=60, b=30))
        st.plotly_chart(fig_profit, use_container_width=True)

    with right:
        fig_pie = px.pie(channel_summary, values="매출액", names="채널", hole=0.48, title="채널별 매출 비중")
        fig_pie.update_layout(height=430, plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=20, r=20, t=60, b=30))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown('<div class="section-label">채널별 매출 요약</div>', unsafe_allow_html=True)
    st.dataframe(
        channel_summary.style.format({"매출액": "{:,.0f}", "이익액": "{:,.0f}", "수량": "{:,.0f}", "마진율(%)": "{:.1f}", "매출비중(%)": "{:.1f}"})
        .background_gradient(subset=["매출액"], cmap="Blues")
        .background_gradient(subset=["이익액"], cmap="Greens")
        .background_gradient(subset=["마진율(%)"], cmap="YlGn"),
        use_container_width=True,
    )

    fig_channel = px.bar(channel_summary.sort_values("매출액"), x="매출액", y="채널", orientation="h", text="매출비중(%)", title="채널별 매출액 및 비중", color="마진율(%)", color_continuous_scale="YlGn")
    fig_channel.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_channel.update_layout(xaxis_tickformat=",", height=440, plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=20, r=20, t=60, b=30))
    st.plotly_chart(fig_channel, use_container_width=True)

    st.markdown('<div class="section-label">TOP 10 판매 상품</div>', unsafe_allow_html=True)
    st.dataframe(
        top10.style.format({"매출액": "{:,.0f}", "이익액": "{:,.0f}", "수량": "{:,.0f}", "마진율(%)": "{:.1f}", "매출비중(%)": "{:.1f}"})
        .background_gradient(subset=["매출액"], cmap="Blues")
        .background_gradient(subset=["이익액"], cmap="Greens")
        .background_gradient(subset=["마진율(%)"], cmap="YlGn"),
        use_container_width=True,
    )

    fig_top10 = px.bar(top10.sort_values("매출액"), x="매출액", y="상품명", orientation="h", text="마진율(%)", title="TOP10 상품 매출 및 마진율", color="마진율(%)", color_continuous_scale="YlGn")
    fig_top10.update_traces(texttemplate="마진 %{text:.1f}%", textposition="outside")
    fig_top10.update_layout(xaxis_tickformat=",", height=540, plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=20, r=20, t=60, b=30))
    st.plotly_chart(fig_top10, use_container_width=True)

    st.divider()
    st.markdown('<div class="section-label">다운로드</div>', unsafe_allow_html=True)

    excel_output = BytesIO()
    with pd.ExcelWriter(excel_output, engine="openpyxl") as writer:
        channel_summary.to_excel(writer, sheet_name="채널별_요약", index=False)
        top10.to_excel(writer, sheet_name="TOP10_상품", index=False)
        df.to_excel(writer, sheet_name="정리_원본", index=False)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.download_button("분석 결과 엑셀 다운로드", data=excel_output.getvalue(), file_name="Online_Monthly_Report_Result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with col_b:
        if st.button("PDF 리포트 생성"):
            try:
                pdf_output = make_pdf(ts, gp, total_fixed_cost, net_profit, net_margin, channel_summary, top10)
                st.download_button("PDF 리포트 다운로드", data=pdf_output, file_name="online_report.pdf", mime="application/pdf")
            except Exception as pdf_error:
                st.error(f"PDF 생성 오류: {pdf_error}")

except Exception as e:
    st.error(f"에러 발생: {e}")
