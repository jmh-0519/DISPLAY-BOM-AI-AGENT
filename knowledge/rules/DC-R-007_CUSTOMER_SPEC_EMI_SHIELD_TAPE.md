+++
rule_id = "DC-R-007"
revision_no = 1
rule_name = "CUSTOMER_SPEC MATERIAL suitability"
description = "고객 사양 대응을 위한 EMI SHIELD TAPE MATERIAL 추가 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["ADD"]
reason_codes = ["CUSTOMER_SPEC"]
evaluation_item = "EMI SHIELD TAPE"
required = true
weight = 100
tags = ["customer-spec", "add", "emi-shield"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "EMI_SHIELD_TAPE"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "shielding_db"
operator = "GE"
expected_value = "60"
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
# Customer Spec EMI Shield Tape ADD Rule

고객 사양 대응을 위한 신규 자재 추가는 사용자에게 추가 대상을 먼저 특정받고, 해당 품목군의 기술 Evidence만 평가한다.
