import html
import re
from datetime import date
from urllib.parse import quote

import streamlit as st

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None


st.set_page_config(
    page_title="라벨톡 | 약·영양제 안내",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: Pretendard, sans-serif; }
    .stApp { background: linear-gradient(180deg, #f7fbff 0%, #ffffff 42%); }
    .block-container { max-width: 1050px; padding-top: 2.2rem; padding-bottom: 3rem; }
    .hero { padding: 1.5rem 1.7rem; border-radius: 24px; background: linear-gradient(120deg,#e9f6ff,#f3f0ff); border: 1px solid #dceafa; }
    .hero h1 { font-size: 2.35rem; margin: 0; color: #172554; letter-spacing: -1px; }
    .hero p { color: #475569; margin: .55rem 0 0; font-size: 1.05rem; }
    .pill { display:inline-block; padding: .28rem .7rem; margin-bottom:.65rem; border-radius: 999px; background:#fff; color:#315b91; font-size:.82rem; font-weight:700; }
    .info-card { background:#fff; border:1px solid #e2e8f0; border-radius:18px; padding:1.1rem 1.2rem; margin:.55rem 0; }
    .muted { color:#64748b; font-size:.92rem; }
    .result { background:#f0f9ff; border:1px solid #bae6fd; border-radius:16px; padding:1rem 1.1rem; }
    .warn { background:#fff7ed; border:1px solid #fed7aa; border-radius:16px; padding:1rem 1.1rem; }
    div.stButton > button, div.stDownloadButton > button { border-radius:12px; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def summarize_label(text: str) -> dict:
    """Summarize timing words that the user copied from a package or prescription label.

    This function does not invent a dose or choose a time of day. It only detects
    explicit phrases in the text supplied by the user.
    """
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if not clean:
        return {
            "found": False,
            "timing": "복용 안내 문구를 입력해 주세요.",
            "frequency": "",
        }

    timing_patterns = [
        (r"취침\s*전", "취침 전이라고 표시되어 있어요."),
        (r"기상\s*후", "기상 후라고 표시되어 있어요."),
        (r"식사\s*와\s*함께|식사\s*중", "식사와 함께 복용하라고 표시되어 있어요."),
        (r"식전\s*\d+\s*분", None),
        (r"식후\s*\d+\s*분", None),
        (r"식간", "식간이라고 표시되어 있어요."),
        (r"공복", "공복이라고 표시되어 있어요."),
        (r"식전", "식전이라고 표시되어 있어요."),
        (r"식후", "식후라고 표시되어 있어요."),
        (r"아침|점심|저녁", None),
    ]

    timing = None
    for pattern, message in timing_patterns:
        match = re.search(pattern, clean)
        if match:
            if message is not None:
                timing = message
            else:
                timing = f"‘{match.group(0)}’라고 표시되어 있어요."
            break

    frequency_match = re.search(r"1\s*일\s*\d+\s*회|하루\s*\d+\s*회", clean)
    frequency = frequency_match.group(0) if frequency_match else ""

    if timing:
        return {"found": True, "timing": timing, "frequency": frequency}
    return {
        "found": False,
        "timing": "입력한 문구에서 식전·식후 같은 시간 안내를 찾지 못했어요. 앱이 복용 시간을 추측하지 않습니다.",
        "frequency": frequency,
    }


def mfds_medicine_url(product_name: str) -> str:
    return "https://nedrug.mfds.go.kr/searchDrug?itemName=" + quote(product_name) + "&searchYn=true"


def render_sources(product_name: str, category: str) -> None:
    if category == "의약품":
        st.write(f"식약처 의약품안전나라에서 제품명을 확인하세요: {product_name}")
        st.markdown(f"[식약처 의약품안전나라 검색 결과 열기]({mfds_medicine_url(product_name)})")
    else:
        st.markdown(
            "[식약처 의약품안전나라 건강기능식품 정보 검색](https://nedrug.mfds.go.kr/searchEasyDrug)"
        )


st.markdown(
    """
    <div class="hero">
      <span class="pill">운동하는 사람과 일반인을 위한 정보 안내</span>
      <h1>라벨톡 💊</h1>
      <p>약·영양제 포장에 적힌 안내를 쉽게 정리하고, 선수는 도핑 확인 경로까지 찾아볼 수 있어요.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")
st.warning(
    "라벨톡은 복용법을 처방하거나 도핑 여부를 최종 판정하지 않습니다. "
    "처방전·약 봉투의 지시와 공식 자료를 확인하세요. 처방약을 임의로 중단하거나 복용량을 바꾸지 마세요."
)

tab_general, tab_athlete, tab_about = st.tabs(
    ["일반인 · 약/영양제 안내", "운동선수 · 도핑 확인", "앱의 기준과 한계"]
)


with tab_general:
    st.subheader("제품 안내를 쉬운 말로 정리하기")
    st.caption("제품명을 검색하거나 포장·약 봉투 사진에서 글자를 읽어, 시간 관련 표시를 정리합니다.")

    uploaded_image = st.file_uploader(
        "약 상자·약 봉투·영양제 라벨 사진 (선택)",
        type=["png", "jpg", "jpeg"],
        help="이름, 생년월일, 처방번호 등 개인 정보는 가리거나 잘라낸 뒤 올려 주세요.",
    )
    if uploaded_image is not None:
        try:
            image = Image.open(uploaded_image).convert("RGB") if Image else None
            if image is not None:
                st.image(image, caption="업로드한 사진 (현재 접속 세션에서만 처리)", width=420)
            if st.button("사진에서 글자 읽기", key="run_ocr"):
                if pytesseract is None or image is None:
                    st.error("OCR 구성요소를 불러오지 못했어요. 아래 칸에 라벨 문구를 직접 입력해 주세요.")
                else:
                    try:
                        recognized = pytesseract.image_to_string(image, lang="kor+eng")
                        if recognized.strip():
                            st.session_state["ocr_text"] = recognized.strip()
                            st.success("글자를 읽었어요. 인식 결과를 꼭 확인하고 틀린 부분을 고쳐 주세요.")
                        else:
                            st.warning("사진에서 글자를 찾지 못했어요. 더 선명한 사진을 올리거나 직접 입력해 주세요.")
                    except Exception:
                        st.error("사진 글자 읽기에 실패했어요. 선명한 사진을 사용하거나 안내 문구를 직접 입력해 주세요.")
        except Exception:
            st.error("이미지를 열 수 없어요. PNG 또는 JPG 사진을 다시 선택해 주세요.")

    with st.form("label_form"):
        product = st.text_input("제품명", placeholder="예: 제품 포장에 적힌 이름")
        category = st.radio("제품 종류", ["의약품", "건강기능식품"], horizontal=True)
        label_text = st.text_area(
            "포장·약 봉투에 적힌 안내 문구",
            placeholder="예: 1일 2회, 식후 30분에 복용한다.",
            value=st.session_state.get("ocr_text", ""),
            height=105,
            help="처방전 또는 제품 표시 내용을 그대로 옮겨 적어 주세요. 개인 정보는 입력하지 마세요.",
        )
        submitted = st.form_submit_button("안내 정리하기", type="primary", use_container_width=True)

    if submitted:
        if not product.strip():
            st.error("제품명을 입력해 주세요.")
        elif not label_text.strip():
            st.error("포장이나 약 봉투의 안내 문구를 입력해 주세요.")
        else:
            summary = summarize_label(label_text)
            st.session_state["label_result"] = {
                "product": product.strip(),
                "category": category,
                "label": label_text.strip(),
                "summary": summary,
                "checked": date.today().isoformat(),
            }

    result = st.session_state.get("label_result")
    if result:
        st.markdown("### 확인 결과")
        st.markdown(
            f"""
            <div class="result">
              <b>{html.escape(result['product'])}</b><br>
              <span>{html.escape(result['summary']['timing'])}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if result["summary"]["frequency"]:
            st.info(f"횟수 안내도 감지했어요: {result['summary']['frequency']} (입력한 문구 기준)")
        if not result["summary"]["found"]:
            st.warning("정확한 시간대가 표시되어 있지 않거나 입력 문구에서 확인되지 않았어요. 제품 표시나 약사에게 확인하세요.")
        st.caption(f"입력 문구: {result['label']} · 정리 날짜: {result['checked']}")
        render_sources(result["product"], result["category"])
        st.markdown(
            "<div class='muted'>알림을 설정하려면 공식 안내를 확인한 뒤, 그 지시를 기준으로 휴대전화의 알람에 등록하세요.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div class='info-card'><b>영양제 시간대 안내 원칙</b><br><span class='muted'>제품 표시가 식전·식후 등 구체적인 시간대를 말할 때만 그대로 정리합니다. 표시가 없으면 앱이 ‘아침이 좋다’처럼 임의로 추천하지 않습니다.</span></div>", unsafe_allow_html=True)
    st.caption("사진 글자 인식은 틀릴 수 있습니다. 복용 전에 반드시 원래 약 봉투·제품 표시와 대조하세요.")


with tab_athlete:
    st.subheader("선수용 성분 확인 길잡이")
    st.caption("제품명보다 유효 성분을 기준으로 공식 금지약물 정보를 확인하는 편이 정확합니다.")
    with st.form("athlete_form"):
        athlete_product = st.text_input("약/영양제 제품명", placeholder="제품 포장에 적힌 이름")
        ingredient = st.text_input("유효 성분", placeholder="라벨에서 확인한 성분명")
        sport = st.selectbox("종목", ["축구", "농구", "배구", "육상", "수영", "기타 / 종목 선택"])
        competition = st.selectbox("확인할 상황", ["경기 기간", "경기 외 기간", "잘 모르겠음"])
        athlete_submit = st.form_submit_button("확인 준비하기", type="primary", use_container_width=True)

    if athlete_submit:
        if not athlete_product.strip() and not ingredient.strip():
            st.error("제품명이나 유효 성분 중 하나를 입력해 주세요.")
        else:
            st.session_state["athlete_result"] = {
                "product": athlete_product.strip(),
                "ingredient": ingredient.strip(),
                "sport": sport,
                "competition": competition,
            }

    athlete_result = st.session_state.get("athlete_result")
    if athlete_result:
        st.markdown("### 공식 확인 단계")
        st.markdown(
            f"""
            <div class="warn">
              <b>검색 정보</b><br>
              제품: {html.escape(athlete_result['product'] or '입력되지 않음')}<br>
              유효 성분: {html.escape(athlete_result['ingredient'] or '아직 확인되지 않음')}<br>
              종목: {html.escape(athlete_result['sport'])} · 시기: {html.escape(athlete_result['competition'])}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("[KADA 한국도핑방지위원회 공식 사이트에서 금지약물 검색 열기](https://kada.or.kr/)")
        st.markdown("[WADA 금지목록 공식 자료](https://www.wada-ama.org/en/resources/world-anti-doping-code-and-international-standards/prohibited-list)")
        st.info("공식 검색에서 성분명, 종목, 경기 시기를 직접 확인하세요. 결과가 불분명하면 KADA 또는 의료진에게 확인하고 처방약을 임의로 중단하지 마세요.")


with tab_about:
    st.subheader("앱이 정보를 다루는 기준")
    st.markdown(
        """
        - 입력한 라벨 문장에서 복용 시간 표현을 찾아 정리합니다.
        - 라벨에 없는 시간이나 복용량은 만들어 내지 않습니다.
        - 선수용 화면은 KADA·WADA 공식 확인 경로를 안내하며, 앱 자체가 도핑 여부를 판정하지 않습니다.
        - 제품명과 라벨 문구는 입력해도 저장되지 않습니다. 현재 결과는 브라우저 세션이 끝나면 사라집니다.

        **현재 시제품의 한계**

        - 사진 글자 인식(OCR)은 흐릿한 사진이나 작은 글씨를 잘못 읽을 수 있어, 사용자가 원래 라벨과 대조해야 합니다.
        - 식약처와 도핑 기관의 모든 제품 정보를 앱 안에 복제하지 않았습니다. 공식 자료에서 최종 확인해야 합니다.
        - 개인의 질환, 나이, 임신 여부, 복용 중인 다른 약을 고려한 맞춤 복용 지침을 제공하지 않습니다.
        """
    )


st.divider()
st.caption("시제품 · 정보 확인일: " + date.today().strftime("%Y-%m-%d"))
