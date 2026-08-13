# v8 Query Normalization

## 1. 도입 배경
DB에는 `40IN FHD 60HZ LCD MODEL`이 등록되어 있지만 사용자는 `40인치 FHD 60Hz LCD 모델`처럼 질문한다. 단순 `str.contains()` 검색만으로는 이런 표현 차이를 안정적으로 처리할 수 없다.

## 2. 구성
```text
data/query_aliases.csv
services/query_normalizer.py
tests/test_query_normalizer.py
```

### CSV에서 관리
- 현업 용어
- 한글/영문 동의어
- 약어
- Alias

예:
```text
인치 → IN
실란트/실런트 → SEALANT
ASSY/조립품 → ASSEMBLY
```

### 코드에서 관리
- 대소문자 통일
- 공백 처리
- 숫자+단위 정규화
- Alias 치환
- Tokenization
- Match Score / Ranking

## 3. 검색 정책
```text
1. Exact ID
2. Normalized 문자열 포함
3. All Token Match
4. Partial Token Match
```

All Token Match가 존재하면 느슨한 Partial 후보는 제거한다.

## 4. 기존 기능 보존
초기 개선 과정에서 `LTA400`, `LTA400HR01` 같은 ID 부분검색이 깨지는 회귀가 발생했다. `normalized_query in normalized_candidate` 점수를 추가하여 기존 부분검색과 신규 자연어 검색을 모두 보존했다.

## 5. 검증 결과
- QueryNormalizer 단위 테스트
- BomService 검색 테스트
- MCP Client/Query 회귀 테스트
- 전체 pytest: **222 passed**

## 6. E2E 성공 사례
```text
40인치 FHD 60Hz LCD 모델의 BOM을 보여줘.
 ↓
40IN FHD 60HZ LCD MODEL
 ↓
LTA400HR01-0
 ↓
get_bom
 ↓
정상 BOM 응답
```

자재 `LC 실란트` 검색도 `LC SEALANT` 후보 5개로 정상 정규화되었다.
