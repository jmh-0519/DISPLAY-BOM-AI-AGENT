# Next Step Roadmap

## 현재
Single-step LLM Tool Calling Agent 완료.

지원 기능:
- BOM 조회
- 자재 검색
- 제품 검색
- Streamlit Chat UI

## Phase 1 - Conversation Memory
이전 사용자/Agent 대화를 다음 요청의 Context로 사용한다.

예:
```text
사용자: LED 제품을 찾아줘.
Agent: 43A와 55A가 있습니다.
사용자: 첫 번째 제품 BOM 보여줘.
```

이전 검색 결과를 이용해 첫 번째 제품을 식별할 수 있어야 한다.

## Phase 2 - Multi-step Tool Calling
한 요청에서 여러 Tool을 순차적으로 실행한다.

## Phase 3 - Planning
사용자의 업무 요청을 여러 Step으로 분해한다.

예:
```text
LED 제품을 찾아 BOM을 확인하고 조건부 승인 자재를 점검해줘.
```

Plan:
1. search_product
2. get_bom
3. approval status 검증
4. 결과 정리

## Phase 4 - BOM 설계변경 Workflow
설계변경 기준 확인 → 대상 검색 → 변경 영향 분석 → BOM 변경 → 검증

## Phase 5 - 품평회
변경된 BOM을 품평회 기준으로 자동 점검한다.

## Phase 6 - 보고서
설계변경 및 품평회 결과를 기반으로 완료 보고서를 자동 생성한다.

## 최종 목표
Planning + Tool + Memory를 사용하는 Single AI Agent로 BOM 설계변경 업무를 수행하고, 품평회 점검과 완료 보고서 작성까지 연결한다.
