# Display BOM AI Agent - v6 Sample Data Refresh v2

## 목적
LCD Display BOM 업무 구조를 기준으로 전체 샘플 데이터를 재구성한 데이터 세트입니다.

## BOM 핵심 스키마
`bom.csv`는 단순 Parent-Child 관계 집합으로 관리합니다.

- bom_parent
- bom_parent_name
- bom_child
- bom_child_name
- location
- sequence_no
- quantity
- start_date
- end_date

`bom_id`, `bom_level`, `parent_id`, `child_id`, 누적수량은 저장하지 않습니다.

## 최상위 Root 규칙
모델의 최초 관계는 반드시 다음과 같습니다.

MODEL -> 실제 Model ID

예:
MODEL -> LTA400HR01-0

## 표준 Assembly 계층
MODEL(LV1) -> FA(LV2) -> OLB(LV3) -> CP(LV4) -> BIN(LV5) -> LC(LV6) -> CF(LV7) -> TFT(LV8)

- Model 예: LTA400HR01-0
- FA 예: LTA400HR01-001
- OLB~TFT Assembly: LJ94- + 6자리 Sequence
- Assembly 하위 일반 자재: 4자리숫자-6자리숫자

## sequence_no
동일 Parent 하위 Child 간 정렬 순서를 관리합니다.

- 기본 10 단위 채번
- 예: 10, 20, 30, ...
- Oracle 조회 시 `ORDER SIBLINGS BY sequence_no` 활용 가능

## quantity
`quantity`는 해당 Parent 1개를 구성하기 위해 필요한 Child의 직접 소요수량입니다.

예:
FA 1개당 OLB 1개
OLB 1개당 DRIVER IC 6개

누적 소요량은 `bom.csv`에 저장하지 않고 BOM Explosion 조회 시 계산합니다.

예:
MODEL -> FA x1 -> OLB x2 -> DRIVER IC x6
모델 1대 기준 DRIVER IC 누적수량 = 1 x 2 x 6 = 12

## 유효일자
BOM 관계는 `start_date`, `end_date`로 유효기간을 관리합니다.
조회 기준일이 해당 범위에 포함되는 BOM 관계만 현재 BOM으로 간주합니다.

## Oracle 목표 조회 형태
실제 Oracle DB에서는 `START WITH / CONNECT BY PRIOR` 구조로 전체 BOM을 조회합니다.

예시:

```sql
SELECT
    LEVEL AS bom_level,
    CONNECT_BY_ROOT bom_child AS root_model,
    bom_parent,
    bom_parent_name,
    bom_child,
    bom_child_name,
    location,
    sequence_no,
    quantity,
    start_date,
    end_date,
    SYS_CONNECT_BY_PATH(bom_child, '/') AS bom_path
FROM bom
WHERE :as_of_date BETWEEN start_date AND end_date
START WITH bom_parent = 'MODEL'
       AND bom_child = :model_id
CONNECT BY PRIOR bom_child = bom_parent
ORDER SIBLINGS BY sequence_no;
```

Python 샘플 구현에서도 저장 스키마는 동일하게 유지하고 아래 값은 조회 시 동적으로 계산합니다.

- level
- root_model
- bom_path
- required_quantity (누적 소요량)

## 주요 파일
- products.csv: Model Master
- materials.csv: FA/Assembly/Component Master
- bom.csv: Parent-Child BOM 관계
- bom_hierarchy.csv: 표준 Assembly hierarchy 정의
- material_attributes.csv: Rule Engine용 구조화 사양
- compatibility.csv: Model/Assembly 간 호환성
- rules.csv: 설계변경/품평회 Rule
- change_history.csv: 변경 이력
- review_checklist.csv: 품평회 Checklist
- suppliers.csv: 공급사 Master
- test_questions.csv: Agent 평가 질문
- data_dictionary.csv: 데이터 Dictionary

## 설계변경 Assembly REPLACE 원칙
1. 대상 Model의 Virtual BOM에서 기존 Assembly 연결과 그 하위 subtree 제거
2. 신규 Assembly를 같은 위치에 연결
3. 신규 Assembly가 가진 전체 하위 BOM subtree 재귀 추가
4. 새 관계의 sequence_no / quantity 유지 또는 교체 기준에 따라 반영
5. 실제 BOM 반영 전 Rule / Compatibility / Approval / Lifecycle 검증
