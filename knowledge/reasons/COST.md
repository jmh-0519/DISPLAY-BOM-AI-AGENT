+++
reason_code = "COST"
reason_name_ko = "원가 절감"
description = "구매비 또는 제조비 절감"
category = "COST"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "COST"]

[[aliases]]
text = "원가"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[aliases]]
text = "단가 절감"
language = "KO"
match_type = "KEYWORD"
priority = 20

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

[[scopes]]
target_type = "ASSY"
action_type = "REPLACE"

+++

# 원가 절감

구매비 또는 제조비 절감.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
