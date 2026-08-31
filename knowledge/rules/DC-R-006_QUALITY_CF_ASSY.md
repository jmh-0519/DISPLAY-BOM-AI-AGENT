+++
rule_id = "DC-R-006"
revision_no = 1
rule_name = "QUALITY ASSY suitability"
description = "품질 개선을 위한 CF ASSY 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["ASSY"]
action_types = ["REPLACE"]
reason_codes = ["QUALITY"]
evaluation_item = "CF"
required = true
weight = 100
tags = ["quality", "cf"]

[[conditions]]
attribute_name = "process_name"
operator = "EQ"
expected_value = "CF"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "panel_size_inch"
operator = "IN"
expected_value = "55.0"
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
# Quality CF ASSY Replacement Rule

품질 개선 목적이라도 기존 제품과 공정/제품 적용 조건이 일치하는지 먼저 검증한다.
