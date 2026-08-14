from app.streamlit_app import sanitize_agent_download_links
from agents.bom_agent_graph import BomAgentGraph
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import json


def test_sanitize_agent_download_links_when_real_artifact_exists():
    answer = "[보고서 다운로드](sandbox:/mnt/data/report.docx)"
    cleaned = sanitize_agent_download_links(answer, True)
    assert cleaned == "보고서 다운로드"
    assert "sandbox:" not in cleaned


def test_keep_normal_answer_without_artifact():
    answer = "일반 조회 결과입니다."
    assert sanitize_agent_download_links(answer, False) == answer


def test_agent_extracts_structured_bom_view():
    rows = [{"root_code": "LJ94-100004", "root_type": "ASSEMBLY", "bom_title": "ASSY BOM"}]
    message = ToolMessage(content=json.dumps(rows), tool_call_id="call-1", name="get_bom")
    assert BomAgentGraph._extract_bom_views([message]) == [rows]


def test_bom_view_is_stored_separately_from_llm_answer():
    """BOM Tool 데이터는 Streamlit 공통 Renderer가 사용할 별도 구조로 유지합니다."""
    rows = [{
        "root_code": "LTA400HR01-001",
        "root_type": "VERSION",
        "bom_title": "제품 BOM",
        "bom_parent": "LTA400HR01-001",
        "bom_child": "LJ94-100001",
    }]
    message = ToolMessage(content=json.dumps(rows), tool_call_id="call-2", name="get_bom")
    views = BomAgentGraph._extract_bom_views([message])
    assert views == [rows]
    assert bool(views) is True


def test_current_turn_messages_survives_checkpoint_message_merge():
    old_tool = ToolMessage(content="[]", tool_call_id="old", name="get_bom")
    rows = [{"root_code": "LTA400HR01-001", "bom_title": "제품 BOM"}]
    current_tool = ToolMessage(
        content=json.dumps(rows), tool_call_id="new", name="get_bom"
    )
    messages = [
        HumanMessage(content="이전 질문"), old_tool, AIMessage(content="이전 답변"),
        HumanMessage(content="LTA400HR01-001의 BOM을 보여줘"),
        AIMessage(content="", tool_calls=[{
            "name": "get_bom", "args": {"product_id": "LTA400HR01-001"},
            "id": "new", "type": "tool_call",
        }]),
        current_tool, AIMessage(content="LLM 임의 표"),
    ]
    current = BomAgentGraph._current_turn_messages(
        messages, "LTA400HR01-001의 BOM을 보여줘"
    )
    assert current[0].content == "LTA400HR01-001의 BOM을 보여줘"
    assert BomAgentGraph._extract_bom_views(current) == [rows]


def test_bom_result_title_query_is_normalized_to_common_query():
    query = "제품 BOM BOM 조회 대상 코드: LTA400HR01-001"
    assert BomAgentGraph._normalize_bom_query(query) == (
        "LTA400HR01-001의 BOM을 보여줘"
    )


def test_assy_bom_query_is_normalized_to_common_query():
    assert BomAgentGraph._normalize_bom_query("LJ94-100004 ASSY BOM 조회") == (
        "LJ94-100004의 BOM을 보여줘"
    )


def test_non_bom_or_multiple_code_query_is_not_rewritten():
    normal = "BOM 관리 기준을 알려줘"
    comparison = "LJ94-100004와 LJ94-100005의 BOM을 비교해줘"
    assert BomAgentGraph._normalize_bom_query(normal) == normal
    assert BomAgentGraph._normalize_bom_query(comparison) == comparison
