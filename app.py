import os
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

# =========================
# 기본 수수료율
# =========================
FEE_RATES = {
    "쿠팡": 0.1188,
    "쿠팡그로스": 0.1188,
    "네이버": 0.06,
    "네이버파이낸셜": 0.06,
    "안트": 0.0,
    "옥션": 0.143,
    "지마켓": 0.143,
    "11번가": 0.143,
    "십일번가": 0.143,
    "오늘의집": 0.22,
    "버킷플레이스": 0.22,
    "카카오톡": 0.055,
    "알리": 0.11,
    "AliExpress": 0.11,
    "사업자거래": 0.0,
    "온라인 소비자": 0.0,
}

st.set_page_config(page_title="온라인 월간 리포트", layout="wide")
st.title("📊 온라인 월간 리포트")
st.caption("매출 엑셀 1개와 고정비를 넣으면 기본 리포트를 생성합니다.")

# =========================
# 공통 함수
# =========================
def to_number(s):
    return pd.to_numeric(
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce",
    ).fillna(0)


def won(v):
    return f"{int(round(v)):,.0f}원"


def get_fee_rate(channel):
    channel = str(channel)
    for key, rate in FEE_RATES.items():
        if key in channel:
            return rate
    return 0.10


def read_file(uploaded_file, header=None):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, header=header, encoding="utf-8-sig")
    return pd.read_excel(uploaded_file, header=header)


def read_fixed_cost(uploaded_file):
    if uploaded_file is None:
        return 0

    try:
        df = read_file(uploaded_file, header=0)

        # 금액 컬럼이 없으면 원본에서 금액이 있는 행을 헤더로 찾음
        if "금액" not in [str(c).strip() for c in df.columns]:
            raw = read_file(uploaded_file, header=None)
            for i in range(len(raw)):
                row = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[i].values]
                if "금액" in row:
                    df = raw.iloc[i + 1 :].copy()
                    df.columns = [str(x).strip() for x in raw.iloc[i].values]
                    break

        amount_col = None
        for c in df.columns:
            if "금액" in str(c):
                amount_col = c
                break

        if amount_col is None:
            st.sidebar.warning("고정비 파일에서 '금액' 컬럼을 찾지 못했습니다.")
            return 0

        df["금액_숫자"] = to_number(df[amount_col])

        total = 0
        for _, row in df.iterrows():
            amount = abs(row["금액_숫자"])
            row_text = " ".join([str(x) for x in row.values])
            if any(x in row_text for x in ["보상", "환급", "환불", "취소"]):
                total -= amount
            else:
                total += amount

        return total
    except Exception as e:
        st.sidebar.error(f"고정비 파일 오류: {e}")
        return 0


def parse_sales_file(uploaded_file):
    raw = read_file(uploaded_file, header=None)

    # 헤더 행 찾기
    h_idx = -1
    for i in range(len(raw)):
        row = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[i].values]
        if "거래처명" in row:
            h_idx = i
            break

    if h_idx == -1:
        raise ValueError("헤더 행에서 '거래처명'을 찾지 못했습니다.")

    h1 = raw.iloc[h_idx].values.tolist()
    h2 = raw.iloc[h_idx + 1].values.tolist()

    # 이카운트 2줄 헤더 조합
    filled = []
    current = ""
    for v in h1:
        if pd.notna(v) and str(v).strip() != "":
            current = str(v).strip()
        filled.append(current)

    cols = []
    for a, b in zip(filled, h2):
        a = str(a).strip() if pd.notna(a) else ""
        b = str(b).strip() if pd.notna(b) else ""
        if a and b:
            cols.append(f"{a}_{b}")
        elif a:
            cols.append(a)
        elif b:
            cols.append(b)
        else:
            cols.append("Unnamed")

    df = raw.iloc[h_idx + 2 :].copy()
    df.columns = cols
    df = df[~df.iloc[:, 0].astype(str).str.contains("계|합계", na=False)]

    # 필요한 컬럼명 통일
    rename = {}
    for c in df.columns:
        c_text = str(c)
        if "거래처명" in c_text:
            rename[c] = "채널"
        elif "품목명" in c_text:
            rename[c] = "상품명"
        elif "판매_수량" in c_text:
            rename[c] = "수량"
        elif "판매_금액" in c_text:
            rename[c] = "매출액"
        elif "원가_금액" in c_text:
            rename[c] = "매입원가"

    df = df.rename(columns=rename)

    need = ["채널", "상품명", "수량", "매출액", "매입원가"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")

    df = df[need].copy()
    df["채널"] = df["채널"].fillna("").astype(str).str.strip()
    df["상품명"] = df["상품명"].fillna("").astype(str).str.strip()

    for c in ["수량", "매출액", "매입원가"]:
        df[c] = to_number(df[c])

    df = df[(df["매출액"] != 0) | (df["수량"] != 0)].copy()

    df["수수료율"] = df["채널"].apply(get_fee_rate)
    df["수수료"] = df["매출액"] * df["수수료율"]
    df["이익액"] = df["매출액"] - df["매입원가"] - df["수수료"]
    df["마진율(%)"] = (df["이익액"] / df["매출액"].replace(0, pd.NA) * 100).fillna(0)
    return df


def make_pdf(ts, gp, fixed_cost, net_profit, net_margin, channel_summary, top10):
    pdf = FPDF()
    pdf.add_page()

    font_path = "NanumGothic.ttf"
    use_font = os.path.exists(font_path)
    if use_font:
        pdf.add_font("Nanum", "", font_path)
        pdf.set_font("Nanum", size=18)
    else:
        pdf.set_font("Arial", "B", 16)

    pdf.cell(190, 10, "온라인 월간 리포트" if use_font else "Online Monthly Report", ln=True, align="C")
    pdf.ln(8)

    pdf.set_font("Nanum" if use_font else "Arial", size=12)
    pdf.cell(190, 8, f"1. 총 매출액: {int(ts):,} 원", ln=True)
    pdf.cell(190, 8, f"2. 상품 마진: {int(gp):,} 원", ln=True)
    pdf.cell(190, 8, f"3. 총 고정비: {int(fixed_cost):,} 원", ln=True)
    pdf.cell(190, 8, f"4. 최종 순이익: {int(net_profit):,} 원 (이익률: {net_margin:.1f}%)", ln=True)
    pdf.ln(8)

    pdf.cell(190, 8, "[ 채널별 매출 요약 ]", ln=True)
    pdf.set_font("Nanum" if use_font else "Arial", size=9)
    for _, r in channel_summary.iterrows():
        name = str(r["채널"])
        if len(name) > 14:
            name = name[:14] + "..."
        pdf.cell(190, 7, f"{name} | 매출 {int(r['매출액']):,}원 | 이익 {int(r['이익액']):,}원 | 마진 {r['마진율(%)']:.1f}%", ln=True)

    pdf.ln(5)
    pdf.cell(190, 8, "[ TOP 10 상품 ]", ln=True)
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        name = str(r["상품명"])
        if len(name) > 24:
            name = name[:24] + "..."
        pdf.cell(190, 7, f"{i}. {name} | {int(r['매출액']):,}원 | 마진 {r['마진율(%)']:.1f}%", ln=True)

    out = pdf.output(dest="S")
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, bytes):
        return out
    return out.encode("latin-1")


# =========================
# 입력 영역
# =========================
with st.sidebar:
    st.header("입력")
    fixed_file = st.file_uploader("고정비 파일", type=["csv", "xlsx", "xls"])
    manual_fixed = st.number_input("기타 고정비 직접입력", value=0, step=10000)
    st.divider()
    main_file = st.file_uploader("이카운트 매출 엑셀", type=["xlsx", "xls", "csv"])

fixed_cost = read_fixed_cost(fixed_file) + manual_fixed

if main_file is None:
    st.info("왼쪽에서 이카운트 매출 엑셀을 업로드하세요.")
    st.stop()

try:
    df = parse_sales_file(main_file)

    ts = df["매출액"].sum()
    gp = df["이익액"].sum()
    net_profit = gp - fixed_cost
    net_margin = (net_profit / ts * 100) if ts else 0

    channel_summary = (
        df.groupby("채널", as_index=False)
        .agg(매출액=("매출액", "sum"), 이익액=("이익액", "sum"), 수량=("수량", "sum"))
        .sort_values("매출액", ascending=False)
    )
    channel_summary["마진율(%)"] = (channel_summary["이익액"] / channel_summary["매출액"].replace(0, pd.NA) * 100).fillna(0)
    channel_summary["매출비중(%)"] = (channel_summary["매출액"] / channel_summary["매출액"].sum() * 100).fillna(0)

    top10 = (
        df.groupby("상품명", as_index=False)
        .agg(매출액=("매출액", "sum"), 이익액=("이익액", "sum"), 수량=("수량", "sum"))
        .sort_values("매출액", ascending=False)
        .head(10)
    )
    top10["마진율(%)"] = (top10["이익액"] / top10["매출액"].replace(0, pd.NA) * 100).fillna(0)

    # KPI
    st.subheader("핵심 요약")
    a, b, c, d = st.columns(4)
    a.metric("총 매출액", won(ts))
    b.metric("상품 마진", won(gp), f"마진율 {(gp / ts * 100) if ts else 0:.1f}%")
    c.metric("총 고정비", f"-{won(fixed_cost)}")
    d.metric("최종 순이익", won(net_profit), f"순이익률 {net_margin:.1f}%")

    st.divider()

    # 차트
    st.subheader("도표")
    left, right = st.columns(2)

    with left:
        summary_chart = pd.DataFrame({
            "항목": ["매출", "상품마진", "고정비", "순이익"],
            "금액": [ts, gp, fixed_cost, net_profit],
            "구분": ["매출", "이익", "비용", "이익"],
        })
        fig = px.bar(
            summary_chart,
            x="항목",
            y="금액",
            color="구분",
            text="금액",
            title="이익 계산 요약",
            color_discrete_map={"매출": "#2563EB", "이익": "#16A34A", "비용": "#F97316"},
        )
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(yaxis_tickformat=",", height=420)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig_pie = px.pie(
            channel_summary,
            names="채널",
            values="매출액",
            hole=0.45,
            title="채널별 매출 비중",
        )
        fig_pie.update_layout(height=420)
        st.plotly_chart(fig_pie, use_container_width=True)

    fig_channel = px.bar(
        channel_summary,
        x="채널",
        y="매출액",
        color="마진율(%)",
        text="매출비중(%)",
        title="채널별 매출액 / 마진율",
        color_continuous_scale="Blues",
    )
    fig_channel.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_channel.update_layout(yaxis_tickformat=",", height=420)
    st.plotly_chart(fig_channel, use_container_width=True)

    # 표
    st.subheader("채널별 매출 요약")
    st.dataframe(
        channel_summary.style.format({
            "매출액": "{:,.0f}",
            "이익액": "{:,.0f}",
            "수량": "{:,.0f}",
            "마진율(%)": "{:.1f}",
            "매출비중(%)": "{:.1f}",
        }),
        use_container_width=True,
    )

    st.subheader("TOP 10 판매 상품")
    st.dataframe(
        top10.style.format({
            "매출액": "{:,.0f}",
            "이익액": "{:,.0f}",
            "수량": "{:,.0f}",
            "마진율(%)": "{:.1f}",
        }),
        use_container_width=True,
    )

    fig_top = px.bar(
        top10.sort_values("매출액"),
        x="매출액",
        y="상품명",
        orientation="h",
        color="마진율(%)",
        text="마진율(%)",
        title="TOP10 상품 매출 / 마진율",
        color_continuous_scale="Greens",
    )
    fig_top.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_top.update_layout(xaxis_tickformat=",", height=520)
    st.plotly_chart(fig_top, use_container_width=True)

    st.divider()

    # 다운로드
    st.subheader("다운로드")
    excel_out = BytesIO()
    with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
        channel_summary.to_excel(writer, sheet_name="채널별요약", index=False)
        top10.to_excel(writer, sheet_name="TOP10상품", index=False)
        df.to_excel(writer, sheet_name="정리원본", index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "엑셀 다운로드",
            data=excel_out.getvalue(),
            file_name="online_report_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        if st.button("PDF 생성"):
            pdf_bytes = make_pdf(ts, gp, fixed_cost, net_profit, net_margin, channel_summary, top10)
            st.download_button("PDF 다운로드", data=pdf_bytes, file_name="online_report.pdf", mime="application/pdf")

except Exception as e:
    st.error(f"에러 발생: {e}")
