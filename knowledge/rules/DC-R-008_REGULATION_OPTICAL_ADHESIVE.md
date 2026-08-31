+++
rule_id = "DC-R-008"
revision_no = 1
rule_name = "REGULATION MATERIAL suitability"
description = "규제 대응을 위한 OPTICAL ADHESIVE MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["REGULATION"]
evaluation_item = "OPTICAL ADHESIVE"
required = true
weight = 100
tags = ["regulation", "optical-adhesive", "rohs"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "OPTICAL_ADHESIVE"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "rohs_status"
operator = "EQ"
expected_value = "COMPLIANT"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "halogen_free"
operator = "EQ"
expected_value = "Y"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Regulation Optical Adhesive Replacement Rule

규제 대응에서는 규제 준수 상태와 환경 요구 조건을 기술 적합성 Evidence로 확인한다.
