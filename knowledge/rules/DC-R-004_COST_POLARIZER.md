+++
rule_id = "DC-R-004"
revision_no = 1
rule_name = "COST MATERIAL suitability"
description = "원가 절감을 위한 POLARIZER MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["COST"]
evaluation_item = "POLARIZER"
required = true
weight = 100
tags = ["cost", "polarizer"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "POLARIZER"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "transmittance_pct"
operator = "GE"
expected_value = "42"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "thickness_um"
operator = "LE"
expected_value = "220"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Cost Reduction POLARIZER Rule

원가가 낮더라도 광학 특성과 두께 조건을 만족하지 못하면 대체 후보로 승인할 수 없다.
