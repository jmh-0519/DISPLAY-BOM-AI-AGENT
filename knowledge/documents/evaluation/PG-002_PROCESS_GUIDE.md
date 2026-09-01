+++
document_id = "PG-002"
document_title = "공용 ASSY 영향 확인 절차"
document_type = "PROCESS_GUIDE"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = ["ASSY"]
tags = ["PROCESS", "COMMON_ASSY", "IMPACT", "WHERE_USED"]

[attributes]
owner = "PLM_PROCESS"
authority = "REFERENCE"
+++

# 공용 ASSY 영향 확인 절차

## 공용 여부 확인

변경 대상이 ASSY이거나 공용 자재이면 where-used와 적용 모델 범위를 확인해 단독 사용인지 공용 사용인지 구분한다.

## 영향 범위

공용 ASSY 변경은 요청 모델 외 다른 모델이나 BOM에 영향을 줄 수 있으므로 영향 범위를 사용자에게 명시한다. 자동으로 다른 모델의 Production BOM을 수정하지 않는다.

## 사용자 확인

공용 영향이 존재하면 Request 생성 전에 변경 범위와 동기화 필요성을 확인한다. 명시적 승인 없는 범위 확대는 허용하지 않는다.
