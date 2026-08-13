from pathlib import Path
import re
import sys
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from core.skill_loader import SkillLoader
from mcp_client.client import DisplayBomMcpClient

from agents.bom_agent_graph import BomAgentGraph
from app.views.bom_query_page import render_bom_query_page
from app.views.ai_design_change_workflow_page import render_ai_design_change_workflow_page
from app.views.design_change_history_page import render_design_change_history_page
from app.views.bom_review_history_page import render_bom_review_history_page
from core.azure_openai_client import AzureOpenAIClient
from core.settings import Settings


@st.cache_resource
def create_agent() -> BomAgentGraph:
    """
    Streamlit 애플리케이션에서 사용할
    BomAgentGraph를 생성합니다.
    """

    settings = Settings.from_env()

    azure_client = AzureOpenAIClient(
        settings
    )

    mcp_client = DisplayBomMcpClient()

    skill_loader = SkillLoader(
        PROJECT_ROOT / "skills"
    )

    skill_context = skill_loader.load_many(
        [
            "bom-query",
            "bom-design-change",
        ]
    )

    return BomAgentGraph(
        client=azure_client,
        mcp_client=mcp_client,
        skill_context=skill_context,
    )


def initialize_session_state() -> None:
    """채팅 메시지와 LangGraph 대화 ID를 초기화합니다."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "안녕하세요. Display BOM AI Agent입니다.\n\n"
                    "제품 BOM 조회, 자재·제품 검색, "
                    "설계변경 분석·Review BOM 생성·AI 품평·보고서·최종 적용을 요청해 주세요."
                ),
            }
        ]

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(
            uuid.uuid4()
        )


def render_chat_history() -> None:
    """Session State에 저장된 기존 채팅 내용을 표시합니다."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for index, artifact in enumerate(message.get("artifacts", [])):
                st.download_button(
                    f"{artifact['file_name']} 다운로드",
                    artifact["file_bytes"], file_name=artifact["file_name"],
                    mime=artifact["mime_type"],
                    key=f"history_download_{message.get('id', index)}_{index}",
                )


def clear_chat_history() -> None:
    """채팅 기록과 LangGraph 대화 Memory를 초기화합니다."""
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "대화가 초기화되었습니다.\n\n"
                "새로운 질문을 입력해 주세요."
            ),
        }
    ]

    st.session_state.thread_id = str(
        uuid.uuid4()
    )


def sanitize_agent_download_links(answer: str, has_artifacts: bool) -> str:
    """Streamlit에서 열 수 없는 내부 sandbox 링크를 답변에서 제거합니다."""
    if not has_artifacts:
        return answer
    cleaned = re.sub(r"\[([^\]]+)\]\(sandbox:[^)]+\)", r"\1", answer)
    cleaned = re.sub(r"sandbox:/\S+", "", cleaned)
    return cleaned.strip()


def render_agent_chat() -> None:
    """기존 Agent 채팅 화면을 표시합니다."""
    initialize_session_state()

    with st.sidebar:
        st.markdown(
            """
            **지원 기능**

            - 제품 BOM 조회
            - 자재 검색
            - 제품 검색
            - 설계변경 분석 및 변경 예정 BOM
            - Review BOM 생성과 AI 체크리스트 검증
            - 보고서 확인 후 양산 E-BOM 최종 적용
            """
        )

        st.divider()

        st.markdown(
            """
            **질문 예시**

            - `LTA400HR01-0의 BOM을 보여줘.`
            - `LC 자재를 검색해줘.`
            - `제품 목록을 보여줘.`
            - `변경 요청으로 Review BOM을 만들어줘.`
            - `AI 품평 결과 보고서를 생성해줘.`
            """
        )

        st.divider()

        if st.button(
            "대화 초기화",
            width="stretch",
        ):
            clear_chat_history()
            st.rerun()

    render_chat_history()

    user_input = st.chat_input(
        "BOM, 자재 또는 제품에 대해 질문해 주세요."
    )

    if not user_input:
        return

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input,
        }
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner(
            "Azure OpenAI가 요청을 분석하고 있습니다..."
        ):
            try:
                agent = create_agent()
                response = agent.run_with_artifacts(
                    user_input,
                    thread_id=(
                        st.session_state.thread_id
                    ),
                )
                answer = response["answer"]
                artifacts = response["artifacts"]
                answer = sanitize_agent_download_links(answer, bool(artifacts))

            except Exception as error:
                answer = (
                    "요청을 처리하는 중 오류가 발생했습니다.\n\n"
                    f"`{type(error).__name__}: {error}`"
                )
                st.error(answer)

            else:
                st.markdown(answer)
                for index, artifact in enumerate(artifacts):
                    st.download_button(
                        f"{artifact['file_name']} 다운로드", artifact["file_bytes"],
                        file_name=artifact["file_name"], mime=artifact["mime_type"],
                        key=f"new_download_{len(st.session_state.messages)}_{index}",
                    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "artifacts": artifacts if 'artifacts' in locals() else [],
            "id": str(uuid.uuid4()),
        }
    )


def main() -> None:
    st.set_page_config(
        page_title="Display BOM AI Agent",
        page_icon="🤖",
        layout="wide",
    )

    st.title("Display BOM AI Agent")
    st.caption(
        "Azure OpenAI 기반 Display BOM 업무 지원 Agent"
    )

    with st.sidebar:
        st.header("메뉴")

        menu = st.radio(
            "업무 선택",
            [
                "Agent 채팅",
                "BOM 조회",
                "AI 설계변경 Workflow",
                "설계변경 이력",
                "품평회 이력",
            ],
        )

        st.divider()

    if menu == "Agent 채팅":
        render_agent_chat()

    elif menu == "BOM 조회":
        render_bom_query_page()

    elif menu == "AI 설계변경 Workflow":
        render_ai_design_change_workflow_page()

    elif menu == "설계변경 이력":
        render_design_change_history_page()

    elif menu == "품평회 이력":
        render_bom_review_history_page()


if __name__ == "__main__":
    main()
