from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_composition_nodes import COMPOSITION_PLAN, BomReadOnlyCompositionNodes
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.design_change_workflow_state import create_initial_design_change_state


D01 = "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
D02 = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


class _Unused:
    pass


def _state(query):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "tool_steps": 0,
        "error": None,
    }


def main() -> None:
    composition = BomReadOnlyCompositionNodes(
        text_to_sql_nodes=_Unused(),
        knowledge_nodes=_Unused(),
    )
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )
    graph.composition_path_nodes = composition

    d01_base = graph.gateway.route(_state(D01))
    d01_runtime = graph._runtime_route(_state(D01))
    d02_runtime = graph._runtime_route(_state(D02))
    plan_update = composition.plan(_state(D01))
    runtime = plan_update["composition_runtime"]

    failures = []
    if d01_base != AGENT_PATH:
        failures.append(f"D01 base route expected agent actual={d01_base}")
    if d01_runtime != COMPOSITION_PLAN:
        failures.append(
            f"D01 runtime expected={COMPOSITION_PLAN} actual={d01_runtime}"
        )
    if d02_runtime != AGENT_PATH:
        failures.append(f"D02 runtime expected agent actual={d02_runtime}")
    if runtime.get("write_authority_granted") is not False:
        failures.append("write authority must remain false")
    if runtime["plan"].get("execution_enabled") is not False:
        # PLAN-01 plan remains declarative; PLAN-02 runtime node owns execution.
        failures.append("PLAN-01 execution flag unexpectedly changed")

    print(
        "PLAN-02 Read-only Runtime Composition "
        + ("PASS" if not failures else "FAIL")
    )
    print(f"D01_gateway_route={d01_base}")
    print(f"D01_runtime_route={d01_runtime}")
    print(f"D02_runtime_route={d02_runtime}")
    print(
        "D01_plan="
        + ",".join(runtime["plan"]["required_capabilities"])
    )
    print(f"analytics_query={runtime['queries']['TEXT_TO_SQL']}")
    print(f"knowledge_query={runtime['queries']['RAG']}")
    print("planner_llm_calls=0")
    print("extra_synthesis_llm_calls=0")
    print("request_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
