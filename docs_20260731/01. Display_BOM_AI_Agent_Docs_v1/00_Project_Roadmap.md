# 프로젝트 로드맵

## 프로젝트 기간

6주

## Week 1 — End-to-End MVP

### 목표

사용자 질문이 Tool과 Service를 거쳐 CSV 데이터를 조회하고 결과를 반환하는 최소 기능을 완성한다.

### 주요 작업

- 프로젝트 구조 구성
- 합성 BOM 데이터 준비
- `BomService` 구현
- 제품 조회
- 자재 검색
- 1레벨 BOM 조회
- Tool Registry와 Executor 구현
- Azure OpenAI 연결
- Streamlit 기본 화면

### 완료 기준

- 제품 ID로 제품 조회 가능
- 키워드로 자재 검색 가능
- 제품 또는 조립품의 직계 BOM 조회 가능
- 잘못된 제품 ID에 안전하게 응답
- Agent가 적절한 Tool을 선택해 결과 설명

## Week 2 — BOM 핵심 기능

- Multi-level BOM Explosion
- Where-Used
- BOM 비교
- 버전 조회
- 출력 표준화

## Week 3 — BOM Validation

- 필수 구성품 규칙
- 단종 자재 검사
- 승인 상태 검사
- 중복 자재 검사
- 수량 검사
- 호환성 검사
- 공급업체 규칙

## Week 4 — Engineering Change 및 데이터 확장

- 변경 영향 분석
- 변경 이력 조회
- Repository 계층 검토
- SQLite 또는 Oracle 연계 준비
- 안전한 SQL 원칙
- 로깅과 예외 처리 강화

## Week 5 — 품질과 테스트

- 단위 테스트
- 통합 테스트
- Agent 시나리오 테스트
- 프롬프트 평가
- 보안 테스트
- 성능과 토큰 사용 점검

## Week 6 — 최종 완성

- 전체 회귀 테스트
- UI 개선
- 문서 정합성 확인
- 데모 시나리오 구성
- 발표 자료 준비
- 최종 회고와 아키텍처 리뷰
