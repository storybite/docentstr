import streamlit as st
import base64
import re, datetime, time
import asyncio
import streamlit as st
import threading
from concurrent.futures import Future
from reservation.reservation_agent import ReservationAgent
from docent import DocentBot

# Streamlit 페이지 설정
st.set_page_config(page_title="도슨트 봇", page_icon="🎭", layout="centered")

# CSS를 사용하여 메시지 너비 조절 & 우측 고정 박스 유지
st.markdown(
    """
    <style>        
        .stSidebar {
            width: 35rem !important;
        }          
        
        .intro-text {
            text-align: center; 
            padding: 20px; 
            margin-top: 20px; 
            border-radius: 10px; 
            background-color: #f9f9f9; 
            color: #333333;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        .relic-card {
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .relic-header {
            font-weight: bold;
            font-size: 18px;
            color: #333;
            margin-top: -20px;
        }

        .relic-title {
            font-weight: bold;
            font-size: 18px;
            margin-bottom: 15px;
            color: #333;
        }

        /* 채팅 메시지 컨테이너의 최대 너비 조정 */
        .stChatInput {
            margin-left: -5rem;
        }

         .stSpinner {
            position: fixed;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);            
            margin: 0 auto;
            width: 350px;
            font-size: 20px;
            font-weight: bold;
            background-color: #f0f0f0; /* 스피너 배경색 추가 */
            padding: 10px; /* 배경색이 잘 보이도록 패딩 추가 */
            border-radius: 5px; /* 모서리 둥글게 */
            z-index: 9999; /* 최상단에 위치 */
        }
        
        .disable_overlay {
            position: fixed;
            top: 0; 
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 9998; 
            background-color: rgba(0,0,0,0);
            box-shadow: 2px 2px 10px rgba(0,0,0,0);
        }

       
    </style>
    """,
    unsafe_allow_html=True,
)

how_to_use = """
### 사용 방법
1. 작품에 대해 궁금한 점을 입력해주세요
2. AI 도슨트가 전문적인 설명을 제공합니다

### 예시 질문
- 이 작품의 작가는 누구인가요?
- 작품의 제작 기법에 대해 설명해주세요
- 작품의 역사적 배경은 무엇인가요?
- 작품에 담긴 상징적 의미는 무엇인가요?
"""


def on_progress(func):
    overlay_placeholder = st.empty()
    overlay_placeholder.markdown(
        """
        <div class="disable_overlay"></div>
        """,
        unsafe_allow_html=True,
    )
    with st.spinner("잠시만 기다려주세요."):
        result = func()

    overlay_placeholder.empty()
    return result


# 1) 앱 전체에서 단 한 번만 실행되는 이벤트 루프
@st.cache_resource(show_spinner=False)
def _get_loop() -> asyncio.AbstractEventLoop:
    """
    • 새로운 이벤트 루프를 만들고
    • 별도 데몬 스레드에서 run_forever 로 영원히 돌린다.
    Streamlit 스크립트가 재실행되어도 이 루프는 그대로 유지된다.
    """
    loop = asyncio.new_event_loop()  # 새 루프
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop


# 2) 아무 코루틴이든 스레드-세이프하게 던져 주는 헬퍼
def run_async(coro) -> Future:
    """
    • `coro` (async 함수 호출 결과)를 백그라운드 루프에 스케줄.
    • concurrent.futures.Future 를 즉시 반환하므로
      Streamlit 쪽에서는 동기 코드처럼 상태를 확인할 수 있다.
    """
    loop = _get_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop)


# 자원 캐싱 → ReservationAgent도 한 번만 생성
@st.cache_resource(show_spinner=False)
def get_reservation_agent():
    agent = ReservationAgent()
    # SSE 연결을 백그라운드에서 시작 (불-앤-포겟)
    # SSE 연결을 이벤트 루프에서 실행
    future = run_async(agent.connect_sse_server())
    return agent, future


def check_background_jobs():
    """ThreadPoolExecutor에서 돌아가는 작업(Future)의 결과·예외를 표시하고 정리한다."""
    future_resv = st.session_state.get("future_resv")
    if not future_resv:  # 처리 중인 예약이 없으면 바로 종료
        return

    if not future_resv.done():  # 아직 끝나지 않았으면 잠깐만 스피너로 표시
        with st.spinner("예약 처리 중…"):
            time.sleep(0.1)  # 0.1초 정도면 렌더링 부하 거의 없음
        return

    # 여기까지 왔으면 작업이 끝난 상태이므로 결과·예외를 꺼낸다
    exc = future_resv.exception()
    if exc:
        st.error(f"예약 처리 중 오류: {exc}")
    else:
        st.success("예약이 성공적으로 처리됐습니다!")

    # 한 번 표시했으면 세션 상태에서 제거해서 다음 렌더링 땐 안 보이게
    del st.session_state["future_resv"]


check_background_jobs()
resv_agent, future = get_reservation_agent()


def init_page():

    # 사이드바 설정
    with st.sidebar:
        st.markdown(how_to_use)

    # 카드 형태의 안내문구
    st.markdown(
        """
        <div class="intro-text">
            <h2>e-뮤지엄 도슨트 챗봇입니다</h2>
            <p>안녕하세요! 저희 e-뮤지엄에 오신 것을 환영합니다.<p>
            <p>
                저는 e-박물관에서 일하는 도슨트 챗봇이에요.
                이곳에서는 500여 여종의 대한민국 국보/보물 이미지를 보관하고 있습니다. 역사와 배경은 물론 저의 감상까지도 자세히 말씀드려요!
            </p>
            <p>
                아래의 <strong>'입장하기'</strong> 버튼을 눌러 투어를 시작해 보세요!
            </p>            
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3개의 컬럼으로 나눈 후 가운데에만 버튼을 배치하여 중앙 정렬
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        if st.button("입장하기", use_container_width=True, type="primary"):
            print("입장하기 버튼이 클릭되었습니다.")
            st.session_state.entered = True
            docent_bot = DocentBot()
            st.session_state.docent_bot = docent_bot
            on_progress(lambda: docent_bot.move(is_next=True))
            st.session_state.relic_card = docent_bot.relics.current_to_card()
            st.rerun()


def main_page():

    docent_bot: DocentBot = st.session_state.docent_bot

    def side_bar():
        # 사이드바 설정
        with st.sidebar:

            header, img_path, title = (
                st.session_state.relic_card["header"],
                st.session_state.relic_card["img_path"],
                st.session_state.relic_card["title"],
            )

            with open(img_path, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode()

            st.markdown(
                f'<div class="relic-card">'
                f'<div class="relic-header">{header}</div>'
                f'<img src="data:image/png;base64,{img_base64}" style="width:450px; height:540px; object-fit:contain;">'
                f'<div class="relic-title">{title}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

            _, col_left, _, col_right, _ = st.columns(
                [5, 5, 1, 5, 5]
            )  # 네비게이션 버튼
            with col_left:
                if st.button("이전", use_container_width=True):
                    print("이전 버튼이 클릭되었습니다.")
                    on_progress(lambda: docent_bot.move(is_next=False))
                    st.session_state.relic_card = docent_bot.relics.current_to_card()
                    st.rerun()

            with col_right:
                if st.button("다음", use_container_width=True):
                    print("다음 버튼이 클릭되었습니다.")
                    on_progress(lambda: docent_bot.move(is_next=True))
                    st.session_state.relic_card = docent_bot.relics.current_to_card()
                    st.rerun()

            st.markdown(
                """     
                <div style="font-size: 0.87em; text-align: center;">
                본 이미지는 <strong>국립중앙박물관</strong>이 공공누리 제1유형으로 개방한 자료로서<br><a href="https://www.museum.go.kr">museum.go.kr</a>에서 무료로 다운로드 받을 수 있습니다.
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("---")
            st.markdown(how_to_use)

            with st.form("docent_program_form"):
                st.subheader("도슨트 프로그램 신청")

                program = st.selectbox(
                    label="프로그램을 선택하세요.",
                    options=[
                        "대표 유물 해설",
                        "전시관별 해설",
                        "외국인을 위한 해설(영어)",
                        "외국인을 위한 해설(중국어)",
                        "외국인을 위한 해설(일본어)",
                    ],
                    disabled=st.session_state.get("form_submitted", False),
                )

                tomorrow = datetime.date.today() + datetime.timedelta(days=1)
                weekday_map = ["월", "화", "수", "목", "금"]
                weekdays = []
                d = tomorrow
                while len(weekdays) < 10:
                    if d.weekday() < 5:  # 0~4: 월~금
                        weekdays.append(
                            f"{d.strftime('%Y-%m-%d')} ({weekday_map[d.weekday()]})"
                        )
                    d += datetime.timedelta(days=1)

                visit_date = st.selectbox(
                    label="방문 일자를 선택하세요",
                    options=weekdays,
                    disabled=st.session_state.get("form_submitted", False),
                )

                visit_hours = st.selectbox(
                    label="방문 시간을 선택하세요",
                    options=["11:00", "13:00", "15:00"],
                    disabled=st.session_state.get("form_submitted", False),
                )

                visitors = st.number_input(
                    label="방문 인원수를 입력하세요",
                    min_value=1,
                    value=1,
                    disabled=st.session_state.get("form_submitted", False),
                )

                applicant_email = st.text_input(
                    label="신청자 이메일을 입력하세요",
                    value="heyjin337@gmail.com",
                    disabled=st.session_state.get("form_submitted", False),
                )

                submitted = st.form_submit_button(
                    label="신청하기",
                    disabled=st.session_state.get("form_submitted", False),
                )
                if submitted:
                    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                    if not re.match(email_pattern, applicant_email):
                        st.error("유효한 이메일 주소를 입력해주세요.")
                        return

                    st.session_state.form_submitted = True
                    application = {
                        "program": program,
                        "visit_date": visit_date,
                        "visit_hours": visit_hours,
                        "visitors": visitors,
                        "applicant_email": applicant_email,
                    }
                    # ① 아직 연결 중이라면: 메시지만 띄우고 함수 종료``
                    if not future.done():
                        st.error(
                            "SSE 서버에 연결 중입니다. 연결이 완료되면 다시 '신청하기'를 눌러 주세요."
                        )
                        return

                    if future.done() and future.exception():
                        st.error(f"SSE 서버 연결 실패: {future.exception()}")
                        return

                    run_async(resv_agent.make_reservation(application))
                    try:
                        st.session_state.future_resv = run_async(
                            st.session_state.resv_agent.make_reservation(application)
                        )
                    except Exception as e:
                        st.error("예약 처리 중 예외 발생: " + str(e))

                    st.success("신청이 완료되었습니다!")
                    st.rerun()
                else:

                    st.markdown(
                        "🔔도슨트가 배정되면 이메일로 알려드립니다.  \n🚨부득이한 사정으로 취소해야 할 경우 방문일 전일까지 배정된 도슨트님의 이메일로 통지 부탁드립니다."
                    )

    def chat_area():
        for message in docent_bot.get_conversation():
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_message = st.chat_input("메시지를 입력하세요.")
        if user_message:
            with st.chat_message("user"):
                st.markdown(user_message)
            docent_answer = on_progress(lambda: docent_bot.answer(user_message))
            with st.chat_message("assistant"):
                st.markdown(docent_answer)

    side_bar()
    chat_area()


if "entered" not in st.session_state:
    init_page()
else:
    main_page()
