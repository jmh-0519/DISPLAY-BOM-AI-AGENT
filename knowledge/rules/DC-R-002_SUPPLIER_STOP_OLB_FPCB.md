+++
rule_id = "DC-R-002"
revision_no = 1
rule_name = "SUPPLIER_STOP MATERIAL suitability"
description = "공급 중단 대응을 위한 OLB FPCB MATERIAL 대체 적합성 기준"
status = "ACTIVE"
valid_from = "2026-08-15"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["SUPPLIER_STOP"]
evaluation_item = "OLB FPCB"
required = true
weight = 100
tags = ["supply", "supplier-stop", "olb-fpcb"]

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "OLB_FPCB"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "layer_count"
operator = "IN"
expected_value = "4.0"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100

[[conditions]]
attribute_name = "connector_pitch_mm"
operator = "IN"
expected_value = "0.5"
missing_result = "CONDITIONAL"
fail_result = "FAIL"
score = 100
+++
# Supplier Stop OLB FPCB Replacement Rule

공급 중단 시 기존 OLB FPCB의 기능적 정합성을 유지하기 위해 층수와 커넥터 피치 Evidence를 확인한다.
