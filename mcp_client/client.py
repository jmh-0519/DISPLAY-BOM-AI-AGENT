from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import (
    ClientSession,
    StdioServerParameters,
)
from mcp.client.stdio import stdio_client


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


class DisplayBomMcpClient:
    """
    Display BOM MCP Server 호출을 담당하는 Client입니다.

    역할:
    - MCP Server 연결
    - MCP Tool 목록 조회
    - Azure OpenAI용 Tool Definition 생성
    - MCP Tool 범용 호출
    - BOM / 제품 / 자재 Query Tool 호출
    """

    def __init__(self) -> None:
        self.server_params = (
            StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "mcp_server.server",
                ],
                cwd=str(PROJECT_ROOT),
                # MCP Server는 별도 Process로 실행됩니다.
                # 조회 저장소 선택값을 포함한 현재 실행 환경을 명시적으로
                # 전달해야 Streamlit과 MCP Server가 동일한 Mode를 사용합니다.
                env=os.environ.copy(),
            )
        )

    # =========================================================
    # MCP 공통 기능
    # =========================================================

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        MCP Server의 Tool을 호출합니다.
        """

        tool_error_message: str | None = None

        async with stdio_client(
            self.server_params
        ) as (read, write):

            async with ClientSession(
                read,
                write,
            ) as session:

                await session.initialize()

                result = await session.call_tool(
                    tool_name,
                    arguments=arguments,
                )

                if result.is_error:
                    tool_error_message = (
                        result.content[0].text
                        if result.content
                        else (
                            "MCP Tool 실행 중 "
                            "오류가 발생했습니다."
                        )
                    )

        # MCP/AnyIO TaskGroup 내부에서 예외를 발생시키면 실제 Tool 오류가
        # ExceptionGroup으로 포장됩니다. Session과 stdio가 정상 종료된 뒤
        # 업무 오류를 전달하여 사용자에게 원래 메시지가 보이게 합니다.
        if tool_error_message is not None:
            raise RuntimeError(tool_error_message)

        return result

    async def _list_tools(
        self,
    ):
        """
        MCP Server가 제공하는 Tool 목록을 조회합니다.
        """

        async with stdio_client(
            self.server_params
        ) as (read, write):

            async with ClientSession(
                read,
                write,
            ) as session:

                await session.initialize()

                result = (
                    await session.list_tools()
                )

                return result.tools

    @staticmethod
    def _extract_result(
        result: Any,
    ) -> Any:
        """
        MCP Tool 결과에서 실제 데이터를 추출합니다.
        """

        if result.structured_content:
            structured = (
                result.structured_content
            )

            if "result" in structured:
                return structured[
                    "result"
                ]

            return structured

        if not result.content:
            return None

        text_content = (
            result.content[0]
        )

        if not hasattr(
            text_content,
            "text",
        ):
            return None

        text = text_content.text

        try:
            return json.loads(
                text
            )

        except json.JSONDecodeError:
            return text

    @staticmethod
    def _ensure_list(
        data: Any,
        tool_name: str,
    ) -> list[dict]:
        """
        MCP Query Tool 결과가 list 형식인지 검증합니다.
        """

        if data is None:
            return []

        if not isinstance(
            data,
            list,
        ):
            raise RuntimeError(
                f"{tool_name} 결과가 "
                "예상한 목록 형식이 아닙니다."
            )

        return data

    @staticmethod
    def _ensure_dict(
        data: Any,
        tool_name: str,
    ) -> dict:
        """MCP 분석 Tool 결과가 dict 형식인지 검증합니다."""

        if not isinstance(data, dict):
            raise RuntimeError(
                f"{tool_name} 결과가 예상한 객체 형식이 아닙니다."
            )

        return data

    # =========================================================
    # Agent용 범용 MCP 기능
    # =========================================================

    def get_tool_definitions(
        self,
    ) -> list[dict]:
        """
        MCP Tool 목록을 조회하고
        Azure OpenAI Tool Calling 형식으로 변환합니다.
        """

        return asyncio.run(
            self._get_tool_definitions_async()
        )

    async def _get_tool_definitions_async(
        self,
    ) -> list[dict]:
        """
        MCP Tool Definition을
        Azure OpenAI 형식으로 변환합니다.
        """

        tools = await self._list_tools()

        definitions: list[dict] = []

        for tool in tools:

            parameters = (
                tool.input_schema
                if tool.input_schema
                else {
                    "type": "object",
                    "properties": {},
                }
            )

            definitions.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        tool.description
                        or ""
                    ),
                    "parameters": (
                        parameters
                    ),
                },
            })

        return definitions

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Tool 이름과 arguments를 이용해
        MCP Tool을 범용적으로 호출합니다.
        """

        return asyncio.run(
            self._call_tool_generic_async(
                tool_name,
                arguments,
            )
        )

    async def _call_tool_generic_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        MCP Tool 범용 비동기 호출입니다.
        """

        result = await self._call_tool(
            tool_name,
            arguments,
        )

        return self._extract_result(
            result
        )

    # =========================================================
    # get_bom
    # =========================================================

    def get_bom(
        self,
        product_id: str,
        as_of_date: str | None = None,
        plant_code: str = "P01",
    ) -> list[dict]:
        """
        제품 BOM을 조회합니다.
        """

        return asyncio.run(
            self._get_bom_async(
                product_id=product_id,
                as_of_date=as_of_date,
                plant_code=plant_code,
            )
        )

    async def _get_bom_async(
        self,
        product_id: str,
        as_of_date: str | None = None,
        plant_code: str = "P01",
    ) -> list[dict]:
        """
        MCP get_bom Tool을 호출합니다.
        """

        result = await self._call_tool(
            "get_bom",
            {
                "plant_code": plant_code,
                "product_id": (
                    product_id
                ),
                "as_of_date": (
                    as_of_date
                ),
            },
        )

        data = self._extract_result(
            result
        )

        return self._ensure_list(
            data,
            "get_bom",
        )

    def list_plants(
        self,
        reference_code: str | None = None,
        as_of_date: str | None = None,
    ) -> list[dict]:
        """대상 VERSION/ASSY/MATERIAL이 실제 존재하는 활성 Plant를 조회합니다."""
        args = {}
        if reference_code:
            args["reference_code"] = str(reference_code).strip().upper()
        if as_of_date:
            args["as_of_date"] = as_of_date
        return self._ensure_list(self.call_tool("list_plants", args), "list_plants")

    # =========================================================
    # reverse BOM / master detail
    # =========================================================

    def get_bom_where_used(
        self,
        item_code: str,
        plant_code: str,
        as_of_date: str | None = None,
    ) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_bom_where_used",
            {"item_code": item_code, "plant_code": plant_code, "as_of_date": as_of_date},
        ), "get_bom_where_used")

    def get_product_detail(
        self,
        product_id: str,
        as_of_date: str | None = None,
    ) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_product_detail",
            {"product_id": product_id, "as_of_date": as_of_date},
        ), "get_product_detail")

    def get_item_detail(
        self,
        item_code: str,
        as_of_date: str | None = None,
    ) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_item_detail",
            {"item_code": item_code, "as_of_date": as_of_date},
        ), "get_item_detail")

    # =========================================================
    # list_products
    # =========================================================

    def list_products(
        self,
    ) -> list[dict]:
        """
        전체 제품 목록을 조회합니다.
        """

        return asyncio.run(
            self._list_products_async()
        )

    async def _list_products_async(
        self,
    ) -> list[dict]:

        result = await self._call_tool(
            "list_products",
            {},
        )

        data = self._extract_result(
            result
        )

        return self._ensure_list(
            data,
            "list_products",
        )

    # =========================================================
    # search_product
    # =========================================================

    def search_product(
        self,
        keyword: str,
    ) -> list[dict]:
        """
        제품 ID 또는 제품명으로 검색합니다.
        """

        return asyncio.run(
            self._search_product_async(
                keyword
            )
        )

    async def _search_product_async(
        self,
        keyword: str,
    ) -> list[dict]:

        result = await self._call_tool(
            "search_product",
            {
                "keyword": keyword,
            },
        )

        data = self._extract_result(
            result
        )

        return self._ensure_list(
            data,
            "search_product",
        )

    # =========================================================
    # list_materials
    # =========================================================

    def list_materials(
        self,
    ) -> list[dict]:
        """
        전체 자재 목록을 조회합니다.
        """

        return asyncio.run(
            self._list_materials_async()
        )

    async def _list_materials_async(
        self,
    ) -> list[dict]:

        result = await self._call_tool(
            "list_materials",
            {},
        )

        data = self._extract_result(
            result
        )

        return self._ensure_list(
            data,
            "list_materials",
        )

    # =========================================================
    # search_material
    # =========================================================

    def search_material(
        self,
        keyword: str,
    ) -> list[dict]:
        """
        자재 ID 또는 자재명으로 검색합니다.
        """

        return asyncio.run(
            self._search_material_async(
                keyword
            )
        )

    async def _search_material_async(
        self,
        keyword: str,
    ) -> list[dict]:

        result = await self._call_tool(
            "search_material",
            {
                "keyword": keyword,
            },
        )

        data = self._extract_result(
            result
        )

        return self._ensure_list(
            data,
            "search_material",
        )

    # =========================================================
    # analyze_design_change
    # =========================================================

    def analyze_design_change(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | None = None,
        plant_code: str = "P01",
    ) -> dict:
        """자재 교체 설계변경의 가능 여부와 영향을 분석합니다."""

        return asyncio.run(
            self._analyze_design_change_async(
                product_id=product_id,
                old_material_id=old_material_id,
                new_material_id=new_material_id,
                as_of_date=as_of_date,
                plant_code=plant_code,
            )
        )

    def create_ai_change_request(self, **arguments) -> dict:
        return self._ensure_dict(
            self.call_tool("create_ai_change_request", arguments),
            "create_ai_change_request",
        )

    def create_review_bom(self, **arguments) -> dict:
        return self._ensure_dict(
            self.call_tool("create_review_bom", arguments), "create_review_bom"
        )

    def run_ai_bom_review(self, **arguments) -> dict:
        return self._ensure_dict(
            self.call_tool("run_ai_bom_review", arguments), "run_ai_bom_review"
        )

    def generate_design_change_report(self, change_id: str) -> dict:
        return self._ensure_dict(
            self.call_tool("generate_design_change_report", {"change_id": change_id}),
            "generate_design_change_report",
        )

    @staticmethod
    def _decode_download(data: dict, tool_name: str) -> dict:
        if data.get("success") and data.get("file_data_base64"):
            data = dict(data)
            try:
                data["file_bytes"] = base64.b64decode(
                    data.pop("file_data_base64"), validate=True
                )
            except (ValueError, TypeError) as error:
                raise RuntimeError(f"{tool_name} 파일 데이터가 올바르지 않습니다.") from error
        return data

    def export_bom_excel(
        self, product_id: str, as_of_date: str | None = None, plant_code: str = "P01"
    ) -> dict:
        data = self._ensure_dict(
            self.call_tool("export_bom_excel", {
                "plant_code": plant_code, "product_id": product_id,
                "as_of_date": as_of_date,
            }),
            "export_bom_excel",
        )
        return self._decode_download(data, "export_bom_excel")

    def export_design_change_report(self, change_id: str) -> dict:
        data = self._ensure_dict(
            self.call_tool("export_design_change_report", {"change_id": change_id}),
            "export_design_change_report",
        )
        return self._decode_download(data, "export_design_change_report")

    def export_phase3_completion_report(self, request_id: str) -> dict:
        data = self._ensure_dict(
            self.call_tool("export_phase3_completion_report", {"request_id": request_id}),
            "export_phase3_completion_report",
        )
        return self._decode_download(data, "export_phase3_completion_report")

    def list_design_changes(self) -> list[dict]:
        return self._ensure_list(self.call_tool("list_design_changes", {}), "list_design_changes")

    def get_design_change(self, change_id: str) -> dict:
        return self._ensure_dict(
            self.call_tool("get_design_change", {"change_id": change_id}), "get_design_change"
        )

    def list_bom_reviews(self) -> list[dict]:
        return self._ensure_list(self.call_tool("list_bom_reviews", {}), "list_bom_reviews")

    def get_bom_review(self, review_id: str) -> dict:
        return self._ensure_dict(
            self.call_tool("get_bom_review", {"review_id": review_id}), "get_bom_review"
        )

    def apply_reviewed_bom(self, **arguments) -> dict:
        return self._ensure_dict(
            self.call_tool("apply_reviewed_bom", arguments), "apply_reviewed_bom"
        )

    async def _analyze_design_change_async(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | None = None,
        plant_code: str = "P01",
    ) -> dict:
        result = await self._call_tool(
            "analyze_design_change",
            {
                "plant_code": plant_code,
                "product_id": product_id,
                "old_material_id": old_material_id,
                "new_material_id": new_material_id,
                "as_of_date": as_of_date,
            },
        )

        data = self._extract_result(result)

        return self._ensure_dict(
            data,
            "analyze_design_change",
        )

    # =========================================================
    # create_design_change_preview
    # =========================================================

    def create_design_change_preview(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | None = None,
    ) -> dict:
        """분석 완료 건의 읽기 전용 변경 BOM Preview를 생성합니다."""

        return asyncio.run(
            self._create_design_change_preview_async(
                product_id=product_id,
                old_material_id=old_material_id,
                new_material_id=new_material_id,
                as_of_date=as_of_date,
            )
        )

    async def _create_design_change_preview_async(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | None = None,
    ) -> dict:
        result = await self._call_tool(
            "create_design_change_preview",
            {
                "product_id": product_id,
                "old_material_id": old_material_id,
                "new_material_id": new_material_id,
                "as_of_date": as_of_date,
            },
        )
        return self._ensure_dict(
            self._extract_result(result),
            "create_design_change_preview",
        )

    # =========================================================
    # record_design_change_decision
    # =========================================================

    def record_design_change_decision(
        self,
        preview_revision: str,
        decision: str,
        comment: str | None = None,
    ) -> dict:
        """Preview에 대한 사용자 승인·반려 의사를 기록합니다."""

        return asyncio.run(
            self._record_design_change_decision_async(
                preview_revision=preview_revision,
                decision=decision,
                comment=comment,
            )
        )

    async def _record_design_change_decision_async(
        self,
        preview_revision: str,
        decision: str,
        comment: str | None = None,
    ) -> dict:
        result = await self._call_tool(
            "record_design_change_decision",
            {
                "preview_revision": preview_revision,
                "decision": decision,
                "comment": comment,
            },
        )
        return self._ensure_dict(
            self._extract_result(result),
            "record_design_change_decision",
        )

    def apply_approved_design_change(
        self,
        preview_revision: str,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        preview_as_of_date: str,
        effective_date: str,
        applied_by: str,
    ) -> dict:
        return self.call_tool(
            "apply_approved_design_change",
            {
                "preview_revision": preview_revision,
                "product_id": product_id,
                "old_material_id": old_material_id,
                "new_material_id": new_material_id,
                "preview_as_of_date": preview_as_of_date,
                "effective_date": effective_date,
                "applied_by": applied_by,
            },
        )

    def analyze_design_change_candidates(self, request: dict, actions: list[dict]) -> dict:
        return self._ensure_dict(self.call_tool(
            "analyze_design_change_candidates", {"request": request, "actions": actions}),
            "analyze_design_change_candidates")

    def revalidate_design_change_analysis(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("revalidate_design_change_analysis", arguments),
                                 "revalidate_design_change_analysis")

    def preview_design_change_analysis_impact(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("preview_design_change_analysis_impact", arguments),
                                 "preview_design_change_analysis_impact")

    def create_design_change_request_from_analysis(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("create_design_change_request_from_analysis", arguments),
                                 "create_design_change_request_from_analysis")

    def explain_design_change_analysis_session(self, analysis: dict) -> dict:
        return self._ensure_dict(self.call_tool("explain_design_change_analysis_session", {"analysis": analysis}),
                                 "explain_design_change_analysis_session")

    def explain_design_change_analysis_candidate(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("explain_design_change_analysis_candidate", arguments),
                                 "explain_design_change_analysis_candidate")

    def compare_design_change_analysis_candidates(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("compare_design_change_analysis_candidates", arguments),
                                 "compare_design_change_analysis_candidates")

    def create_design_change_request(self, request: dict, actions: list[dict]) -> dict:
        return self._ensure_dict(self.call_tool(
            "create_design_change_request", {"request": request, "actions": actions}),
            "create_design_change_request")

    def evaluate_replacement_candidates(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("evaluate_replacement_candidates", arguments),
                                 "evaluate_replacement_candidates")

    def select_candidate_and_supplier(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("select_candidate_and_supplier", arguments),
                                 "select_candidate_and_supplier")

    def confirm_candidate_selection(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("confirm_candidate_selection", arguments),
                                 "confirm_candidate_selection")

    def approve_candidate_impact(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("approve_candidate_impact", arguments),
                                 "approve_candidate_impact")

    def submit_candidate_additional_data(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("submit_candidate_additional_data", arguments),
                                 "submit_candidate_additional_data")

    def record_exception_approval(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("record_exception_approval", arguments),
                                 "record_exception_approval")

    def get_change_request_result(self, request_id: str) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_change_request_result", {"request_id": request_id}),
            "get_change_request_result")

    def get_design_change_analysis(self, request_id: str) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_design_change_analysis", {"request_id": request_id}),
            "get_design_change_analysis")

    def get_candidate_evaluation_detail(
        self, request_id: str, candidate_item_code: str, action_id: str | None = None
    ) -> dict:
        return self._ensure_dict(self.call_tool(
            "get_candidate_evaluation_detail", {
                "request_id": request_id,
                "candidate_item_code": candidate_item_code,
                "action_id": action_id,
            }), "get_candidate_evaluation_detail")

    def compare_design_change_candidates(
        self, request_id: str, candidate_item_codes: list[str] | None = None,
        action_id: str | None = None, criterion: str = "SPEC_SIMILARITY"
    ) -> dict:
        return self._ensure_dict(self.call_tool(
            "compare_design_change_candidates", {
                "request_id": request_id,
                "candidate_item_codes": candidate_item_codes,
                "action_id": action_id,
                "criterion": criterion,
            }), "compare_design_change_candidates")

    def create_multi_action_preview(self, request_id: str, created_by: str) -> dict:
        return self._ensure_dict(self.call_tool("create_multi_action_preview", {
            "request_id": request_id, "created_by": created_by}), "create_multi_action_preview")

    def record_final_apply_approval(self, request_id: str, approved_by: str) -> dict:
        return self._ensure_dict(self.call_tool("record_final_apply_approval", {
            "request_id": request_id, "approved_by": approved_by}), "record_final_apply_approval")

    def apply_approved_change_request(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("apply_approved_change_request", arguments),
                                 "apply_approved_change_request")

    def list_rules(self, as_of_date: str | None = None) -> list[dict]:
        return self._ensure_list(self.call_tool("list_rules", {"as_of_date": as_of_date}),
                                 "list_rules")

    def create_rule(self, rule: dict, conditions: list[dict]) -> dict:
        return self._ensure_dict(self.call_tool("create_rule", {
            "rule": rule, "conditions": conditions}), "create_rule")

    def update_rule(self, rule: dict, conditions: list[dict]) -> dict:
        return self._ensure_dict(self.call_tool("update_rule", {
            "rule": rule, "conditions": conditions}), "update_rule")

    def deactivate_rule(self, rule_id: str, revision_no: int) -> dict:
        return self._ensure_dict(self.call_tool("deactivate_rule", {
            "rule_id": rule_id, "revision_no": revision_no}), "deactivate_rule")

    def list_phase3_change_history(self) -> list[dict]:
        return self._ensure_list(self.call_tool("list_phase3_change_history", {}),
                                 "list_phase3_change_history")

    def record_performance_outcome(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("record_performance_outcome", arguments),
                                 "record_performance_outcome")

    def export_training_dataset(self, **arguments) -> dict:
        return self._ensure_dict(self.call_tool("export_training_dataset", arguments),
                                 "export_training_dataset")
