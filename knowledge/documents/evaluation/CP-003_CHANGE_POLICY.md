+++
document_id = "CP-003"
document_title = "공용화 및 모델 범위 변경 정책"
document_type = "CHANGE_POLICY"
version = "1.0"
effective_date = "2026-09-01"
status = "ACTIVE"
language = "KO"
product_families = ["DISPLAY"]
material_types = ["ASSY", "BRACKET"]
tags = ["POLICY", "COMMONIZATION", "MODEL_SCOPE", "COMMON_ASSY"]

[attributes]
owner = "PLM_GOVERNANCE"
authority = "REFERENCE"
+++

# 공용화 및 모델 범위 변경 정책

## 범위 원칙

모델과 PLANT가 명확한 요청은 해당 범위를 우선한다. 공용 부품이라는 이유만으로 요청되지 않은 모델까지 자동 확대하지 않는다.

## 공용화 변경

공용화를 목적으로 자재 또는 ASSY를 변경할 때는 현재 사용처와 대상 모델의 BOM 구조를 확인한다.

## 동기화

여러 모델에서 동일 ASSY를 공유하는 경우 설계 의도상 동기화가 필요한지 사용자 확인을 거친다. 시스템은 영향 범위를 설명하되 승인 권한을 대신하지 않는다.
