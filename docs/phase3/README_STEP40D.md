# STEP40-D - Request Detail Continuity UX

## 목적
Analysis 후보 확정 후 실제 Design Change Request를 생성했을 때 Agent 채팅 화면의 업무 맥락이 사라지는 문제를 개선한다.

## 변경 사항
1. 후보 선택 재확인 정보 보강
   - 후보 코드/품목명/DESCRIPTION
   - 종합/기술/공급/재고 평가
   - BOM 수량/가용재고
   - 점수/등급
   - 공급사/단가/납기
   - Rule/Attribute 기술 Evidence 펼침 영역

2. Request 생성 후 Agent 채팅 화면 연속성
   - `설계변경 이력` 상세조회와 동일한 공용 Renderer 사용
   - Request ID/PLANT/제품/요청 원문/변경 사유/요청자
   - Workflow/후보승인/최종승인/Production Apply 상태
   - 확정 Action
   - 변경 전/후 품목 Master 상세
   - 상세정보 아래에서 Preview/최종승인/Apply/Report Workflow 계속 진행

3. 설계변경 이력 상세조회 개선
   - Agent 채팅과 동일한 공용 Request 상세 Renderer 사용
   - 변경 전/후 품목명, DESCRIPTION, 품목유형, 상태, BOM 수량 표시

## 변경 파일
- `app/views/phase3_agent_view.py`
- `app/views/design_change_history_page.py`

## 주의
- DB 스키마/데이터 변경 없음
- Analysis/Request/Apply 업무 로직 변경 없음
- 사용자 확정 APPLY 안내 문구 유지
