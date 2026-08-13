# v8 Test and E2E Status

## 1. 테스트 전략
기능 추가 시 기존 기능을 깨뜨리지 않는 것을 우선하며 pytest 회귀 테스트를 반복 수행한다.

## 2. 주요 검증 이력
- MCP Server import 확인
- MCP Tool 직접 호출
- MCP Client BOM 조회
- MCP Tool Definition 동적 조회
- Skill/Agent Multi-step 호출
- QueryNormalizer 18개 테스트
- 제품/자재 검색 정책 테스트
- 기존 ID 부분검색 회귀 복구
- 전체 **222 passed**

## 3. Streamlit E2E 검증
### 성공
- 정식 제품 ID BOM 조회
- 자연어 제품명 BOM 조회
- `40인치 FHD 60Hz LCD 모델` → `LTA400HR01-0` 식별 → BOM 조회
- `50인치 모델도 있어?` → `LTA500HR01-0` 제품 검색
- `LC 실란트 자재를 찾아줘` → LC SEALANT 5개 반환

### 발견된 Gap
- `그 중에서 9000번대로 시작하는 자재가 있어?`에서 직전 검색 결과를 범위로 사용하지 못함
- 원인: Conversation Memory/Tool Observation Context 미연결

## 4. 현재 품질 판단
단일 질문 기반의 조회/검색/MCP Tool Calling은 안정적인 수준에 도달했다. 다음 품질 병목은 **다중 턴 Context 유지**이다.
