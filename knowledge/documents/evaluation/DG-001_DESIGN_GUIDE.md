+++
document_id = "DG-001"
document_title = "DRIVE-IC 대체 전기 호환 설계 가이드"
document_type = "DESIGN_GUIDE"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["LCD"]
material_types = ["DRIVE-IC"]
tags = ["DESIGN_CHANGE", "REPLACE", "DRIVE_IC", "ELECTRICAL"]

[attributes]
owner = "DISPLAY_ENGINEERING"
authority = "REFERENCE"
+++

# DRIVE-IC 대체 전기 호환 설계 가이드

## 목적

DRIVE-IC 대체 검토에서 전기적 인터페이스와 구동 조건을 확인하기 위한 참고 가이드다. 실제 적합성 판정은 구조화 RuleEngine과 BOM/자재 데이터가 결정하며, 이 문서는 검토 항목과 설명 근거를 제공한다.

## 전기 호환 확인

대체 후보는 인터페이스 방식, 동작 전압 범위, 신호 레벨, 채널 구성, 타이밍 요구사항을 기존 적용품과 비교한다. LVDS와 같은 인터페이스 특성은 단순 명칭 일치만 보지 않고 제품 회로가 요구하는 연결 조건과 함께 검토한다. 전기 조건이 명확하지 않으면 후보를 확정하지 않고 추가 근거를 요청한다.

## 검토 기록

분석 결과에는 비교한 핵심 전기 조건과 확인되지 않은 항목을 구분해 남긴다. RAG 근거는 설계자가 이해하기 위한 참고이며 PASS/CONDITIONAL/FAIL 결과를 직접 생성하지 않는다.
