# 프로젝트 개요

## 1. 프로젝트명

Display BOM AI Agent

## 2. 배경

Display 제품의 BOM 정보는 제품, 조립품, 부품, 버전, 승인 상태, 공급업체, 변경 이력 등 여러 데이터와 업무 규칙으로 구성된다. 사용자가 자연어로 질문하고 필요한 조회와 검증을 수행할 수 있는 단일 AI Agent를 구현한다.

## 3. 목표

- 자연어 기반 제품 및 자재 조회
- 제품 BOM 조회와 전개
- 자재 역전개(Where-Used)
- BOM 비교와 버전 분석
- BOM 품질 및 규칙 검증
- 설계변경 영향 분석
- 근거가 포함된 답변 제공

## 4. 학습 목표

- AI Agent와 Tool Calling의 동작 이해
- 계층형 아키텍처 설계 경험
- Registry와 Executor 패턴 구현
- Azure OpenAI 연동
- 결정적 업무 로직과 LLM 역할 분리
- 테스트 및 문서화 습관 형성

## 5. 대상 사용자

- BOM 설계 담당자
- 자재 및 부품 담당자
- 품질 및 승인 담당자
- 설계변경 담당자
- 프로젝트 관리자

## 6. 범위

### 포함

- 합성 Display BOM 데이터
- CSV 기반 초기 구현
- 단일 Agent
- Tool 기반 조회 및 검증
- Streamlit UI
- Azure OpenAI

### 초기 범위 제외

- 실제 회사 데이터
- 운영 시스템 직접 연계
- 쓰기 SQL 및 자동 승인
- Multi-Agent
- 완전 자동 설계변경 수행

## 7. 기술 스택

- Python
- Streamlit
- Azure OpenAI
- Pandas
- Pydantic
- Pytest
- CSV, 추후 SQLite 및 Oracle

## 8. 기대 효과

- BOM 조회 시간 단축
- 반복 검증 자동화
- 설계변경 영향 파악 지원
- AI Agent 설계 및 구현 역량 확보
- 재사용 가능한 개인 AI Agent 템플릿 구축
