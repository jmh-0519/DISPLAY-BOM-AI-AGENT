from datetime import date
from pathlib import Path

import pandas as pd

from services.bom_service import BomService
from services.design_change_apply_service import DesignChangeApplyService


class DesignChangeService:
    """
    Display BOM 설계변경 가능 여부를 분석하는 Service입니다.

    Preview BOM 생성/교체 구조 계산은 DesignChangeApplyService에 위임합니다.
    이 클래스는 분석과 판정만 담당합니다.
    """

    def __init__(
        self,
        bom_service: BomService,
        data_dir: str = "data",
        apply_service: DesignChangeApplyService | None = None,
    ) -> None:
        self.bom_service = bom_service
        self.data_dir = Path(data_dir)
        self.apply_service = (
            apply_service
            if apply_service is not None
            else DesignChangeApplyService(bom_service)
        )

        self.compatibility = self._load_csv("compatibility.csv")
        self.rules = self._load_csv("rules.csv")
        self.material_attributes = self._load_csv(
            "material_attributes.csv"
        )
        self.suppliers = self._load_csv("suppliers.csv")

    def _load_csv(self, file_name: str) -> pd.DataFrame:
        file_path = self.data_dir / file_name
        if not file_path.exists():
            raise FileNotFoundError(
                f"데이터 파일을 찾을 수 없습니다: {file_path.resolve()}"
            )
        return pd.read_csv(file_path, encoding="utf-8-sig")

    def analyze_replace(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | date | None = None,
    ) -> dict:
        checks: list[dict] = []
        blocking_reasons: list[str] = []

        product = self.bom_service.get_product(product_id)

        if product is None:
            checks.append({
                "check": "PRODUCT_EXISTS",
                "status": "FAIL",
                "message": f"대상 Model을 찾을 수 없습니다: {product_id}",
            })
            blocking_reasons.append(
                f"대상 Model이 존재하지 않습니다: {product_id}"
            )
            return self._build_result(
                product_id,
                old_material_id,
                new_material_id,
                checks,
                blocking_reasons,
            )

        checks.append({
            "check": "PRODUCT_EXISTS",
            "status": "PASS",
            "message": f"대상 Model이 존재합니다: {product_id}",
        })

        bom = self.bom_service.get_bom_explosion(
            model_id=product_id,
            as_of_date=as_of_date,
        )

        old_material_exists = (
            not bom.empty
            and bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(old_material_id.strip().upper())
            .any()
        )

        if not old_material_exists:
            checks.append({
                "check": "OLD_MATERIAL_IN_BOM",
                "status": "FAIL",
                "message": (
                    "기존 자재가 대상 Model의 현재 유효 BOM에 없습니다: "
                    f"{old_material_id}"
                ),
            })
            blocking_reasons.append(
                f"기존 자재가 대상 Model BOM에 없습니다: {old_material_id}"
            )
            return self._build_result(
                product_id,
                old_material_id,
                new_material_id,
                checks,
                blocking_reasons,
            )

        checks.append({
            "check": "OLD_MATERIAL_IN_BOM",
            "status": "PASS",
            "message": (
                "기존 자재가 대상 Model의 현재 유효 BOM에 존재합니다: "
                f"{old_material_id}"
            ),
        })

        new_material = self._find_exact_material(new_material_id)

        if new_material is None:
            checks.append({
                "check": "NEW_MATERIAL_EXISTS",
                "status": "FAIL",
                "message": f"신규 자재를 찾을 수 없습니다: {new_material_id}",
            })
            blocking_reasons.append(
                f"신규 자재가 존재하지 않습니다: {new_material_id}"
            )
            return self._build_result(
                product_id,
                old_material_id,
                new_material_id,
                checks,
                blocking_reasons,
            )

        checks.append({
            "check": "NEW_MATERIAL_EXISTS",
            "status": "PASS",
            "message": f"신규 자재가 존재합니다: {new_material_id}",
        })

        approval_status = str(
            new_material.get("approval_status", "")
        ).strip().upper()

        if approval_status == "APPROVED":
            approval_check = "PASS"
            approval_message = (
                f"신규 자재가 승인된 상태입니다: {new_material_id}"
            )
        elif approval_status == "CONDITIONAL":
            approval_check = "CONDITIONAL"
            approval_message = (
                f"신규 자재가 조건부 승인 상태입니다: {new_material_id}"
            )
        else:
            approval_check = "FAIL"
            approval_message = (
                "신규 자재의 승인 상태가 부적합합니다: "
                f"{approval_status}"
            )
            blocking_reasons.append(
                f"신규 자재 승인 상태가 부적합합니다: {approval_status}"
            )

        checks.append({
            "check": "NEW_MATERIAL_APPROVAL",
            "status": approval_check,
            "message": approval_message,
        })

        lifecycle_status = str(
            new_material.get("lifecycle_status", "")
        ).strip().upper()

        if lifecycle_status == "ACTIVE":
            lifecycle_check = "PASS"
            lifecycle_message = (
                "신규 자재가 사용 가능한 Lifecycle 상태입니다: "
                f"{lifecycle_status}"
            )
        else:
            lifecycle_check = "FAIL"
            lifecycle_message = (
                "신규 자재가 사용 불가능한 Lifecycle 상태입니다: "
                f"{lifecycle_status}"
            )
            blocking_reasons.append(
                "신규 자재 Lifecycle 상태가 부적합합니다: "
                f"{lifecycle_status}"
            )

        checks.append({
            "check": "NEW_MATERIAL_LIFECYCLE",
            "status": lifecycle_check,
            "message": lifecycle_message,
        })

        self._append_compatibility_check(
            product_id=product_id,
            new_material_id=new_material_id,
            exploded_bom=bom,
            checks=checks,
            blocking_reasons=blocking_reasons,
        )

        virtual_bom = self.apply_service.preview_replace(
            product_id=product_id,
            old_material_id=old_material_id,
            new_material_id=new_material_id,
            as_of_date=as_of_date,
        )

        self._append_rule_validation_check(
            product_id=product_id,
            virtual_bom=virtual_bom,
            checks=checks,
            blocking_reasons=blocking_reasons,
        )

        return self._build_result(
            product_id,
            old_material_id,
            new_material_id,
            checks,
            blocking_reasons,
        )

    def _find_exact_material(
        self,
        material_id: str,
    ) -> dict | None:
        materials = self.bom_service.materials
        result = materials[
            materials["material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(material_id.strip().upper())
        ]
        if result.empty:
            return None
        return result.iloc[0].to_dict()

    def _append_compatibility_check(
        self,
        product_id: str,
        new_material_id: str,
        exploded_bom: pd.DataFrame,
        checks: list[dict],
        blocking_reasons: list[str],
    ) -> None:
        candidate_rows = self.compatibility[
            self.compatibility["source_material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(new_material_id.strip().upper())
            & self.compatibility["active_yn"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("Y")
        ]

        bom_material_ids = (
            set()
            if exploded_bom.empty
            else set(
                exploded_bom["bom_child"]
                .astype(str)
                .str.strip()
                .str.upper()
                .tolist()
            )
        )

        applicable_rows = []

        for _, row in candidate_rows.iterrows():
            target_type = str(row["target_type"]).strip().upper()
            target_id = str(row["target_id"]).strip()

            if (
                target_type == "MODEL"
                and target_id.upper() == product_id.upper()
            ):
                applicable_rows.append(row)
            elif (
                target_type == "MATERIAL"
                and target_id.upper() in bom_material_ids
            ):
                applicable_rows.append(row)

        if not applicable_rows:
            checks.append({
                "check": "COMPATIBILITY",
                "status": "PASS",
                "message": (
                    "적용 대상에 대해 정의된 Compatibility 제한이 없습니다."
                ),
            })
            return

        status = "PASS"
        messages: list[str] = []

        for row in applicable_rows:
            result = str(row["result"]).strip().upper()
            target_id = str(row["target_id"]).strip()
            reason = str(row["reason"]).strip()

            if result == "INCOMPATIBLE":
                status = "FAIL"
                message = (
                    "신규 자재와 대상 간 Compatibility가 부적합합니다. "
                    f"대상: {target_id}, 사유: {reason}"
                )
                messages.append(message)
                blocking_reasons.append(message)
            elif result == "CONDITIONAL" and status != "FAIL":
                status = "CONDITIONAL"
                messages.append(
                    "신규 자재 적용 시 추가 검토가 필요합니다. "
                    f"대상: {target_id}, 사유: {reason}"
                )
            elif result == "COMPATIBLE":
                messages.append(
                    f"Compatibility 조건을 충족합니다. 대상: {target_id}"
                )

        checks.append({
            "check": "COMPATIBILITY",
            "status": status,
            "message": " ".join(messages),
        })

    def validate_compatibility(
        self,
        product_id: str,
        new_material_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        """
        기존 Compatibility 검증 로직을
        외부 Service에서도 사용할 수 있도록 제공합니다.
        """

        checks: list[dict] = []
        blocking_reasons: list[str] = []

        self._append_compatibility_check(
            product_id=product_id,
            new_material_id=new_material_id,
            exploded_bom=bom,
            checks=checks,
            blocking_reasons=blocking_reasons,
        )

        compatibility_check = next(
            (
                check
                for check in checks
                if check["check"] == "COMPATIBILITY"
            ),
            None,
        )

        if compatibility_check is None:
            return {
                "status": "PASS",
                "message": (
                    "Compatibility 검증 결과가 없습니다."
                ),
                "blocking_reasons": [],
            }

        return {
            "status": compatibility_check["status"],
            "message": compatibility_check["message"],
            "blocking_reasons": blocking_reasons,
        }        

    def get_applicable_rules(
        self,
        product_id: str,
    ) -> pd.DataFrame:
        product = self.bom_service.get_product(product_id)

        if product is None:
            return pd.DataFrame(columns=self.rules.columns)

        product_id_value = str(
            product.get("product_id", product_id)
        ).strip().upper()
        product_type_value = str(
            product.get("product_type", "")
        ).strip().upper()
        market_value = str(
            product.get("market", "")
        ).strip().upper()

        active_rules = self.rules[
            self.rules["active_yn"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("Y")
        ].copy()

        def matches_values(
            actual_value: str,
            expected_expression: str,
        ) -> bool:
            expected_values = {
                value.strip().upper()
                for value in expected_expression.split("|")
                if value.strip()
            }
            return actual_value in expected_values

        def is_applicable(scope: str) -> bool:
            scope_value = str(scope).strip()

            if not scope_value:
                return False

            if scope_value.upper() == "ALL":
                return True

            if "=" not in scope_value:
                return False

            scope_key, scope_expected = scope_value.split("=", 1)
            scope_key = scope_key.strip().upper()
            scope_expected = scope_expected.strip()

            if scope_key == "PRODUCT":
                return matches_values(
                    product_id_value, scope_expected
                )
            if scope_key == "PRODUCT_TYPE":
                return matches_values(
                    product_type_value, scope_expected
                )
            if scope_key == "MARKET":
                return matches_values(
                    market_value, scope_expected
                )
            if scope_key == "CATEGORY":
                return True

            return False

        applicable_mask = (
            active_rules["scope"]
            .astype(str)
            .apply(is_applicable)
        )

        return active_rules[applicable_mask].copy()

    def _evaluate_operator(
        self,
        actual_value,
        operator: str,
        expected_value,
        expected_value_max=None,
    ) -> bool:
        operator = str(operator).strip().upper()

        if operator == "EXISTS":
            return actual_value is not None

        if operator in {"IN", "NOT_IN"}:
            expected_values = {
                value.strip().upper()
                for value in str(expected_value).split("|")
                if value.strip()
            }
            actual = str(actual_value).strip().upper()
            if operator == "IN":
                return actual in expected_values
            return actual not in expected_values

        if operator == "=":
            return (
                str(actual_value).strip().upper()
                == str(expected_value).strip().upper()
            )

        if operator == "!=":
            return (
                str(actual_value).strip().upper()
                != str(expected_value).strip().upper()
            )

        try:
            actual_number = float(actual_value)
            expected_number = float(expected_value)
        except (TypeError, ValueError):
            return False

        if operator == ">=":
            return actual_number >= expected_number
        if operator == ">":
            return actual_number > expected_number
        if operator == "<=":
            return actual_number <= expected_number
        if operator == "<":
            return actual_number < expected_number

        if operator == "BETWEEN":
            try:
                max_number = float(expected_value_max)
            except (TypeError, ValueError):
                return False
            return expected_number <= actual_number <= max_number

        return False

    def _get_virtual_bom_materials(
        self,
        virtual_bom: pd.DataFrame,
    ) -> pd.DataFrame:
        if virtual_bom.empty:
            return pd.DataFrame(
                columns=self.bom_service.materials.columns
            )

        material_ids = set(
            virtual_bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .tolist()
        )

        materials = self.bom_service.materials.copy()

        return materials[
            materials["material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(material_ids)
        ].copy()

    def _get_attribute_values(
        self,
        virtual_bom: pd.DataFrame,
        target_category: str,
        attribute_name: str,
    ) -> list:
        materials = self._get_virtual_bom_materials(
            virtual_bom
        )

        if materials.empty:
            return []

        category_materials = materials[
            materials["category"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(str(target_category).strip().upper())
        ]

        if category_materials.empty:
            return []

        material_ids = set(
            category_materials["material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .tolist()
        )

        attributes = self.material_attributes[
            self.material_attributes["material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(material_ids)
            & self.material_attributes["attribute_name"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(str(attribute_name).strip().upper())
        ]

        return attributes["attribute_value"].tolist()

    def _validate_single_rule(
        self,
        rule: pd.Series,
        virtual_bom: pd.DataFrame,
    ) -> dict:
        rule_id = str(rule["rule_id"])
        metric = str(rule["metric"]).strip().upper()
        operator = str(rule["operator"]).strip().upper()
        expected_value = rule["expected_value"]
        expected_value_max = rule.get("expected_value_max")
        target_category = str(
            rule.get("target_category", "")
        ).strip().upper()
        severity = str(rule["severity"]).strip().upper()
        message = str(rule["message_ko"])

        passed = False
        actual_value = None

        if metric == "LOCATION_EXISTS":
            locations = set(
                virtual_bom["location"]
                .astype(str)
                .str.strip()
                .str.upper()
                .tolist()
            )
            actual_value = target_category
            passed = target_category in locations

        elif metric == "LIFECYCLE_STATUS":
            materials = self._get_virtual_bom_materials(
                virtual_bom
            )
            failed_materials = []

            for _, material in materials.iterrows():
                value = material["lifecycle_status"]
                if not self._evaluate_operator(
                    value,
                    operator,
                    expected_value,
                    expected_value_max,
                ):
                    failed_materials.append(
                        str(material["material_id"])
                    )

            passed = len(failed_materials) == 0
            actual_value = (
                failed_materials
                if failed_materials
                else "ALL_VALID"
            )

        elif metric == "APPROVAL_STATUS":
            materials = self._get_virtual_bom_materials(
                virtual_bom
            )
            failed_materials = []

            for _, material in materials.iterrows():
                value = material["approval_status"]
                if not self._evaluate_operator(
                    value,
                    operator,
                    expected_value,
                    expected_value_max,
                ):
                    failed_materials.append(
                        str(material["material_id"])
                    )

            passed = len(failed_materials) == 0
            actual_value = (
                failed_materials
                if failed_materials
                else "ALL_VALID"
            )

        elif metric == "SUPPLIER_GRADE":
            materials = self._get_virtual_bom_materials(
                virtual_bom
            )

            merged = materials[
                ["material_id", "supplier_id"]
            ].merge(
                self.suppliers[["supplier_id", "grade"]],
                on="supplier_id",
                how="left",
            )

            failed_materials = []

            for _, material in merged.iterrows():
                if not self._evaluate_operator(
                    material["grade"],
                    operator,
                    expected_value,
                    expected_value_max,
                ):
                    failed_materials.append(
                        str(material["material_id"])
                    )

            passed = len(failed_materials) == 0
            actual_value = (
                failed_materials
                if failed_materials
                else "ALL_VALID"
            )

        else:
            values = self._get_attribute_values(
                virtual_bom=virtual_bom,
                target_category=target_category,
                attribute_name=metric,
            )

            if not values:
                passed = False
                actual_value = None
            else:
                aggregation = str(
                    rule.get("aggregation", "")
                ).strip().upper()

                numeric_values = []
                for value in values:
                    try:
                        numeric_values.append(float(value))
                    except (TypeError, ValueError):
                        pass

                if aggregation == "MAX" and numeric_values:
                    actual_value = max(numeric_values)
                elif aggregation == "MIN" and numeric_values:
                    actual_value = min(numeric_values)
                else:
                    actual_value = values[0]

                passed = self._evaluate_operator(
                    actual_value,
                    operator,
                    expected_value,
                    expected_value_max,
                )

        if passed:
            status = "PASS"
        elif severity == "WARNING":
            status = "CONDITIONAL"
        else:
            status = "FAIL"

        return {
            "rule_id": rule_id,
            "status": status,
            "metric": metric,
            "actual_value": actual_value,
            "expected_value": expected_value,
            "message": message,
        }

    def _validate_rules(
        self,
        product_id: str,
        virtual_bom: pd.DataFrame,
    ) -> list[dict]:
        applicable_rules = self.get_applicable_rules(
            product_id
        )

        return [
            self._validate_single_rule(
                rule=rule,
                virtual_bom=virtual_bom,
            )
            for _, rule in applicable_rules.iterrows()
        ]

    def validate_bom_rules(
        self,
        product_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        """
        이미 생성되어 있는 BOM DataFrame 전체를
        기존 Rule Engine으로 검증합니다.

        Design Change BOM과 Review BOM에서
        공통으로 사용할 수 있습니다.
        """

        rule_results = self._validate_rules(
            product_id=product_id,
            virtual_bom=bom,
        )

        statuses = {
            str(result["status"])
            .strip()
            .upper()
            for result in rule_results
        }

        if "FAIL" in statuses:
            result = "FAIL"

        elif "CONDITIONAL" in statuses:
            result = "CONDITIONAL"

        else:
            result = "PASS"

        return {
            "result": result,
            "rule_results": rule_results,
        }    

    def _append_rule_validation_check(
        self,
        product_id: str,
        virtual_bom: pd.DataFrame,
        checks: list[dict],
        blocking_reasons: list[str],
    ) -> None:
        rule_results = self._validate_rules(
            product_id=product_id,
            virtual_bom=virtual_bom,
        )

        fail_results = [
            result
            for result in rule_results
            if result["status"] == "FAIL"
        ]
        conditional_results = [
            result
            for result in rule_results
            if result["status"] == "CONDITIONAL"
        ]

        if fail_results:
            messages = [
                (
                    f"{result['rule_id']}: "
                    f"{result['message']} "
                    f"(actual={result['actual_value']})"
                )
                for result in fail_results
            ]
            message = " ".join(messages)

            checks.append({
                "check": "RULE_VALIDATION",
                "status": "FAIL",
                "message": message,
                "rule_results": rule_results,
            })
            blocking_reasons.append(message)
            return

        if conditional_results:
            messages = [
                (
                    f"{result['rule_id']}: "
                    f"{result['message']} "
                    f"(actual={result['actual_value']})"
                )
                for result in conditional_results
            ]

            checks.append({
                "check": "RULE_VALIDATION",
                "status": "CONDITIONAL",
                "message": " ".join(messages),
                "rule_results": rule_results,
            })
            return

        checks.append({
            "check": "RULE_VALIDATION",
            "status": "PASS",
            "message": "적용 가능한 모든 BOM Rule을 충족했습니다.",
            "rule_results": rule_results,
        })

    def _build_result(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        checks: list[dict],
        blocking_reasons: list[str],
    ) -> dict:
        warnings = [
            check["message"]
            for check in checks
            if check["status"] == "CONDITIONAL"
        ]

        if blocking_reasons:
            result = "FAIL"
            changeable = False
            recommended_action = "CHANGE_BLOCKED"
        elif warnings:
            result = "CONDITIONAL"
            changeable = True
            recommended_action = "REVIEW_REQUIRED"
        else:
            result = "PASS"
            changeable = True
            recommended_action = "READY_FOR_NEXT_CHECK"

        return {
            "success": True,
            "product_id": product_id,
            "change_type": "REPLACE",
            "old_material_id": old_material_id,
            "new_material_id": new_material_id,
            "result": result,
            "changeable": changeable,
            "checks": checks,
            "warnings": warnings,
            "blocking_reasons": blocking_reasons,
            "recommended_action": recommended_action,
        }
