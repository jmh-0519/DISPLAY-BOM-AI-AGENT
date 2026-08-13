# v7 Current Status and Next Step

## 1. 오늘까지의 핵심 성과

### Backend
- Design Change Analysis
- Compatibility 검증
- BOM Rule 검증
- Preview/Apply 기반 Service
- Review / Revalidation
- Review Check Result 저장/교체

### UI
- Agent Chat 유지
- 설계변경 전용 화면
- 검증결과 한글화
- Preview BOM
- 계층형 BOM Tree Viewer

### Test
기능 추가 과정에서 pytest 회귀 테스트를 반복 수행하여 기존 기능과 신규 기능의 동작을 확인했다.

## 2. BOM Tree Viewer Baseline

현재 Viewer의 UI 원칙:

- Parent/Child 계층 표시
- Parent 접기/펼치기
- Parent 코드: 파란색 + Bold
- Parent 자재명: Bold
- 일반 자재: 일반 표시
- Tree 연결선 및 마지막 Child 종료 표현
- Tree/들여쓰기는 자재코드 컬럼에만 적용
- 자재명/구분/수량은 고정 컬럼
- 동일 Parent의 Child끼리만 정렬
- 일반 자재 → Assembly
- 같은 종류는 자재코드 오름차순

## 3. v6 방향과의 차이
원래 Roadmap에서는 MCP Foundation을 Design Change 구현보다 먼저 진행하도록 계획했다.

실제 개발은:
```text
Architecture
↓
Design Change Service
↓
Apply/Preview
↓
Review
↓
Streamlit UI
```

순으로 진행되었다.

이는 목표 아키텍처 위반은 아니다. 다만 MCP / Skill / Planner 계층보다 Domain Service가 먼저 구현된 것이다.

오히려 다음 단계에서는 검증된 Service를 MCP로 감싸는 방식으로 위험을 줄일 수 있다.

## 4. 다음 작업
다음 개발의 1순위는 **MCP Foundation**으로 권장한다.

완료 조건:
- Display BOM MCP Server 기본 구조
- MCP Client
- 기존 Query Capability 노출
- analyze_design_change 노출
- apply_design_change 노출
- evaluate_bom_review 노출
- MCP 호출 테스트

그 다음 Skill / Planner / Workflow State를 연결한다.
