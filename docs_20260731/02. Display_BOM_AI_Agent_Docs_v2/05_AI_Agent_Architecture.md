# 05. AI Agent Architecture

## Agent의 역할
- 사용할 Tool 결정
- 입력값 생성
- 결과를 자연어로 반환

예시:

사용자: OLED55-A100 모델의 BOM을 보여줘.

판단:
```json
{"tool_name":"get_bom","arguments":{"product_id":"OLED55-A100"}}
```

Agent는 직접 데이터를 조회하지 않는다.

---
## 변경 이력
### 2026-07-31
- Agent 책임 명확화
