# STEP40-H – Action Validation Styling & Model-only Impact Preview

## Changes
- Action 검증 표의 `변경 전`, `변경 전 수량`은 파란색 Bold로 표시합니다.
- Action 검증 표의 `변경 후`, `변경 후 수량`은 빨간색 Bold로 표시합니다.
- Workflow의 `전체 영향 Preview`에서는 TARGET/PARENT_ASSY 전체 상위 경로를 노출하지 않고 최상위 VERSION/MODEL만 표시합니다.
- 전체 영향 경로 데이터 자체는 삭제하지 않으며 DB/Workflow Evidence에는 그대로 보존합니다.
- MODEL 코드가 직접 VERSION Parent인 ADD처럼 Preview impact가 TARGET만 생성되는 경우 Request의 version_code를 최상위 MODEL로 표시합니다.
