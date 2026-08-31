+++
reason_code = "COMMONIZATION"
reason_name_ko = "부품 공용화"
description = "모델 간 자재 또는 ASSY 통합"
category = "COMMONIZATION"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "COMMONIZATION"]

[[aliases]]
text = "공용화"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[aliases]]
text = "공통화"
language = "KO"
match_type = "KEYWORD"
priority = 20

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

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
action_type = "QUANTITY_CHANGE"

+++

# 부품 공용화

모델 간 자재 또는 ASSY 통합.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
