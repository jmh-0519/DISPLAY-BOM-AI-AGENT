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
from app.views.master_query_page import render_master_query_page
from app.views.bom_view import render_bom_result_table
from app.views.where_used_view import render_where_used_result
import pandas as pd
from app.views.design_change_history_page import render_design_change_history_page
from app.views.design_change_workflow_view import render_design_change_workflow
from app.views.product_cost_scan_view import render_product_cost_scan
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
                    "설계변경 후보 분석·재검증·영향확인·최종 적용·완료 보고서를 요청해 주세요."
                ),
            }
        ]

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(
            uuid.uuid4()
        )


def synchronize_design_change_workflow(workflow: dict) -> None:
    """UI 직접 승인 결과를 채팅 Snapshot과 LangGraph Memory에 반영합니다."""

    context_id = workflow.get("request_id") or workflow.get("analysis_id")
    # Request 생성 전에는 analysis_id, 생성 후에는 request_id를 기준으로 후보분석 패널과
    # 이후 Follow-up Snapshot을 동기화한다.
    for message in st.session_state.messages:
        saved = message.get("workflow") or {}
        saved_context_id = saved.get("request_id") or saved.get("analysis_id")
        if saved_context_id == context_id:
            message["workflow"] = dict(workflow)

    create_agent().update_design_change_state(
        workflow,
        thread_id=st.session_state.thread_id,
    )


PLANT_CODE_RE = re.compile(r"(?<![A-Z0-9])P\d{2,}(?![A-Z0-9])", re.IGNORECASE)
ITEM_CODE_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{2,}[A-Z0-9]*-\d{3,}(?:-\d+)?|\d{4}-\d{6})(?![A-Z0-9])",
    re.IGNORECASE,
)
PLANT_CONTEXT_MARKERS = (
    "bom", "설계변경", "변경", "교체", "대체", "후보", "추가", "삭제", "수량",
    "역방향", "where used", "where-used", "사용된 모델", "포함하는 모델",
    "가지고 있는 모델", "어떤 모델", "어느 모델", "상위 assy", "상위assy", "사용처",
)


def _requires_conversational_plant_gate(user_input: str) -> bool:
    text = str(user_input or "")
    if PLANT_CODE_RE.search(text):
        return False
    normalized = " ".join(text.lower().split())
    return any(marker in normalized for marker in PLANT_CONTEXT_MARKERS)


def _relevant_plant_options(user_input: str) -> list[dict]:
    """Resolve only Plants where the referenced BOM/model/ASSY/material exists.

    Multiple known codes are intersected when possible so a product + material
    question does not surface a Plant that contains only one side of the request.
    """
    if not _requires_conversational_plant_gate(user_input):
        return []
    codes = list(dict.fromkeys(
        match.group(0).upper() for match in ITEM_CODE_RE.finditer(str(user_input or ""))
    ))
    if not codes:
        return []

    client = DisplayBomMcpClient()
    scoped_sets: list[dict[str, dict]] = []
    for code in codes:
        options = client.list_plants(reference_code=code)
        if not options:
            # A new ADD candidate may not be in a BOM yet; an empty code scope must
            # not erase a valid product/old-item scope from the same request.
            continue
        scoped_sets.append({str(row.get("plant_code") or "").upper(): row for row in options})

    if not scoped_sets:
        return []
    common = set(scoped_sets[0])
    for mapping in scoped_sets[1:]:
        common &= set(mapping)
    if not common:
        # Conflicting known target scopes are safer as "no valid Plant" than
        # falling back to every active Plant.
        return []
    first = scoped_sets[0]
    return [first[code] for code in sorted(common)]


def _render_plant_choice_block(message: dict) -> None:
    options = list(message.get("plant_options") or [])
    if not options:
        return
    st.markdown("**요청 대상이 실제 존재하는 PLANT를 선택해 주세요.**")
    st.caption("선택한 PLANT를 원래 요청에 자동 반영하여 업무를 계속합니다.")
    columns = st.columns(min(len(options), 4))
    for index, option in enumerate(options):
        plant_code = str(option.get("plant_code") or "").upper()
        plant_name = str(option.get("plant_name") or "-")
        with columns[index % len(columns)]:
            if st.button(
                f"{plant_code} · {plant_name}",
                key=f"plant_choice_{message.get('id')}_{plant_code}",
                use_container_width=True,
            ):
                st.session_state["pending_plant_selection"] = {
                    "plant_code": plant_code,
                    "plant_name": plant_name,
                    "original_request": message.get("pending_user_request") or "",
                }
                st.rerun()


def _append_agent_response(response: dict, pending_user_request: str | None = None) -> None:
    answer = sanitize_agent_download_links(response["answer"], bool(response.get("artifacts")))
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "artifacts": response.get("artifacts", []),
        "bom_views": response.get("bom_views", []),
        "where_used_views": response.get("where_used_views", []),
        "cost_scan_views": response.get("cost_scan_views", []),
        "plant_options": response.get("plant_options", []),
        "pending_user_request": pending_user_request or "",
        "workflow": response.get("workflow", {}),
        "render_design_change_panel": bool(response.get("render_design_change_panel", False)),
        "suppress_answer": bool(response.get("suppress_answer", False)),
        "id": str(uuid.uuid4()),
    })


def _process_pending_plant_selection() -> None:
    pending = st.session_state.pop("pending_plant_selection", None)
    if not pending:
        return
    plant_code = str(pending.get("plant_code") or "").upper()
    plant_name = str(pending.get("plant_name") or "-")
    original_request = str(pending.get("original_request") or "").strip()
    if not plant_code or not original_request:
        return

    st.session_state.messages.append({
        "role": "user",
        "content": f"PLANT 선택: {plant_code} · {plant_name}",
    })
    agent_input = f"{original_request}\nPLANT는 {plant_code}이야."
    try:
        response = create_agent().run_with_artifacts(
            agent_input,
            thread_id=st.session_state.thread_id,
        )
    except Exception as error:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "요청을 처리하는 중 오류가 발생했습니다.\n\n"
                       f"`{type(error).__name__}: {error}`",
            "id": str(uuid.uuid4()),
        })
    else:
        _append_agent_response(response, pending_user_request=original_request)
    st.rerun()


def render_chat_history() -> None:
    """Session State에 저장된 기존 채팅 내용을 표시합니다."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            bom_views = message.get("bom_views", [])
            workflow = message.get("workflow", {})
            suppress_answer = bool(message.get("suppress_answer", False))
            render_design_change_panel = bool(message.get("render_design_change_panel", False))
            # 후보 분석을 생성한 턴만 구조화 패널을 보여주고, Explain 후속질문은
            # 자연어 답변만 표시하여 기존 후보표를 반복 렌더링하지 않습니다.
            if not suppress_answer:
                st.markdown(message["content"])
            _render_plant_choice_block(message)
            for bom_view in bom_views:
                render_bom_result_table(pd.DataFrame(bom_view))
            for where_used in message.get("where_used_views", []):
                render_where_used_result(where_used)
            for cost_scan in message.get("cost_scan_views", []):
                render_product_cost_scan(cost_scan)
            for index, artifact in enumerate(message.get("artifacts", [])):
                st.download_button(
                    f"{artifact['file_name']} 다운로드",
                    artifact["file_bytes"], file_name=artifact["file_name"],
                    mime=artifact["mime_type"],
                    key=f"history_download_{message.get('id', index)}_{index}",
                )
            if render_design_change_panel:
                render_design_change_workflow(
                    message.get("workflow", {}),
                    on_workflow_update=synchronize_design_change_workflow,
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

            - 제품/ASSY BOM 조회
            - 자재 Where-used(역방향 BOM) 조회
            - 자재·모델 Master 검색
            - 설계변경 후보 분석·재검증·후속질문
            - 후보/공용 영향 확인 후 설계변경 Request 생성
            - 적용 전 최종 확인·승인 후 양산 E-BOM 적용
            - 적용 완료 Word 보고서
            """
        )

        st.divider()

        st.markdown(
            """
            **질문 예시**

            - `LTA400HR01-0의 BOM을 보여줘.`
            - `0001-310501 자재가 사용된 모델을 알려줘.`
            - `LC 자재를 검색해줘.`
            - `제품 목록을 보여줘.`
            - `이 자재가 단종됐어. 변경 가능한 후보를 찾아줘.`
            - `왜 이 후보가 CONDITIONAL이야?`
            """
        )

        st.divider()

        if st.button(
            "대화 초기화",
            width="stretch",
        ):
            clear_chat_history()
            st.rerun()

    _process_pending_plant_selection()
    render_chat_history()

    # Submission is handled in two Streamlit runs.
    #
    # Run 1:
    #   chat_input -> store the user message + pending request -> rerun
    #
    # Run 2:
    #   history already contains the user message -> process the pending
    #   request without rendering another chat input -> append Agent response
    #
    # This keeps the visible order stable even while Azure OpenAI is working:
    #   previous Agent output -> user question -> spinner -> Agent response
    #   -> next chat input.
    user_input = str(st.session_state.pop("_pending_agent_user_input", "") or "").strip()

    if not user_input:
        with st.container():
            submitted = st.chat_input(
                "BOM, 자재 또는 제품에 대해 질문해 주세요."
            )

        if not submitted:
            return

        user_input = str(submitted).strip()
        st.session_state.messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )
        st.session_state["_pending_agent_user_input"] = user_input
        st.rerun()

    # The UI PLANT gate runs before LangGraph, so it must honor the same
    # active-BOM inheritance rule as the Graph Gateway. Otherwise a valid
    # follow-up such as "LJ94-100006 수량 바꾸고싶어" is intercepted here even
    # though the user is already viewing LTA400HR01-001 / P01.
    agent = create_agent()
    inherit_active_bom = agent.can_inherit_active_bom_context(
        user_input,
        thread_id=st.session_state.thread_id,
    )

    if (
        _requires_conversational_plant_gate(user_input)
        and not inherit_active_bom
    ):
        try:
            plant_options = _relevant_plant_options(user_input)
        except Exception as error:
            plant_options = []
            plant_error = error
        else:
            plant_error = None

        if plant_options:
            plant_message = {
                "role": "assistant",
                "content": "PLANT 선택이 필요합니다.",
                "plant_options": plant_options,
                "pending_user_request": user_input,
                "id": str(uuid.uuid4()),
            }
            st.session_state.messages.append(plant_message)
            # Re-render from Session State so the inline chat input is placed
            # below the newly appended PLANT selection response.
            st.rerun()
        if plant_error is not None:
            # MCP 조회 자체가 실패한 경우에만 기존 Agent fallback으로 넘긴다.
            pass

    with st.chat_message("assistant"):
        with st.spinner(
            "Azure OpenAI가 요청을 분석하고 있습니다..."
        ):
            try:
                response = agent.run_with_artifacts(
                    user_input,
                    thread_id=(
                        st.session_state.thread_id
                    ),
                )
                answer = response["answer"]
                artifacts = response["artifacts"]
                bom_views = response.get("bom_views", [])
                cost_scan_views = response.get("cost_scan_views", [])
                workflow = response.get("workflow", {})
                render_design_change_panel = bool(response.get("render_design_change_panel", False))
                suppress_answer = bool(response.get("suppress_answer", False))
                answer = sanitize_agent_download_links(answer, bool(artifacts))

            except Exception as error:
                answer = (
                    "요청을 처리하는 중 오류가 발생했습니다.\n\n"
                    f"`{type(error).__name__}: {error}`"
                )
                st.error(answer)

            else:
                # BOM/후보분석 생성 턴만 중복 LLM 본문을 숨깁니다. Explain/Compare
                # 후속질문은 기존 분석 패널을 반복하지 않고 자연어 답변을 표시합니다.
                if not suppress_answer:
                    st.markdown(answer)
                current_plant_options = response.get("plant_options", [])
                if current_plant_options:
                    _render_plant_choice_block({
                        "id": f"current-{len(st.session_state.messages)}",
                        "plant_options": current_plant_options,
                        "pending_user_request": user_input,
                    })
                for bom_view in bom_views:
                    render_bom_result_table(pd.DataFrame(bom_view))
                for where_used in response.get("where_used_views", []):
                    render_where_used_result(where_used)
                for cost_scan in cost_scan_views:
                    render_product_cost_scan(cost_scan)
                for index, artifact in enumerate(artifacts):
                    st.download_button(
                        f"{artifact['file_name']} 다운로드", artifact["file_bytes"],
                        file_name=artifact["file_name"], mime=artifact["mime_type"],
                        key=f"new_download_{len(st.session_state.messages)}_{index}",
                    )
                if render_design_change_panel:
                    render_design_change_workflow(
                        workflow,
                        on_workflow_update=synchronize_design_change_workflow,
                    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "artifacts": artifacts if 'artifacts' in locals() else [],
            "bom_views": bom_views if 'bom_views' in locals() else [],
            "where_used_views": (response.get("where_used_views", []) if 'response' in locals() else []),
            "cost_scan_views": cost_scan_views if 'cost_scan_views' in locals() else [],
            "plant_options": (response.get("plant_options", []) if 'response' in locals() else []),
            "pending_user_request": user_input,
            "workflow": workflow if 'workflow' in locals() else {},
            "render_design_change_panel": render_design_change_panel if 'render_design_change_panel' in locals() else False,
            "suppress_answer": suppress_answer if 'suppress_answer' in locals() else False,
            "id": str(uuid.uuid4()),
        }
    )

    # The input was rendered before the just-generated response on this run.
    # Re-render once from Session State so the final stable order is always:
    # user -> Agent output/panel -> chat input.
    st.rerun()


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

    # ------------------------------------------------------------------
    # Sidebar navigation
    # ------------------------------------------------------------------
    # Navigation note:
    # Streamlit button/radio/container components each add their own vertical
    # spacing. To keep every menu row at exactly the same height, the sidebar
    # navigation itself is rendered as one HTML block. Only the content pages
    # remain normal Streamlit views.
    view_to_menu = {
        "agent": "Agent 채팅",
        "bom": "BOM",
        "model": "모델",
        "material": "자재",
        "history": "설계변경 이력",
    }
    menu_to_view = {value: key for key, value in view_to_menu.items()}

    requested_view = str(st.query_params.get("view", "agent") or "agent")
    requested_menu = view_to_menu.get(requested_view, "Agent 채팅")
    previous_menu = st.session_state.get("main_menu")

    if previous_menu != requested_menu:
        st.session_state["main_menu"] = requested_menu

        # 설계변경 이력 화면에서 다른 업무로 이동하면 이전에 클릭했던
        # Request 상세 선택 상태를 제거한다.
        if previous_menu == "설계변경 이력" and requested_menu != "설계변경 이력":
            st.session_state.pop(
                "design_change_history_selected_request_id",
                None,
            )
    elif "main_menu" not in st.session_state:
        st.session_state["main_menu"] = requested_menu

    menu = st.session_state.get("main_menu", "Agent 채팅")
    active_view = menu_to_view.get(menu, "agent")

    def _menu_link(label: str, view: str, indent_px: int = 0) -> str:
        is_active = active_view == view
        background = "rgba(151,166,195,0.16)" if is_active else "transparent"
        return (
            f'<a href="?view={view}" target="_self" '
            f'style="display:flex;align-items:center;box-sizing:border-box;'
            f'height:30px;margin:0;padding:0 6px 0 {6 + indent_px}px;'
            f'font-size:14px;font-weight:400;line-height:30px;'
            f'color:inherit;text-decoration:none;border-radius:5px;'
            f'background:{background};">●&nbsp;{label}</a>'
        )

    with st.sidebar:
        st.header("업무")

        menu_html = "".join([
            '<div style="display:flex;flex-direction:column;gap:0;'
            'margin:4px 0 0 0;padding:0;">',
            _menu_link("Agent 채팅", "agent"),
            '<div style="display:flex;align-items:center;box-sizing:border-box;'
            'height:30px;margin:0;padding:0 6px;font-size:14px;'
            'font-weight:400;line-height:30px;">●&nbsp;Master 조회</div>',
            _menu_link("BOM", "bom", 24),
            _menu_link("모델", "model", 24),
            _menu_link("자재", "material", 24),
            _menu_link("설계변경 이력", "history"),
            '</div>',
        ])
        st.html(menu_html)
        st.divider()

    # ------------------------------------------------------------------
    # Page routing
    # ------------------------------------------------------------------
    if menu == "Agent 채팅":
        render_agent_chat()

    elif menu == "BOM":
        render_master_query_page("BOM")

    elif menu == "모델":
        render_master_query_page("모델")

    elif menu == "자재":
        render_master_query_page("자재")

    elif menu == "설계변경 이력":
        render_design_change_history_page()


if __name__ == "__main__":
    main()
