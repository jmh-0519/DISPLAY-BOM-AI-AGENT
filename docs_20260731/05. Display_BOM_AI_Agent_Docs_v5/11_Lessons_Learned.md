# Lessons Learned

## 1. LLM은 Tool을 실행하지 않는다
LLM은 어떤 Tool을 어떤 argument로 호출할지 결정한다. 실제 실행은 Application의 책임이다.

## 2. Tool Definition과 실제 구현은 다르다
LLM에 `search_product`를 등록했다고 해서 실제 제품 검색 기능이 구현된 것은 아니다.

`Tool → Service → Data` 전체 경로가 구현되어야 실제 기능이 된다.

실제 개발 중 `ProductTool`은 존재했지만 `BomService.search_product()`가 없어 실행 오류가 발생했고, Service 메서드를 구현하여 해결하였다.

## 3. LLM과 Business Logic을 분리해야 한다
AzureBomAgent가 CSV를 직접 조회하지 않는다. 실제 업무 로직은 Tool과 Service가 담당한다.

## 4. Tool 결과를 다시 LLM에게 전달한다
LLM은 실제 업무 데이터를 직접 생성하는 것이 아니라 Tool에서 조회된 결과를 해석하고 자연어로 표현한다.

## 5. UI Session과 Agent Memory는 다르다
Streamlit Session State가 대화를 화면에 유지한다고 해서 LLM이 이전 대화를 기억하는 것은 아니다.

## 6. 작은 단위부터 검증하는 것이 중요하다
`Tool 선택 → Tool 실행 → 결과 재전달 → Agent → UI` 순서로 개발했기 때문에 오류 발생 위치를 쉽게 찾을 수 있었다.

## 7. 실제 UI 테스트가 통합 오류를 발견한다
터미널 단위 테스트만으로 발견하지 못했던 Service 구현 누락과 대화 Context 문제를 Streamlit에서 확인할 수 있었다.
