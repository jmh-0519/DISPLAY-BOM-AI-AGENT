+++
reason_code = "SUPPLIER_STOP"
reason_name_ko = "공급 중단 대응"
description = "특정 공급사의 공급 중단에 대응"
category = "SUPPLY"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "SUPPLY"]

[[aliases]]
text = "공급 중단"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[aliases]]
text = "납품 중단"
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

# 공급 중단 대응

특정 공급사의 공급 중단에 대응.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
