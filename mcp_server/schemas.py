from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


ChangeReasonCode = Literal[
    "EOL",
    "SUPPLIER_STOP",
    "LEAD_TIME",
    "COST",
    "INVENTORY",
    "QUALITY",
    "CUSTOMER_SPEC",
    "REGULATION",
    "COMMONIZATION",
]


class Phase3ChangeRequestInput(TypedDict):
    """Phase3 설계변경 요청의 MCP 입력 계약입니다.

    version_code와 plant_code만 업무 대상 식별에 필수입니다. 날짜, 수요 출처,
    표준 reason_code는 Service가 원문/DB를 기준으로 안전하게 보완할 수 있습니다.
    복수 사유는 reasons에 모두 보존될 수 있으며 Service가 Primary/Secondary를 확정합니다.
    """

    version_code: str
    plant_code: Literal["P01", "P02", "P03", "P04"]
    reasons: NotRequired[list[ChangeReasonCode]]
    as_of_date: NotRequired[str]
    effective_date: NotRequired[str]
    demand_source: NotRequired[Literal[
        "USER",
        "PRODUCTION_PLAN",
        "UNAVAILABLE",
    ]]
    requested_by: NotRequired[str]
    request_id: NotRequired[str]
    original_request: NotRequired[str]
    normalized_request: NotRequired[str]
    demand_quantity: NotRequired[float | None]


class Phase3ChangeActionInput(TypedDict):
    """Phase3 설계변경 Action의 MCP 입력 계약입니다.

    target_type/parent/location은 기존 품목과 제품 BOM 관계에서 Service가
    결정할 수 있으므로 자연어 요청에서 명확하지 않으면 생략할 수 있습니다.
    REPLACE 후보 추천의 new_item_code는 생략하며 후보를 동적으로 탐색합니다.
    ADD도 후보 탐색 요청에서는 new_item_code를 생략할 수 있고 target_type을 기준으로
    활성 Rule/Item Master에서 전체 후보를 평가합니다. 실제 Request 생성 시에는 사용자가
    선택한 ADD 후보가 new_item_code로 확정됩니다.
    """

    action_type: Literal[
        "REPLACE",
        "ADD",
        "DELETE",
        "QUANTITY_CHANGE",
    ]
    target_type: NotRequired[Literal["MATERIAL", "ASSY"]]
    target_item_name: NotRequired[str]
    parent_item_code: NotRequired[str]
    reason_code: NotRequired[ChangeReasonCode]
    action_id: NotRequired[str]
    old_item_code: NotRequired[str]
    new_item_code: NotRequired[str]
    location_code: NotRequired[str]
    old_quantity: NotRequired[float]
    new_quantity: NotRequired[float]
