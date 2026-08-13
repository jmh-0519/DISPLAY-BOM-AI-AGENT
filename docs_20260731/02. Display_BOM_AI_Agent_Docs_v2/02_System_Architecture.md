# 02. System Architecture

## 목적
Display BOM AI Agent의 전체 시스템 구조를 정의한다.

## 전체 시스템 구조

```text
User
↓
BOM Agent
↓
Tool Executor
↓
Tool Registry
↓
Tool
↓
Service
↓
CSV / Oracle
```

## 요청 처리 흐름
1. Agent가 질문을 분석한다.
2. Tool을 결정한다.
3. Executor가 실행을 관리한다.
4. Registry가 Tool을 찾는다.
5. Tool이 Service를 호출한다.
6. Service가 데이터를 조회한다.
7. 결과를 사용자에게 반환한다.

---
## 변경 이력
### 2026-07-31
- 전체 처리 흐름 반영
