# 시스템 아키텍처

## 전체 구조

```mermaid
flowchart TD
    U[사용자] --> A[BomAgent]
    A --> E[ToolExecutor]
    E --> R[ToolRegistry]
    R --> BT[BomTool]
    R --> MT[MaterialTool]
    R --> PT[ProductTool]
    BT --> S[BomService]
    MT --> S
    PT --> S
    S --> D[(CSV Data)]
```

## 계층별 책임

### Agent Layer
사용자 입력을 분석하고 어떤 Tool을 실행할지 결정한다. 현재는 미구현이며 다음 단계에서 Rule-based Agent를 구현한다.

### Tool Layer
Agent가 업무 기능을 호출할 수 있도록 표준 인터페이스를 제공한다. Tool은 비즈니스 로직을 직접 구현하지 않고 Service에 위임한다.

### Service Layer
BOM, 자재, 제품 데이터를 조회하는 업무 로직을 수행한다. 현재는 CSV 기반이며 이후 Oracle Repository로 교체할 수 있다.

### Data Layer
합성 CSV 데이터를 저장한다.

## 요청 처리 흐름

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant Executor as ToolExecutor
    participant Registry as ToolRegistry
    participant Tool
    participant Service as BomService
    participant Data as CSV

    User->>Agent: 자연어 질문
    Agent->>Executor: ToolRequest
    Executor->>Registry: Tool 이름으로 조회
    Registry-->>Executor: Tool 인스턴스
    Executor->>Tool: execute(**arguments)
    Tool->>Service: 업무 메서드 호출
    Service->>Data: 데이터 조회
    Data-->>Service: 조회 결과
    Service-->>Tool: 결과
    Tool-->>Executor: 결과
    Executor-->>Agent: ToolResponse
    Agent-->>User: 최종 응답
```

## 향후 확장 Tool

- `WhereUsedTool`
- `CompareBomTool`
- `ImpactAnalysisTool`
- `ValidationTool`
- `EngineeringChangeTool`
