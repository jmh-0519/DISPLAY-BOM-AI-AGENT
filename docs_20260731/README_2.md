# Display BOM AI Agent 문서 안내서

## 1. 문서의 목적

이 문서 모음은 Display BOM AI Agent의 기능만 기록하는 산출물이 아니다. 프로젝트를 진행하면서 배우는 AI Agent 설계, 개발, 테스트, 운영 지식을 축적하는 개인 기술 자산이다.

프로젝트의 핵심 목표는 다음과 같다.

> Display BOM AI Agent 하나를 완성하는 데서 끝나지 않고, AI Agent를 설계하고 구현하며 그 선택을 설명할 수 있는 개발 역량을 만든다.

## 2. 개발 철학

이 프로젝트는 아래 순서로 진행한다.

```text
요구사항 이해
    ↓
설계 대안 검토
    ↓
선택 이유 기록
    ↓
구현
    ↓
테스트
    ↓
회고
    ↓
문서 업데이트
```

코드만 동작하게 만드는 것보다 다음 질문에 답할 수 있어야 한다.

- 왜 이 구조를 선택했는가?
- 다른 대안은 무엇이었는가?
- 현재 구조의 장점과 한계는 무엇인가?
- 데이터 소스나 모델이 바뀌면 어느 계층을 수정해야 하는가?
- 같은 설계를 다른 AI Agent 프로젝트에도 재사용할 수 있는가?

## 3. 문서 작성 원칙

새로운 기능이나 설계 요소를 추가할 때 가능한 한 다음 순서를 따른다.

1. 문제 또는 요구사항
2. 필요한 이유
3. 검토한 대안
4. 선택한 설계
5. 선택 이유
6. 입력과 출력
7. 예외 및 제약사항
8. 구현 내용
9. 테스트 결과
10. 배운 점과 개선점

모든 문서를 한 번에 완성하려 하지 않는다. 개발과 학습이 진행될 때마다 조금씩 갱신한다.

## 4. 문서 목록

| 문서 | 목적 |
|---|---|
| `00_Project_Roadmap.md` | 6주 개발 일정과 단계별 완료 기준 |
| `01_Project_Overview.md` | 배경, 목표, 사용자, 범위, 기대 효과 |
| `02_System_Architecture.md` | 전체 계층 구조와 데이터 흐름 |
| `03_Design_Decisions.md` | 주요 설계 결정과 선택 이유 기록 |
| `04_Data_Model.md` | CSV 및 향후 DB 데이터 구조 |
| `05_AI_Agent_Architecture.md` | Agent의 역할, 처리 흐름, 상태 및 응답 전략 |
| `06_Tool_Architecture.md` | Tool 계약, Registry, Executor, Tool별 설계 |
| `07_Prompt_Engineering.md` | 시스템 프롬프트, Tool 선택, 환각 방지 전략 |
| `08_Azure_OpenAI.md` | Azure OpenAI 설정과 호출 구조 |
| `09_Streamlit_UI.md` | UI 구조, 상태 관리, 사용자 흐름 |
| `10_Test_Strategy.md` | 단위, 통합, Agent, 보안 테스트 전략 |
| `11_Deployment.md` | 실행 환경, 배포, 환경변수, 운영 준비 |
| `12_Lessons_Learned.md` | 학습 내용과 회고 |
| `13_Troubleshooting.md` | 오류, 원인, 해결 방법 축적 |
| `14_Glossary.md` | AI Agent 및 소프트웨어 설계 용어 사전 |
| `15_Change_Log.md` | 코드와 문서의 주요 변경 이력 |
| `16_Architecture_Review.md` | 주차별 아키텍처 리뷰와 개선 기록 |
| `AI_AGENT_PRINCIPLES.md` | 프로젝트 전체가 따르는 개발 원칙 |

## 5. 문서 갱신 규칙

- 새로운 Tool을 추가하면 `06_Tool_Architecture.md`와 `15_Change_Log.md`를 갱신한다.
- 새로운 설계 판단이 발생하면 `03_Design_Decisions.md`에 ADR 형식으로 기록한다.
- 오류를 해결하면 `13_Troubleshooting.md`에 재현 조건과 해결 방법을 기록한다.
- 새로운 용어를 학습하면 `14_Glossary.md`에 추가한다.
- 한 단계가 끝나면 `12_Lessons_Learned.md`와 `16_Architecture_Review.md`를 갱신한다.
- 민감한 키, 비밀번호, 실제 회사 데이터는 문서에 기록하지 않는다.

## 6. 프로젝트 산출물의 기준

완성된 프로젝트는 다음 조건을 만족해야 한다.

- 동작하는 코드가 있다.
- 주요 설계 선택의 이유가 기록되어 있다.
- Tool과 Service의 책임이 구분되어 있다.
- 테스트로 핵심 기능을 검증할 수 있다.
- CSV에서 Oracle로 변경할 때 영향 범위를 설명할 수 있다.
- 다른 사람에게 구조와 처리 흐름을 설명할 수 있다.
