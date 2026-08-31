+++
rule_id = "DC-R-009"
revision_no = 1
rule_name = "COMMONIZATION MATERIAL suitability"
description = "부품 공용화를 위한 BRACKET MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["COMMONIZATION"]
evaluation_item = "BRACKET"
required = true
weight = 100
tags = ["commonization", "bracket"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "BRACKET"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "hole_pitch_mm"
operator = "IN"
expected_value = "80.0"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "material_grade"
operator = "EQ"
expected_value = "AL6061"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Commonization BRACKET Replacement Rule

공용화 목적의 변경은 여러 BOM에 영향을 줄 수 있으므로 기술 적합성과 함께 기존 공용 영향 분석 절차를 유지한다.
