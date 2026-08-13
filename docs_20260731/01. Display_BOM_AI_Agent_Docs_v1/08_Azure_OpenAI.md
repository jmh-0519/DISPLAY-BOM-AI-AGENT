# Azure OpenAI 연동

## 1. 목적

Azure OpenAI 모델을 BOM AI Agent의 자연어 이해, Tool 선택, 결과 설명에 사용한다.

## 2. 환경변수

실제 값은 `.env`에만 저장하며 문서나 코드 저장소에 기록하지 않는다.

```text
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_DEPLOYMENT=
```

## 3. 보안 원칙

- API Key를 코드에 하드코딩하지 않는다.
- `.env`를 공유하거나 ZIP 백업에 포함할 때 주의한다.
- 로그에 Key, 전체 요청 본문, 민감 데이터가 남지 않게 한다.
- 실제 회사 데이터를 외부 모델에 전송하지 않는다.

## 4. 구현 시 확인사항

- Endpoint 형식
- Deployment 이름
- API Version
- 모델의 Tool Calling 지원
- Timeout과 Retry
- Rate Limit 처리
- 토큰 사용량 기록

## 5. 오류 기록 항목

- 인증 실패
- Deployment 미존재
- API Version 불일치
- 연결 Timeout
- Rate Limit
- 잘못된 Tool Call 형식

## 6. 향후 추가 내용

- 클라이언트 래퍼 구조
- 요청/응답 예제
- 재시도 정책
- 비용 모니터링
- 모델 변경 절차
