# --- 사이드바: 고정비 입력 및 파일 업로드 추가 ---
with st.sidebar:
    st.header("💸 월간 고정비 설정")
    st.info("파일을 업로드하거나 직접 금액을 입력하세요.")
    
    # 1. 파일 업로드 방식 (이사님이 원하신 기능)
    st.subheader("📁 파일로 자동 입력")
    fixed_file = st.file_uploader("고정비 엑셀/CSV 업로드", type=['csv', 'xlsx'])
    
    file_fixed_cost = 0
    if fixed_file is not None:
        try:
            if fixed_file.name.endswith('.csv'):
                # 한글 깨짐 방지를 위해 cp949 또는 utf-8-sig 사용
                try:
                    f_df = pd.read_csv(fixed_file, encoding='utf-8-sig')
                except:
                    f_df = pd.read_csv(fixed_file, encoding='cp949')
            else:
                f_df = pd.read_excel(fixed_file)
            
            # '금액' 컬럼에서 숫자만 추출하여 합산
            if '금액' in f_df.columns:
                f_df['금액'] = pd.to_numeric(f_df['금액'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                file_fixed_cost = f_df['금액'].sum()
                st.success(f"파일 데이터 반영: {file_fixed_cost:,.0f}원")
            else:
                st.error("'금액' 컬럼을 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")

    st.write("---")

    # 2. 수동 입력 방식 (기존 기능 유지)
    st.subheader("⌨️ 추가/수동 입력")
    ad_cost = st.number_input("광고비 직접 입력 (원)", value=0, step=10000, format="%d")
    shipping_cost = st.number_input("물류비 직접 입력 (원)", value=0, step=10000, format="%d")
    etc_cost = st.number_input("기타 운영비 직접 입력 (원)", value=0, step=10000, format="%d")
    manual_fixed_cost = ad_cost + shipping_cost + etc_cost

    # 최종 합계: 파일 금액 + 수동 입력 금액
    total_fixed_cost = file_fixed_cost + manual_fixed_cost
    st.write("---")
    st.metric("총 고정비 합계 (최종)", f"{total_fixed_cost:,.0f} 원")
