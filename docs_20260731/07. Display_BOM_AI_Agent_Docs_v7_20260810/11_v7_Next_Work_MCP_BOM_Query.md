# Display BOM AI Agent --- 다음 작업 계획

**작성 기준일:** 2026-08-10\
**기준 문서:** Display BOM AI Agent Docs v7\
**다음 개발 주제:** BOM 조회 독립 메뉴 + MCP 첫 적용

------------------------------------------------------------------------

## 1. 다음 작업 목표

다음 개발에서는 **BOM 조회 기능을 독립 업무 메뉴로 분리**하고, 이 기능을
프로젝트의 **첫 번째 MCP 적용 사례**로 구현한다.

첫 번째 완료 목표는 다음 End-to-End 흐름을 실제로 동작시키는 것이다.

``` text
Streamlit BOM 조회 화면
        ↓
MCP Client
        ↓
Display BOM MCP Server
        ↓
get_bom MCP Tool
        ↓
BomService
        ↓
BOM Data
        ↓
기존 BOM Tree Viewer
```

MCP 자체를 복잡하게 확장하기 전에 `get_bom` 하나로 전체 연결 구조를
검증한다.

------------------------------------------------------------------------

## 2. Streamlit 메뉴 변경

현재 업무 메뉴에 **BOM 조회**를 독립 메뉴로 추가한다.

``` text
업무 선택
├─ Agent 채팅
├─ BOM 조회        ← 신규
└─ 설계변경
```

향후 업무 기능이 확장되면 품평회, 적용, 보고서 등을 별도 메뉴로 추가할
수 있다.

------------------------------------------------------------------------

## 3. BOM 조회 화면

신규 파일 후보:

``` text
app/views/bom_query_page.py
```

기본 화면 구성:

``` text
BOM 조회

모델 ID    [ 제품 선택 또는 입력 ]
기준일     [ YYYY-MM-DD ]

[ BOM 조회 ]

--------------------------------

제품 BOM

▼ MODEL
   ▼ ASSEMBLY
      ├─ MATERIAL-A
      ├─ MATERIAL-B
      └─ MATERIAL-C
```

BOM 표시에는 현재 완성한 `bom_view.py`의 Tree Viewer를 그대로
재사용한다.

### BOM Tree Viewer 유지 기준

-   Parent/Child 계층 표시
-   Parent 접기/펼치기
-   Parent 자재코드: 파란색 + Bold
-   Parent 자재명: Bold
-   일반 자재: 기본 표시
-   Tree 연결선 표시
-   마지막 Child는 `└─` 형태로 종료
-   Tree 표현은 자재코드 컬럼에만 적용
-   자재명 / 구분 / 수량은 고정 컬럼 정렬
-   동일 Parent의 Child끼리만 정렬
-   일반 자재 → Assembly 순서
-   같은 종류는 자재코드 오름차순

------------------------------------------------------------------------

## 4. MCP Server 추가

프로젝트에 MCP 관련 구조를 추가한다.

예상 구조:

``` text
DISPLAY-BOM-AI-AGENT
├─ agents
├─ app
├─ core
├─ data
├─ models
├─ services
├─ tests
├─ tools
│
├─ mcp_server
│  ├─ __init__.py
│  ├─ server.py
│  └─ capabilities
│     ├─ __init__.py
│     └─ query.py
│
└─ mcp_client
   ├─ __init__.py
   └─ client.py
```

초기 단계에서는 구조를 필요 이상으로 복잡하게 만들지 않는다.

------------------------------------------------------------------------

## 5. 첫 MCP Capability

첫 MCP Tool은 다음 하나로 시작한다.

``` text
get_bom
```

역할:

``` text
제품 ID 입력
   ↓
BomService 호출
   ↓
BOM 조회
   ↓
구조화된 결과 반환
```

중요 원칙:

> MCP Tool 내부에 기존 BOM 업무 로직을 다시 구현하지 않는다.

올바른 구조:

``` text
get_bom MCP Tool
      ↓
BomService
      ↓
기존 BOM 조회 Logic
```

MCP는 **Capability Interface**, Service는 **Business Logic** 역할을
유지한다.

------------------------------------------------------------------------

## 6. MCP Client

MCP Server의 `get_bom`을 Streamlit에서 호출하기 위한 Client를 구현한다.

초기 호출 흐름:

``` text
bom_query_page.py
      ↓
MCP Client
      ↓
get_bom
      ↓
MCP Server
```

MCP Client가 반환한 데이터를 DataFrame 또는 BOM Tree Viewer가 사용할 수
있는 형태로 변환한다.

------------------------------------------------------------------------

## 7. 기존 Agent 처리 방침

MCP 도입 첫 단계에서는 기존 Agent 구조를 변경하지 않는다.

``` text
Agent 채팅
   ↓
기존 ToolRegistry / ToolExecutor
```

신규 BOM 조회 메뉴만 MCP를 사용한다.

``` text
BOM 조회 메뉴
   ↓
MCP Client
   ↓
MCP Server
```

즉, 초기에는 두 방식을 병행한다.

MCP가 안정화된 이후 Agent Tool을 MCP 중심으로 전환할지 별도로 결정한다.

------------------------------------------------------------------------

## 8. 개발 순서

다음 작업은 아래 순서로 진행한다.

### STEP 1 --- 현재 Baseline 확인

-   현재 pytest 전체 실행
-   Streamlit 실행 확인
-   BOM Tree Viewer 정상 동작 확인

### STEP 2 --- MCP 개발환경 구성

-   MCP Python SDK 설치
-   설치 버전 확인
-   requirements 반영

### STEP 3 --- MCP Server 기본 구조

-   `mcp_server` 생성
-   Server 실행 확인
-   최소 Tool 등록 구조 작성

### STEP 4 --- get_bom MCP Tool

-   기존 `BomService` 연결
-   제품 ID 입력
-   BOM 결과 반환
-   Business Logic 중복 구현 금지

### STEP 5 --- MCP 단독 테스트

-   MCP Server 실행
-   `get_bom` 호출
-   정상 제품
-   존재하지 않는 제품
-   빈 BOM 등 오류/경계 Case 확인

### STEP 6 --- MCP Client

-   `mcp_client` 생성
-   Server 연결
-   Tool 조회
-   `get_bom` 호출
-   응답 변환

### STEP 7 --- BOM 조회 메뉴

-   `bom_query_page.py` 생성
-   `streamlit_app.py` 메뉴 추가
-   모델 입력/선택
-   조회 버튼
-   오류 메시지 처리

### STEP 8 --- BOM Tree 연결

-   MCP 반환 결과를 기존 `render_bom_expandable_tree()`에 전달
-   현재 확정된 Tree UI 유지

### STEP 9 --- pytest

-   MCP Capability 테스트
-   Client 호출 테스트
-   BOM 조회 화면에서 사용하는 변환 Logic 테스트
-   기존 회귀 테스트 재실행

------------------------------------------------------------------------

## 9. 첫 번째 완료 기준

다음 시나리오가 정상 동작하면 첫 MCP 적용을 완료한 것으로 본다.

``` text
1. Streamlit 실행
2. "BOM 조회" 메뉴 선택
3. 모델 ID 선택 또는 입력
4. "BOM 조회" 실행
5. Streamlit이 MCP Client 호출
6. MCP Client가 MCP Server의 get_bom 호출
7. MCP Server가 기존 BomService 호출
8. BOM 데이터 반환
9. Streamlit에서 기존 Tree Viewer로 출력
10. Parent/Child 구조 및 정렬 정상 확인
```

즉 단순히 MCP Server가 실행되는 것만으로 완료 처리하지 않고,

> **Streamlit → MCP → Service → BOM → Tree Viewer**

전체 흐름이 동작하는 것을 완료 조건으로 한다.

------------------------------------------------------------------------

## 10. 첫 적용 이후 확장 순서

`get_bom`이 안정적으로 동작하면 다음 Capability를 순차적으로 MCP로
노출한다.

``` text
get_bom
   ↓
list_products / search_product
   ↓
list_materials / search_material
   ↓
analyze_design_change
   ↓
evaluate_bom_review
   ↓
apply_design_change
   ↓
generate_change_report
```

Write 성격의 `apply_design_change`는 조회/분석 Capability가 안정화된
이후 적용한다.

실제 변경은 Human Approval 구조와 함께 연결하는 것을 원칙으로 한다.

------------------------------------------------------------------------

## 11. 이번 MCP 작업에서 하지 않을 것

첫 MCP 적용 단계에서는 다음 기능까지 한꺼번에 구현하지 않는다.

-   Multi-Agent
-   Planner
-   Skill
-   Workflow Memory
-   MCP-RAG
-   Tool Retrieval
-   Human Approval 전체 Workflow
-   Report Generation
-   기존 ToolRegistry 전면 제거

첫 목표는 **작고 명확한 MCP Vertical Slice 하나를 완성하는 것**이다.

------------------------------------------------------------------------

## 12. 다음 작업 시작점

다음 개발 세션은 아래 순서로 바로 시작한다.

``` text
① 현재 테스트 Baseline 확인
        ↓
② MCP SDK 설치
        ↓
③ mcp_server/server.py 생성
        ↓
④ get_bom MCP Tool 구현
        ↓
⑤ MCP 단독 호출 테스트
        ↓
⑥ MCP Client 구현
        ↓
⑦ BOM 조회 Streamlit 메뉴 생성
        ↓
⑧ 기존 BOM Tree Viewer 연결
        ↓
⑨ 전체 회귀 테스트
```

이 문서를 다음 개발 세션의 작업 기준으로 사용한다.
