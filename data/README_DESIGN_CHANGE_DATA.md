# Design Change Data Schema

## design_changes.csv
설계변경 요청/분석/승인/실제 적용 상태를 관리하는 Header 데이터입니다.

### 주요 상태값
- analysis_result: PASS / CONDITIONAL / FAIL
- approval_status: PENDING / APPROVED / REJECTED
- apply_status: REQUESTED / READY / APPLIED / FAILED / CANCELLED

### 적용 정책 예시
- FAIL: 적용 불가
- PASS + APPROVED: 실제 적용 가능
- CONDITIONAL + APPROVED: 검토 승인 후 적용 가능
- PENDING: 실제 BOM 적용 금지

## design_change_items.csv
하나의 설계변경(change_id)에 포함된 실제 BOM 변경 관계를 관리하는 Detail 데이터입니다.

- action: REPLACE / ADD / REMOVE
- bom_parent: 변경 대상 관계의 Parent
- old_bom_child: 변경 전 Child
- new_bom_child: 변경 후 Child
- location: BOM 위치
- sequence_no: 동일 Parent 내 순서
- quantity: Parent 1개 기준 Child 직접 수량
- effective_date: 해당 변경 관계의 적용 시작일

## BOM 적용 원칙
실제 BOM 적용 시 기존 bom.csv 행은 삭제하지 않습니다.
기존 관계의 end_date를 effective_date - 1일로 종료하고,
신규 관계를 effective_date부터 새 행으로 생성합니다.

Assembly REPLACE 시에는 대상 모델 경로에서 Parent -> 신규 Assembly 관계만 변경합니다.
신규 Assembly의 하위 subtree는 bom.csv에 이미 정의된 Assembly BOM 구조를 참조합니다.
