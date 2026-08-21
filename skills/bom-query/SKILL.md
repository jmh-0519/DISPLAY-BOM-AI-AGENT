---
name: bom-query
description: >
  Display 제품, BOM, 자재의 조회 및 검색 요청을 처리하기 위한
  업무 절차와 의사결정 규칙을 정의한다.
---

# BOM Query Skill

## Goal

사용자의 Display 제품, BOM, 자재 조회 요청을 정확하게 처리한다.

조회 결과는 반드시 MCP Tool이 반환한 데이터를 근거로 판단하며,
존재하지 않는 제품, 자재 또는 BOM 정보를 임의로 생성하지 않는다.


## Available Tools

이 Skill에서 사용할 수 있는 MCP Tool은 다음과 같다.

- `get_bom`
  - 특정 VERSION/ASSY의 기준일 하위 BOM을 조회한다.

- `get_bom_where_used`
  - MATERIAL/ASSY가 사용된 직접 상위 품목과 최상위 MODEL을 역방향으로 조회한다.

- `get_product_detail`
  - 모델 Master 및 상세 속성정보를 조회한다.

- `get_item_detail`
  - MATERIAL/ASSY Master 및 상세 속성정보를 조회한다.

- `export_bom_excel`
  - 동일 조회조건의 BOM 결과를 Excel 파일로 생성한다.
  - 읽기 전용이며 Production BOM을 변경하지 않는다.
  - 조회결과가 없으면 빈 파일을 생성하지 않는다.

- `list_products`
  - 등록된 전체 제품 목록을 조회한다.

- `search_product`
  - 제품 ID 또는 제품명으로 제품을 검색한다.

- `list_materials`
  - 등록된 전체 자재 목록을 조회한다.

- `search_material`
  - 자재 ID 또는 자재명으로 자재를 검색한다.


## Workflow

### 1. BOM 조회

사용자가 특정 제품의 BOM 조회를 요청한 경우:

1. 제품 ID와 기준일을 확인한다.
2. 제품 ID가 명확하면 `get_bom`을 호출한다.
3. 제품 ID가 명확하지 않으면 `search_product`를 먼저 호출한다.
4. 검색 결과가 하나라면 해당 제품 ID를 사용한다.
5. 검색 결과가 여러 개라면 임의로 선택하지 않는다.
6. 필요한 경우 사용자에게 제품 선택을 요청한다.
7. 제품이 결정되면 `get_bom`을 호출한다.
8. 반환된 BOM 데이터를 기준으로 결과를 설명한다.


### 2. 역방향 BOM 조회

사용자가 특정 자재/ASSY가 어떤 상위 ASSY 또는 MODEL에 사용되는지 질문한 경우:

1. 대상 품목 코드를 식별한다.
2. PLANT가 없으면 해당 품목이 실제 사용되는 PLANT를 조회해 사용자 선택을 받는다.
3. `get_bom_where_used`를 호출한다.
4. 직접 상위 품목과 최상위 MODEL을 모두 설명한다.
5. 결과가 없으면 선택한 PLANT의 현재 BOM에 구성되어 있지 않다고 알린다.
6. MATERIAL에 `get_bom`을 호출하지 않는다.


### 3. 제품 검색

사용자가 제품 검색을 요청한 경우:

1. 검색어가 있으면 `search_product`를 호출한다.
2. 검색어 없이 전체 제품을 요청하면 `list_products`를 호출한다.
3. 검색 결과를 제품 ID와 제품명을 중심으로 설명한다.


### 4. 자재 검색

사용자가 자재 검색을 요청한 경우:

1. 검색어가 있으면 `search_material`을 호출한다.
2. 검색어 없이 전체 자재를 요청하면 `list_materials`를 호출한다.
3. 검색 결과를 자재 ID와 자재명을 중심으로 설명한다.


### 5. BOM 내 자재 확인

사용자가 특정 제품 BOM에 특정 자재가 포함되어 있는지 질문한 경우:

1. 대상 제품을 식별한다.
2. 제품 ID가 불명확하면 `search_product`를 호출한다.
3. 필요한 경우 `search_material`을 이용하여 대상 자재를 식별한다.
4. `get_bom`으로 대상 제품의 BOM을 조회한다.
5. 반환된 BOM 데이터에서 대상 자재의 포함 여부를 확인한다.
6. Tool 결과를 근거로 사용자에게 결과를 설명한다.


## Decision Rules

### Product

- 제품 ID를 임의로 생성하지 않는다.
- 제품이 명확하지 않으면 검색을 먼저 수행한다.
- 검색 결과가 여러 개인 경우 임의로 하나를 선택하지 않는다.


### Material

- 자재 ID를 임의로 생성하지 않는다.
- 자재명만 제공된 경우 검색 결과를 이용해 자재를 식별한다.
- 검색 결과가 여러 개인 경우 임의로 하나를 선택하지 않는다.


### BOM

- BOM 구성 여부는 반드시 `get_bom` 결과를 기준으로 판단한다.
- BOM 구조를 LLM의 일반 지식으로 추측하지 않는다.
- 기준일이 제공되면 해당 기준일을 사용한다.
- 수량과 소요 수량을 임의로 계산하거나 변경하지 않는다.


## Tool Selection Rules

다음 기준으로 MCP Tool을 선택한다.

| 사용자 요청 | 우선 Tool |
| --- | --- |
| 특정 제품/ASSY 하위 BOM 조회 | `get_bom` |
| 자재/ASSY의 상위 BOM·MODEL 조회 | `get_bom_where_used` |
| 모델 상세 속성 조회 | `get_product_detail` |
| 자재/ASSY 상세 속성 조회 | `get_item_detail` |
| 조회한 BOM의 Excel 다운로드 | `export_bom_excel` |
| 제품 전체 목록 | `list_products` |
| 제품 검색 | `search_product` |
| 자재 전체 목록 | `list_materials` |
| 자재 검색 | `search_material` |
| 특정 BOM의 자재 포함 여부 | `get_bom` |
| 제품이 불명확한 BOM 요청 | `search_product` → `get_bom` |


## Planning Rules

하나의 Tool 호출만으로 요청을 처리할 수 없는 경우
Tool 결과를 확인한 후 다음 Tool을 선택한다.

예:

사용자 요청:

> 40IN FHD 60HZ LCD MODEL의 BOM을 보여줘.

실행 계획:

1. `search_product`
2. 제품 검색 결과 확인
3. 대상 제품 ID 결정
4. `get_bom`
5. BOM 조회 결과 설명


사용자 요청:

> LTA400HR01-0에 LC SEALANT가 들어가는지 확인해줘.

실행 계획:

1. `search_material`
2. 대상 자재 확인
3. `get_bom`
4. BOM에서 대상 자재 확인
5. 결과 설명


## Failure Handling

### 제품을 찾을 수 없는 경우

제품이 존재한다고 추측하지 않는다.

검색 결과가 없음을 사용자에게 알린다.


### 자재를 찾을 수 없는 경우

자재 코드를 생성하거나 유사한 자재를 임의로 선택하지 않는다.

검색 결과가 없음을 사용자에게 알린다.


### MCP Tool 실행 실패

Tool 실행 실패를 정상적인 조회 결과처럼 설명하지 않는다.

실행에 실패했음을 명확히 구분한다.


### 여러 후보가 존재하는 경우

후보를 임의로 하나 선택하지 않는다.

사용자가 선택할 수 있도록 후보 정보를 제공한다.


## Output Guidelines

### BOM

`get_bom`으로 BOM을 조회한 경우 Tool이 반환한 BOM 계층 구조를
유지하여 결과를 표시한다.

Tool 결과에 존재하는 모든 BOM 항목에 대해 다음 정보를 반드시
누락 없이 표시한다.

- Version 코드
- 자재 코드
- 자재명
- 구분
- 수량
- 소요 수량

제품 정보가 Tool 결과에 존재하면 다음 정보도 표시한다.

- 제품 ID
- 제품명
- 기준일

자재 코드는 자재명보다 앞에 표시한다.

Tool 결과에 없는 값은 임의로 생성하지 않으며,
해당 값이 없음을 명확하게 표시한다.

BOM 조회 결과는 다음 형식을 기본으로 사용한다.

조회한 Version 코드를 표 위에 명시하고 각 행의 구분은 
`item_type` 또는 `bom_child_type`을 사용한다.

| Version 코드 | 자재 코드 | 자재명 | 구분 | 수량 | 소요 수량 |
| --- | --- | --- | --- | ---: | ---: |
| Tool 반환값 | Tool 반환값 | Tool 반환값 | Tool 반환값 | Tool 반환값 | Tool 반환값 |

BOM이 계층 구조인 경우 Level 또는 들여쓰기를 사용하여
상위·하위 자재 관계를 유지한다.

사용자가 요약을 명시적으로 요청하지 않은 경우
BOM 항목을 임의로 생략하거나 통합하지 않는다.


### Product

가능한 경우 다음 정보를 제공한다.

- 제품 ID
- 제품명


### Material

가능한 경우 다음 정보를 제공한다.

- 자재 ID
- 자재명


## Constraints

- 조회 Tool은 데이터를 변경하지 않는다.
- 조회 과정에서 Production BOM을 수정하지 않는다.
- 조회 결과에 없는 업무 데이터를 생성하지 않는다.
- Tool 실행 결과와 Agent의 설명을 구분한다.
- 사용자의 조회 요청을 설계변경 요청으로 임의 확대하지 않는다.
