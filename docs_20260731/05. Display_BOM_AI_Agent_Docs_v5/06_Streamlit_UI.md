# Streamlit UI

## 목적
AzureBomAgent를 사용자가 직접 사용할 수 있는 Chat UI와 연결한다.

## 실행
```powershell
streamlit run app/streamlit_app.py
```

## 주요 기능
- Chat Input
- 사용자/Agent 메시지 표시
- Session State 기반 화면 대화 기록
- AzureBomAgent 호출
- 오류 표시
- 대화 초기화

## Import 경로 이슈
Streamlit 실행 시 프로젝트 루트가 Python import 경로에 포함되지 않아 `ModuleNotFoundError: No module named 'agents'`가 발생하였다.

`streamlit_app.py`에서 프로젝트 루트를 `sys.path`에 추가하여 해결하였다.

## 중요: UI Session과 Agent Memory의 차이
현재 Session State에 메시지를 저장하지만 이 기록이 AzureBomAgent의 Context로 전달되는 것은 아니다.

따라서 화면에서 이전 대화가 보이는 것과 Agent가 이전 대화를 기억하는 것은 서로 다른 개념이다.

예:
```text
사용자: LED 제품을 찾아줘.
Agent: 두 제품이 있습니다.
사용자: 응. BOM 정보도 조회해줘.
Agent: 어떤 제품의 BOM인가요?
```

현재 Agent에는 Conversation Memory가 없기 때문에 후속 질문의 지시 대상을 자동으로 연결하지 못한다.
