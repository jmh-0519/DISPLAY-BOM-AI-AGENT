+++
reason_code = "EOL"
reason_name_ko = "단종 대응"
description = "품목의 생산 또는 공급 수명 종료에 대응"
category = "LIFECYCLE"
status = "ACTIVE"
valid_from = "2026-01-01"
tags = ["DESIGN_CHANGE", "LIFECYCLE"]

[[aliases]]
text = "단종"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[aliases]]
text = "생산 종료"
language = "KO"
match_type = "KEYWORD"
priority = 20

[[aliases]]
text = "END OF LIFE"
language = "EN"
match_type = "KEYWORD"
priority = 20

[[aliases]]
text = "OBSOLETE"
language = "EN"
match_type = "KEYWORD"
priority = 20

[[aliases]]
text = "DISCONTINUED"
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

# 단종 대응

품목의 생산 또는 공급 수명 종료에 대응.

이 문서는 설계변경 사유의 구조화 메타데이터와 RAG 설명 근거를 함께 관리한다.
