from services.bom_service import BomService
from services.design_change_service import DesignChangeService


TEST_DATE = "2026-08-10"


def create_service() -> DesignChangeService:
    return DesignChangeService(
        bom_service=BomService()
    )


def test_design_change_service_loads_data() -> None:
    service = create_service()
    assert not service.compatibility.empty
    assert not service.rules.empty
    assert not service.material_attributes.empty


def test_analyze_replace_passes_product_check() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["PRODUCT_EXISTS"] == "PASS"


def test_analyze_replace_fails_when_product_not_found() -> None:
    service = create_service()
    result = service.analyze_replace(
        "UNKNOWN-MODEL", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    assert result["result"] == "FAIL"
    assert result["changeable"] is False
    assert result["recommended_action"] == "CHANGE_BLOCKED"


def test_analyze_replace_finds_nested_old_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-100004", "LJ94-190004",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["OLD_MATERIAL_IN_BOM"] == "PASS"


def test_analyze_replace_fails_when_old_material_not_in_bom() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-130004", "LJ94-190004",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert result["result"] == "FAIL"
    assert statuses["OLD_MATERIAL_IN_BOM"] == "FAIL"


def test_analyze_replace_fails_when_new_material_not_found() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-100004", "LJ94-999999",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert result["result"] == "FAIL"
    assert statuses["NEW_MATERIAL_EXISTS"] == "FAIL"


def test_analyze_replace_passes_approved_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["NEW_MATERIAL_APPROVAL"] == "PASS"
    assert statuses["NEW_MATERIAL_LIFECYCLE"] == "PASS"


def test_analyze_replace_returns_conditional_for_conditional_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-100004", "LJ94-190004",
        as_of_date=TEST_DATE,
    )
    assert result["result"] == "CONDITIONAL"
    assert result["changeable"] is True
    assert result["recommended_action"] == "REVIEW_REQUIRED"


def test_analyze_replace_fails_rejected_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA550HR01-0", "LJ94-130006", "LJ94-190006",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert result["result"] == "FAIL"
    assert statuses["NEW_MATERIAL_APPROVAL"] == "FAIL"


def test_analyze_replace_fails_discontinued_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA550HR01-0", "LJ94-130006", "LJ94-190006",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["NEW_MATERIAL_LIFECYCLE"] == "FAIL"


def test_analyze_replace_includes_compatibility_check() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert "COMPATIBILITY" in statuses


def test_analyze_replace_passes_compatible_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["COMPATIBILITY"] == "PASS"
    assert result["result"] == "PASS"


def test_analyze_replace_returns_conditional_for_compatibility() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-100001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["COMPATIBILITY"] == "CONDITIONAL"
    assert result["result"] == "CONDITIONAL"


def test_analyze_replace_fails_incompatible_material() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "LJ94-100005", "LJ94-190005",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["COMPATIBILITY"] == "FAIL"
    assert result["result"] == "FAIL"


def test_analyze_replace_uses_current_effective_bom() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-119905", "LJ94-190005",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["OLD_MATERIAL_IN_BOM"] == "FAIL"


def test_analyze_replace_can_use_historical_bom() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-119905", "LJ94-190005",
        as_of_date="2026-06-15",
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["OLD_MATERIAL_IN_BOM"] == "PASS"


def test_get_applicable_rules_returns_active_rules() -> None:
    service = create_service()
    result = service.get_applicable_rules("LTA400HR02-0")
    assert not result.empty
    assert result["active_yn"].astype(str).str.upper().eq("Y").all()


def test_get_applicable_rules_includes_product_specific_rule() -> None:
    service = create_service()
    result = service.get_applicable_rules("LTA400HR02-0")
    assert "RULE-011" in set(result["rule_id"].astype(str).tolist())


def test_get_applicable_rules_excludes_other_product_rule() -> None:
    service = create_service()
    result = service.get_applicable_rules("LTA400HR02-0")
    rule_ids = set(result["rule_id"].astype(str).tolist())
    assert "RULE-012" not in rule_ids
    assert "RULE-013" not in rule_ids
    assert "RULE-014" not in rule_ids


def test_get_applicable_rules_includes_all_rules() -> None:
    service = create_service()
    result = service.get_applicable_rules("LTA400HR01-0")
    rule_ids = set(result["rule_id"].astype(str).tolist())
    for rule_id in [
        "RULE-001", "RULE-002", "RULE-003", "RULE-004",
        "RULE-005", "RULE-006", "RULE-007", "RULE-008",
        "RULE-009", "RULE-010",
    ]:
        assert rule_id in rule_ids


def test_get_applicable_rules_returns_empty_for_unknown_product() -> None:
    service = create_service()
    assert service.get_applicable_rules("UNKNOWN-MODEL").empty


def test_rule_validation_passes_valid_virtual_bom() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["RULE_VALIDATION"] == "PASS"
    assert result["result"] == "PASS"


def test_rule_validation_fails_invalid_virtual_bom() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA550HR01-0", "LJ94-130006", "LJ94-190006",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["RULE_VALIDATION"] == "FAIL"
    assert result["result"] == "FAIL"


def test_rule_validation_returns_rule_details() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    rule_check = next(
        x for x in result["checks"] if x["check"] == "RULE_VALIDATION"
    )
    assert "rule_results" in rule_check
    assert rule_check["rule_results"]
    assert "RULE-011" in {x["rule_id"] for x in rule_check["rule_results"]}


def test_rule_validation_can_return_multiple_fail_rules() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA550HR01-0", "LJ94-130006", "LJ94-190006",
        as_of_date=TEST_DATE,
    )
    rule_check = next(
        x for x in result["checks"] if x["check"] == "RULE_VALIDATION"
    )
    failed_rules = [
        x for x in rule_check["rule_results"] if x["status"] == "FAIL"
    ]
    assert len(failed_rules) >= 1
    assert result["result"] == "FAIL"
    assert result["changeable"] is False


def test_rule_validation_detail_has_required_fields() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    rule_check = next(
        x for x in result["checks"] if x["check"] == "RULE_VALIDATION"
    )
    for rule_result in rule_check["rule_results"]:
        assert "rule_id" in rule_result
        assert "status" in rule_result
        assert "metric" in rule_result
        assert "actual_value" in rule_result
        assert "expected_value" in rule_result
        assert "message" in rule_result


def test_analyze_replace_includes_rule_validation_check() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR02-0", "LJ94-110001", "LJ94-190001",
        as_of_date=TEST_DATE,
    )
    assert "RULE_VALIDATION" in {
        x["check"] for x in result["checks"]
    }


def test_rule_validation_returns_conditional_for_warning_rule() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "0001-200010", "9000-290004",
        as_of_date=TEST_DATE,
    )
    statuses = {x["check"]: x["status"] for x in result["checks"]}
    assert statuses["NEW_MATERIAL_APPROVAL"] == "PASS"
    assert statuses["NEW_MATERIAL_LIFECYCLE"] == "PASS"
    assert statuses["COMPATIBILITY"] == "PASS"
    assert statuses["RULE_VALIDATION"] == "CONDITIONAL"
    assert result["result"] == "CONDITIONAL"
    assert result["changeable"] is True
    assert result["recommended_action"] == "REVIEW_REQUIRED"


def test_rule_validation_identifies_supplier_grade_warning() -> None:
    service = create_service()
    result = service.analyze_replace(
        "LTA400HR01-0", "0001-200010", "9000-290004",
        as_of_date=TEST_DATE,
    )
    rule_check = next(
        x for x in result["checks"] if x["check"] == "RULE_VALIDATION"
    )
    conditional_rule_ids = {
        x["rule_id"]
        for x in rule_check["rule_results"]
        if x["status"] == "CONDITIONAL"
    }
    assert "RULE-010" in conditional_rule_ids

def test_validate_bom_rules_can_validate_existing_bom() -> None:
    service = create_service()

    bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR02-0",
            as_of_date=TEST_DATE,
        )
    )

    result = service.validate_bom_rules(
        product_id="LTA400HR02-0",
        bom=bom,
    )

    assert "result" in result
    assert "rule_results" in result

    assert result["result"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }

    assert len(
        result["rule_results"]
    ) > 0

def test_validate_compatibility_public_wrapper() -> None:
    service = create_service()

    bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR02-0",
            as_of_date=TEST_DATE,
        )
    )

    result = service.validate_compatibility(
        product_id="LTA400HR02-0",
        new_material_id="LJ94-190001",
        bom=bom,
    )

    assert isinstance(
        result,
        dict,
    )

    assert "status" in result

    assert result["status"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }

    assert "message" in result

    assert "blocking_reasons" in result    