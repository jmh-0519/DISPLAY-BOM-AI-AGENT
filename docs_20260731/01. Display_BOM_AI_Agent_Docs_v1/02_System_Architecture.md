# 시스템 아키텍처

## 1. 전체 구조

```text
사용자
  ↓
Streamlit UI
  ↓
BOM AI Agent
  ↓
Tool Registry
  ↓
Tool Executor
  ↓
개별 Tool
  ↓
Service
  ↓
CSV → SQLite → Oracle
```

## 2. 계층별 책임

### Streamlit UI

- 사용자 입력 수집
- 대화와 표 표시
- 오류 및 진행 상태 표현
- Session State 관리

### BOM AI Agent

- 사용자 의도 해석
- 사용할 Tool 선택
- Tool 입력값 구성
- 실행 결과를 자연어로 설명

### Tool Registry

- 사용 가능한 Tool 등록
- Tool 이름으로 검색
- LLM에 제공할 Tool 메타데이터 생성

### Tool Executor

- Tool 존재 여부 확인
- 입력 검증
- 실행 및 예외 처리
- 실행 로그와 시간 측정
- 결과 형식 표준화

### Tool

- Agent가 호출할 수 있는 업무 기능 제공
- 명확한 이름, 설명, 입력 스키마 보유
- Service를 호출해 결과 반환

### Service

- BOM 도메인 조회와 데이터 가공
- 데이터 소스 세부 구현을 상위 계층에서 격리

### Data Source / Repository

- CSV, SQLite, Oracle 등 실제 저장소 접근
- 향후 Repository Pattern 적용 검토

## 3. 핵심 데이터 흐름

예: "PRD-LED-43-A의 BOM을 보여줘"

1. UI가 질문을 Agent에 전달한다.
2. Agent가 `get_bom` Tool을 선택한다.
3. Executor가 `parent_id`를 검증한다.
4. Tool이 `BomService.get_bom()`을 호출한다.
5. Service가 CSV를 조회하고 자재 정보를 결합한다.
6. Tool 결과가 Agent로 전달된다.
7. Agent가 근거와 함께 결과를 설명한다.
8. UI가 표와 답변을 표시한다.

## 4. 현재 아키텍처의 특징

- Single Agent
- Tool 기반 명시적 기능 호출
- LLM과 비즈니스 로직 분리
- 데이터 소스 교체 가능성 확보
- 독립적인 단위 테스트 가능

## 5. 향후 발전 방향

- Repository 인터페이스 도입
- Oracle 조회 구현
- 구조화된 Tool Result 모델
- 권한 및 정책 검사 계층
- 관찰 가능성 강화
- 필요 시 RAG 또는 MCP 연계
