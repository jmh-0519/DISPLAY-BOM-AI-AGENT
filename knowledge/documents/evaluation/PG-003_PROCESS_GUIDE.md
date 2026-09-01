+++
document_id = "PG-003"
document_title = "Production BOM 적용 및 Rollback 절차"
document_type = "PROCESS_GUIDE"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = []
tags = ["PROCESS", "APPLY", "ROLLBACK", "TRANSACTION"]

[attributes]
owner = "PLM_PROCESS"
authority = "REFERENCE"
+++

# Production BOM 적용 및 Rollback 절차

## 적용 전

Request와 Preview가 확정되고 사용자가 설계변경 확정을 수행한 경우에만 Production E-BOM 적용을 시작한다.

## 원자적 적용

Production 반영은 하나의 트랜잭션으로 처리한다. 일부 자재만 변경되고 나머지가 실패하는 부분 적용을 허용하지 않는다.

## 실패 처리

적용 중 오류가 발생하면 전체 변경을 Rollback하고 기존 BOM 상태를 유지한다. 완료 이력에는 성공 또는 실패 결과와 적용 근거를 남긴다.
