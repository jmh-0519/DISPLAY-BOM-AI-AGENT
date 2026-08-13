# 배포 및 실행 환경

## 1. 초기 실행 환경

- Windows
- Python 가상환경
- VSCode
- Streamlit 로컬 실행
- Azure OpenAI
- CSV 데이터

## 2. 로컬 실행 절차

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## 3. 환경별 설정

- 개발: 합성 CSV, 상세 로그
- 테스트: 고정 테스트 데이터, 자동 테스트
- 운영 후보: Oracle, 제한된 로그, 권한 적용

## 4. 배포 전 점검

- `.env` 미포함 확인
- 실제 회사 데이터 미포함 확인
- 의존성 버전 고정
- 테스트 통과
- 로그 경로 및 보존 정책
- 오류 화면 확인
- API 사용량 및 비용 한도

## 5. 향후 검토

- Docker
- Azure App Service 또는 VM
- 사내망 배포
- Secret 관리
- CI/CD
- Health Check
