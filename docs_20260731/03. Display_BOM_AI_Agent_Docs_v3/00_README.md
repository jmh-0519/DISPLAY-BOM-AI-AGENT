# Display BOM AI Agent 문서 패키지 v3

## 1. 문서 목적

본 문서 패키지는 Display BOM AI Agent 프로젝트의 현재 설계와 구현 상태를 정리한다.

현재까지 완료된 범위는 다음과 같다.

- 개발 환경 구성
- 합성 데이터 구성
- `BomService` 구현
- Tool Layer 공통 프레임워크 구현
- BOM, 자재, 제품 조회 Tool 구현
- pytest 기반 단위 테스트 구성
- 불필요한 중복 통합 테스트 정리

다음 개발 단계는 Rule-based `BomAgent` 구현이다.

## 2. 현재 개발 단계

```text
Environment        완료
Data Layer         완료
Service Layer      완료
Tool Framework     완료
Business Tools     완료
Unit Test          완료

Rule-based Agent   다음 단계
Azure OpenAI       예정
Streamlit UI       예정
```

## 3. 문서 목록

| 문서 | 설명 |
|---|---|
| `01_Project_Status.md` | 프로젝트 진행 현황과 다음 단계 |
| `02_System_Architecture.md` | 전체 시스템 구조 |
| `03_Design_Decisions.md` | 주요 설계 결정과 근거 |
| `04_Tool_Layer_Design.md` | Tool Layer 상세 설계 |
| `05_Test_Strategy.md` | 테스트 구조와 운영 방침 |
| `06_Current_File_Structure.md` | 현재 프로젝트 파일 구조 |
| `07_Implementation_Guide.md` | 현재 구현 코드의 역할과 확장 방법 |
| `08_Next_Step_BomAgent.md` | 다음 단계인 BomAgent 구현 계획 |
| `09_Lessons_Learned.md` | 현재까지의 교훈 |
| `10_Change_Log.md` | 변경 이력 |

## 4. 문서 관리 방식

```text
설계 → 구현 → 테스트 → 관련 문서 전체 재생성 → ZIP 배포
```
