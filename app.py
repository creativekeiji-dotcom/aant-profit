import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import os

# --- 설정: 채널별 수수료율 ---
FEE_RATES = {
    "쿠팡": 0.1188,
    "쿠팡그로스": 0.1188,
    "네이버": 0.06,
    "옥션": 0.143,
    "지마켓": 0.143,
    "11번가": 0.143,
    "오늘의집": 0.22,
    "카카오톡": 0.055,
    "알리": 0.11,
    "사업자거래": 0.0,
}

st.set_page_config(page_title="AANT 월간 경영리포트", layout="wide")
st.title("📊 AANT(안트) 경영 분석 및 PDF 리포트")

# --- 1. 사이드바: 고정비 설정 ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    fixed_file = st.file_uploader("고정비 파일 업로드", type=["csv", "xlsx"])
    file_fixed_sum = 0

    if fixed_file is not None:
        try:
            if fixed_file.name.endswith(".csv"):
                f_df = pd.read_csv(fixed_file, encoding="utf-8-sig")
            else:
                f_df = pd.read_excel(fixed_file)

            if "금액" not in f_df.columns:
                for i in range(len(f_df)):
                    if "금액" in f_df.iloc[i].values:
                        f_df.columns = f_df.iloc[i]
                        f_df = f_df.iloc[i + 1 :].reset_index(drop=True)
                        break

            if "금액" in f_df.columns:
                f_df["amt"] = pd.to_numeric(
                    f_df["금액"].astype(str).str.replace(",", ""),
                    errors="coerce"
                ).fillna(0)

                total = 0
                for _, row in f_df.iterrows():
                    v = abs(row["amt"])
                    if "보상" in str(row.values):
                        total -= v
                    else:
                        total += v

                file_fixed_sum = total
                st.success(f"고정비 반영: {file_fixed_sum:,.0f}원")
            else:
                st.error("고정비 파일에 '금액' 컬럼을 찾지 못했습니다.")
        except Exception:
            st.error("고정비 파일 확인")

    total_fixed_cost = file_fixed_sum + st.number_input("기타 직접입력", value=0)

# --- 2. 메인: 데이터 처리 및 분석 ---
main_file = st.file_uploader("이카운트 매출 엑셀 업로드", type=["xlsx", "xls", "csv"])

if main_file is not None:
    try:
        # 원본 파일 읽기
        if main_file.name.endswith(".csv"):
            raw = pd.read_csv(main_file)
        else:
            raw = pd.read_excel(main_file)

        # 헤더 행 찾기
        h_idx = -1
        for i in range(len(raw)):
            if "거래처명" in [str(v) for v in raw.iloc[i].values]:
                h_idx = i
                break

        if h_idx == -1:
            st.error("엑셀에서 헤더(거래처명)를 찾지 못했습니다.")
        else:
            # 2줄 헤더 조합
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
                p1 = str(p1).strip()
                p2 = str(p2).strip() if pd.notna(p2) else ""

                if p1 and p2:
                    new_cols.append(f"{p1}_{p2}")
                elif p1:
                    new_cols.append(p1)
                elif p2:
                    new_cols.append(p2)
                else:
                    new_cols.append("Unnamed")

            # 실제 데이터 영역
            df = raw.iloc[h_idx + 2 :].copy()
            df.columns = new_cols
            df = df[~df.iloc[:, 0].astype(str).str.contains("계|합계", na=False)]

            # 컬럼명 통일
            col_map = {
                "거래처명": "채널",
                "품목명": "상품명",
                "판매_수량": "수량",
                "판매_금액": "매출액",
                "원가_금액": "매입원가",
            }

            for c in df.columns:
                for k, v in col_map.items():
                    if k in c:
                        df.rename(columns={c: v}, inplace=True)

            # 필수 컬럼 체크
            required_cols = ["채널", "상품명", "수량", "매출액", "매입원가"]
            for col in required_cols:
                if col not in df.columns:
                    st.error(f"필수 컬럼이 없습니다: {col}")
                    st.stop()

            # 숫자형 변환
            for col in ["수량", "매출액", "매입원가"]:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", ""),
                    errors="coerce"
                ).fillna(0)

            # 계산
            df["채널"] = df["채널"].astype(str).str.strip()
            df["수수료율"] = df["채널"].apply(
                lambda x: next((v for k, v in FEE_RATES.items() if k in x), 0.1)
            )
            df["이익액"] = df["매출액"] - df["매입원가"] - (df["매출액"] * df["수수료율"])

            ts = df["매출액"].sum()
            gp = df["이익액"].sum()
            net_profit = gp - total_fixed_cost
            net_margin = (net_profit / ts * 100) if ts > 0 else 0

            # --- 상품 TOP10 ---
            top10 = (
                df.groupby("상품명")[["매출액", "이익액", "수량"]]
                .sum()
                .sort_values(by="매출액", ascending=False)
                .head(10)
            )
            top10["마진율(%)"] = (top10["이익액"] / top10["매출액"] * 100).round(1)

            # --- 채널 요약표 ---
            channel_summary = (
                df.groupby("채널")[["매출액", "이익액", "수량"]]
                .sum()
                .sort_values(by="매출액", ascending=False)
                .reset_index()
            )
            channel_summary["마진율(%)"] = (
                channel_summary["이익액"] / channel_summary["매출액"] * 100
            ).round(1)

            # --- 대시보드 화면 ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💰 실 매출액", f"{int(ts):,}원")
            c2.metric("📦 상품 마진", f"{int(gp):,}원")
            c3.metric("💸 총 고정비", f"-{int(total_fixed_cost):,}원")
            c4.metric("🏆 최종 순이익", f"{int(net_profit):,}원", delta=f"{net_margin:.1f}%")
            st.divider()

            # --- 화면용 채널 요약표 ---
            st.subheader("🏪 채널별 매출 요약")
            st.dataframe(
                channel_summary.style.format(
                    {
                        "매출액": "{:,.0f}",
                        "이익액": "{:,.0f}",
                        "수량": "{:,.0f}",
                        "마진율(%)": "{:,.1f}",
                    }
                ),
                use_container_width=True,
            )

            # --- 화면용 TOP10 ---
            st.subheader("🔝 최고 판매 상품 TOP 10 (매출 기준)")
            st.dataframe(
                top10.style.format(
                    {
                        "매출액": "{:,.0f}",
                        "이익액": "{:,.0f}",
                        "수량": "{:,.0f}",
                        "마진율(%)": "{:,.1f}",
                    }
                ),
                use_container_width=True,
            )

            # --- 화면용 차트 ---
            fig_pie = px.pie(
                df,
                values="매출액",
                names="채널",
                title="채널별 매출 비중",
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            # --- PDF 생성 및 다운로드 ---
            if st.button("📄 경영 분석 PDF 리포트 생성"):
                pdf = FPDF()
                pdf.add_page()

                font_path = "NanumGothic.ttf"
                use_korean_font = os.path.exists(font_path)

                if use_korean_font:
                    pdf.add_font("Nanum", "", font_path)
                    pdf.set_font("Nanum", size=18)
                    header_text = "AANT 월간 경영 분석 리포트"
                else:
                    pdf.set_font("Arial", "B", 16)
                    header_text = "AANT Monthly Business Report"

                pdf.cell(190, 10, txt=header_text, ln=True, align="C")
                pdf.ln(8)

                if use_korean_font:
                    pdf.set_font("Nanum", size=12)
                else:
                    pdf.set_font("Arial", size=12)

                pdf.cell(190, 8, txt=f"1. 총 매출액: {int(ts):,} 원", ln=True)
                pdf.cell(190, 8, txt=f"2. 상품 마진(수수료 차감 후): {int(gp):,} 원", ln=True)
                pdf.cell(190, 8, txt=f"3. 총 고정비 지출: {int(total_fixed_cost):,} 원", ln=True)
                pdf.cell(
                    190,
                    8,
                    txt=f"4. 최종 순이익: {int(net_profit):,} 원 (이익률: {net_margin:.1f}%)",
                    ln=True,
                )
                pdf.ln(8)

                # --- PDF용 채널 요약표 ---
                pdf.cell(190, 8, txt="[ 채널별 매출 요약 ]", ln=True)
                pdf.ln(2)

                if use_korean_font:
                    pdf.set_font("Nanum", size=9)
                else:
                    pdf.set_font("Arial", size=9)

                pdf.cell(45, 8, txt="채널", border=1, align="C")
                pdf.cell(42, 8, txt="매출액", border=1, align="C")
                pdf.cell(42, 8, txt="이익액", border=1, align="C")
                pdf.cell(25, 8, txt="수량", border=1, align="C")
                pdf.cell(25, 8, txt="마진율%", border=1, ln=True, align="C")

                for _, row in channel_summary.iterrows():
                    channel_name = str(row["채널"])
                    if len(channel_name) > 12:
                        channel_name = channel_name[:12] + "..."

                    pdf.cell(45, 8, txt=channel_name, border=1)
                    pdf.cell(42, 8, txt=f"{int(row['매출액']):,}", border=1, align="R")
                    pdf.cell(42, 8, txt=f"{int(row['이익액']):,}", border=1, align="R")
                    pdf.cell(25, 8, txt=f"{int(row['수량']):,}", border=1, align="R")
                    pdf.cell(25, 8, txt=f"{row['마진율(%)']:.1f}", border=1, ln=True, align="R")

                pdf.ln(8)

                # --- PDF용 TOP10 요약 ---
                pdf.cell(190, 8, txt="[ TOP 10 판매 상품 요약 ]", ln=True)
                pdf.ln(2)

                for i, (name, row) in enumerate(top10.iterrows(), start=1):
                    short_name = str(name)
                    if len(short_name) > 25:
                        short_name = short_name[:25] + "..."

                    line_text = (
                        f"{i}. {short_name}: {int(row['매출액']):,}원 "
                        f"(마진 {row['마진율(%)']:.1f}%)"
                    )
                    pdf.cell(190, 8, txt=line_text, ln=True)

                pdf_output_raw = pdf.output(dest="S")
                if isinstance(pdf_output_raw, bytearray):
                    pdf_output = bytes(pdf_output_raw)
                elif isinstance(pdf_output_raw, bytes):
                    pdf_output = pdf_output_raw
                else:
                    pdf_output = pdf_output_raw.encode("latin-1")

                st.download_button(
                    label="📥 PDF 리포트 다운로드",
                    data=pdf_output,
                    file_name="AANT_Report.pdf",
                    mime="application/pdf",
                )

    except Exception as e:
        st.error(f"에러 발생: {e}")
