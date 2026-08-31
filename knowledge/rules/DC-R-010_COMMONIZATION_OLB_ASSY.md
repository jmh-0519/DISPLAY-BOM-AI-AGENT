+++
rule_id = "DC-R-010"
revision_no = 1
rule_name = "COMMONIZATION ASSY suitability"
description = "공용 ASSY 통합을 위한 OLB ASSY 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["ASSY"]
action_types = ["REPLACE"]
reason_codes = ["COMMONIZATION"]
evaluation_item = "OLB"
required = true
weight = 100
tags = ["commonization", "assy", "olb"]

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
expected_value = "75.0"
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
# Commonization OLB ASSY Replacement Rule

공용 ASSY 통합에서는 공정 및 제품 적용 조건을 검증하고, 실제 변경 전 공용 BOM 영향 범위를 별도로 확인한다.
