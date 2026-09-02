from langchain_core.messages import HumanMessage

from agents.bom_text_to_sql_nodes import BomTextToSqlPathNodes
from text_to_sql.pipeline import TextToSqlPipelineResult


class FakePipeline:
    def __init__(self, result):
        self.result = result
        self.questions = []

    def run(self, question):
        self.questions.append(question)
        return self.result


def test_runtime_node_formats_sql_result_without_second_llm():
    pipeline = FakePipeline(
        TextToSqlPipelineResult(
            status="SQL",
            question="공급사별 평균 단가",
            sql="SELECT ...",
            reason="",
            columns=("supplier_code", "avg_unit_price"),
            rows=(
                {"supplier_code": "SUP-101", "avg_unit_price": 120.5},
                {"supplier_code": "SUP-102", "avg_unit_price": 130.0},
            ),
            row_count=2,
            truncated=False,
            elapsed_ms=1.0,
        )
    )
    node = BomTextToSqlPathNodes(pipeline=pipeline)

    state = node.query({
        "messages": [HumanMessage(content="공급사별 평균 자재 단가를 알려줘")],
        "user_query": "공급사별 평균 자재 단가를 알려줘",
    })

    answer = state["messages"][-1].content
    assert pipeline.questions == ["공급사별 평균 자재 단가를 알려줘"]
    assert "총 2건" in answer
    assert "SUP-101" in answer
    assert "avg_unit_price" in answer
    assert "SELECT" not in answer


def test_runtime_node_returns_user_safe_message_for_unsupported_result():
    node = BomTextToSqlPathNodes(
        pipeline=FakePipeline(
            TextToSqlPipelineResult(
                status="UNSUPPORTED",
                question="q",
                sql=None,
                reason="현재 읽기 전용 분석 범위에서 지원하지 않습니다.",
            )
        )
    )
    state = node.query({
        "messages": [HumanMessage(content="공급사별 평균 자재 단가를 알려줘")],
        "user_query": "공급사별 평균 자재 단가를 알려줘",
    })
    assert "지원하지 않습니다" in state["messages"][-1].content
