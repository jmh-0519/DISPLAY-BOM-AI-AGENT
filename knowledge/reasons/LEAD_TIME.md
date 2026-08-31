+++
reason_code = "LEAD_TIME"
reason_name_ko = "납기 개선"
description = "조달 또는 생산 납기 단축"
category = "SUPPLY"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "SUPPLY"]

[[aliases]]
text = "납기"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[aliases]]
text = "LEAD TIME"
language = "EN"
match_type = "KEYWORD"
priority = 20

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

[[scopes]]
target_type = "ASSY"
action_type = "REPLACE"

+++

# 납기 개선

조달 또는 생산 납기 단축.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
