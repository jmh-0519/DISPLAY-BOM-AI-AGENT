# 목표 업무 Workflow

## 프로젝트 역할

BOM AI Agent는 기존 BOM 시스템의 모든 화면과 다사용자 결재를 복제하지 않는다. 설계변경 분석, Review BOM 생성, 정형 체크리스트 검증, 설명 가능한 판정, 보고서 작성을 자동화한다.

## 실행 순서

1. 사용자가 모델, 기존/신규 자재, 변경 사유, 적용 예정일을 입력한다.
2. Agent가 E-BOM 포함 여부, 자재 상태, Compatibility, BOM Rule을 분석한다.
3. 통과 건을 변경 요청으로 등록하고 변경 예정 BOM Snapshot을 생성한다.
4. Snapshot을 Review BOM Rev.1로 생성한다.
5. Agent가 기존 Rule 기반 체크리스트를 자동 실행하고 항목별 근거를 저장한다.
6. PASS이면 적용 전 보고서를 생성한다. CONDITIONAL은 확인 대기, FAIL은 차단한다.
7. 사용자가 화면 또는 다운로드 파일로 보고서를 확인한다.
8. 사용자가 양산 반영을 명시 승인하면 승인된 Review BOM Revision만 E-BOM에 적용한다.

## 상태

```text
CHANGE_REQUESTED
→ REVIEW_BOM_CREATED
→ AI_REVIEW_COMPLETED
→ REPORT_COMPLETED
→ WAITING_FINAL_APPLY
→ CHANGE_COMPLETED
```

예외 상태는 `ANALYSIS_FAILED`, `REVIEW_NEEDS_CONFIRMATION`, `REVIEW_FAILED`, `APPLY_FAILED`이다.

## 최종 통제 원칙

보고서 다운로드 자체는 승인이 아니다. 화면의 확인 체크와 적용 버튼 또는 대화에서 사용자의 명시적 적용 요청이 있어야만 Production E-BOM을 변경한다.

