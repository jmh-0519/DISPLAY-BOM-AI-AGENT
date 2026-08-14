# STEP24-B1 v2 적용 및 검증

## 1. 파일 덮어쓰기

ZIP을 프로젝트 루트에 압축 해제하여 동일 경로의 파일을 덮어씁니다.

이번 ZIP에는 A2 실제 CSV 보정사항도 포함됩니다.

- `material_attributes.item_code → item_master`
- `material_compatibility.source_item_code → item_master`

## 2. DB 재생성

아직 SQLite Runtime 전환 전이므로 기존 A2 빈 DB를 v2 보정 Schema로 다시 만듭니다.

```powershell
python -m scripts.init_database --database data/display_bom.db --recreate
```

## 3. CSV 초기 이관

```powershell
python -m scripts.migrate_csv_to_sqlite --data-dir data --database data/display_bom.db --report data/migration_report.json
```

정상 결과의 주요 건수:

```text
supplier_master: 8
item_master: 105
version_master: 4
assembly_master: 30
material_master: 71
material_attributes: 101
bom_master: 98
material_compatibility: 10
foreign_key_errors: 0
orphan_bom_items: 0
invalid_hierarchy_edges: 0
cycle_count: 0
```

`data/migration_report.json`의 `status`가 `SUCCESS`여야 합니다.

## 4. 자동화 테스트

```powershell
python -m pytest tests/test_database_schema.py tests/test_csv_to_sqlite_migration.py -q
python -m pytest -q
```

## 5. DB Browser 화면 확인

`data/display_bom.db`를 연 뒤 Browse Data에서 확인합니다.

- `version_master`: 4건
- `assembly_master`: 30건
- `material_master`: 71건
- `bom_master`: 98건
- `location_master`: 11건

`bom_master`에는 `root_version_code`, Parent/Child 이름 컬럼이 없고
`location_code`가 있어야 합니다.

## 변환 참고

- MODEL 가상 행 4건 제거
- MOD/product→FA 행 4건 제거
- CF→TFT를 LC→TFT로 변환
- LC 연결 근거가 없는 독립 CF→TFT 1건은 제외하고 Report 경고에 기록
- 기존 물리 위치가 아닌 역할성 Location은 일반 자재 관계의 `ALL`로 표준화
- 설계변경·품평·변경이력 CSV는 B1 범위에서 아직 이관하지 않으며 Report에 목록을 기록

정상이면 `1`, 문제가 있으면 명령 출력과 `migration_report.json` 내용과 함께
`0`으로 회신합니다.
