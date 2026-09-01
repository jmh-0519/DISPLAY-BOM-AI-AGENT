+++
document_id = "PG-001"
document_title = "설계변경 분석 및 후보 재검증 절차"
document_type = "PROCESS_GUIDE"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = []
tags = ["PROCESS", "ANALYSIS", "REVALIDATION", "CANDIDATE"]

[attributes]
owner = "PLM_PROCESS"
authority = "REFERENCE"
+++

# 설계변경 분석 및 후보 재검증 절차

## 분석 시작

자연어 요청을 구조화해 Action, Target, Reason, Model/Plant 범위를 확인한 뒤 분석을 시작한다. 분석 단계에서는 Request를 생성하지 않고 Production BOM을 변경하지 않는다.

## 후보 검토

REPLACE 또는 ADD에서 후보가 필요한 경우 현재 BOM 사실과 RuleEngine 평가를 사용한다. 사용자가 조건을 바꾸거나 후보를 재검토하면 동일 Analysis Session 안에서 재검증 결과를 누적할 수 있다.

## 분석 종료

사용자가 분석안을 선택하고 설계변경 진행을 명시적으로 승인하기 전까지 Request 생성 단계로 넘어가지 않는다.
