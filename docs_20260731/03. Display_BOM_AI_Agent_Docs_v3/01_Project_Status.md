# 프로젝트 진행 현황

## 프로젝트명

**Display BOM AI Agent**

## 프로젝트 목표

디스플레이 제품의 BOM, 자재 및 제품 데이터를 기반으로 사용자의 자연어 질문을 이해하고 적절한 도구를 실행하여 결과를 제공하는 단일 AI Agent를 구현한다.

초기 버전은 CSV 기반으로 개발하고, 이후 Oracle DB와 Azure OpenAI를 연결할 수 있도록 계층을 분리한다.

## 완료 항목

- Python, VS Code, 가상환경 및 pytest 구성
- 디스플레이 BOM용 합성 데이터 구성
- CSV 기반 `BomService` 구현
- `BaseTool`, `ToolRegistry`, `ToolRequest`, `ToolResponse`, `ToolExecutor` 구현
- `BomTool`, `MaterialTool`, `ProductTool` 구현
- Service, Tool, Registry, Executor 및 데이터 단위 테스트 구성

## 현재 상태

```text
User
  │
  ▼
Agent                 미구현
  │
  ▼
ToolExecutor          완료
  │
  ▼
ToolRegistry          완료
  │
  ▼
BaseTool 구현체       완료
  ├── BomTool
  ├── MaterialTool
  └── ProductTool
  │
  ▼
BomService            완료
  │
  ▼
CSV Data              완료
```

## 다음 단계

다음 단계는 Azure OpenAI 연결 전에 Rule-based `BomAgent`를 구현하는 것이다.

- Agent와 Tool Layer 연결 검증
- LLM 문제와 애플리케이션 문제 분리
- 전체 실행 흐름 안정화
- 향후 LLM Agent로 교체해도 Tool Layer 재사용
