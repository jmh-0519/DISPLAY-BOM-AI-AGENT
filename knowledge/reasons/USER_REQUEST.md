+++
reason_code = "USER_REQUEST"
reason_name_ko = "사용자 요청"
description = "사용자가 별도 업무 사유를 명시하지 않은 직접 설계변경 요청"
category = "GENERAL"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "GENERAL"]

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

[[scopes]]
target_type = "MATERIAL"
action_type = "ADD"

[[scopes]]
target_type = "MATERIAL"
action_type = "DELETE"

[[scopes]]
target_type = "MATERIAL"
action_type = "QUANTITY_CHANGE"

[[scopes]]
target_type = "ASSY"
action_type = "REPLACE"

[[scopes]]
target_type = "ASSY"
action_type = "ADD"

[[scopes]]
target_type = "ASSY"
action_type = "DELETE"

[[scopes]]
target_type = "ASSY"
action_type = "QUANTITY_CHANGE"

+++

# 사용자 요청

사용자가 별도 업무 사유를 명시하지 않은 직접 설계변경 요청.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
