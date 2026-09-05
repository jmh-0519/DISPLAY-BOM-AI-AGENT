# Read-only Text-to-SQL

Text-to-SQL은 Display BOM AI Agent의 관계형 데이터 Analytics 계층입니다.

## Authority Model

- LLM: 허용된 Schema Context를 사용해 SQL candidate 생성
- `SqlSchemaCatalog`: 승인된 business-read schema만 노출
- SQL Guard: multi-statement / DDL / DML / 금지 객체 차단
- `ReadOnlySqlExecutor`: SQLite read-only / query_only / authorizer / timeout / row cap 적용
- SQLite: 결과 데이터의 factual authority

Workflow / Approval / Apply 등 변경 권한이 필요한 테이블은 Text-to-SQL allowlist에서 제외합니다.

## Runtime Flow

```text
Natural Language
  ↓
SqlSchemaCatalog
  ↓
Azure SQL Generation Model
  ↓
Structured SQL / UNSUPPORTED
  ↓
Read-only SQL Guard
  ↓
ReadOnlySqlExecutor
  ↓
Result Evidence
```

BOM Scope가 명확한 Cost/Commonality 분석은 가능한 경우 deterministic scoped SQL을 우선하여 불필요한 SQL-generation LLM call을 줄입니다.

## Commands

```powershell
python -m scripts.validate_text_to_sql_foundation
python -m scripts.smoke_test_text_to_sql_readonly
python -m scripts.smoke_test_text_to_sql_generation
python -m scripts.run_text_to_sql_generation_evaluation --strict
```

## v4.0 Evaluation

```text
Cases                  23
SQL Cases              15
UNSUPPORTED Cases      8
Overall Accuracy       100.00%
Status Accuracy        100.00%
Execution Success      100.00%
Semantic Result Match  100.00%
UNSUPPORTED Accuracy   100.00%
P95 Latency            1720.17 ms
Gate                   PASS
```
