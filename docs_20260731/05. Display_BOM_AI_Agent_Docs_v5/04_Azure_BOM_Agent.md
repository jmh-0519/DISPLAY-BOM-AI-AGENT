# AzureBomAgent

## 목적
Azure OpenAI Tool Calling과 기존 Tool Layer를 하나의 Agent 실행 흐름으로 통합한다.

## 실행 인터페이스
```python
agent.run(user_input)
```

## 처리 과정
1. 사용자 입력 검증
2. Tool Definition 조회
3. Azure OpenAI 호출
4. Tool Call 분석
5. ToolRequest 생성
6. ToolExecutor 실행
7. Tool 결과 직렬화
8. Azure OpenAI 재호출
9. 최종 자연어 답변 반환

## 기존 Agent와 비교

| 구분 | BomAgent | AzureBomAgent |
|---|---|---|
| Tool 선택 | Python Rule | LLM |
| 자연어 이해 | 제한적 | LLM |
| Tool 실행 | ToolExecutor | ToolExecutor |
| 최종 답변 | ToolResponse | LLM 자연어 |
| Azure 필요 | X | O |
