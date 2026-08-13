# 06. Tool Architecture

## Tool Registry
Tool 이름과 Tool 객체를 연결한다.

## Tool Executor
Tool 실행을 담당하고 로그, 예외 처리를 수행한다.

## Tool
하나의 업무만 수행한다.

## Service
CSV 또는 Oracle에서 데이터를 조회한다.

## Tool과 Service 차이
|Tool|Service|
|---|---|
|업무|데이터 조회|

---
## 변경 이력
### 2026-07-31
- Registry/Executor 설명 추가
