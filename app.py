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
    add_line(
