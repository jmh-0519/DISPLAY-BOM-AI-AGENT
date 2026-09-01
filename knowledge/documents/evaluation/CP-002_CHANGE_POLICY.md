+++
document_id = "CP-002"
document_title = "조건부 및 부적합 후보 처리 정책"
document_type = "CHANGE_POLICY"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = []
tags = ["POLICY", "CONDITIONAL", "FAIL", "SCORE", "CANDIDATE"]

[attributes]
owner = "PLM_GOVERNANCE"
authority = "REFERENCE"
+++

# 조건부 및 부적합 후보 처리 정책

## 평가 등급

후보 평가는 PASS, CONDITIONAL, FAIL로 구분한다. 최종 판정은 RuleEngine과 구조화 업무 데이터가 결정한다.

## 점수 공개

PASS 후보는 비교를 위한 score, grade, rank를 표시할 수 있다. CONDITIONAL과 FAIL은 확정적인 점수나 순위를 공개하지 않는다.

## 적용 제한

FAIL 후보는 Production 적용 대상으로 확정할 수 없다. CONDITIONAL 후보는 필요한 추가 확인이나 예외 승인 조건을 명확히 제시한다.
