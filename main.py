import html
import re
import uuid
from datetime import date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import streamlit as st

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None


KST = ZoneInfo("Asia/Seoul")

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
    .block-container { max-width: 1050px; padding-top: 2rem; padding-bottom: 3rem; }
    .hero { padding: 1.5rem 1.7rem; border-radius: 24px; background: linear-gradient(120deg,#e9f6ff,#f3f0ff); border: 1px solid #dceafa; }
    .hero h1 { font-size: 2.35rem; margin: 0; color: #172554; letter-spacing: -1px; }
    .hero p { color: #475569; margin: .55rem 0 0; font-size: 1.05rem; }
    .pill { display:inline-block; padding: .28rem .7rem; margin-bottom:.65rem; border-radius: 999px; background:#fff; color:#315b91; font-size:.82rem; font-weight:700; }
    .card { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:1rem 1.1rem; margin:.5rem 0; }
    .muted { color:#64748b; font-size:.92rem; }
    .result { background:#f0f9ff; border:1px solid #bae6fd; border-radius:16px; padding:1rem 1.1rem; }
    .warn { background:#fff7ed; border:1px solid #fed7aa; border-radius:16px; padding:1rem 1.1rem; }
    div.stButton > button, div.stDownloadButton > button { border-radius:12px; font-weight:700; }
    </style>
    """,
    unsafe_allow_html=True,
)


def initialize_state():
    defaults = {
        "ocr_text": "",
        "label_result": None,
        "athlete_result": None,
        "reminders": [],
        "alerts": {},
        "dose_records": [],
        "saved_products": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def summarize_label(text: str) -> dict:
    """사용자가 입력한 안내 문구에서 명시된 시간과 횟수 표현만 찾습니다."""
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if not clean:
        return {
            "found": False,
            "timing": "안내 문구가 입력되지 않았어요.",
            "frequency": "",
        }

    patterns = [
        r"취침\s*전",
        r"기상\s*후",
        r"식사\s*와\s*함께|식사\s*중",
        r"식전\s*\d+\s*분",
        r"식후\s*\d+\s*분",
        r"식간",
        r"공복",
        r"식전",
        r"식후",
        r"아침|점심|저녁",
    ]

    timing = ""
    for pattern in patterns:
        match = re.search(pattern, clean)
        if match:
            timing = f"‘{match.group(0)}’라고 표시되어 있어요."
            break

    frequency_match = re.search(
        r"1\s*일\s*\d+\s*회|하루\s*\d+\s*회",
        clean,
    )
    frequency = frequency_match.group(0) if frequency_match else ""

    if timing:
        return {
            "found": True,
            "timing": timing,
            "frequency": frequency,
        }

    return {
        "found": False,
        "timing": (
            "입력 문구에서 구체적인 섭취 시점을 찾지 못했어요. "
            "앱이 시간을 추측하지 않습니다."
        ),
        "frequency": frequency,
    }


def supplement_guidance(
    product: str,
    ingredient: str,
    label_text: str,
    summary: dict,
) -> str:
    """제품 표시사항을 우선하며 개인별 복용법을 새로 처방하지 않습니다."""
    if summary["found"]:
        return (
            "제품 표시사항에서 섭취 시점을 확인했어요. "
            "아래 문구는 입력한 라벨을 기준으로 정리한 결과입니다."
        )

    search_text = f"{product} {ingredient}"

    if "유산균" in search_text or "프로바이오틱스" in search_text:
        return (
            "유산균은 모든 제품에 공통으로 적용되는 ‘가장 좋은 시간’을 "
            "단정하기 어려워요. 제품 표시사항을 먼저 따르고, 별도 시간 안내가 "
            "없다면 제조사나 약사에게 확인하세요. 시간을 정해 알림을 설정할 수 "
            "있지만, 그 시간은 앱이 효능을 보장해 추천한 시간이 아닙니다."
        )

    return (
        "제품별 섭취 방법이 다를 수 있어요. 포장지의 1일 섭취량과 섭취 방법을 "
        "확인해 주세요. 구체적인 시간 안내를 찾지 못했으므로 앱이 "
        "아침·점심·저녁 중 하나를 임의로 추천하지 않습니다."
    )


def medicine_url(product_name: str) -> str:
    return (
        "https://nedrug.mfds.go.kr/searchDrug?itemName="
        + quote(product_name)
        + "&searchYn=true"
    )


def add_dose_record(product: str, note: str = "복용 완료"):
    now = datetime.now(KST)
    st.session_state.dose_records.insert(
        0,
        {
            "product": product,
            "note": note,
            "when": now.strftime("%Y-%m-%d %H:%M"),
        },
    )
    st.session_state.dose_records = st.session_state.dose_records[:100]


def reminder_panel():
    """브라우저 앱이 열려 있는 동안 설정된 알림 시간을 확인합니다."""

    @st.fragment(run_every="30s")
    def live_panel():
        now = datetime.now(KST)
        today = now.date().isoformat()

        for reminder in st.session_state.reminders:
            try:
                reminder_time = time.fromisoformat(reminder["time"])
            except (KeyError, ValueError, TypeError):
                continue

            scheduled = datetime.combine(
                now.date(),
                reminder_time,
                tzinfo=KST,
            )
            elapsed = now - scheduled
            already_notified = reminder.get("last_notified") == today

            if (
                timedelta(0) <= elapsed < timedelta(minutes=3)
                and not already_notified
            ):
                reminder["last_notified"] = today
                st.session_state.alerts[reminder["id"]] = today

        st.markdown("### 복용 알림")

        if not st.session_state.reminders:
            st.caption(
                "등록된 알림이 없어요. 제품 표시사항을 확인한 뒤 시간을 설정해 주세요."
            )
        else:
            for reminder in list(st.session_state.reminders):
                reminder_id = reminder["id"]
                reminder_time = time.fromisoformat(
                    reminder["time"]
                ).strftime("%H:%M")

                col1, col2, col3 = st.columns([5, 2, 1])
                col1.write(f"**{html.escape(reminder['product'])}**")
                col2.write(f"매일 {reminder_time}")

                if col3.button(
                    "삭제",
                    key=f"delete_reminder_{reminder_id}",
                ):
                    st.session_state.reminders = [
                        item
                        for item in st.session_state.reminders
                        if item["id"] != reminder_id
                    ]
                    st.session_state.alerts.pop(reminder_id, None)
                    st.rerun()

                if reminder_id in st.session_state.alerts:
                    st.warning(
                        f"🔔 설정한 시간이에요: {reminder['product']} — "
                        "제품 안내를 확인하고 복용 여부를 기록하세요."
                    )

                    if st.button(
                        "복용 완료로 기록",
                        key=f"done_{reminder_id}_{today}",
                    ):
                        add_dose_record(reminder["product"])
                        st.session_state.alerts.pop(reminder_id, None)
                        st.success("복용 완료를 기록했어요.")

        st.caption(
            "알림은 앱을 열어 둔 동안에만 확인할 수 있어요. "
            "앱을 닫은 상태의 휴대전화 푸시 알림은 제공하지 않습니다."
        )

    live_panel()


initialize_state()

st.markdown(
    """
    <div class="hero">
      <span class="pill">일반인과 운동선수를 위한 제품 정보 안내</span>
      <h1>라벨톡 💊</h1>
      <p>포장지 안내를 쉽게 정리하고, 직접 설정한 복용 알림과 공식 도핑 확인 경로를 이용해 보세요.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")
st.warning(
    "라벨톡은 복용법을 처방하거나 도핑 여부를 최종 판정하지 않습니다. "
    "처방약을 임의로 중단하거나 복용량을 바꾸지 말고, 제품 표시와 공식 자료를 확인하세요."
)

tab_general, tab_athlete, tab_history, tab_about = st.tabs(
    [
        "일반인 · 약/영양제 안내",
        "운동선수 · 도핑 확인",
        "복용 알림·기록",
        "앱의 기준과 한계",
    ]
)


with tab_general:
    st.subheader("제품 안내 확인")
    st.caption(
        "제품명과 표시 내용을 입력하거나 사진으로 읽어 보세요. "
        "사진 판독 결과는 꼭 원본과 비교해 주세요."
    )

    uploaded_image = st.file_uploader(
        "약 상자·약 봉투·건강기능식품 라벨 사진 (선택)",
        type=["png", "jpg", "jpeg"],
        help=(
            "이름, 생년월일, 처방번호 등 개인정보는 "
            "가리거나 잘라낸 뒤 올려 주세요."
        ),
    )

    image = None

    if uploaded_image is not None:
        try:
            if Image is not None:
                image = Image.open(uploaded_image).convert("RGB")
                st.image(
                    image,
                    caption="업로드한 사진 · 현재 접속 세션에서 처리",
                    width=420,
                )

            if st.button("사진에서 글자 읽기", key="run_ocr"):
                if pytesseract is None or image is None:
                    st.error(
                        "사진 인식 기능을 사용할 수 없어요. "
                        "아래 칸에 문구를 직접 입력해 주세요."
                    )
                else:
                    try:
                        text = pytesseract.image_to_string(
                            image,
                            lang="kor+eng",
                        ).strip()

                        if text:
                            st.session_state.ocr_text = text
                            st.success(
                                "글자를 읽었어요. 인식 결과를 확인하고 "
                                "틀린 부분을 수정해 주세요."
                            )
                        else:
                            st.warning(
                                "글자를 찾지 못했어요. 더 선명한 사진을 "
                                "사용하거나 직접 입력해 주세요."
                            )
                    except Exception:
                        st.error(
                            "사진 글자 읽기에 실패했어요. PNG/JPG 사진을 "
                            "다시 선택하거나 직접 입력해 주세요."
                        )
        except Exception:
            st.error("이미지를 열 수 없어요. PNG 또는 JPG 사진을 다시 선택해 주세요.")

    with st.form("product_form"):
        product = st.text_input(
            "제품명",
            placeholder="포장지에 적힌 제품명",
        )
        category = st.radio(
            "제품 종류",
            ["의약품", "건강기능식품"],
            horizontal=True,
        )
        ingredient = st.text_input(
            "주요 성분 (선택)",
            placeholder="예: 유산균 등 라벨에 적힌 성분",
        )
        label_text = st.text_area(
            "포장·약 봉투에 적힌 안내 문구 (선택)",
            placeholder="예: 1일 1회, 식후에 섭취한다.",
            value=st.session_state.ocr_text,
            height=105,
            help=(
                "처방전 또는 제품 표시 내용을 그대로 옮겨 적어 주세요. "
                "개인정보는 입력하지 마세요."
            ),
        )
        submitted = st.form_submit_button(
            "안내 정리하기",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not product.strip():
            st.error("제품명을 입력해 주세요.")
        elif category == "의약품" and not label_text.strip():
            st.error(
                "의약품은 약 봉투나 제품 안내 문구를 입력해 주세요. "
                "앱이 복용법을 추측하지 않습니다."
            )
        else:
            summary = summarize_label(label_text)
            st.session_state.label_result = {
                "product": product.strip(),
                "category": category,
                "ingredient": ingredient.strip(),
                "label": label_text.strip(),
                "summary": summary,
                "checked": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            }

            if not any(
                item["product"] == product.strip()
                for item in st.session_state.saved_products
            ):
                st.session_state.saved_products.append(
                    {
                        "product": product.strip(),
                        "category": category,
                        "ingredient": ingredient.strip(),
                        "label": label_text.strip(),
                    }
                )

    result = st.session_state.label_result

    if result:
        st.markdown("### 확인 결과")
        st.markdown(
            f"<div class='result'><b>{html.escape(result['product'])}</b><br>"
            f"{html.escape(result['summary']['timing'])}</div>",
            unsafe_allow_html=True,
        )

        if result["summary"]["frequency"]:
            st.info(
                f"횟수 안내: {result['summary']['frequency']} "
                "(입력한 문구 기준)"
            )

        if not result["summary"]["found"]:
            st.warning(
                "구체적인 시점을 확인하지 못했어요. "
                "제품 설명서나 약사에게 확인해 주세요."
            )

        if result["category"] == "건강기능식품":
            st.markdown("#### 섭취 시간 안내")
            st.write(
                supplement_guidance(
                    result["product"],
                    result["ingredient"],
                    result["label"],
                    result["summary"],
                )
            )

            search_text = f"{result['product']} {result['ingredient']}"
            if (
                "유산균" in search_text
                or "프로바이오틱스" in search_text
            ):
                st.markdown(
                    "[NIH ODS 프로바이오틱스 정보]"
                    "(https://ods.od.nih.gov/factsheets/"
                    "Probiotics-HealthProfessional/)"
                )

        st.caption(
            f"입력한 안내: {result['label'] or '없음'} · "
            f"정리 시각: {result['checked']}"
        )

        if result["category"] == "의약품":
            st.markdown(
                f"[식약처 의약품안전나라에서 제품 검색]"
                f"({medicine_url(result['product'])})"
            )
        else:
            st.markdown(
                "[식약처 의약품안전나라 건강기능식품 정보 검색]"
                "(https://nedrug.mfds.go.kr/searchEasyDrug)"
            )

        with st.form("reminder_create_form"):
            reminder_time = st.time_input(
                "매일 알림 받을 시간",
                value=time(8, 0),
                key="new_reminder_time",
            )
            add_reminder = st.form_submit_button("이 제품 알림 설정")

        if add_reminder:
            reminder_time_text = reminder_time.strftime("%H:%M")
            duplicate = any(
                item["product"] == result["product"]
                and item["time"] == reminder_time_text
                for item in st.session_state.reminders
            )

            if duplicate:
                st.info("같은 제품과 시간의 알림이 이미 등록되어 있어요.")
            else:
                st.session_state.reminders.append(
                    {
                        "id": uuid.uuid4().hex[:10],
                        "product": result["product"],
                        "time": reminder_time_text,
                        "last_notified": "",
                    }
                )
                st.success(
                    "알림을 등록했어요. 제품 표시사항을 기준으로 "
                    "설정했는지 확인해 주세요."
                )

    with st.expander("내 제품 목록"):
        if st.session_state.saved_products:
            for item in st.session_state.saved_products:
                st.write(f"• {item['product']} · {item['category']}")
        else:
            st.caption("아직 등록한 제품이 없어요.")


WADA_DATA_VERSION = "WADA 금지목록 2026"
WADA_DATA_START = date(2026, 1, 1)
WADA_DATA_END = date(2026, 12, 31)
WADA_LIST_URL = (
    "https://www.wada-ama.org/sites/default/files/"
    "2025-09/2026list_en_final_clean_september_2025.pdf"
)

# 수행평가용 대표 성분 데이터입니다. 전체 금지목록이 아닙니다.
# status: all_time, in_competition,
# threshold_in_competition, monitored_not_prohibited
WADA_EXAMPLE_DB = [
    {
        "names": ["testosterone", "테스토스테론"],
        "class": "S1.1 동화작용제",
        "status": "all_time",
    },
    {
        "names": ["stanozolol", "스타노졸롤"],
        "class": "S1.1 동화작용제",
        "status": "all_time",
    },
    {
        "names": ["nandrolone", "난드롤론"],
        "class": "S1.1 동화작용제",
        "status": "all_time",
    },
    {
        "names": ["clenbuterol", "클렌부테롤"],
        "class": "S1.2 기타 동화작용제",
        "status": "all_time",
    },
    {
        "names": ["cocaine", "코카인"],
        "class": "S6.A 비특정 흥분제",
        "status": "in_competition",
    },
    {
        "names": ["tramadol", "트라마돌"],
        "class": "S7 마약류",
        "status": "in_competition",
    },
    {
        "names": ["pseudoephedrine", "슈도에페드린"],
        "class": "S6.A 흥분제",
        "status": "threshold_in_competition",
    },
    {
        "names": ["caffeine", "카페인"],
        "class": "2026 모니터링 프로그램",
        "status": "monitored_not_prohibited",
    },
]


def normalize_ingredient(value: str) -> str:
    """성분명을 비교할 때 대소문자, 공백, 기호 차이를 줄입니다."""
    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        (value or "").casefold(),
    )


def judge_wada_example(
    ingredient: str,
    competition_period: str,
) -> dict:
    """내장된 대표 성분만 판별하고, 미등록 성분은 허용으로 취급하지 않습니다."""
    today = datetime.now(KST).date()

    if not (WADA_DATA_START <= today <= WADA_DATA_END):
        return {
            "status": "outdated",
            "message": (
                "내장 데이터의 적용 기간이 끝났어요. "
                "최신 공식 자료에서 확인해 주세요."
            ),
        }

    target = normalize_ingredient(ingredient)

    found = next(
        (
            item
            for item in WADA_EXAMPLE_DB
            if target
            and target
            in {
                normalize_ingredient(name)
                for name in item["names"]
            }
        ),
        None,
    )

    if found is None:
        return {
            "status": "unknown",
            "message": (
                "내장된 대표 성분 목록에서 찾지 못했어요. "
                "허용이라는 뜻은 아니므로 KADA에서 확인하세요."
            ),
        }

    rule = found["status"]

    if rule == "all_time":
        message = (
            "WADA 2026 목록에서 경기 기간과 경기 기간 외 모두 "
            "금지된 분류로 확인됩니다."
        )
        result_status = "prohibited"

    elif rule == "in_competition":
        if competition_period == "경기 기간":
            message = (
                "WADA 2026 목록에서 경기 기간 중 금지된 "
                "분류로 확인됩니다."
            )
            result_status = "prohibited"
        else:
            message = (
                "WADA 2026 목록에서 경기 기간 중 금지로 분류됩니다. "
                "경기 외 기간의 사용 판단도 KADA에서 확인하세요."
            )
            result_status = "conditional"

    elif rule == "threshold_in_competition":
        message = (
            "경기 기간 중 소변 농도가 기준치(150 μg/mL)를 넘으면 "
            "금지됩니다. 앱은 개인의 체내 농도를 알 수 없으므로 "
            "KADA와 의료진에게 확인하세요."
        )
        result_status = "conditional"

    else:
        message = (
            "WADA 2026 모니터링 프로그램에 포함되어 있지만 "
            "금지약물은 아닙니다. 제품 전체의 안전성을 뜻하지는 않습니다."
        )
        result_status = "monitored"

    return {
        "status": result_status,
        "ingredient": found["names"][0],
        "class": found["class"],
        "message": message,
    }


with tab_athlete:
    st.subheader("운동선수용 도핑 성분 확인")
    st.caption(
        "성분명을 내장된 대표 목록과 대조합니다. "
        "제품명만으로는 성분을 추측하지 않습니다."
    )

    with st.form("athlete_form"):
        athlete_product = st.text_input(
            "제품명 (선택)",
            placeholder="약·보충제 포장에 적힌 이름",
        )
        athlete_ingredient = st.text_input(
            "유효 성분명",
            placeholder="예: testosterone 또는 테스토스테론",
            help="제품 포장이나 설명서에서 유효 성분을 확인해 입력하세요.",
        )
        athlete_kind = st.radio(
            "제품 종류",
            ["의약품", "건강기능식품·보충제"],
            horizontal=True,
        )
        sport = st.selectbox(
            "종목",
            ["축구", "농구", "배구", "육상", "수영", "기타 / 종목 선택"],
        )
        competition = st.selectbox(
            "확인할 상황",
            ["경기 기간", "경기 기간 외"],
        )
        athlete_submit = st.form_submit_button(
            "내장 목록으로 확인",
            type="primary",
            use_container_width=True,
        )

    if athlete_submit:
        if not athlete_ingredient.strip():
            st.error(
                "제품명만으로는 판단할 수 없어요. "
                "유효 성분명을 입력해 주세요."
            )
        else:
            result = judge_wada_example(
                athlete_ingredient,
                competition,
            )
            st.session_state.athlete_lookup = {
                "product": athlete_product.strip(),
                "ingredient": athlete_ingredient.strip(),
                "kind": athlete_kind,
                "sport": sport,
                "competition": competition,
                "result": result,
                "checked_at": datetime.now(KST).strftime(
                    "%Y-%m-%d %H:%M KST"
                ),
            }

    lookup = st.session_state.get("athlete_lookup")

    if lookup:
        result = lookup["result"]

        st.markdown("#### 확인 결과")
        st.write(
            f"제품: {lookup['product'] or '미입력'} · "
            f"성분: {lookup['ingredient']} · "
            f"종목: {lookup['sport']} · "
            f"상황: {lookup['competition']}"
        )

        if result["status"] == "prohibited":
            st.error(
                f"도핑 금지 가능성이 확인됐어요. {result['message']}"
            )
        elif result["status"] == "conditional":
            st.warning(
                f"조건에 따라 금지될 수 있어요. {result['message']}"
            )
        elif result["status"] == "monitored":
            st.info(result["message"])
        elif result["status"] == "outdated":
            st.error(result["message"])
        else:
            st.warning(result["message"])

        if result.get("class"):
            st.caption(
                f"분류: {result['class']} · 기준: {WADA_DATA_VERSION}"
            )

        st.caption(f"확인 시각: {lookup['checked_at']}")

        if lookup["kind"] == "건강기능식품·보충제":
            st.warning(
                "성분 결과만으로 보충제 제품 전체를 판단할 수 없어요. "
                "표시되지 않은 성분이나 제조 중 오염 가능성은 "
                "이 앱의 목록으로 확인할 수 없습니다."
            )

        st.link_button(
            "KADA 공식 금지약물 검색",
            "https://www.kada-ad.or.kr/kada?where=drug%2Fdrug_search",
        )
        st.markdown(
            f"[WADA 2026 공식 금지목록]({WADA_LIST_URL})"
        )
        st.caption(
            "이 앱의 내장 목록은 수행평가용 대표 성분 예시만 포함하며 "
            "전체 약물 데이터베이스가 아닙니다. 목록에 없는 성분은 "
            "허용으로 판정하지 않습니다. 투여 경로·용량·종목별 예외와 "
            "최신 규정은 KADA에서 확인하세요."
        )


with tab_history:
    st.subheader("알림과 복용 기록")
    reminder_panel()

    st.markdown("### 복용 기록")
    if st.session_state.dose_records:
        for record in st.session_state.dose_records:
            st.write(
                f"✅ {record['when']} · "
                f"{record['product']} · {record['note']}"
            )

        if st.button("복용 기록 지우기"):
            st.session_state.dose_records = []
            st.rerun()
    else:
        st.caption(
            "알림에서 ‘복용 완료로 기록’을 누르면 여기에 기록돼요."
        )


with tab_about:
    st.subheader("앱의 기준과 한계")
    st.markdown(
        """
        - 사진 글자 인식 결과는 사용자가 원본 포장과 대조해야 합니다.
        - 앱은 표시된 복용·섭취 안내만 정리하고, 표시되지 않은 시간이나 용량을 만들어 내지 않습니다.
        - 건강기능식품의 섭취 시간은 제품 표시사항을 우선합니다. 유산균도 모든 제품에 공통으로 가장 좋은 시간이 있다고 단정하지 않습니다.
        - 알림과 복용 기록은 현재 브라우저 세션에 저장됩니다. 브라우저를 닫으면 알림이 울리지 않으며, 앱을 다시 열면 기록이 초기화될 수 있습니다.
        - 도핑 정보는 KADA와 WADA의 공식 자료에서 사용자가 직접 확인해야 합니다. 이 앱은 안전 여부를 확정하지 않습니다.
        - 개인 건강 상태, 복용 중인 다른 약과의 상호작용을 진단하지 않습니다. 필요한 경우 의사나 약사에게 문의하세요.
        """
    )
