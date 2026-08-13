# Change Log

## v3

### 추가

- `ProductTool` 설계 및 테스트
- Tool Layer 상세 설계
- 테스트 전략
- 현재 파일 구조
- Rule-based `BomAgent` 구현 계획
- Azure OpenAI Tool Calling 확장 방향

### 변경

- 테스트 정책을 단위 테스트 중심으로 정리
- Agent 구현 전 중복 통합 테스트를 만들지 않도록 결정
- `test_bom_tool_integration.py`, `test_material_tool_integration.py`를 제거 가능 파일로 분류
- 프로젝트 상태를 Business Tool 완료 단계로 갱신

### 현재 완료

- `BaseTool`
- `ToolRegistry`
- `ToolRequest`
- `ToolResponse`
- `ToolExecutor`
- `BomTool`
- `MaterialTool`
- `ProductTool`
- 관련 pytest 단위 테스트

### 다음 버전 예정

- Rule-based `BomAgent`
- `test_bom_agent.py`
- Agent와 Tool Layer 통합 흐름
