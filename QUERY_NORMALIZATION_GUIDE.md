# Query Normalization 적용 가이드

## 추가 파일

```text
data/
└─ query_aliases.csv

services/
└─ query_normalizer.py

tests/
└─ test_query_normalizer.py
```

## 관리 원칙

`query_aliases.csv`에는 현업 용어, 동의어, 약어, 한글/영문 표현을 관리합니다.

`QueryNormalizer`에는 프로그램 규칙을 둡니다.

- 대소문자
- 공백
- 숫자+단위
- Alias 적용
- Tokenization
- Match Score / Ranking

## 권장 연결 위치

제품/자재 검색 Service에서 재사용합니다.

```text
search_product()
    ↓
QueryNormalizer
    ↓
Exact ID 우선
    ↓
Normalized Exact Match
    ↓
Token Match / Ranking
```

```text
search_material()
    ↓
QueryNormalizer
    ↓
Exact ID 우선
    ↓
Normalized Exact Match
    ↓
Token Match / Ranking
```

BOM 조회는 Product ID가 불명확할 경우 Agent Skill이
`search_product -> get_bom` 순서를 사용하므로 제품 검색 정규화 효과를 그대로 받습니다.

## MCP와의 책임 분리

```text
MCP
= Capability Interface

Service / QueryNormalizer
= Search Logic
```

정규화/Alias/Ranking 로직을 MCP Server에 직접 넣지 않습니다.

## 1차 확인

파일 복사 후:

```powershell
pytest tests/test_query_normalizer.py -v
```

예상 결과:

```text
8 passed
```

그 다음 기존 `BomService.search_product()`와
`BomService.search_material()`에 연결합니다.
