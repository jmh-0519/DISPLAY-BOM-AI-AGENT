# STEP24-C Repository 적용 및 검증

## 적용 범위

- `repositories/protocols.py`: 공통 읽기 계약
- `repositories/csv_repository.py`: v2 구조 비교용 CSV Adapter
- `repositories/sqlite_repository.py`: SQLite Adapter 및 재귀 조회
- `repositories/common.py`: 공통 컬럼·날짜·정렬 규칙
- `tests/test_repository_contract.py`: CSV/SQLite 계약 테스트

기존 `BomService` Runtime은 변경하지 않습니다.

## 1. 파일 적용

ZIP을 프로젝트 루트에 압축 해제하여 경로대로 추가합니다.

## 2. STEP24-C 계약 테스트

```powershell
python -m pytest tests/test_repository_contract.py -q
```

예상 결과:

```text
14 passed
```

## 3. 전체 회귀 테스트

```powershell
python -m pytest -q
```

B1 검증 완료 상태가 270개였으므로 신규 14개를 더해 예상 전체 결과는
`284 passed`입니다.

## 확인사항

- 테스트는 임시 SQLite DB에 CSV를 이관하여 수행합니다.
- 기존 `data/display_bom.db`를 삭제하거나 재생성할 필요가 없습니다.
- CSV와 SQLite는 동일한 FA 기준 결과를 반환합니다.
- SQLite Tree는 `WITH RECURSIVE`로 조회합니다.
- Repository 결과에 내부 `bom_id`와 `root_version_code`가 없습니다.
- Service Runtime 전환은 다음 단계에서 별도로 수행합니다.

정상이면 `1`, 문제가 있으면 오류 전체와 함께 `0`으로 회신합니다.
