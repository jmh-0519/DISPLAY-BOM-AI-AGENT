# STEP24-E1 SQLite Production Transaction 기반 및 조회 표시 보정

## 변경 내용

### BOM 조회

- 모든 SQLite BOM 행에 `version_code` 추가
- `item_type`, `bom_child_type` 추가
- Agent Skill의 표 출력 기준에 Version 코드와 구분을 필수로 지정

### Production Transaction

- `SQLiteUnitOfWork` 추가
- 승인 상태와 BOM Revision 재확인
- 기존 관계 종료 및 신규 관계 생성
- 설계변경 상태, 적용 이력, Workflow Event 동시 기록
- 성공 시 전체 Commit, 실패 시 전체 Rollback

현재 MCP 최종 Apply는 아직 CSV 경로입니다. E2에서 설계변경·품평 데이터를
SQLite로 이관한 후 연결합니다.

## 1. 적용

ZIP을 프로젝트 루트에 압축 해제하여 동일 경로에 덮어씁니다.

## 2. 전용 테스트

```powershell
python -m pytest tests/test_repository_bom_service.py tests/test_sqlite_production_bom_service.py -q
```

예상 결과:

```text
13 passed
```

## 3. 전체 테스트

```powershell
python -m pytest -q
```

예상 결과:

```text
297 passed
```

## 4. 화면 확인

Streamlit을 `Ctrl+C`로 완전히 종료하고 같은 PowerShell에서 확인합니다.

```powershell
$env:BOM_STORAGE_MODE="SQLITE"
$env:BOM_SQLITE_PATH="data/display_bom.db"
streamlit run app/streamlit_app.py
```

대화를 초기화하고:

```text
LTA400HR01-001의 BOM을 보여줘
```

정상 기준:

- Version 코드: `LTA400HR01-001`
- 표의 구분: `ASSEMBLY` 또는 `MATERIAL`
- MODEL/MOD 행 없음
- CF/TFT는 LC의 형제
- `bom_id` 없음

정상이면 `1`, 문제면 오류 또는 화면과 함께 `0`으로 회신합니다.
