+++
document_id = "FAQ-001"
document_title = "FAQ - CONDITIONAL과 FAIL 후보에 점수와 순위를 표시하지 않는 이유"
document_type = "FAQ"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = []
tags = ["FAQ", "CONDITIONAL", "FAIL", "SCORE", "RANK"]

[attributes]
owner = "PLM_PROCESS"
authority = "REFERENCE"
+++

# FAQ - CONDITIONAL과 FAIL 후보에 점수와 순위를 표시하지 않는 이유

## 질문

왜 CONDITIONAL 또는 FAIL 후보에는 점수와 순위를 표시하지 않나요?

## 답변

점수와 순위는 후보가 기본 적용 가능 범위에 있을 때 비교 편의를 위해 사용한다. CONDITIONAL은 추가 확인이 필요하고 FAIL은 적용 불가이므로 숫자 순위가 사용자를 오도할 수 있다. 따라서 PASS에만 공개 score/grade/rank를 허용한다.
