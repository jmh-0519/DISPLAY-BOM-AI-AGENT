+++
rule_id = "DC-R-003"
revision_no = 1
rule_name = "LEAD_TIME ASSY suitability"
description = "납기 개선을 위한 OLB ASSY 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["ASSY"]
action_types = ["REPLACE"]
reason_codes = ["LEAD_TIME"]
evaluation_item = "OLB"
required = true
weight = 100
tags = ["supply", "lead-time", "olb"]

[[conditions]]
attribute_name = "process_name"
operator = "EQ"
expected_value = "OLB"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "panel_size_inch"
operator = "IN"
expected_value = "50.0"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "resolution"
operator = "EQ"
expected_value = "UHD"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Lead Time OLB ASSY Replacement Rule

납기 개선 목적의 ASSY 교체에서도 공정 종류와 제품 적용 조건은 유지되어야 한다.
