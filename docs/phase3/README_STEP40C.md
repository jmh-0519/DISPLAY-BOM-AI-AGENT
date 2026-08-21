# STEP40-C - ADD Target Resolution / PLANT Button Gate / BOM Quantity Simplification

STEP40 적용 이후 덮어쓰는 패치입니다.

## 변경 내용

1. ADD 자연어 요청의 품목군/Rule Identity 기반 후보 제한
   - 예: 고객 EMI 사양 차폐 테이프 요청은 `EMI_SHIELD_TAPE` 계열 후보만 탐색합니다.
2. Sidebar의 PLANT 안내 문구 제거
3. PLANT 누락 시 관련 모델/BOM/ASSY/자재가 실제 존재하는 PLANT만 DB에서 조회해 버튼으로 선택
4. Phase3 수량 기준을 BOM `QUANTITY`로 단순화
   - REPLACE: 현재 BOM QUANTITY
   - ADD: 추가 후 BOM QUANTITY (미지정 시 1)
   - DELETE: 현재 BOM QUANTITY 표시
   - QUANTITY_CHANGE: 변경 후 BOM QUANTITY
   - 생산계획 기반 수요 계산은 활성 Phase3 후보/재고 평가에서 사용하지 않음
5. Analysis 화면의 임시 Master Attribute 입력 제거
   - 기준정보가 부족하면 DB Master Data 보완 후 재검증
6. 사용자 확정 APPLY 안내 문구를 `app/views/phase3_agent_view.py` 전체 파일에 반영

## 적용 방법

프로젝트 루트에 ZIP 내용을 덮어쓴 뒤 기존 Runtime DB의 잘못된 STEP40 ADD Sample Metadata를 보정합니다.

```powershell
python -m scripts.apply_step40c_business_data_patch --database data/display_bom.db
```

DB Sample 검증:

```powershell
python -m scripts.verify_phase3_business_sample --database data/display_bom.db
```

전체 테스트:

```powershell
python -m scripts.run_tests -q
```

## 주의

- `data/display_bom.db` 파일은 패키지에 포함하지 않습니다. 기존 설계변경 이력을 덮어쓰지 않습니다.
- `apply_step40c_business_data_patch`는 기존 Request/Approval/Preview/Apply History를 삭제하지 않고 ADD Sample Metadata만 보정합니다.
- Runtime에서 특정 Sample Code를 분기 조건으로 사용하지 않습니다.
