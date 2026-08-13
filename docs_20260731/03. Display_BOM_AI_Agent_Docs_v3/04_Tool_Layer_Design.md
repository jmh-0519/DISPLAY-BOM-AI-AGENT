# Tool Layer 상세 설계

## BaseTool

공통 속성:

- `name`
- `description`
- `input_schema`

공통 메서드:

- `execute()`
- `get_definition()`

`get_definition()`은 향후 Azure OpenAI Tool Calling 정의 생성에 사용된다.

## ToolRegistry

Tool 인스턴스를 이름으로 관리한다.

```text
{
  "get_bom": BomTool(...),
  "search_material": MaterialTool(...),
  "search_product": ProductTool(...)
}
```

주요 기능:

- `register(tool)`
- `get(name)`
- `get_all()`
- `contains(name)`

## ToolRequest

```python
ToolRequest(
    tool_name="get_bom",
    arguments={"product_id": "OLED55-A100"},
)
```

## ToolResponse

```python
ToolResponse(
    success=True,
    tool_name="get_bom",
    data=[...],
    error=None,
    execution_time_ms=1.25,
)
```

## ToolExecutor

1. `ToolRequest` 수신
2. Registry에서 Tool 검색
3. 실행 시간 측정
4. Tool의 `execute()` 호출
5. 정상 또는 실패 `ToolResponse` 반환

## 업무 Tool

### BomTool
- 이름: `get_bom`
- 입력: `product_id`
- 위임: `BomService.get_bom(product_id)`

### MaterialTool
- 이름: `search_material`
- 입력: `keyword`
- 위임: `BomService.search_material(keyword)`

### ProductTool
- 이름: `search_product`
- 입력: `keyword`
- 위임: `BomService.search_product(keyword)`

## 설계 원칙

- Tool은 CSV를 직접 읽지 않는다.
- 복잡한 업무 로직을 포함하지 않는다.
- 입력값을 검증한다.
- Service에 처리를 위임한다.
- Azure OpenAI 호환 JSON Schema를 제공한다.
