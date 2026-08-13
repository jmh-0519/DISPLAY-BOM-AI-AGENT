# Tool 아키텍처

## 1. Tool의 정의

Tool은 Agent가 호출할 수 있는 명시적인 업무 기능이다. 각 Tool은 이름, 설명, 입력 스키마, 실행 로직, 출력 계약을 가진다.

## 2. 초기 Tool 목록

| Tool | 목적 | 주요 입력 |
|---|---|---|
| `get_product` | 제품 정보 조회 | `product_id` |
| `search_material` | 자재 ID 또는 이름 검색 | `keyword` |
| `get_bom` | 상위 ID의 직계 BOM 조회 | `parent_id` |

## 3. 향후 Tool

- `explode_bom`
- `where_used`
- `compare_bom`
- `validate_bom`
- `get_change_history`
- `analyze_change_impact`

## 4. Tool 공통 계약

각 Tool은 최소한 아래 정보를 제공한다.

- `name`: 고유 이름
- `description`: 언제 사용하는지 명확한 설명
- `input_schema`: 입력 타입과 필수 여부
- `execute()`: 실제 실행

## 5. Registry의 책임

- Tool 등록
- 중복 이름 차단
- 이름으로 Tool 조회
- LLM용 Tool 스키마 생성
- 사용 가능한 Tool 목록 제공

## 6. Executor의 책임

- 요청한 Tool의 존재 확인
- 입력값 검증
- 실행 시간 측정
- 예외 처리
- 로그 기록
- 공통 출력 형식 반환

## 7. 권장 출력 형식

```json
{
  "success": true,
  "tool_name": "get_bom",
  "message": "BOM 6건을 조회했습니다.",
  "data": [],
  "metadata": {
    "row_count": 6,
    "execution_ms": 12
  },
  "error": null
}
```

## 8. Tool 설계 체크리스트

- Tool 이름이 동사 중심으로 명확한가?
- 설명만 보고 LLM이 사용 시점을 구분할 수 있는가?
- 입력이 최소화되어 있는가?
- 빈 값과 잘못된 값이 검증되는가?
- 비즈니스 로직이 LLM 프롬프트에만 존재하지 않는가?
- 단위 테스트가 가능한가?
- 민감한 동작에 권한 검사가 있는가?

## 9. Tool 설계 템플릿

```markdown
### Tool 이름

- 목적:
- 사용 조건:
- 입력:
- 출력:
- 예외:
- 호출 Service:
- 테스트 케이스:
- 보안 고려사항:
```
