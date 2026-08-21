# STEP40-J – Master Query & Reverse BOM

## Scope

1. Agent 채팅에서 MATERIAL/ASSY Where-used(역방향 BOM) 조회
2. BOM 조회 화면에서 MATERIAL 코드 입력 시 상위 ASSY/최상위 MODEL 역방향 조회
3. 선택 PLANT의 BOM에 사용되지 않는 MATERIAL은 Traceback 대신 업무 안내 표시
4. Sidebar `BOM 조회`를 `Master 조회`로 변경
5. Master 조회 세부 UI: `BOM 조회 / 모델 조회 / 자재 조회`
6. 모델/자재 Master 및 상세 속성정보 조회 MCP Tool 추가

## New MCP tools

- `get_bom_where_used(item_code, plant_code, as_of_date)`
- `get_product_detail(product_id, as_of_date)`
- `get_item_detail(item_code, as_of_date)`

## Reverse BOM behavior

- MATERIAL/ASSY → 직접 상위 품목 → 상위 ASSY → 최상위 VERSION(MODEL)
- PLANT 미지정 Agent 요청은 대상 자재가 실제 사용되는 PLANT만 선택 버튼으로 제시
- MATERIAL을 `get_bom` root로 호출하지 않음
- 결과 0건이면 `해당 품목은 선택한 PLANT의 현재 BOM에 구성되어 있지 않습니다.` 표시

## Verification

Dependency-independent tests executed in build environment:

```text
10 passed
Phase3 Business Sample Verification: PASS
Python compile: PASS
```

User environment final regression:

```powershell
python -m scripts.run_tests -q
```

No DB patch is required for STEP40-J.
