# Basic Query Tools

## get_bom
- 입력: `product_id`
- 역할: 제품 ID 기준 BOM 조회
- Service: `BomService.get_bom()`

## search_material
- 입력: `keyword`
- 역할: 자재 ID 또는 자재명 검색
- Service: `BomService.search_material()`

## search_product
- 입력: `keyword`
- 역할: 제품 ID 또는 제품명 검색
- Service: `BomService.search_product()`

## Streamlit 검증 질문
```text
PRD-LED-43-A의 BOM을 보여줘.
Speaker 자재를 검색해줘.
LED 제품을 찾아줘.
```

세 기능 모두 실제 데이터 조회 후 자연어 응답까지 정상 동작함을 확인하였다.
