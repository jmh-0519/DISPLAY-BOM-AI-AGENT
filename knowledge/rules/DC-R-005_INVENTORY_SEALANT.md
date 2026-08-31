+++
rule_id = "DC-R-005"
revision_no = 1
rule_name = "INVENTORY MATERIAL suitability"
description = "재고 문제 대응을 위한 SEALANT MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["INVENTORY"]
evaluation_item = "SEALANT"
required = true
weight = 100
tags = ["inventory", "sealant"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "SEALANT"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "curing_type"
operator = "EQ"
expected_value = "UV"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "viscosity_cps"
operator = "LE"
expected_value = "3500"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Inventory SEALANT Replacement Rule

재고 문제를 해결하기 위한 대체라도 재료 계열, 경화 방식, 점도 조건은 기술 적합성 Evidence로 검증한다.
