# STEP24-A2 v2 적용 안내

## 변경 파일

- `database/schema.sql`
- `database/schema.py`
- `database/__init__.py`
- `scripts/init_database.py`
- `tests/test_database_schema.py`

압축파일의 위 파일들을 프로젝트 루트의 동일 경로에 덮어씁니다.

## 기존 A2 초안 DB 재생성

기존 `data/display_bom.db`에는 이전 Schema가 있으므로 새 Schema와 혼합하지 않습니다.
필요하면 DB 파일을 먼저 별도 위치에 복사한 뒤 다음 명령을 실행합니다.

```powershell
python -m scripts.init_database --database data/display_bom.db --recreate
```

정상 출력:

```text
SQLite schema v2 initialized: data\display_bom.db
```

SQLite 프로그램을 별도로 설치할 필요는 없습니다. Python 표준 라이브러리의
`sqlite3`가 DB 생성과 접근을 담당합니다.

## 테스트

기존 프로젝트 가상환경에서 실행합니다.

```powershell
python -m pytest -q
```

신규 Schema 테스트만 먼저 확인하려면:

```powershell
python -m pytest tests/test_database_schema.py -q
```

정상이면 `1`, 문제가 있으면 전체 오류 로그와 함께 `0`으로 회신합니다.

## 주의

- CSV 데이터 이관은 아직 실행하지 않습니다.
- 기존 B1 초안 파일은 적용하지 않습니다.
- 이번 단계에서는 빈 SQLite Schema와 초기화 기반만 확인합니다.
