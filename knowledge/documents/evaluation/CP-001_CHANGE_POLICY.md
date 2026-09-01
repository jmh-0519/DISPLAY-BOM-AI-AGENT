+++
document_id = "CP-001"
document_title = "설계변경 승인 단계 정책"
document_type = "CHANGE_POLICY"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = []
tags = ["POLICY", "APPROVAL", "REQUEST", "PREVIEW", "APPLY"]

[attributes]
owner = "PLM_GOVERNANCE"
authority = "REFERENCE"
+++

# 설계변경 승인 단계 정책

## 단계 분리

Analysis와 Design Change Request는 동일한 상태가 아니다. 분석 중에는 후보와 영향도를 검토하며 Request 번호를 생성하지 않는다.

## Request 생성

사용자가 분석안을 확정하고 설계변경 진행을 승인한 시점에 최초 Request를 생성한다. 이후 Preview에서 실제 변경 예정 내용을 확인한다.

## 최종 승인

Production E-BOM 반영은 별도의 설계변경 확정 이후에만 수행한다. 분석 승인만으로 Production Apply가 실행되어서는 안 된다.
