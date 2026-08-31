+++
rule_id = "DC-R-001"
revision_no = 1
rule_name = "EOL MATERIAL suitability"
description = "단종 대응을 위한 DRIVE-IC 계열 MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["EOL"]
evaluation_item = "DRIVE-IC"
required = true
weight = 100
tags = ["lifecycle", "eol", "drive-ic"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "DRIVER_IC"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "interface"
operator = "EQ"
expected_value = "LVDS"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "operating_voltage"
operator = "LE"
expected_value = "3.3"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# EOL DRIVE-IC Replacement Rule

단종된 DRIVE-IC를 교체할 때 후보의 기본 계열, 인터페이스, 동작 전압을 확인한다.
기술 Evidence가 누락되면 임의로 적합하다고 판단하지 않고 `CONDITIONAL`로 유지한다.
