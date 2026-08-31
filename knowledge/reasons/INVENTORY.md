+++
reason_code = "INVENTORY"
reason_name_ko = "재고 문제 대응"
description = "재고 부족·과잉·장기재고 문제 해결"
category = "INVENTORY"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "INVENTORY"]

[[aliases]]
text = "재고"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"

[[scopes]]
target_type = "ASSY"
action_type = "REPLACE"

+++

# 재고 문제 대응

재고 부족·과잉·장기재고 문제 해결.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
