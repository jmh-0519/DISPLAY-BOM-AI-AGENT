# STEP24-D 조회 Service SQLite 단계 전환

## 적용 내용

- 조회 Service Factory 추가
- 기본 저장소는 CSV 유지
- 환경변수로 SQLite 조회 모드 선택
- MCP 조회 기능에 Factory 연결
- 기존 product ID를 FA `VERSION_CODE`로 해석
- SQLite 결과를 기존 Tool/MCP DataFrame 컬럼으로 변환

설계변경 Apply Runtime은 아직 CSV를 사용합니다.

## 1. 파일 적용

ZIP을 프로젝트 루트에 압축 해제하여 동일 경로의 파일을 덮어씁니다.

## 2. STEP24-D 전용 테스트

```powershell
python -m pytest tests/test_repository_bom_service.py -q
```

예상 결과:

```text
8 passed
```

## 3. 전체 회귀 테스트

```powershell
python -m pytest -q
```

예상 결과:

```text
292 passed
```

## 4. 현재 PowerShell에서 SQLite 조회 모드 설정

```powershell
$env:BOM_STORAGE_MODE="SQLITE"
$env:BOM_SQLITE_PATH="data/display_bom.db"
```

설정값 확인:

```powershell
echo $env:BOM_STORAGE_MODE
echo $env:BOM_SQLITE_PATH
```

이 환경변수는 현재 PowerShell 창에만 적용되며 `.env` 파일은 필요하지 않습니다.

## 5. SQLite 모드 테스트

```powershell
python -m pytest tests/test_repository_bom_service.py -q
```

MCP Server는 Streamlit에서 실행될 때 현재 PowerShell 환경변수를 상속합니다.

## 6. 화면 확인

같은 PowerShell 창에서 기존 Streamlit 실행 명령을 실행합니다.

```powershell
streamlit run app/streamlit_app.py
```

다음 두 질의는 같은 FA BOM을 반환해야 합니다.

- `LTA400HR01-0의 BOM을 보여줘`
- `LTA400HR01-001의 BOM을 보여줘`

SQLite 모드에서는 결과의 Root가 `LTA400HR01-001`이며 MODEL/MOD 가상 행은
표시되지 않습니다. CF와 TFT는 LC의 동일 레벨 Child로 표시되어야 합니다.

## CSV 모드로 되돌리기

```powershell
$env:BOM_STORAGE_MODE="CSV"
```

잘못된 모드, DB 파일 누락, A2 Schema 미적용, B1 데이터 미이관 상태에서는
CSV로 자동 우회하지 않고 오류를 표시합니다.

정상이면 `1`, 문제가 있으면 오류 전체와 함께 `0`으로 회신합니다.
