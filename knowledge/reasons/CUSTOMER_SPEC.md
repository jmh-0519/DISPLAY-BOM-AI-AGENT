+++
reason_code = "CUSTOMER_SPEC"
reason_name_ko = "고객 사양 대응"
description = "고객 요구사항 신규 또는 변경 대응"
category = "SPECIFICATION"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "SPECIFICATION"]

[[aliases]]
text = "고객 사양"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[scopes]]
target_type = "MATERIAL"
action_type = "ADD"

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

[[scopes]]
target_type = "ASSY"
action_type = "ADD"

[[scopes]]
target_type = "ASSY"
action_type = "REPLACE"

+++

# 고객 사양 대응

고객 요구사항 신규 또는 변경 대응.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
