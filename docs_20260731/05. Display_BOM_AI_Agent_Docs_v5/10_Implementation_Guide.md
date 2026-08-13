# Implementation Guide

## v5 개발 순서
1. Azure API Key 발급 및 Gateway 정보 확인
2. Settings 환경설정
3. AzureOpenAIClient 연결
4. 일반 Chat Completion 테스트
5. Tool Definition을 Azure 형식으로 변환
6. Azure OpenAI Tool 선택 테스트
7. Tool Call → ToolRequest 변환
8. ToolExecutor 연결
9. 실제 CSV 조회
10. Tool 결과 Azure 재전달
11. 최종 자연어 답변 생성
12. AzureBomAgent로 통합
13. Agent 단위 테스트
14. Streamlit UI 연결
15. Streamlit import 경로 문제 해결
16. get_bom 검증
17. search_material 검증
18. search_product Service 구현 및 검증

## 현재 실행 예

Agent 직접 실행:
```powershell
python -m scripts.run_azure_bom_agent
```

Streamlit 실행:
```powershell
streamlit run app/streamlit_app.py
```

전체 테스트:
```powershell
pytest -v
```
