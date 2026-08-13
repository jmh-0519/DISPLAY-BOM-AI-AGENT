# LLM Tool Calling

## 핵심 개념
LLM이 Tool을 직접 실행하는 것이 아니다.

LLM의 역할:
1. 사용자 질문 이해
2. 적절한 Tool 선택
3. Tool arguments 생성

실제 Tool 실행은 Application이 담당한다.

## 실행 흐름

```text
사용자
↓
Azure OpenAI
↓
Tool 선택
↓
Tool arguments
↓
ToolRequest
↓
ToolExecutor
↓
Business Tool
↓
BomService
↓
CSV
```

## 실제 예제

사용자: `PRD-LED-43-A의 BOM을 보여줘.`

LLM 판단:
```json
{
  "tool": "get_bom",
  "arguments": {"product_id": "PRD-LED-43-A"}
}
```

## Tool 결과 재전달

```text
LLM Tool 선택
↓
Tool 실행
↓
실제 데이터
↓
LLM 재호출
↓
자연어 답변
```
