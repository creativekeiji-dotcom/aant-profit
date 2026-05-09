import re
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# =========================================================
# AANT 온라인 월간 경영 리포트 v2
# - 여러 월 매출 파일 업로드
# - 월별 매출/순이익 추이
# - 전월 대비 증감률
# - 채널별 비중/성장률
# - TOP10 상품 도표 및 성장률
# - 고정비/광고비 파일 월별 반영
# =========================================================

FEE_RATES = {
    "쿠팡그로스": 0.1188,
    "그로스": 0.1188,
    "쿠팡": 0.1188,
    "네이버파이낸셜": 0.06,
    "네이버": 0.06,
    "안트": 0.0,
    "삼원전기": 0.0,
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

CHANNEL_ALIASES = {
    "쿠팡 주식회사": "쿠팡",
    "네이버파이낸셜 주식회사": "네이버",
    "AliExpress Korea Limited[알리익스프레스]": "알리익스프레스",
    "주식회사 지마켓": "지마켓",
    "십일번가 주식회사": "11번가",
    "(주)버킷플레이스": "오늘의집",
    "주식회사 안트": "안트",
}

st.set_page_config(page_title="AANT 온라인 경영 리포트 v2", layout="wide")
st.title("📊 AANT 온라인 월간 경영 리포트 v2")
st.caption("여러 월의 이카운트 매출 파일과 광고비/고정비 파일을 업로드하면 월별 추이·채널 비중·TOP10 상품을 자동 분석합니다.")


def clean_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.replace(" ", "", regex=False),
        errors="coerce",
    ).fillna(0)


def extract_month_from_text(text: str) -> Optional[str]:
    """파일명 또는 엑셀 첫 줄에서 YYYY-MM 형태 추출."""
    text = str(text)

    # 2026/04/01, 2026-04-01
    m = re.search(r"(20\d{2})[./-]\s*(\d{1,2})[./-]\s*\d{1,2}", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"

    # 26년4월, 2026년 4월
    m = re.search(r"(20\d{2}|\d{2})\s*년\s*(\d{1,2})\s*월", text)
    if m:
        year = int(m.group(1))
        if year < 100:
            year += 2000
        return f"{year:04d}-{int(m.group(2)):02d}"

    # 4월매출 / 3월_안트매출
    m = re.search(r"(?<!\d)(\d{1,2})\s*월", text)
    if m:
        # 현재 자료 기준: 2026년. 필요하면 사이드바에서 일괄 변경 가능.
        return f"2026-{int(m.group(1)):02d}"

    return None


def normalize_channel(channel: str) -> str:
    channel = str(channel).strip()
    for raw, alias in CHANNEL_ALIASES.items():
        if raw in channel:
            return alias
    if "쿠팡" in channel:
        return "쿠팡"
    if "네이버" in channel:
        return "네이버"
    if "Ali" in channel or "알리" in channel:
        return "알리익스프레스"
    if "지마켓" in channel:
        return "지마켓"
    if "십일" in channel or "11번" in channel:
        return "11번가"
    if "버킷" in channel or "오늘" in channel:
        return "오늘의집"
    return channel if channel else "미분류"


def get_fee_rate(channel: str, product_name: str = "") -> float:
    text = f"{channel} {product_name}"
    for key, rate in FEE_RATES.items():
        if key in text:
            return rate
    return 0.10


def read_sales_file(uploaded_file, default_year: int = 2026) -> Tuple[pd.DataFrame, str]:
    """이카운트 일별이익현황 형태의 파일을 표준 컬럼으로 변환."""
    filename = uploaded_file.name

    if filename.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded_file, header=None)
    else:
        raw = pd.read_excel(uploaded_file, header=None)

    first_text = " ".join(raw.head(3).astype(str).fillna("").values.flatten().tolist())
    month = extract_month_from_text(first_text) or extract_month_from_text(filename)
    if month and month.startswith("2026") is False and re.match(r"^\d{4}-\d{2}$", month):
        pass
    if month is None:
        month = st.text_input(f"{filename}의 월을 입력하세요. 예: 2026-04", value=f"{default_year}-01")

    # 헤더 행 찾기
    h_idx = -1
    for i in range(len(raw)):
        row_values = [str(v).strip() for v in raw.iloc[i].values]
        if "거래처명" in row_values:
            h_idx = i
            break
    if h_idx == -1:
        raise ValueError(f"{filename}: 헤더 행에서 '거래처명'을 찾지 못했습니다.")

    h1 = raw.iloc[h_idx].values.tolist()
    h2 = raw.iloc[h_idx + 1].values.tolist()

    h1_filled = []
    curr = ""
    for v in h1:
        if pd.notna(v) and str(v).strip() != "":
            curr = str(v).strip()
        h1_filled.append(curr)

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

    # 합계 행 제거
    df = df[~df.iloc[:, 0].astype(str).str.contains("계|합계", na=False)]

    # 컬럼명 통일
    col_map = {
        "일자-No.": "일자",
        "거래처명": "채널",
        "품목코드": "품목코드",
        "품목명": "상품명",
        "품목명[규격]": "상품명",
        "판매_수량": "수량",
        "판매_단가": "판매단가",
        "판매_금액": "매출액",
        "원가_단가": "원가단가",
        "원가_금액": "매입원가",
    }

    renamed = {}
    for c in df.columns:
        cs = str(c)
        for k, v in col_map.items():
            if k in cs:
                renamed[c] = v
                break
    df.rename(columns=renamed, inplace=True)

    required_cols = ["채널", "상품명", "수량", "매출액", "매입원가"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{filename}: 필수 컬럼 누락 - {missing}")

    df = df[required_cols + [c for c in ["일자", "품목코드"] if c in df.columns]].copy()
    df["월"] = month
    df["채널_raw"] = df["채널"].fillna("").astype(str).str.strip()
    df["채널"] = df["채널_raw"].apply(normalize_channel)
    df["상품명"] = df["상품명"].fillna("").astype(str).str.strip()

    for col in ["수량", "매출액", "매입원가"]:
        df[col] = clean_number(df[col])

    df = df[(df["매출액"] != 0) | (df["수량"] != 0)].copy()
    df["수수료율"] = df.apply(lambda r: get_fee_rate(r["채널_raw"], r["상품명"]), axis=1)
    df["수수료"] = df["매출액"] * df["수수료율"]
    df["상품마진"] = df["매출액"] - df["매입원가"] - df["수수료"]
    df["마진율(%)"] = (df["상품마진"] / df["매출액"].replace(0, pd.NA) * 100).fillna(0)
    return df, month


def read_cost_file(uploaded_file, default_year: int = 2026) -> pd.DataFrame:
    """광고비/고정비 파일에서 월별 비용 합계 추출."""
    filename = uploaded_file.name
    if filename.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded_file, header=None)
    else:
        raw = pd.read_excel(uploaded_file, header=None)

    month = extract_month_from_text(filename) or extract_month_from_text(
    " ".join(raw.head(3).astype(str).fillna("").values.flatten().tolist())
)
    if month is None:
        month = f"{default_year}-01"

    # '금액'이 있는 행을 헤더로 승격
    header_idx = None
    for i in range(min(len(raw), 10)):
        if "금액" in [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[i].values]:
            header_idx = i
            break

    if header_idx is not None:
        df = raw.iloc[header_idx + 1 :].copy()
        df.columns = [str(x).strip() for x in raw.iloc[header_idx].values]
    else:
        df = raw.copy()

    # 금액 컬럼 찾기
    amount_col = None
    for c in df.columns:
        if "금액" in str(c):
            amount_col = c
            break
    if amount_col is None:
        # 숫자가 가장 많이 잡히는 컬럼을 금액으로 추정
        scores = {}
        for c in df.columns:
            scores[c] = clean_number(df[c]).abs().sum()
        amount_col = max(scores, key=scores.get)

    df["금액"] = clean_number(df[amount_col])
    df["row_text"] = df.astype(str).agg(" ".join, axis=1)

    rows = []
    for _, row in df.iterrows():
        amt = row["금액"]
        if amt == 0:
            continue
        text = row["row_text"]
        # 비용은 음수/양수 혼재 가능. 비용은 +, 보상/환급은 - 처리.
        cost_value = abs(amt)
        if any(k in text for k in ["보상", "환급", "환불", "취소"]):
            cost_value = -abs(amt)
        rows.append({"월": month, "항목": text[:80], "고정비": cost_value, "파일명": filename})

    return pd.DataFrame(rows)


def format_won(v: float) -> str:
    return f"{int(round(v)):,.0f}원"


def format_pct(v: float) -> str:
    if pd.isna(v):
        return "-"
    return f"{v:+.1f}%"


def calc_growth(df: pd.DataFrame, value_col: str, group_cols=None) -> pd.DataFrame:
    group_cols = group_cols or []
    out = df.sort_values(group_cols + ["월"]).copy()

    if len(group_cols) == 0:
        out["전월"] = out[value_col].shift(1)
    else:
        out["전월"] = out.groupby(group_cols, dropna=False)[value_col].shift(1)

    out["증감액"] = out[value_col] - out["전월"]
    out["증감률(%)"] = (
        out["증감액"] / out["전월"].replace(0, pd.NA) * 100
    ).fillna(0)

    return out


with st.sidebar:
    st.header("① 파일 업로드")
    sales_files = st.file_uploader(
        "월별 이카운트 매출 파일 업로드", type=["xlsx", "xls", "csv"], accept_multiple_files=True
    )
    cost_files = st.file_uploader(
        "월별 광고비/고정비 파일 업로드", type=["xlsx", "xls", "csv"], accept_multiple_files=True
    )

    st.header("② 기본 설정")
    default_year = st.number_input("파일명에 연도가 없을 때 적용할 연도", min_value=2020, max_value=2035, value=2026)
    extra_fixed_cost = st.number_input("월 공통 추가 고정비", min_value=0, value=0, step=10000)
    dependency_threshold = st.slider("채널 의존도 경고 기준", 40, 90, 60, 5)
    low_margin_threshold = st.slider("저마진 상품 경고 기준", 0, 30, 15, 1)

    st.header("③ PDF 요약값 수동 반영")
    use_manual_kpi = st.checkbox("1월처럼 원본 엑셀이 없는 월의 PDF 요약값을 반영", value=True)

manual_kpi = pd.DataFrame()
if use_manual_kpi:
    with st.expander("PDF 요약값 입력/수정", expanded=False):
        st.caption("원본 엑셀이 없는 월은 여기서 총매출/상품마진/고정비/순이익을 입력하면 월별 추이 그래프에 포함됩니다.")
        default_manual = pd.DataFrame(
            [
                {"월": "2026-01", "매출액": 136_874_553, "상품마진": 44_265_557, "고정비": 23_734_481, "순이익": 20_531_076},
                {"월": "2026-03", "매출액": 135_780_084, "상품마진": 42_032_919, "고정비": 14_799_438, "순이익": 27_233_481},
            ]
        )
        manual_kpi = st.data_editor(default_manual, num_rows="dynamic", use_container_width=True)
        for c in ["매출액", "상품마진", "고정비", "순이익"]:
            manual_kpi[c] = pd.to_numeric(manual_kpi[c], errors="coerce").fillna(0)

if not sales_files and manual_kpi.empty:
    st.info("좌측에서 매출 파일을 업로드하세요. 1월 PDF처럼 원본이 없는 월은 'PDF 요약값'으로 월별 추이에 반영할 수 있습니다.")
    st.stop()

# ---------------------------------------------------------
# 1. 파일 로딩
# ---------------------------------------------------------
sales_frames = []
loaded_months = []
load_errors = []

for f in sales_files or []:
    try:
        df_one, m = read_sales_file(f, default_year=default_year)
        sales_frames.append(df_one)
        loaded_months.append((f.name, m, len(df_one)))
    except Exception as e:
        load_errors.append(f"{f.name}: {e}")

if load_errors:
    for err in load_errors:
        st.error(err)

master_df = pd.concat(sales_frames, ignore_index=True) if sales_frames else pd.DataFrame()

cost_frames = []
for f in cost_files or []:
    try:
        cost_frames.append(read_cost_file(f, default_year=default_year))
    except Exception as e:
        st.warning(f"고정비 파일 처리 실패 - {f.name}: {e}")

cost_df = pd.concat(cost_frames, ignore_index=True) if cost_frames else pd.DataFrame(columns=["월", "고정비"])

if loaded_months:
    with st.expander("업로드 처리 결과", expanded=False):
        st.dataframe(pd.DataFrame(loaded_months, columns=["파일명", "인식 월", "행 수"]), use_container_width=True)

# ---------------------------------------------------------
# 2. 월별 KPI 계산
# ---------------------------------------------------------
if not master_df.empty:
    monthly_sales = master_df.groupby("월", as_index=False).agg(
        매출액=("매출액", "sum"),
        매입원가=("매입원가", "sum"),
        수수료=("수수료", "sum"),
        상품마진=("상품마진", "sum"),
        판매수량=("수량", "sum"),
    )
else:
    monthly_sales = pd.DataFrame(columns=["월", "매출액", "매입원가", "수수료", "상품마진", "판매수량"])

monthly_cost = cost_df.groupby("월", as_index=False)["고정비"].sum() if not cost_df.empty else pd.DataFrame(columns=["월", "고정비"])
monthly_sales = monthly_sales.merge(monthly_cost, on="월", how="left")
monthly_sales["고정비"] = monthly_sales["고정비"].fillna(0) + extra_fixed_cost
monthly_sales["순이익"] = monthly_sales["상품마진"] - monthly_sales["고정비"]
monthly_sales["순이익률(%)"] = (monthly_sales["순이익"] / monthly_sales["매출액"].replace(0, pd.NA) * 100).fillna(0)
monthly_sales["마진율(%)"] = (monthly_sales["상품마진"] / monthly_sales["매출액"].replace(0, pd.NA) * 100).fillna(0)

# 수동 KPI는 같은 월의 원본 계산값보다 우선 선택 가능하게 별도 표시 후 병합
if use_manual_kpi and not manual_kpi.empty:
    manual = manual_kpi.copy()
    manual = manual[manual["월"].astype(str).str.match(r"^\d{4}-\d{2}$", na=False)]
    manual["매입원가"] = 0
    manual["수수료"] = 0
    manual["판매수량"] = 0
    manual["순이익률(%)"] = (manual["순이익"] / manual["매출액"].replace(0, pd.NA) * 100).fillna(0)
    manual["마진율(%)"] = (manual["상품마진"] / manual["매출액"].replace(0, pd.NA) * 100).fillna(0)
    manual["데이터구분"] = "PDF요약"
    monthly_sales["데이터구분"] = "원본계산"

    # 같은 월이 있으면 PDF요약 우선. 원하면 아래 keep='last' 대신 first로 바꾸면 됨.
    monthly_kpi = pd.concat([monthly_sales, manual[monthly_sales.columns]], ignore_index=True)
    monthly_kpi = monthly_kpi.sort_values(["월", "데이터구분"]).drop_duplicates("월", keep="last")
else:
    monthly_sales["데이터구분"] = "원본계산"
    monthly_kpi = monthly_sales.copy()

monthly_kpi = monthly_kpi.sort_values("월").reset_index(drop=True)
monthly_kpi = calc_growth(monthly_kpi, "매출액") if len(monthly_kpi) > 0 else monthly_kpi
monthly_kpi.rename(columns={"증감률(%)": "매출증감률(%)", "증감액": "매출증감액"}, inplace=True)
monthly_kpi["전월순이익"] = monthly_kpi["순이익"].shift(1)
monthly_kpi["순이익증감액"] = monthly_kpi["순이익"] - monthly_kpi["전월순이익"]
monthly_kpi["순이익증감률(%)"] = (monthly_kpi["순이익증감액"] / monthly_kpi["전월순이익"].replace(0, pd.NA) * 100).fillna(0)

# ---------------------------------------------------------
# 3. 메인 대시보드
# ---------------------------------------------------------
if monthly_kpi.empty:
    st.warning("분석 가능한 월별 데이터가 없습니다.")
    st.stop()

selected_month = st.selectbox("분석 월 선택", monthly_kpi["월"].tolist(), index=len(monthly_kpi) - 1)
current = monthly_kpi[monthly_kpi["월"] == selected_month].iloc[0]

st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💰 매출액", format_won(current["매출액"]), delta=format_pct(current.get("매출증감률(%)", 0)))
c2.metric("📦 상품마진", format_won(current["상품마진"]), delta=f"마진율 {current['마진율(%)']:.1f}%")
c3.metric("💸 고정비/광고비", format_won(current["고정비"]))
c4.metric("🏆 순이익", format_won(current["순이익"]), delta=format_pct(current.get("순이익증감률(%)", 0)))
c5.metric("📈 순이익률", f"{current['순이익률(%)']:.1f}%")
st.divider()

# 월별 KPI 표
with st.expander("월별 KPI 원본표", expanded=False):
    show_cols = ["월", "데이터구분", "매출액", "매출증감액", "매출증감률(%)", "상품마진", "고정비", "순이익", "순이익률(%)"]
    st.dataframe(
        monthly_kpi[show_cols].style.format({
            "매출액": "{:,.0f}", "매출증감액": "{:,.0f}", "매출증감률(%)": "{:+.1f}",
            "상품마진": "{:,.0f}", "고정비": "{:,.0f}", "순이익": "{:,.0f}", "순이익률(%)": "{:.1f}",
        }),
        use_container_width=True,
    )

# ---------------------------------------------------------
# 4. 월별 추이 그래프
# ---------------------------------------------------------
st.subheader("① 월별 매출·순이익 추이")
trend_df = monthly_kpi[["월", "매출액", "상품마진", "순이익"]].melt(id_vars="월", var_name="항목", value_name="금액")
fig_trend = px.line(trend_df, x="월", y="금액", color="항목", markers=True, title="월별 매출 / 상품마진 / 순이익 추이")
fig_trend.update_layout(yaxis_tickformat=",", hovermode="x unified")
st.plotly_chart(fig_trend, use_container_width=True)

fig_growth = px.bar(monthly_kpi, x="월", y="매출증감률(%)", text="매출증감률(%)", title="전월 대비 매출 증감률")
fig_growth.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
fig_growth.update_layout(yaxis_ticksuffix="%")
st.plotly_chart(fig_growth, use_container_width=True)

# ---------------------------------------------------------
# 5. 선택 월 상세 분석
# ---------------------------------------------------------
if not master_df.empty and selected_month in master_df["월"].unique():
    month_df = master_df[master_df["월"] == selected_month].copy()

    st.subheader("② 이익 구조 Waterfall")
    waterfall_values = [
        current["매출액"],
        -month_df["매입원가"].sum(),
        -month_df["수수료"].sum(),
        -current["고정비"],
        current["순이익"],
    ]
    fig_waterfall = go.Figure(go.Waterfall(
        name="이익 구조",
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["매출액", "매입원가", "플랫폼 수수료", "고정비/광고비", "순이익"],
        y=waterfall_values,
        connector={"line": {"width": 1}},
        text=[format_won(v) for v in waterfall_values],
        textposition="outside",
    ))
    fig_waterfall.update_layout(title=f"{selected_month} 이익 계산 흐름", yaxis_tickformat=",")
    st.plotly_chart(fig_waterfall, use_container_width=True)

    # 채널 요약
    channel_summary = month_df.groupby("채널", as_index=False).agg(
        매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"), 수량=("수량", "sum")
    ).sort_values("매출액", ascending=False)
    channel_summary["마진율(%)"] = (channel_summary["상품마진"] / channel_summary["매출액"].replace(0, pd.NA) * 100).fillna(0)
    channel_summary["매출비중(%)"] = (channel_summary["매출액"] / channel_summary["매출액"].sum() * 100).fillna(0)

    st.subheader("③ 채널별 비중과 수익성")
    left, right = st.columns([1, 1])
    with left:
        fig_channel_pie = px.pie(channel_summary, names="채널", values="매출액", hole=0.45, title=f"{selected_month} 채널별 매출 비중")
        st.plotly_chart(fig_channel_pie, use_container_width=True)
    with right:
        fig_channel_bar = px.bar(channel_summary, x="채널", y="상품마진", text="마진율(%)", title=f"{selected_month} 채널별 이익액 및 마진율")
        fig_channel_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_channel_bar.update_layout(yaxis_tickformat=",")
        st.plotly_chart(fig_channel_bar, use_container_width=True)

    max_channel = channel_summary.iloc[0]
    if max_channel["매출비중(%)"] >= dependency_threshold:
        st.warning(f"{selected_month} 기준 '{max_channel['채널']}' 매출 비중이 {max_channel['매출비중(%)']:.1f}%입니다. 단일 채널 의존도가 높습니다.")

    st.dataframe(
        channel_summary.style.format({"매출액": "{:,.0f}", "상품마진": "{:,.0f}", "수량": "{:,.0f}", "마진율(%)": "{:.1f}", "매출비중(%)": "{:.1f}"}),
        use_container_width=True,
    )

    # 채널별 월간 변화
    if master_df["월"].nunique() >= 2:
        st.subheader("④ 채널별 월간 매출 변화")
        channel_month = master_df.groupby(["월", "채널"], as_index=False).agg(매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"))
        fig_ch_trend = px.line(channel_month, x="월", y="매출액", color="채널", markers=True, title="채널별 월간 매출 추이")
        fig_ch_trend.update_layout(yaxis_tickformat=",", hovermode="x unified")
        st.plotly_chart(fig_ch_trend, use_container_width=True)

        ch_growth = calc_growth(channel_month, "매출액", ["채널"])
        ch_growth_sel = ch_growth[ch_growth["월"] == selected_month].sort_values("증감액", ascending=False)
        fig_ch_growth = px.bar(ch_growth_sel, x="채널", y="증감률(%)", text="증감률(%)", title=f"{selected_month} 채널별 전월 대비 매출 증감률")
        fig_ch_growth.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
        fig_ch_growth.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig_ch_growth, use_container_width=True)

    # TOP10 상품
    st.subheader("⑤ TOP10 판매 상품 도표")
    top_products = month_df.groupby("상품명", as_index=False).agg(
        매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"), 수량=("수량", "sum")
    ).sort_values("매출액", ascending=False).head(10)
    top_products["마진율(%)"] = (top_products["상품마진"] / top_products["매출액"].replace(0, pd.NA) * 100).fillna(0)
    top_products["매출비중(%)"] = (top_products["매출액"] / month_df["매출액"].sum() * 100).fillna(0)

    if master_df["월"].nunique() >= 2:
        product_month = master_df.groupby(["월", "상품명"], as_index=False).agg(매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"), 수량=("수량", "sum"))
        pg = calc_growth(product_month, "매출액", ["상품명"])
        pg_sel = pg[pg["월"] == selected_month][["상품명", "전월", "증감액", "증감률(%)"]]
        top_products = top_products.merge(pg_sel, on="상품명", how="left")
    else:
        top_products["전월"] = 0
        top_products["증감액"] = 0
        top_products["증감률(%)"] = 0

    st.dataframe(
        top_products.style.format({
            "매출액": "{:,.0f}", "상품마진": "{:,.0f}", "수량": "{:,.0f}", "마진율(%)": "{:.1f}",
            "매출비중(%)": "{:.1f}", "전월": "{:,.0f}", "증감액": "{:,.0f}", "증감률(%)": "{:+.1f}",
        }),
        use_container_width=True,
    )

    fig_top = px.bar(top_products.sort_values("매출액"), x="매출액", y="상품명", orientation="h", text="마진율(%)", title=f"{selected_month} TOP10 상품 매출 및 마진율")
    fig_top.update_traces(texttemplate="마진 %{text:.1f}%", textposition="outside")
    fig_top.update_layout(xaxis_tickformat=",", height=520)
    st.plotly_chart(fig_top, use_container_width=True)

    low_margin = top_products[top_products["마진율(%)"] <= low_margin_threshold].sort_values("매출액", ascending=False)
    if not low_margin.empty:
        st.error(f"TOP10 중 마진율 {low_margin_threshold}% 이하 저마진 상품이 {len(low_margin)}개 있습니다.")
        st.dataframe(low_margin[["상품명", "매출액", "상품마진", "마진율(%)", "매출비중(%)"]].style.format({"매출액": "{:,.0f}", "상품마진": "{:,.0f}", "마진율(%)": "{:.1f}", "매출비중(%)": "{:.1f}"}), use_container_width=True)

else:
    st.info("선택한 월은 PDF 요약값만 있어 채널/상품 상세 분석은 원본 엑셀 업로드가 필요합니다.")

# ---------------------------------------------------------
# 6. 다운로드
# ---------------------------------------------------------
st.subheader("⑥ 분석 결과 다운로드")
output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    monthly_kpi.to_excel(writer, sheet_name="월별_KPI", index=False)
    if not master_df.empty:
        master_df.to_excel(writer, sheet_name="통합_원본", index=False)
        master_df.groupby(["월", "채널"], as_index=False).agg(매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"), 수량=("수량", "sum")).to_excel(writer, sheet_name="채널별_월집계", index=False)
        master_df.groupby(["월", "상품명"], as_index=False).agg(매출액=("매출액", "sum"), 상품마진=("상품마진", "sum"), 수량=("수량", "sum")).to_excel(writer, sheet_name="상품별_월집계", index=False)
    if not cost_df.empty:
        cost_df.to_excel(writer, sheet_name="고정비_광고비", index=False)

st.download_button(
    "📥 분석 결과 엑셀 다운로드",
    data=output.getvalue(),
    file_name=f"AANT_온라인_월간경영리포트_{datetime.now().strftime('%Y%m%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

html_report = f"""
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>AANT 온라인 월간 리포트</title></head>
<body style="font-family: Arial, sans-serif; margin: 40px;">
<h1>AANT 온라인 월간 경영 리포트</h1>
<h2>{selected_month} 핵심 KPI</h2>
<ul>
<li>매출액: {format_won(current['매출액'])}</li>
<li>상품마진: {format_won(current['상품마진'])}</li>
<li>고정비/광고비: {format_won(current['고정비'])}</li>
<li>순이익: {format_won(current['순이익'])}</li>
<li>순이익률: {current['순이익률(%)']:.1f}%</li>
</ul>
<p>상세 그래프는 Streamlit 화면에서 확인하고, 이 HTML은 요약 공유/인쇄용입니다.</p>
</body></html>
"""
st.download_button("📄 요약 HTML 다운로드", data=html_report.encode("utf-8"), file_name="AANT_Report_Summary.html", mime="text/html")
