# Azure OpenAI Integration

## 목적
기존 Python Rule 기반 Tool 선택을 LLM 기반 Tool 선택 방식으로 확장한다.

## Azure 설정
환경변수를 통해 다음 정보를 관리한다.
- Endpoint
- API Key
- API Version
- Deployment

API Key는 코드에 직접 작성하지 않는다.

## AzureOpenAIClient 역할

### create_chat_completion()
일반적인 LLM 질의 처리.

### create_tool_call_completion()
사용자 질문과 Tool Definition을 Azure OpenAI에 전달하고 LLM이 Tool과 arguments를 선택하도록 한다.

### create_final_answer()
실제 Tool 실행 결과를 Azure OpenAI에 다시 전달하여 사용자용 자연어 답변을 생성한다.
