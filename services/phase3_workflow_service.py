from __future__ import annotations

import json
import uuid
from datetime import date

from repositories.design_change_repository import SQLiteDesignChangeRepository
from repositories.multi_action_repository import SQLiteMultiActionRepository
from services.impact_analysis_service import ImpactAnalysisService
from services.analysis_explain_service import DesignChangeAnalysisExplainService
from services.change_reason_resolver import ChangeReasonResolver
from services.multi_action_change_service import MultiActionApplyService
from services.query_normalizer import QueryNormalizer
from services.recommendation_service import RecommendationService
from services.supply_evaluation_service import SupplyEvaluationService


class Phase3WorkflowService:
    """Application service used by Phase3 MCP capabilities."""

    def __init__(self, database) -> None:
        self.repository = SQLiteDesignChangeRepository(database)
        self.reason_resolver = ChangeReasonResolver(self.repository)
        self.recommendation = RecommendationService(self.repository)
        self.query_normalizer = QueryNormalizer(database)
        self.supply = SupplyEvaluationService(self.repository)
        self.impact = ImpactAnalysisService(self.repository)
        self.explain = DesignChangeAnalysisExplainService(self.repository)
        self.apply_service = MultiActionApplyService(SQLiteMultiActionRepository(database))

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"

    def _apply_candidate_ranking_score(
        self,
        value: dict,
        supplier: dict,
        inventory: dict,
    ) -> None:
        """Expose a recommendation score only when the *final* candidate status is PASS.

        Technical suitability alone is not enough to rank a candidate.  Supplier
        or inventory evidence may still downgrade an otherwise technical PASS to
        CONDITIONAL/FAIL.  Therefore the final merged ``status`` is authoritative
        for public recommendation scoring.

        Legacy rule scores remain available internally as ``rule_score`` so DB
        persistence can stay backward compatible, while the public Analysis/MCP
        boundary never presents a pending candidate as a low-scored recommendation.
        """
        final_status = str(value.get("status") or "").upper()
        if final_status != "PASS":
            value["ranking_score"] = None
            value["ranking_grade"] = None
            return

        supplier_score = (
            float(supplier["recommended"]["score"])
            if supplier.get("recommended") else 0.0
        )
        inventory_score = {"PASS": 100.0, "CONDITIONAL": 50.0, "FAIL": 0.0}[
            inventory["status"]
        ]
        total_score = round(
            float(value.get("rule_score") or 0.0) * 0.6
            + supplier_score * 0.3
            + inventory_score * 0.1,
            2,
        )
        grade = self.recommendation.rule_engine.grade(total_score)
        value["total_score"] = total_score
        value["grade"] = grade
        value["ranking_score"] = total_score
        value["ranking_grade"] = grade

    @staticmethod
    def _candidate_sort_key(row: dict) -> tuple:
        status_order = {"PASS": 0, "CONDITIONAL": 1, "FAIL": 2}
        ranking_score = row.get("ranking_score")
        return (
            status_order.get(str(row.get("status") or "FAIL"), 9),
            1 if ranking_score is None else 0,
            -float(ranking_score or 0.0),
            str(row.get("candidate_item_code") or ""),
        )

    @staticmethod
    def _apply_public_candidate_score_policy(value: dict) -> None:
        """Project internal candidate evidence to the public Agent/UI contract.

        PASS candidates may expose recommendation score/grade/rank.
        CONDITIONAL means evaluation is pending, so a numeric score or recommendation
        grade would be misleading. FAIL is excluded from recommendation ranking.

        ``rule_score`` is deliberately retained as internal technical evidence; it is
        not a recommendation score and is also used to reconstruct legacy persistence
        fields when an Analysis Session is later committed as a Request.
        """
        status = str(value.get("status") or "").upper()
        if status == "PASS":
            return

        value["ranking_score"] = None
        value["ranking_grade"] = None
        value["rank"] = None
        value["total_score"] = None
        value["grade"] = "평가 보류" if status == "CONDITIONAL" else None

    def _candidate_for_persistence(self, value: dict) -> dict:
        """Restore legacy numeric fields only for repository persistence.

        Candidate tables historically store ``total_score``/``grade`` as numeric
        rule evidence.  The public Analysis contract intentionally hides those values
        for CONDITIONAL/FAIL.  Reconstructing them here keeps existing DB/report
        compatibility without leaking them back through MCP responses.
        """
        persisted = dict(value)
        if persisted.get("total_score") is None:
            score = float(persisted.get("rule_score") or 0.0)
            persisted["total_score"] = score
            persisted["grade"] = self.recommendation.rule_engine.grade(score)
        elif persisted.get("grade") in {None, "", "평가 보류", "HOLD"}:
            persisted["grade"] = self.recommendation.rule_engine.grade(
                float(persisted.get("total_score") or 0.0)
            )
        return persisted

    def create_request(self, request: dict, actions: list[dict]) -> dict:
        if not actions:
            raise ValueError("At least one action is required")

        request = self._normalize_request(dict(request))
        plant = self.repository.validate_plant(request["plant_code"])
        version = self.repository.get_item(request["version_code"])
        if not version or version["item_type"] != "VERSION" or version["active_yn"] != "Y":
            raise ValueError("version_code must be an active VERSION")

        request_context = " ".join(str(request.get(name) or "") for name in (
            "original_request", "normalized_request",
        )).strip()
        normalized_actions = []
        resolved_reasons_by_action = []
        semantic_action_indexes = {}
        for action in actions:
            value = dict(action)
            value.setdefault("action_id", self._id("ACT"))
            self._normalize_and_validate_action(value, request)
            semantic_key = (
                value.get("action_type"), value.get("target_type"),
                value.get("parent_item_code"), value.get("old_item_code"),
                value.get("new_item_code"), value.get("location_code"),
                value.get("new_quantity"),
            )
            resolved = self.reason_resolver.resolve_all(
                proposed_reasons=request.get("reasons"),
                original_request=request_context,
                target_type=value["target_type"],
                action_type=value["action_type"],
                explicit_action_reason=value.get("reason_code"),
            )
            reason_records = [reason.as_record() for reason in resolved]
            # STEP33-C: one business change is one Action even when the LLM emits
            # duplicate actions for multiple reasons (e.g. EOL + COST). Merge any
            # additional reason records into the surviving Action rather than losing
            # them or creating duplicate candidate-selection requirements.
            if semantic_key in semantic_action_indexes:
                index = semantic_action_indexes[semantic_key]
                existing = resolved_reasons_by_action[index]
                existing_codes = {row.get("reason_code") for row in existing}
                for record in reason_records:
                    if record.get("reason_code") in existing_codes:
                        continue
                    merged = dict(record)
                    if any(row.get("is_primary") == "Y" for row in existing):
                        merged["is_primary"] = "N"
                    existing.append(merged)
                    existing_codes.add(merged.get("reason_code"))
                continue
            semantic_action_indexes[semantic_key] = len(normalized_actions)
            normalized_actions.append(value)
            resolved_reasons_by_action.append(reason_records)

        request["reasons"] = list(dict.fromkeys(
            reason["reason_code"]
            for action_reasons in resolved_reasons_by_action
            for reason in action_reasons
        ))
        self.repository.create_request(
            request, normalized_actions, resolved_reasons_by_action
        )
        for action in normalized_actions:
            if action["action_type"] in {"DELETE", "QUANTITY_CHANGE"}:
                self.repository.set_action_evaluation_status(
                    action["action_id"], action.get("evaluation_status") or "PASS"
                )
        return {
            "request_id": request["request_id"],
            "plant_code": plant["plant_code"],
            "plant_name": plant["plant_name"],
            "reasons": request["reasons"],
            "request_defaults": {
                "as_of_date": request["as_of_date"],
                "effective_date": request["effective_date"],
            },
            "actions": normalized_actions,
            "workflow_status": "REQUESTED",
            "production_bom_modified": False,
        }

    def _normalize_request(self, request: dict) -> dict:
        request.setdefault("request_id", self._id("REQ"))
        plant_code = str(request.get("plant_code") or "").strip().upper()
        if not plant_code:
            raise ValueError("plant_code is required")
        request["plant_code"] = plant_code

        version_code = str(request.get("version_code") or "").strip().upper()
        if not version_code:
            raise ValueError("version_code is required")
        request["version_code"] = version_code

        today = date.today().isoformat()
        as_of_date = str(request.get("as_of_date") or today).strip()
        effective_date = str(request.get("effective_date") or as_of_date).strip()
        if effective_date < as_of_date:
            raise ValueError("effective_date must be on or after as_of_date")
        request["as_of_date"] = as_of_date
        request["effective_date"] = effective_date

        # Active Phase3 quantity policy: use the BOM relation QUANTITY only.
        # Legacy request columns remain for schema/backward compatibility but no
        # production-plan or separate requested-demand calculation is performed.
        request["demand_quantity"] = None
        request["demand_source"] = "UNAVAILABLE"

        request.setdefault("requested_by", "agent_user")
        request.setdefault("reasons", [])
        return request

    def _normalize_and_validate_action(self, action: dict, request: dict) -> None:
        action_type = str(action.get("action_type") or "").strip().upper()
        if action_type not in {"REPLACE", "ADD", "DELETE", "QUANTITY_CHANGE"}:
            raise ValueError("Unsupported action_type")
        action["action_type"] = action_type

        old_code = str(action.get("old_item_code") or "").strip().upper() or None
        new_code = str(action.get("new_item_code") or "").strip().upper() or None
        target_item_name = str(action.get("target_item_name") or "").strip()

        if action_type == "ADD" and not new_code and not target_item_name:
            raise ValueError(
                "추가하려는 자재 또는 ASSY가 지정되지 않았습니다. "
                "자재코드, 자재명 또는 품목군을 먼저 입력해 주세요."
            )

        # SPEED2B Macro Target Resolution:
        # For REPLACE/DELETE/QUANTITY_CHANGE the caller may provide only a
        # business target name such as SEALANT / 실런트 / TFT. Resolve the
        # source item from the actual scoped product BOM inside this Service,
        # instead of requiring get_bom -> LLM row selection -> analysis.
        if (
            action_type != "ADD"
            and not old_code
            and target_item_name
        ):
            old_code = self._resolve_source_item_code_by_name(
                request=request,
                target_item_name=target_item_name,
            )
            action["old_item_code"] = old_code
            action["target_resolution_source"] = "SCOPED_BOM_NAME_MATCH"

        if old_code:
            action["old_item_code"] = old_code
        if new_code:
            action["new_item_code"] = new_code

        supplied_target = str(action.get("target_type") or "").strip().upper()
        target_item_code = new_code if action_type == "ADD" else old_code
        target_item = self.repository.get_item(target_item_code) if target_item_code else None

        if action_type == "ADD" and target_item is None:
            # Candidate-discovery ADD does not know new_item_code yet.  Prefer an
            # explicit target_type from the caller, but recover safely from natural
            # language when the user clearly said "자재/MATERIAL" or "ASSY/어셈블리".
            # This prevents a backend schema hint from leaking into the chat UI.
            if supplied_target not in {"MATERIAL", "ASSY"}:
                request_text = str(request.get("original_request") or "").lower()
                material_explicit = any(marker in request_text for marker in ("자재", "material"))
                assy_explicit = any(marker in request_text for marker in ("assy", "어셈블리", "어셈블리"))
                if material_explicit != assy_explicit:
                    supplied_target = "MATERIAL" if material_explicit else "ASSY"
                    action["target_type_resolution_source"] = "EXPLICIT_REQUEST_TEXT"
                else:
                    raise ValueError(
                        "추가 대상 유형을 확인할 수 없습니다. 일반 자재를 추가하려면 '자재', "
                        "조립품을 추가하려면 'ASSY'를 요청에 명시해 주세요."
                    )
            inferred_target = supplied_target
        else:
            if not target_item or target_item["active_yn"] != "Y":
                field = "new_item_code" if action_type == "ADD" else "old_item_code"
                raise ValueError(f"{field} must reference an active item")
            inferred_target = (
                "ASSY" if target_item["item_type"] == "ASSEMBLY"
                else "MATERIAL" if target_item["item_type"] == "MATERIAL"
                else None
            )
            if inferred_target is None:
                raise ValueError("Design change target must be MATERIAL or ASSY")
            if supplied_target and supplied_target != inferred_target:
                raise ValueError("target_type does not match the target item")
        action["target_type"] = inferred_target
        if target_item_name:
            action["target_item_name"] = target_item_name

        if action_type != "ADD":
            relation = self._resolve_source_relation(action, request)
            action["parent_item_code"] = relation["parent_item_code"]
            action["location_code"] = relation["location_code"]
            action.setdefault("old_quantity", float(relation["quantity"]))
        else:
            parent_code = str(action.get("parent_item_code") or "").strip().upper()
            if not parent_code and action["target_type"] == "MATERIAL":
                # A general MATERIAL may be connected directly to FA/VERSION.  When
                # the user only asks for candidates, use the product VERSION as the
                # provisional parent instead of inventing an ASSY.  The choice is
                # visible in Analysis/Impact before Request creation.
                parent_code = request["version_code"]
                action["parent_resolution_source"] = "VERSION_DEFAULT"
            parent = self.repository.get_item(parent_code) if parent_code else None
            if not parent or parent["item_type"] not in {"VERSION", "ASSEMBLY"} or parent["active_yn"] != "Y":
                raise ValueError("ADD requires an active VERSION or ASSEMBLY parent_item_code")
            action["parent_item_code"] = parent_code
            action["location_code"] = str(action.get("location_code") or "N/A").strip().upper()

        if action_type in {"REPLACE", "ADD"} and new_code:
            new = self.repository.get_item(new_code)
            expected_type = "ASSEMBLY" if inferred_target == "ASSY" else "MATERIAL"
            if not new or new["item_type"] != expected_type or new["active_yn"] != "Y":
                raise ValueError("new_item_code does not match target_type or is inactive")
        if action_type == "ADD":
            quantity = action.get("new_quantity")
            if quantity is None:
                # Candidate search must be possible before the user knows the exact
                # addition quantity.  Use one unit per product only as an explicit
                # Analysis default; it remains visible and can be refined before Apply.
                action["new_quantity"] = 1.0
                action["quantity_resolution_source"] = "ANALYSIS_DEFAULT_1"
            elif float(quantity) <= 0:
                raise ValueError("ADD new_quantity must be greater than zero")
            else:
                action["new_quantity"] = float(quantity)
        elif action_type == "QUANTITY_CHANGE":
            quantity = action.get("new_quantity")
            if quantity is None or float(quantity) <= 0:
                raise ValueError("QUANTITY_CHANGE requires new_quantity greater than zero")
            action["new_quantity"] = float(quantity)

    @staticmethod
    def _clean_source_target_hint(value: str) -> str:
        text = " ".join(str(value or "").strip().split())
        # Generic role words should not influence item matching.
        for suffix in (
            " 자재", " 품목", " 부품", " MATERIAL", " ASSY", " 어셈블리",
        ):
            if text.upper().endswith(suffix.upper()):
                text = text[: -len(suffix)].strip()
        return text

    def _resolve_source_item_code_by_name(
        self,
        *,
        request: dict,
        target_item_name: str,
    ) -> str:
        """Resolve a name-only design-change target inside one scoped product BOM.

        This is deliberately product/plant scoped. It never searches the whole
        item master and guesses a write target.

        Matching uses the DB-managed QueryNormalizer aliases, so examples such
        as ``실런트`` -> ``SEALANT`` remain metadata driven.
        """
        hint = self._clean_source_target_hint(target_item_name)
        if not hint:
            raise ValueError("SOURCE_ITEM_NAME_REQUIRED")

        relations = self.repository.list_version_component_relations(
            version_code=request["version_code"],
            plant_code=request["plant_code"],
            as_of_date=request["as_of_date"],
        )
        if not relations:
            raise ValueError(
                "ACTIVE_PRODUCT_BOM_NOT_FOUND: "
                f"{request['plant_code']} PLANT의 {request['version_code']} 활성 BOM이 없습니다."
            )

        scored: list[tuple[int, dict]] = []
        for relation in relations:
            score = self.query_normalizer.match_score(
                hint,
                relation.get("child_item_code"),
                relation.get("item_name"),
                relation.get("description"),
            )
            # Require a meaningful semantic/lexical match. A weak one-token
            # overlap must not silently become a design-change write target.
            if score >= 500:
                scored.append((score, relation))

        if not scored:
            raise ValueError(
                "SOURCE_ITEM_NAME_NOT_FOUND: "
                f"{request['version_code']} / {request['plant_code']} BOM에서 "
                f"'{target_item_name}'에 해당하는 활성 품목을 찾을 수 없습니다."
            )

        best_score = max(score for score, _ in scored)
        best_rows = [row for score, row in scored if score == best_score]

        unique_items: dict[str, dict] = {}
        for row in best_rows:
            code = str(row.get("child_item_code") or "").strip().upper()
            if code:
                unique_items.setdefault(code, row)

        if len(unique_items) != 1:
            labels = ", ".join(
                f"{code}({row.get('item_name') or '-'})"
                for code, row in sorted(unique_items.items())
            )
            raise ValueError(
                "SOURCE_ITEM_NAME_AMBIGUOUS: "
                f"'{target_item_name}'에 해당하는 품목이 둘 이상입니다: {labels}. "
                "품목 코드를 지정해 주세요."
            )

        return next(iter(unique_items))

    def _resolve_source_relation(self, action: dict, request: dict) -> dict:
        old_code = action["old_item_code"]
        relations = self.repository.find_version_source_relations(
            version_code=request["version_code"],
            child_item_code=old_code,
            plant_code=request["plant_code"],
            as_of_date=request["as_of_date"],
        )
        supplied_parent = str(action.get("parent_item_code") or "").strip().upper()
        supplied_location = str(action.get("location_code") or "").strip().upper()
        if supplied_parent:
            parent_matches = [
                row for row in relations
                if str(row["parent_item_code"]).upper() == supplied_parent
            ]
            if parent_matches:
                relations = parent_matches
        if supplied_location and supplied_location not in {"ALL", "N/A"}:
            location_matches = [
                row for row in relations
                if str(row["location_code"]).upper() == supplied_location
            ]
            if location_matches:
                relations = location_matches
        if not relations:
            raise ValueError(
                "ACTIVE_SOURCE_BOM_RELATION_NOT_FOUND: "
                f"{request['as_of_date']} 기준 {request['plant_code']} PLANT의 "
                f"{request['version_code']} 활성 BOM에서 {old_code} 품목을 찾을 수 없습니다. "
                "이미 삭제/교체되었거나 해당 제품 BOM에 존재하지 않는 품목인지 확인해 주세요."
            )
        if len(relations) > 1:
            raise ValueError(
                "ACTIVE_SOURCE_BOM_RELATION_AMBIGUOUS: "
                "요청 제품의 활성 BOM에서 동일 품목이 둘 이상 발견되었습니다. "
                "parent_item_code 또는 location_code를 지정해 주세요."
            )
        return relations[0]

    def _item_summary(self, item_code: str | None, as_of_date: str) -> dict:
        if not item_code:
            return {}
        item = self.repository.get_item(item_code)
        if not item:
            return {}
        profile = self.repository.get_item_profile(item_code, as_of_date)
        status_fields = {
            key: value for key, value in profile.items()
            if "status" in key.lower()
        }
        return {
            "item_code": item_code,
            "item_type": item.get("item_type"),
            "item_name": item.get("item_name"),
            "description": item.get("description") or profile.get("specification"),
            "active_yn": item.get("active_yn"),
            "usage_type": profile.get("usage_type"),
            "specification": profile.get("specification"),
            "status_fields": status_fields,
            "profile": profile,
        }

    def _commercial_unit_price(self, item_code: str, as_of_date: str) -> dict:
        """Resolve a comparable unit price without inventing missing cost data."""
        supplier = self.supply.recommend_supplier(item_code, as_of_date, ["COST"])
        recommended = supplier.get("recommended") or {}
        if recommended.get("unit_price") is not None:
            return {
                "unit_price": float(recommended["unit_price"]),
                "price_source": "SUPPLIER_ITEM",
                "supplier_code": recommended.get("supplier_code"),
                "supplier_name": recommended.get("supplier_name"),
                "supplier_status": supplier.get("status"),
            }
        profile = self.repository.get_item_profile(item_code, as_of_date)
        if profile.get("unit_cost") is not None:
            return {
                "unit_price": float(profile["unit_cost"]),
                "price_source": "ITEM_ATTRIBUTE",
                "supplier_code": None,
                "supplier_name": None,
                "supplier_status": supplier.get("status"),
            }
        return {
            "unit_price": None,
            "price_source": "UNAVAILABLE",
            "supplier_code": None,
            "supplier_name": None,
            "supplier_status": supplier.get("status"),
        }

    def scan_product_cost_reduction_candidates(
        self,
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str | None = None,
        exclude_item_codes: list[str] | None = None,
        exclude_item_names: list[str] | None = None,
        include_target_types: list[str] | None = None,
        candidates_per_item: int = 5,
    ) -> dict:
        """Read-only model-wide cost opportunity scan.

        A broad question such as "이 모델 BOM 전체에서 원가를 낮출 수 있는
        대체 자재를 찾아줘" is not a single Design Change Action.  This method
        first traverses the real BOM and evaluates each replaceable component
        independently.  It never creates a Design Change Request.

        Cost reduction is only labelled CONFIRMED when both the current item and
        candidate have comparable unit-price evidence.  Technical eligibility by
        itself must never be described as proven cost saving.
        """
        version_code = str(version_code or "").strip().upper()
        plant_code = str(plant_code or "").strip().upper()
        if not version_code:
            raise ValueError("version_code is required")
        if not plant_code:
            raise ValueError("plant_code is required")
        self.repository.validate_plant(plant_code)
        version = self.repository.get_item(version_code)
        if not version or version.get("item_type") != "VERSION" or version.get("active_yn") != "Y":
            raise ValueError("version_code must be an active VERSION")

        as_of_date = str(as_of_date or date.today().isoformat()).strip()
        excluded_codes = {
            str(value).strip().upper() for value in (exclude_item_codes or [])
            if str(value).strip()
        }
        excluded_names = {
            str(value).strip().upper() for value in (exclude_item_names or [])
            if str(value).strip()
        }
        target_types = {
            str(value).strip().upper() for value in (include_target_types or ["MATERIAL", "ASSY"])
            if str(value).strip()
        }
        if not target_types or not target_types.issubset({"MATERIAL", "ASSY"}):
            raise ValueError("include_target_types must contain MATERIAL and/or ASSY")
        per_item_limit = max(1, min(int(candidates_per_item or 5), 10))

        relations = self.repository.list_version_component_relations(
            version_code=version_code,
            plant_code=plant_code,
            as_of_date=as_of_date,
        )
        opportunities: list[dict] = []
        scanned_sources = 0
        technical_eligible_count = 0
        confirmed_savings_count = 0
        cost_unverified_count = 0

        for relation in relations:
            source_code = str(relation.get("child_item_code") or "").upper()
            item_name = str(relation.get("item_name") or "").upper()
            target_type = (
                "ASSY" if relation.get("item_type") == "ASSEMBLY"
                else "MATERIAL" if relation.get("item_type") == "MATERIAL"
                else None
            )
            if not target_type or target_type not in target_types:
                continue
            if source_code in excluded_codes or item_name in excluded_names:
                continue
            scanned_sources += 1

            candidates = self.recommendation.evaluate_candidates(
                source_item_code=source_code,
                reasons=["COST"],
                target_type=target_type,
                as_of_date=as_of_date,
                evaluation_items=[],
            )
            eligible = [
                row for row in candidates
                if row.get("status") in {"PASS", "CONDITIONAL"}
            ]
            if not eligible:
                continue

            source_price = self._commercial_unit_price(source_code, as_of_date)
            candidate_rows: list[dict] = []
            for candidate in eligible:
                candidate_code = str(candidate.get("candidate_item_code") or "").upper()
                candidate_summary = self._item_summary(candidate_code, as_of_date)
                candidate_price = self._commercial_unit_price(candidate_code, as_of_date)
                current_price = source_price.get("unit_price")
                new_price = candidate_price.get("unit_price")
                savings_amount = None
                savings_pct = None
                if current_price is None or new_price is None:
                    cost_status = "UNAVAILABLE"
                    cost_unverified_count += 1
                else:
                    savings_amount = round(float(current_price) - float(new_price), 4)
                    savings_pct = (
                        round(savings_amount / float(current_price) * 100.0, 2)
                        if float(current_price) != 0 else None
                    )
                    cost_status = "CONFIRMED" if savings_amount > 0 else "NO_SAVINGS"
                    if cost_status == "CONFIRMED":
                        confirmed_savings_count += 1
                technical_eligible_count += 1
                candidate_rows.append({
                    "candidate_item_code": candidate_code,
                    "candidate_item_name": candidate_summary.get("item_name"),
                    "candidate_description": candidate_summary.get("description"),
                    "technical_status": candidate.get("status"),
                    "technical_score": candidate.get("total_score"),
                    "candidate_unit_price": new_price,
                    "candidate_price_source": candidate_price.get("price_source"),
                    "candidate_supplier_code": candidate_price.get("supplier_code"),
                    "candidate_supplier_name": candidate_price.get("supplier_name"),
                    "supplier_status": candidate_price.get("supplier_status"),
                    "cost_reduction_status": cost_status,
                    "unit_savings": savings_amount,
                    "savings_pct": savings_pct,
                })

            status_order = {"CONFIRMED": 0, "UNAVAILABLE": 1, "NO_SAVINGS": 2}
            candidate_rows.sort(key=lambda row: (
                status_order.get(row["cost_reduction_status"], 9),
                -(row.get("savings_pct") or -999999),
                0 if row.get("technical_status") == "PASS" else 1,
                -float(row.get("technical_score") or 0),
                row.get("candidate_item_code") or "",
            ))
            opportunities.append({
                "source_item_code": source_code,
                "source_item_name": relation.get("item_name"),
                "source_description": relation.get("description"),
                "target_type": target_type,
                "parent_item_code": relation.get("parent_item_code"),
                "location_code": relation.get("location_code"),
                "bom_quantity": relation.get("quantity"),
                "current_unit_price": source_price.get("unit_price"),
                "current_price_source": source_price.get("price_source"),
                "candidates": candidate_rows[:per_item_limit],
            })

        opportunities.sort(key=lambda row: (
            0 if any(c.get("cost_reduction_status") == "CONFIRMED" for c in row["candidates"]) else 1,
            row.get("source_item_code") or "",
        ))
        return {
            "scan_type": "PRODUCT_COST_REDUCTION",
            "version_code": version_code,
            "plant_code": plant_code,
            "as_of_date": as_of_date,
            "excluded_item_codes": sorted(excluded_codes),
            "excluded_item_names": sorted(excluded_names),
            "scanned_source_count": scanned_sources,
            "opportunity_source_count": len(opportunities),
            "technical_eligible_candidate_count": technical_eligible_count,
            "confirmed_cost_reduction_candidate_count": confirmed_savings_count,
            "cost_unverified_candidate_count": cost_unverified_count,
            "opportunities": opportunities,
            "request_created": False,
            "request_id": None,
            "production_bom_modified": False,
            "guidance": (
                "CONFIRMED만 원가 절감이 수치로 검증된 후보입니다. "
                "UNAVAILABLE은 기술적으로 대체 가능하지만 현재품 또는 후보의 비교 가능한 원가 근거가 부족합니다. "
                "NO_SAVINGS는 기술적으로 대체 가능해도 현재 확인된 단가 기준 절감이 아닙니다."
            ),
        }

    @staticmethod
    def _candidate_decision_reasons(candidate: dict) -> list[str]:
        reasons: list[str] = []
        for row in candidate.get("rule_results") or []:
            for condition in (row.get("evidence") or {}).get("conditions") or []:
                if condition.get("status") in {"FAIL", "CONDITIONAL"}:
                    reasons.append(
                        str(condition.get("reason") or
                            f"{condition.get('attribute')}: {condition.get('status')}")
                    )
        for row in candidate.get("attribute_results") or []:
            if row.get("status") in {"FAIL", "CONDITIONAL"}:
                reasons.append(
                    str(row.get("reason") or f"{row.get('attribute')}: {row.get('status')}")
                )
        supplier_status = candidate.get("supplier_status")
        inventory_status = candidate.get("inventory_status")
        if supplier_status and supplier_status != "PASS":
            reasons.append(f"공급사 평가: {supplier_status}")
        if inventory_status and inventory_status != "PASS":
            reasons.append(f"재고 평가: {inventory_status}")
        if candidate.get("add_duplicate_active"):
            reasons.append("동일 PLANT/Parent/Location BOM에 이미 활성 자재로 존재하여 ADD할 수 없습니다.")
        if not reasons:
            reasons.append("기술/공급/재고 평가 조건 충족")
        return list(dict.fromkeys(reasons))


    def _prepare_analysis(self, request: dict, actions: list[dict]) -> dict:
        """Normalize one design-change analysis without creating DB Request/Action rows."""
        if not actions:
            raise ValueError("At least one action is required")
        normalized_request = self._normalize_request(dict(request))
        normalized_request.pop("request_id", None)
        plant = self.repository.validate_plant(normalized_request["plant_code"])
        version = self.repository.get_item(normalized_request["version_code"])
        if not version or version["item_type"] != "VERSION" or version["active_yn"] != "Y":
            raise ValueError("version_code must be an active VERSION")
        if not self.repository.list_version_component_relations(
            version_code=normalized_request["version_code"],
            plant_code=normalized_request["plant_code"],
            as_of_date=normalized_request["as_of_date"],
        ):
            raise ValueError(
                f"선택한 PLANT {normalized_request['plant_code']}에 "
                f"{normalized_request['version_code']}의 활성 BOM이 없습니다."
            )

        request_context = " ".join(str(normalized_request.get(name) or "") for name in (
            "original_request", "normalized_request",
        )).strip()
        prepared_actions: list[dict] = []
        reason_records_by_action: list[list[dict]] = []
        semantic_indexes: dict[tuple, int] = {}
        for raw in actions:
            action = dict(raw)
            action.setdefault("action_id", self._id("ANA-ACT"))
            self._normalize_and_validate_action(action, normalized_request)
            semantic_key = (
                action.get("action_type"), action.get("target_type"),
                action.get("parent_item_code"), action.get("old_item_code"),
                action.get("new_item_code"), action.get("target_item_name"),
                action.get("location_code"), action.get("new_quantity"),
            )
            resolved = self.reason_resolver.resolve_all(
                proposed_reasons=normalized_request.get("reasons"),
                original_request=request_context,
                target_type=action["target_type"],
                action_type=action["action_type"],
                explicit_action_reason=action.get("reason_code"),
            )
            records = [reason.as_record() for reason in resolved]
            if semantic_key in semantic_indexes:
                idx = semantic_indexes[semantic_key]
                existing = reason_records_by_action[idx]
                codes = {row.get("reason_code") for row in existing}
                for record in records:
                    if record.get("reason_code") in codes:
                        continue
                    value = dict(record)
                    if any(row.get("is_primary") == "Y" for row in existing):
                        value["is_primary"] = "N"
                    existing.append(value)
                    codes.add(value.get("reason_code"))
                continue
            semantic_indexes[semantic_key] = len(prepared_actions)
            prepared_actions.append(action)
            reason_records_by_action.append(records)

        normalized_request["reasons"] = list(dict.fromkeys(
            row["reason_code"]
            for records in reason_records_by_action
            for row in records
            if row.get("resolution_status") == "RESOLVED"
        ))
        return {
            "plant": plant,
            "request": normalized_request,
            "actions": prepared_actions,
            "reason_records_by_action": reason_records_by_action,
        }

    def _resolve_action_demand(self, request: dict, action: dict) -> dict:
        """Use BOM QUANTITY as the only active quantity basis."""
        if action.get("action_type") in {"ADD", "QUANTITY_CHANGE"}:
            quantity = action.get("new_quantity")
        else:
            quantity = action.get("old_quantity")
        quantity = float(quantity or 1.0)
        return {
            "quantity": quantity,
            "source": "BOM_QUANTITY",
            "bom_quantity": quantity,
            "production_plan_quantity": None,
            "as_of_date": request.get("as_of_date"),
            "plant_code": request.get("plant_code"),
            "required_quantity_basis": "BOM_QUANTITY",
        }

    def _evaluate_analysis_action(
        self, request: dict, action: dict, reason_records: list[dict]
    ) -> dict:
        primary = next(
            (row for row in reason_records if row.get("is_primary") == "Y"),
            reason_records[0] if reason_records else None,
        )
        resolved = [
            row for row in reason_records if row.get("resolution_status") == "RESOLVED"
        ]
        if not primary or primary.get("resolution_status") != "RESOLVED":
            raise ValueError("REASON_RESOLUTION_REQUIRED")
        reasons = list(dict.fromkeys(row["reason_code"] for row in resolved))
        as_of_date = request["as_of_date"]
        action_type = action["action_type"]

        if action_type == "REPLACE":
            results = self.recommendation.evaluate_candidates(
                source_item_code=action["old_item_code"], reasons=reasons,
                target_type=action["target_type"], as_of_date=as_of_date, evaluation_items=[],
            )
        elif action_type == "ADD":
            if action.get("new_item_code"):
                results = self.recommendation.evaluate_specific_candidate(
                    candidate_item_code=action["new_item_code"], reasons=reasons,
                    target_type=action["target_type"], as_of_date=as_of_date, evaluation_items=[],
                )
            else:
                results = self.recommendation.evaluate_add_candidates(
                    reasons=reasons, target_type=action["target_type"],
                    as_of_date=as_of_date, evaluation_items=[],
                    target_item_name=action.get("target_item_name"),
                )
        elif action_type == "DELETE":
            target = self._item_summary(action.get("old_item_code"), as_of_date)
            parent = self._item_summary(action.get("parent_item_code"), as_of_date)
            evaluated_action = {
                **action,
                "evaluation_status": "PASS",
                "reasons": reason_records,
                "primary_reason": primary,
                "secondary_reasons": [row for row in resolved if row.get("is_primary") != "Y"],
                "decision_reasons": ["현재 BOM 관계가 존재하며 삭제 영향범위 확인이 필요합니다."],
            }
            return {
                "action": evaluated_action,
                "candidates": [],
                "analysis_context": {
                    "version_code": request["version_code"], "plant_code": request["plant_code"],
                    "action_type": action_type, "target_type": action["target_type"],
                    "location_code": action.get("location_code"),
                    "old_quantity": action.get("old_quantity"), "new_quantity": None,
                    "reason_code": primary.get("reason_code"),
                    "primary_reason_code": primary.get("reason_code"),
                    "secondary_reason_codes": [row["reason_code"] for row in resolved if row.get("is_primary") != "Y"],
                    "reason_codes": reasons, "raw_reason_text": primary.get("raw_reason_text"),
                    "target_item": target, "parent_item": parent,
                    "as_of_date": as_of_date, "effective_date": request["effective_date"],
                    "evaluation_status": "PASS",
                },
            }
        elif action_type == "QUANTITY_CHANGE":
            demand = self._resolve_action_demand(request, action)
            inventory = self.supply.evaluate_inventory(
                item_code=action["old_item_code"], plant_code=request["plant_code"],
                demand_quantity=demand.get("quantity"), effective_date=request["effective_date"],
                demand_source=demand.get("source"),
                production_plan_quantity=demand.get("production_plan_quantity"),
            )
            status = inventory.get("status") or "CONDITIONAL"
            target = self._item_summary(action.get("old_item_code"), as_of_date)
            parent = self._item_summary(action.get("parent_item_code"), as_of_date)
            reasons_text = [
                f"재고 평가: {status}",
                f"변경 후 BOM QUANTITY({action.get('new_quantity')})를 기준으로 검증했습니다.",
            ]
            evaluated_action = {
                **action,
                "evaluation_status": status,
                "reasons": reason_records,
                "primary_reason": primary,
                "secondary_reasons": [row for row in resolved if row.get("is_primary") != "Y"],
                "demand": demand,
                "inventory": inventory,
                "inventory_status": status,
                "decision_reasons": reasons_text,
            }
            return {
                "action": evaluated_action,
                "candidates": [],
                "analysis_context": {
                    "version_code": request["version_code"], "plant_code": request["plant_code"],
                    "action_type": action_type, "target_type": action["target_type"],
                    "location_code": action.get("location_code"),
                    "old_quantity": action.get("old_quantity"), "new_quantity": action.get("new_quantity"),
                    "reason_code": primary.get("reason_code"),
                    "primary_reason_code": primary.get("reason_code"),
                    "secondary_reason_codes": [row["reason_code"] for row in resolved if row.get("is_primary") != "Y"],
                    "reason_codes": reasons, "raw_reason_text": primary.get("raw_reason_text"),
                    "target_item": target, "parent_item": parent,
                    "as_of_date": as_of_date, "effective_date": request["effective_date"],
                    "demand_source": demand.get("source"), "demand_quantity": demand.get("quantity"),
                    "bom_quantity": demand.get("bom_quantity"),
                    "demand": demand, "inventory": inventory,
                    "evaluation_status": status,
                },
            }
        else:
            raise ValueError(f"Unsupported action_type: {action_type}")

        demand = self._resolve_action_demand(request, action)
        for value in results:
            # ADD candidate discovery must reject an item that is already active in
            # the exact target BOM edge.  Candidate master ACTIVE status only means
            # the item itself is usable; it does not mean the item is addable to
            # this Parent/Location.  Catch this during Analysis so an invalid ADD
            # candidate can never be selected and fail for the first time at Preview.
            if action_type == "ADD":
                duplicates = self.repository.get_active_bom_relations(
                    parent_item_code=action["parent_item_code"],
                    child_item_code=value["candidate_item_code"],
                    location_code=action["location_code"],
                    plant_code=request["plant_code"],
                    as_of_date=request["effective_date"],
                )
                value["add_duplicate_active"] = bool(duplicates)

            supplier = self.supply.recommend_supplier(
                value["candidate_item_code"], as_of_date, reasons,
            )
            inventory = self.supply.evaluate_inventory(
                item_code=value["candidate_item_code"], plant_code=request["plant_code"],
                demand_quantity=demand["quantity"], effective_date=request["effective_date"],
                demand_source=demand.get("source"),
                production_plan_quantity=demand.get("production_plan_quantity"),
            )
            value["supplier_evaluation"] = supplier
            value["plant_code"] = request["plant_code"]
            value["inventory"] = inventory
            value["demand"] = demand
            value["rule_score"] = value["total_score"]
            value["technical_status"] = value["status"]
            value["supplier_status"] = supplier["status"]
            value["inventory_status"] = inventory["status"]
            summary = self._item_summary(value["candidate_item_code"], as_of_date)
            value["candidate_name"] = summary.get("item_name")
            value["candidate_description"] = summary.get("description")
            value["candidate_usage_type"] = summary.get("usage_type")
            value["candidate_profile"] = summary.get("profile", {})
            if supplier.get("recommended"):
                value["recommended_supplier_item_id"] = supplier["recommended"].get("supplier_item_id")
            statuses = {value["status"], supplier["status"], inventory["status"]}
            if value.get("add_duplicate_active"):
                value["technical_status"] = "FAIL"
                value["status"] = "FAIL"
            else:
                value["status"] = (
                    "FAIL" if "FAIL" in statuses else
                    "CONDITIONAL" if "CONDITIONAL" in statuses else "PASS"
                )
            self._apply_candidate_ranking_score(value, supplier, inventory)
            missing = list(value.get("missing_data", [])) + list(supplier.get("missing_data", []))
            value["missing_data"] = sorted(set(missing))
            value["decision_reasons"] = self._candidate_decision_reasons(value)
            value["action_id"] = action["action_id"]

        results.sort(key=self._candidate_sort_key)
        rank = 0
        for index, value in enumerate(results, 1):
            value["candidate_id"] = f"{action['action_id']}-C{index}"
            if value["status"] == "FAIL" or value.get("ranking_score") is None:
                value["rank"] = None
            else:
                rank += 1
                value["rank"] = rank
            self._apply_public_candidate_score_policy(value)

        target_code = action.get("old_item_code") or action.get("new_item_code")
        target = self._item_summary(target_code, as_of_date) if target_code else {
            "item_code": None,
            "item_name": action.get("target_item_name") or f"신규 {action['target_type']} ADD",
            "description": "요청 품목군에 맞는 후보 탐색 후 선택",
        }
        parent = self._item_summary(action.get("parent_item_code"), as_of_date)
        context = {
            "version_code": request["version_code"], "plant_code": request["plant_code"],
            "action_type": action["action_type"], "target_type": action["target_type"],
            "target_item_name": action.get("target_item_name"),
            "location_code": action.get("location_code"), "old_quantity": action.get("old_quantity"),
            "new_quantity": action.get("new_quantity"),
            "quantity_resolution_source": action.get("quantity_resolution_source"),
            "parent_resolution_source": action.get("parent_resolution_source"),
            "reason_code": primary.get("reason_code"), "primary_reason_code": primary.get("reason_code"),
            "secondary_reason_codes": [row["reason_code"] for row in resolved if row.get("is_primary") != "Y"],
            "reason_codes": reasons, "raw_reason_text": primary.get("raw_reason_text"),
            "target_item": target, "parent_item": parent, "as_of_date": as_of_date,
            "effective_date": request["effective_date"], "demand_source": demand.get("source"),
            "demand_quantity": demand.get("quantity"), "bom_quantity": demand.get("bom_quantity"),
        }
        action_statuses = {row["status"] for row in results}
        evaluation_status = "PASS" if "PASS" in action_statuses else "CONDITIONAL" if "CONDITIONAL" in action_statuses else "FAIL"
        return {
            "action": {**action, "evaluation_status": evaluation_status, "reasons": reason_records,
                       "primary_reason": primary, "secondary_reasons": [row for row in resolved if row.get("is_primary") != "Y"]},
            "candidates": results, "analysis_context": context,
        }

    def analyze_candidates(self, request: dict, actions: list[dict], analysis_id: str | None = None) -> dict:
        """Run candidate analysis as a read-only Analysis Session. No change Request is created."""
        prepared = self._prepare_analysis(request, actions)
        action_results = [
            self._evaluate_analysis_action(prepared["request"], action, reasons)
            for action, reasons in zip(prepared["actions"], prepared["reason_records_by_action"])
        ]
        analyzed_actions = [row["action"] for row in action_results]
        candidates = [candidate for row in action_results for candidate in row["candidates"]]
        contexts = [row["analysis_context"] for row in action_results]
        counts = {status: sum(row.get("status") == status for row in candidates) for status in ("PASS", "CONDITIONAL", "FAIL")}
        action_statuses = [str(row.get("evaluation_status") or "PENDING") for row in analyzed_actions]
        overall = (
            "FAIL" if "FAIL" in action_statuses else
            "CONDITIONAL" if "CONDITIONAL" in action_statuses else
            "PASS"
        )
        return {
            "analysis_id": analysis_id or self._id("ANA"),
            "request_created": False, "request_id": None,
            "request": prepared["request"], "actions": analyzed_actions,
            "candidates": candidates, "analysis_contexts": contexts,
            "analysis_context": contexts[0] if contexts else None,
            "status_counts": counts, "analysis_status": overall,
            "workflow_status": "ANALYSIS_READY",
            "production_bom_modified": False,
        }

    def revalidate_analysis_candidate(
        self, analysis: dict, action_id: str, candidate_item_code: str,
        demand_quantity: float | None = None, attributes: dict | None = None,
    ) -> dict:
        """Re-run an Analysis Session without persisting Request, selection, or master data."""
        if attributes:
            raise ValueError("Analysis-stage ad-hoc master attributes are not persisted; register master data first")
        before = next((row for row in analysis.get("candidates", []) if row.get("action_id") == action_id and row.get("candidate_item_code") == candidate_item_code), None)
        if not before:
            raise ValueError("Candidate does not belong to the active Analysis Session")
        request = dict(analysis.get("request") or {})
        # demand_quantity remains in the public signature only for compatibility.
        # Revalidation always recalculates from the current BOM QUANTITY.
        result = self.analyze_candidates(request, analysis.get("actions") or [], analysis_id=analysis.get("analysis_id"))
        after = next((row for row in result.get("candidates", []) if row.get("action_id") == action_id and row.get("candidate_item_code") == candidate_item_code), None)
        result["revalidation"] = {
            "action_id": action_id, "candidate_item_code": candidate_item_code,
            "before": before, "after": after,
            "changed_fields": {
                key: {"before": before.get(key), "after": (after or {}).get(key)}
                for key in ("status", "technical_status", "supplier_status", "inventory_status", "total_score", "grade")
                if before.get(key) != (after or {}).get(key)
            },
        }
        return result

    def explain_analysis_session(self, analysis: dict) -> dict:
        candidates = list(analysis.get("candidates") or [])
        actions = list(analysis.get("actions") or [])
        counts = {
            status: sum(row.get("status") == status for row in candidates)
            for status in ("PASS", "CONDITIONAL", "FAIL")
        }
        eligible = counts["PASS"] + counts["CONDITIONAL"]

        action_explanations = []
        for action in actions:
            inventory = action.get("inventory") or {}
            action_explanations.append({
                "action_id": action.get("action_id"),
                "action_type": action.get("action_type"),
                "item_code": action.get("old_item_code") or action.get("new_item_code"),
                "status": str(action.get("evaluation_status") or "-").upper(),
                "old_quantity": action.get("old_quantity"),
                "new_quantity": action.get("new_quantity"),
                "decision_reasons": action.get("decision_reasons") or [],
                "inventory_status": action.get("inventory_status") or inventory.get("status"),
                "available_quantity": inventory.get("available_quantity"),
                "shortage_quantity": inventory.get("shortage_quantity"),
            })

        if not candidates and action_explanations:
            first = action_explanations[0]
            reason_text = " ".join(
                str(value)
                for value in (first.get("decision_reasons") or [])
                if value
            )
            if first.get("action_type") == "QUANTITY_CHANGE":
                summary = (
                    f"QUANTITY_CHANGE 평가 결과는 {first.get('status')}입니다. "
                    f"변경 전 수량 {first.get('old_quantity')}에서 "
                    f"변경 후 수량 {first.get('new_quantity')}로 검증했으며, "
                    f"가용재고는 {first.get('available_quantity')}, "
                    f"부족수량은 {first.get('shortage_quantity')}입니다."
                )
                if reason_text:
                    summary += f" {reason_text}"
            elif first.get("action_type") == "DELETE":
                summary = f"DELETE 평가 결과는 {first.get('status')}입니다."
                if reason_text:
                    summary += f" {reason_text}"
            else:
                summary = f"Action 평가 결과는 {first.get('status')}입니다."
        elif not candidates:
            summary = "분석 결과를 설명할 후보 또는 Action 정보가 없습니다."
        elif not eligible:
            summary = (
                f"후보 {len(candidates)}건이 검색되었지만 모두 FAIL하여 "
                "선택 가능한 후보가 없습니다."
            )
        else:
            summary = (
                f"후보 {len(candidates)}건 중 PASS {counts['PASS']}건, "
                f"CONDITIONAL {counts['CONDITIONAL']}건, "
                f"FAIL {counts['FAIL']}건입니다."
            )

        return {
            "analysis_id": analysis.get("analysis_id"),
            "candidate_count": len(candidates),
            "status_counts": counts,
            "summary": summary,
            "actions": action_explanations,
            "request_created": False,
            "production_bom_modified": False,
        }

    def explain_analysis_candidate(self, analysis: dict, candidate_item_code: str, action_id: str | None = None) -> dict:
        rows = [row for row in analysis.get("candidates") or [] if row.get("candidate_item_code") == candidate_item_code]
        if action_id:
            rows = [row for row in rows if row.get("action_id") == action_id]
        if len(rows) != 1:
            raise ValueError("Candidate must resolve to exactly one Analysis Session result")
        row = dict(rows[0])
        return {
            "analysis_id": analysis.get("analysis_id"), "candidate_item_code": candidate_item_code,
            "action_id": row.get("action_id"), "status": row.get("status"),
            "technical_status": row.get("technical_status"), "supplier_status": row.get("supplier_status"),
            "inventory_status": row.get("inventory_status"), "total_score": row.get("total_score"),
            "grade": row.get("grade"), "decision_reasons": row.get("decision_reasons") or [],
            "rule_results": row.get("rule_results") or [], "attribute_results": row.get("attribute_results") or [],
            "inventory": row.get("inventory") or {}, "supplier_evaluation": row.get("supplier_evaluation") or {},
            "missing_data": row.get("missing_data") or [], "request_created": False,
            "production_bom_modified": False,
        }

    def compare_analysis_candidates(self, analysis: dict, candidate_item_codes: list[str] | None = None, action_id: str | None = None, criterion: str = "SPEC_SIMILARITY") -> dict:
        rows = list(analysis.get("candidates") or [])
        if action_id:
            rows = [row for row in rows if row.get("action_id") == action_id]
        if candidate_item_codes:
            wanted = set(candidate_item_codes)
            rows = [row for row in rows if row.get("candidate_item_code") in wanted]
        criterion = str(criterion or "SPEC_SIMILARITY").upper()
        def value(row):
            supplier = (row.get("supplier_evaluation") or {}).get("recommended") or {}
            inventory = row.get("inventory") or {}
            if criterion == "COST":
                return float(supplier.get("unit_price")) if supplier.get("unit_price") is not None else float("inf")
            if criterion == "LEAD_TIME":
                return float(supplier.get("lead_time_days")) if supplier.get("lead_time_days") is not None else float("inf")
            if criterion == "INVENTORY":
                return -float(inventory.get("available_quantity") or 0)
            return -float(row.get("total_score") or 0)
        rows.sort(key=lambda row: (value(row), row.get("candidate_item_code") or ""))
        return {
            "analysis_id": analysis.get("analysis_id"), "criterion": criterion,
            "candidates": [{
                "candidate_item_code": row.get("candidate_item_code"), "status": row.get("status"),
                "total_score": row.get("total_score"), "grade": row.get("grade"),
                "description": row.get("candidate_description"),
                "supplier": ((row.get("supplier_evaluation") or {}).get("recommended") or {}),
                "inventory": row.get("inventory") or {},
                "attribute_results": row.get("attribute_results") or [],
            } for row in rows],
            "request_created": False, "production_bom_modified": False,
        }

    def preview_analysis_impact(self, analysis: dict, selections: list[dict]) -> dict:
        request = dict(analysis.get("request") or {})
        actions = [dict(value) for value in analysis.get("actions") or []]
        selection_by_action = {row.get("action_id"): row for row in selections}
        for action in actions:
            if action.get("action_type") not in {"REPLACE", "ADD"}:
                continue
            selection = selection_by_action.get(action.get("action_id"))
            if not selection:
                raise ValueError("Every REPLACE/ADD analysis action requires a selected candidate")
            candidate_code = selection.get("candidate_item_code")
            candidate = next((row for row in analysis.get("candidates", []) if row.get("action_id") == action.get("action_id") and row.get("candidate_item_code") == candidate_code), None)
            if not candidate or candidate.get("status") == "FAIL":
                raise ValueError("PASS or CONDITIONAL analysis candidate is required")
            action["new_item_code"] = candidate_code
        return self.impact.analyze_selection_context(request=request, actions=actions)

    def commit_analysis_as_request(
        self, analysis: dict, selections: list[dict], approved_by: str,
        exception_reason: str | None = None, impact_confirmed: bool = False,
    ) -> dict:
        """Create the real Design Change Request only after explicit user proceed approval."""
        request = dict(analysis.get("request") or {})
        analysis_actions = [dict(value) for value in analysis.get("actions") or []]
        if not request or not analysis_actions:
            raise ValueError("Completed Analysis Session is required")
        selection_by_action = {row.get("action_id"): row for row in selections}
        selected_rows: list[tuple[dict, dict, dict]] = []
        for action in analysis_actions:
            action_status = str(action.get("evaluation_status") or "PENDING")
            if action_status == "FAIL":
                raise ValueError("FAIL analysis action cannot start a Design Change Request")
            if action_status == "CONDITIONAL" and not str(exception_reason or "").strip():
                raise ValueError("CONDITIONAL analysis requires an exception reason before Design Change Request creation")
            if action.get("action_type") not in {"REPLACE", "ADD"}:
                continue
            selection = selection_by_action.get(action.get("action_id"))
            if not selection:
                raise ValueError("Every REPLACE/ADD action requires one analyzed candidate selection")
            candidate = next((row for row in analysis.get("candidates", []) if row.get("action_id") == action.get("action_id") and row.get("candidate_item_code") == selection.get("candidate_item_code")), None)
            if not candidate or candidate.get("status") == "FAIL":
                raise ValueError("FAIL or unknown analysis candidate cannot start a Design Change Request")
            if candidate.get("status") == "CONDITIONAL" and not str(exception_reason or "").strip():
                raise ValueError("CONDITIONAL analysis requires an exception reason before Design Change Request creation")
            if action.get("action_type") == "ADD":
                action["new_item_code"] = candidate.get("candidate_item_code")
            selected_rows.append((action, selection, candidate))
        impact = self.preview_analysis_impact(analysis, selections)
        if impact.get("requires_impact_approval") and not impact_confirmed:
            raise ValueError("Shared BOM impact must be confirmed before Design Change Request creation")

        request.pop("request_id", None)
        db_actions = []
        for action in analysis_actions:
            value = {key: action.get(key) for key in (
                "action_type", "target_type", "parent_item_code", "reason_code",
                "old_item_code", "new_item_code", "location_code", "old_quantity", "new_quantity",
                "evaluation_status",
            ) if action.get(key) is not None}
            value.pop("new_item_code", None) if value.get("action_type") == "REPLACE" else None
            db_actions.append(value)
        created = self.create_request(request, db_actions)
        db_selections = []
        for analysis_action, db_action in zip(analysis_actions, created["actions"]):
            source_candidates = [dict(row) for row in analysis.get("candidates", []) if row.get("action_id") == analysis_action.get("action_id")]
            if source_candidates:
                persistence_candidates = [
                    self._candidate_for_persistence(row) for row in source_candidates
                ]
                self.repository.save_candidate_evaluations(
                    db_action["action_id"], persistence_candidates
                )
            if analysis_action.get("action_type") in {"REPLACE", "ADD"}:
                selection = selection_by_action[analysis_action.get("action_id")]
                persisted = next((row for row in self.repository.list_candidate_evaluations(db_action["action_id"]) if row.get("candidate_item_code") == selection.get("candidate_item_code")), None)
                if not persisted:
                    raise ValueError("Selected analysis candidate could not be persisted")
                db_selections.append({
                    "action_id": db_action["action_id"], "candidate_id": persisted["candidate_id"],
                    "supplier_item_id": selection.get("supplier_item_id"),
                })
        if db_selections:
            self.repository.select_candidates_atomically(created["request_id"], db_selections)
        if str(exception_reason or "").strip():
            self.repository.record_approval(
                request_id=created["request_id"], approval_id=self._id("APR"),
                stage="CONDITIONAL_EXCEPTION", decision="APPROVED", approved_by=approved_by,
                reason=str(exception_reason).strip(), selection={"analysis_id": analysis.get("analysis_id")},
            )
        approved = self._approve_selected_candidates(created["request_id"], approved_by, impact_review=impact)
        return {
            **approved, "request_id": created["request_id"], "plant_code": created["plant_code"],
            "actions": self.repository.get_request(created["request_id"])["actions"],
            "analysis_id": analysis.get("analysis_id"), "request_created": True,
            "workflow_status": "CANDIDATE_APPROVED", "production_bom_modified": False,
        }

    def evaluate_action(self, action_id: str, reasons: list[str] | None = None,
                        as_of_date: str | None = None,
                        evaluation_items: list[str] | None = None) -> dict:
        """Evaluate with the persisted request as the single source of truth.

        The optional arguments remain for Python-call compatibility only. MCP callers
        no longer provide them because LLM-generated values can drift from the request
        that was already validated and stored.
        """
        action = self.repository.get_action(action_id)
        if not action:
            raise ValueError("Change action not found")
        request = self.repository.get_request(action["request_id"])
        if not request or request["candidate_approval_status"] != "PENDING":
            raise ValueError("Approved or missing request cannot be re-evaluated")
        stored_action = next(
            value for value in request["actions"] if value["action_id"] == action_id
        )
        primary_reason = stored_action.get("primary_reason")
        action_reasons = [
            value for value in stored_action.get("reasons", [])
            if value.get("resolution_status") == "RESOLVED"
        ]
        if not primary_reason or primary_reason.get("resolution_status") != "RESOLVED":
            raise ValueError("REASON_RESOLUTION_REQUIRED")
        authoritative_reasons = list(dict.fromkeys(
            value["reason_code"] for value in action_reasons
        )) or [primary_reason["reason_code"]]
        authoritative_date = request["as_of_date"]
        if action["action_type"] == "ADD":
            results = self.recommendation.evaluate_specific_candidate(
                candidate_item_code=action["new_item_code"], reasons=authoritative_reasons,
                target_type=action["target_type"], as_of_date=authoritative_date,
                evaluation_items=[],
            )
        elif action["action_type"] == "REPLACE" and action.get("old_item_code"):
            results = self.recommendation.evaluate_candidates(
                source_item_code=action["old_item_code"], reasons=authoritative_reasons,
                target_type=action["target_type"], as_of_date=authoritative_date,
                evaluation_items=[],
            )
        else:
            raise ValueError("Candidate evaluation supports REPLACE and ADD actions")
        demand = self._resolve_action_demand(request, action)
        for value in results:
            supplier = self.supply.recommend_supplier(
                value["candidate_item_code"], authoritative_date, authoritative_reasons,
            )
            inventory = self.supply.evaluate_inventory(
                item_code=value["candidate_item_code"],
                plant_code=request["plant_code"],
                demand_quantity=demand["quantity"],
                effective_date=request["effective_date"],
                demand_source=demand.get("source"),
                production_plan_quantity=demand.get("production_plan_quantity"),
            )
            value["supplier_evaluation"] = supplier
            value["plant_code"] = request["plant_code"]
            value["inventory"] = inventory
            value["demand"] = demand
            value["rule_score"] = value["total_score"]
            value["technical_status"] = value["status"]
            value["supplier_status"] = supplier["status"]
            value["inventory_status"] = inventory["status"]
            candidate_summary = self._item_summary(
                value["candidate_item_code"], authoritative_date
            )
            value["candidate_name"] = candidate_summary.get("item_name")
            value["candidate_description"] = candidate_summary.get("description")
            value["candidate_usage_type"] = candidate_summary.get("usage_type")
            value["candidate_profile"] = candidate_summary.get("profile", {})
            if supplier["recommended"]:
                value["recommended_supplier_item_id"] = supplier["recommended"]["supplier_item_id"]
            statuses = {value["status"], supplier["status"], inventory["status"]}
            value["status"] = (
                "FAIL" if "FAIL" in statuses else
                "CONDITIONAL" if "CONDITIONAL" in statuses else "PASS"
            )
            self._apply_candidate_ranking_score(value, supplier, inventory)
            missing = list(value.get("missing_data", []))
            missing.extend(supplier.get("missing_data", []))
            if demand["quantity"] is None:
                missing.append("demand_quantity")
            value["missing_data"] = sorted(set(missing))
            value["decision_reasons"] = self._candidate_decision_reasons(value)
        results.sort(key=self._candidate_sort_key)
        rank = 0
        for value in results:
            if value["status"] == "FAIL" or value.get("ranking_score") is None:
                value["rank"] = None
            else:
                rank += 1
                value["rank"] = rank
        persistence_results = [self._candidate_for_persistence(row) for row in results]
        self.repository.save_candidate_evaluations(action_id, persistence_results)

        # save_candidate_evaluations historically enriched the same candidate dicts
        # with persisted identity fields (candidate_id/action_id). AE-08R now saves
        # persistence-safe copies so CONDITIONAL/FAIL public scores can stay hidden;
        # therefore restore only the DB identity fields from the persisted rows.
        persisted_rows = self.repository.list_candidate_evaluations(action_id)
        persisted_by_code = {
            str(row.get("candidate_item_code") or "").strip().upper(): row
            for row in persisted_rows
            if str(row.get("candidate_item_code") or "").strip()
        }
        for value in results:
            persisted = persisted_by_code.get(
                str(value.get("candidate_item_code") or "").strip().upper()
            )
            if persisted:
                if persisted.get("candidate_id") is not None:
                    value["candidate_id"] = persisted.get("candidate_id")
                value["action_id"] = persisted.get("action_id") or action_id
            else:
                # Keep the action identity available even if a custom repository
                # implementation does not expose list_candidate_evaluations rows.
                value.setdefault("action_id", action_id)
            self._apply_public_candidate_score_policy(value)
        target_summary = self._item_summary(
            action.get("old_item_code") or action.get("new_item_code"), authoritative_date
        )
        parent_summary = self._item_summary(action.get("parent_item_code"), authoritative_date)
        return {
            "action_id": action_id,
            "candidates": results,
            "analysis_context": {
                "request_id": request["request_id"],
                "version_code": request["version_code"],
                "plant_code": request["plant_code"],
                "action_type": action["action_type"],
                "target_type": action["target_type"],
                "location_code": action.get("location_code"),
                "old_quantity": action.get("old_quantity"),
                "reason_code": primary_reason.get("reason_code"),
                "primary_reason_code": primary_reason.get("reason_code"),
                "secondary_reason_codes": [
                    value["reason_code"] for value in action_reasons
                    if value.get("is_primary") != "Y"
                ],
                "reason_codes": authoritative_reasons,
                "raw_reason_text": primary_reason.get("raw_reason_text"),
                "target_item": target_summary,
                "parent_item": parent_summary,
                "as_of_date": authoritative_date,
                "effective_date": request["effective_date"],
                "demand_source": demand.get("source"),
                "demand_quantity": demand.get("quantity"),
                "bom_quantity": demand.get("bom_quantity"),
            },
            "evaluation_context": {
                "reasons": authoritative_reasons,
                "as_of_date": authoritative_date,
                "demand_source": demand.get("source"),
                "plant_code": request["plant_code"],
            },
            "production_bom_modified": False,
        }

    def _validate_complete_candidate_selection(
        self, request_id: str, selections: list[dict]
    ) -> dict:
        if not selections:
            raise ValueError("Candidate selections are required")
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        if request["candidate_approval_status"] != "PENDING" or request["apply_status"] != "NOT_APPLIED":
            raise ValueError("Candidate approval is already finalized")
        required_ids = {
            action["action_id"] for action in request["actions"]
            if action["action_type"] in {"REPLACE", "ADD"}
        }
        selection_ids = [selection.get("action_id") for selection in selections]
        if len(selection_ids) != len(set(selection_ids)) or set(selection_ids) != required_ids:
            raise ValueError("Exactly one candidate selection is required for every REPLACE/ADD action")
        for selection in selections:
            self.repository.validate_candidate_selection(
                request_id=request_id, action_id=selection["action_id"],
                candidate_id=selection["candidate_id"],
                supplier_item_id=selection.get("supplier_item_id"),
            )
        return request

    def _approve_selected_candidates(
        self, request_id: str, approved_by: str, impact_review: dict | None = None
    ) -> dict:
        refreshed = self.repository.get_request(request_id)
        if not refreshed:
            raise ValueError("Change request not found")
        if any(action["evaluation_status"] in {"PENDING", "FAIL"}
               for action in refreshed["actions"]):
            raise ValueError("Every action must be PASS or CONDITIONAL before approval")
        if any(action["action_type"] in {"REPLACE", "ADD"} and
               not action.get("selected_candidate_id") for action in refreshed["actions"]):
            raise ValueError("Every REPLACE/ADD action requires a selected candidate")
        selections = [{
            "action_id": action["action_id"],
            "candidate_id": action.get("selected_candidate_id"),
            "supplier_item_id": action.get("selected_supplier_item_id"),
        } for action in refreshed["actions"] if action["action_type"] in {"REPLACE", "ADD"}]
        approval_id = self._id("APR")
        approval = self.repository.record_approval(
            request_id=request_id, approval_id=approval_id, stage="CANDIDATE",
            decision="APPROVED", approved_by=approved_by,
            selection={
                "selections": selections,
                "impact_review": impact_review or {},
            },
        )
        return {
            **approval,
            "workflow_status": "CANDIDATE_APPROVED",
            "workflow_started": True,
            "selections": selections,
            "impact_review": impact_review or {},
            "requires_exception": (
                any(action["evaluation_status"] == "CONDITIONAL" for action in refreshed["actions"])
                and not self.repository.has_approved_exception(request_id)
            ),
            "production_bom_modified": False,
        }

    def prepare_candidate_selection(
        self, request_id: str, selections: list[dict], selected_by: str
    ) -> dict:
        """Save candidate choices and enforce pre-workflow safety gates.

        STEP33-B keeps CONDITIONAL handling in the analysis phase. A selected
        CONDITIONAL candidate does not start the Design Change Workflow until
        additional-data revalidation or an explicit exception approval has been
        completed. Shared-BOM impact review remains the next gate after that.
        """
        self._validate_complete_candidate_selection(request_id, selections)
        self.repository.select_candidates_atomically(request_id, selections)
        refreshed = self.repository.get_request(request_id)
        if any(action["evaluation_status"] == "CONDITIONAL" for action in refreshed["actions"]):
            self.repository.set_request_workflow_status(
                request_id, "CONDITIONAL_REVIEW_REQUIRED"
            )
            return {
                "request_id": request_id,
                "workflow_status": "CONDITIONAL_REVIEW_REQUIRED",
                "workflow_started": False,
                "selected_by": selected_by,
                "selections": selections,
                "impact_review": None,
                "requires_exception": True,
                "production_bom_modified": False,
            }

        impact_review = self.impact.analyze_selected_candidate_impact(request_id)
        if impact_review["requires_impact_approval"]:
            self.repository.set_request_workflow_status(request_id, "IMPACT_REVIEW_REQUIRED")
            return {
                "request_id": request_id,
                "workflow_status": "IMPACT_REVIEW_REQUIRED",
                "workflow_started": False,
                "selected_by": selected_by,
                "selections": selections,
                "impact_review": impact_review,
                "requires_exception": False,
                "production_bom_modified": False,
            }
        return self._approve_selected_candidates(
            request_id, selected_by, impact_review=impact_review
        )

    def confirm_candidate_selection(
        self, request_id: str, selections: list[dict], confirmed_by: str,
        exception_reason: str | None = None,
    ) -> dict:
        """Persist a user-reviewed selection only after explicit confirmation.

        UI dropdown changes are intentionally not persisted. PASS selections are
        stored here. If any selected candidate is still CONDITIONAL, an exception
        reason is required and the selection + exception approval are committed
        atomically before the shared-impact gate is evaluated.
        """
        self._validate_complete_candidate_selection(request_id, selections)
        selected_statuses = []
        for selection in selections:
            candidate = self.repository.get_candidate_by_id(
                selection["action_id"], selection["candidate_id"]
            )
            if not candidate:
                raise ValueError("Selected candidate not found")
            selected_statuses.append(str(candidate.get("status") or candidate.get("final_status") or ""))
        has_conditional = "CONDITIONAL" in selected_statuses
        if has_conditional and not str(exception_reason or "").strip():
            raise ValueError(
                "CONDITIONAL candidate requires revalidation or an exception reason before confirmation"
            )

        exception_approval_id = None
        if has_conditional:
            exception_approval_id = self._id("APR")
            self.repository.select_candidates_with_exception_atomically(
                request_id=request_id, selections=selections,
                approval_id=exception_approval_id, approved_by=confirmed_by,
                reason=str(exception_reason).strip(),
            )
        else:
            self.repository.select_candidates_atomically(request_id, selections)

        impact_review = self.impact.analyze_selected_candidate_impact(request_id)
        if impact_review["requires_impact_approval"]:
            self.repository.set_request_workflow_status(request_id, "IMPACT_REVIEW_REQUIRED")
            return {
                "request_id": request_id,
                "workflow_status": "IMPACT_REVIEW_REQUIRED",
                "workflow_started": False,
                "confirmed_by": confirmed_by,
                "selections": selections,
                "impact_review": impact_review,
                "exception_approval_id": exception_approval_id,
                "requires_exception": False,
                "production_bom_modified": False,
            }
        approved = self._approve_selected_candidates(
            request_id, confirmed_by, impact_review=impact_review
        )
        if exception_approval_id:
            approved["exception_approval_id"] = exception_approval_id
        return approved

    def approve_candidate_impact(
        self, request_id: str, approved_by: str
    ) -> dict:
        request = self.repository.get_request(request_id)
        if not request or request["candidate_approval_status"] != "PENDING":
            raise ValueError("Candidate impact approval is not pending")
        if request.get("workflow_status") != "IMPACT_REVIEW_REQUIRED":
            raise ValueError("Shared BOM impact review is not required for this request")
        impact_review = self.impact.analyze_selected_candidate_impact(request_id)
        if not impact_review["requires_impact_approval"]:
            raise ValueError("Shared BOM impact approval is not required")
        return self._approve_selected_candidates(
            request_id, approved_by, impact_review=impact_review
        )

    def select_and_approve_candidates(self, request_id: str, selections: list[dict],
                                      approved_by: str) -> dict:
        """Backward-compatible alias. STEP29 selection never bypasses shared impact review."""
        return self.prepare_candidate_selection(request_id, selections, approved_by)

    def submit_additional_data(
        self,
        *,
        action_id: str,
        candidate_item_code: str,
        attributes: dict | None = None,
        demand_quantity: float | None = None,
        evaluation_items: list[str] | None = None,
    ) -> dict:
        action = self.repository.get_action(action_id)
        if not action:
            raise ValueError("Change action not found")
        request = self.repository.get_request(action["request_id"])
        if not request or request["candidate_approval_status"] != "PENDING":
            raise ValueError("Additional data must be submitted before candidate approval")
        attributes = dict(attributes or {})
        if attributes:
            self.repository.upsert_candidate_attributes(
                action_id=action_id, candidate_item_code=candidate_item_code,
                attributes=attributes, valid_from=request["as_of_date"],
            )
        if demand_quantity is not None:
            self.repository.update_request_demand_quantity(
                request["request_id"], float(demand_quantity)
            )
        if not attributes and demand_quantity is None:
            raise ValueError("At least one additional attribute or demand_quantity is required")
        result = self.evaluate_action(action_id)
        return {**result, "revalidated": True, "production_bom_modified": False}

    def approve_exception(self, request_id: str, reason: str, approved_by: str) -> dict:
        if not str(reason).strip():
            raise ValueError("Exception approval reason is required")
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        statuses = {action["evaluation_status"] for action in request["actions"]}
        if "FAIL" in statuses or "CONDITIONAL" not in statuses:
            raise ValueError("Exception approval is allowed only for CONDITIONAL requests")

        # STEP33-B: exception approval is a pre-workflow gate when a CONDITIONAL
        # candidate has been selected but candidate approval is still pending.
        if (
            request["candidate_approval_status"] == "PENDING"
            and request.get("workflow_status") == "CONDITIONAL_REVIEW_REQUIRED"
        ):
            if any(
                action["action_type"] in {"REPLACE", "ADD"}
                and not action.get("selected_candidate_id")
                for action in request["actions"]
            ):
                raise ValueError("A CONDITIONAL candidate must be selected before exception approval")
            exception = self.repository.record_approval(
                request_id=request_id, approval_id=self._id("APR"),
                stage="CONDITIONAL_EXCEPTION", decision="APPROVED",
                approved_by=approved_by, reason=reason.strip(),
            )
            impact_review = self.impact.analyze_selected_candidate_impact(request_id)
            selections = [{
                "action_id": action["action_id"],
                "candidate_id": action.get("selected_candidate_id"),
                "supplier_item_id": action.get("selected_supplier_item_id"),
            } for action in request["actions"] if action["action_type"] in {"REPLACE", "ADD"}]
            if impact_review["requires_impact_approval"]:
                self.repository.set_request_workflow_status(request_id, "IMPACT_REVIEW_REQUIRED")
                return {
                    **exception,
                    "exception_approval_id": exception.get("approval_id"),
                    "request_id": request_id,
                    "workflow_status": "IMPACT_REVIEW_REQUIRED",
                    "workflow_started": False,
                    "selections": selections,
                    "impact_review": impact_review,
                    "requires_exception": False,
                    "production_bom_modified": False,
                }
            approved = self._approve_selected_candidates(
                request_id, approved_by, impact_review=impact_review
            )
            return {
                **approved,
                "exception_approval_id": exception.get("approval_id"),
                "requires_exception": False,
            }

        # Backward compatibility for requests already candidate-approved by older data.
        if request["candidate_approval_status"] != "APPROVED":
            raise ValueError("Candidate selection or approval is required before exception approval")
        return self.repository.record_approval(
            request_id=request_id, approval_id=self._id("APR"),
            stage="CONDITIONAL_EXCEPTION", decision="APPROVED",
            approved_by=approved_by, reason=reason.strip(),
        )

    def create_preview(self, request_id: str, created_by: str) -> dict:
        request = self.repository.get_request(request_id)
        if not request or request["candidate_approval_status"] != "APPROVED":
            raise ValueError("Candidate approval is required before preview")
        if any(action["evaluation_status"] in {"PENDING", "FAIL"}
               for action in request["actions"]):
            raise ValueError("Every action must be PASS or CONDITIONAL before preview")
        return self.impact.create_preview(request_id, created_by)

    def approve_final(self, request_id: str, approved_by: str) -> dict:
        context = SQLiteMultiActionRepository(self.repository.database).get_apply_context(request_id)
        if not context or not context.get("preview"):
            raise ValueError("Preview is required before final approval")
        if context["preview"]["validation_status"] == "FAIL":
            raise ValueError("FAIL preview cannot be approved")
        if context["final_approval_status"] != "PENDING" or context["apply_status"] != "NOT_APPLIED":
            raise ValueError("Final approval is already finalized")
        if any(action["evaluation_status"] in {"PENDING", "FAIL"} for action in context["actions"]):
            raise ValueError("Every action must be PASS or CONDITIONAL before final approval")
        if any(action["evaluation_status"] == "CONDITIONAL" for action in context["actions"]):
            exception = next((approval for approval in context["approvals"] if
                approval["approval_stage"] == "CONDITIONAL_EXCEPTION" and
                approval["decision"] == "APPROVED" and approval.get("decision_reason")), None)
            if exception is None:
                raise ValueError("CONDITIONAL request requires exception approval before final approval")
        approval_id = self._id("APR")
        return self.repository.record_approval(
            request_id=request_id, approval_id=approval_id, stage="FINAL_APPLY",
            decision="APPROVED", approved_by=approved_by,
            selection={"preview_id": context["preview"]["preview_id"]},
        )

    def apply(self, request_id: str, final_approval_id: str, applied_by: str) -> dict:
        return self.apply_service.apply(
            request_id=request_id, final_approval_id=final_approval_id, applied_by=applied_by,
        )

    def get_analysis_explanation(self, request_id: str) -> dict:
        """Return a read-only summary explaining the active candidate analysis."""
        return self.explain.get_analysis(request_id)

    def get_candidate_evaluation_detail(
        self,
        request_id: str,
        candidate_item_code: str,
        action_id: str | None = None,
    ) -> dict:
        """Return persisted technical/supply/inventory evidence for one candidate."""
        return self.explain.get_candidate_detail(
            request_id=request_id,
            candidate_item_code=candidate_item_code,
            action_id=action_id,
        )

    def compare_candidates(
        self,
        request_id: str,
        candidate_item_codes: list[str] | None = None,
        action_id: str | None = None,
        criterion: str = "SPEC_SIMILARITY",
    ) -> dict:
        """Compare persisted candidates without changing the active workflow."""
        return self.explain.compare_candidates(
            request_id=request_id,
            candidate_item_codes=candidate_item_codes,
            action_id=action_id,
            criterion=criterion,
        )

    def get_completion_report_data(self, request_id: str) -> dict:
        """Return frozen/persisted evidence for the final completion report.

        The completion report must explain *why* the approved change was safe, not
        merely that Apply succeeded.  STEP39 therefore gathers persisted candidate
        evaluation evidence, the candidate-approval impact snapshot, final Preview,
        approvals and the actual Apply result.  It does not re-run candidate ranking
        or mutate workflow state.
        """
        request = self.repository.get_request(request_id)
        if not request:
            return {"success": False, "request_id": request_id, "message": "Change request not found"}
        if request.get("apply_status") != "APPLIED":
            return {"success": False, "request_id": request_id, "message": "완료 보고서는 Production Apply 이후 생성할 수 있습니다."}

        multi_repo = SQLiteMultiActionRepository(self.repository.database)
        context = multi_repo.get_apply_context(request_id) or {}
        candidate_rows = self.repository.list_request_candidate_evaluations(request_id)
        for row in candidate_rows:
            item = self.repository.get_item(row.get("candidate_item_code"))
            row["candidate_item_name"] = item.get("item_name") if item else None
            row["candidate_item_description"] = item.get("description") if item else None
        candidate_by_id = {row.get("candidate_id"): row for row in candidate_rows}

        enriched_actions = []
        selected_candidate_details = []
        for action in request.get("actions") or []:
            value = dict(action)
            for prefix, code in (
                ("parent", action.get("parent_item_code")),
                ("old", action.get("old_item_code")),
                ("new", action.get("new_item_code")),
            ):
                item = self.repository.get_item(code) if code else None
                value[f"{prefix}_item_name"] = item.get("item_name") if item else None
                value[f"{prefix}_item_description"] = item.get("description") if item else None

            action_candidates = [
                row for row in candidate_rows if row.get("action_id") == action.get("action_id")
            ]
            value["candidate_count"] = len(action_candidates)
            value["candidate_status_counts"] = {
                status: sum(row.get("final_status") == status for row in action_candidates)
                for status in ("PASS", "CONDITIONAL", "FAIL")
            }
            selected = candidate_by_id.get(action.get("selected_candidate_id"))
            if selected:
                value["selected_candidate"] = {
                    "candidate_id": selected.get("candidate_id"),
                    "candidate_item_code": selected.get("candidate_item_code"),
                    "final_status": selected.get("final_status"),
                    "total_score": selected.get("total_score"),
                    "grade": selected.get("grade"),
                    "rank_no": selected.get("rank_no"),
                }
                detail = self.get_candidate_evaluation_detail(
                    request_id,
                    selected.get("candidate_item_code"),
                    action.get("action_id"),
                )
                if detail:
                    detail = dict(detail)
                    detail["action_seq"] = action.get("action_seq")
                    detail["action_type"] = action.get("action_type")
                    detail["target_type"] = action.get("target_type")
                    detail["parent_item_code"] = action.get("parent_item_code")
                    detail["location_code"] = action.get("location_code")
                    selected_candidate_details.append(detail)
            enriched_actions.append(value)

        approvals = []
        impact_review = {}
        for raw in context.get("approvals") or []:
            approval = dict(raw)
            try:
                approval["selection"] = json.loads(approval.get("selection_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                approval["selection"] = {}
            if approval.get("approval_stage") == "CANDIDATE":
                impact_review = approval["selection"].get("impact_review") or impact_review
            approvals.append(approval)

        preview = dict(context.get("preview") or {})
        if preview:
            try:
                preview["snapshot"] = json.loads(preview.get("snapshot_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                preview["snapshot"] = {}

        with self.repository.database.connection() as connection:
            apply_row = connection.execute(
                "SELECT * FROM change_apply_results WHERE request_id=?", (request_id,)
            ).fetchone()
        apply_result = dict(apply_row) if apply_row else {}
        if apply_result:
            try:
                parsed_apply_result = json.loads(apply_result.get("result_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                parsed_apply_result = []
            apply_result["result_detail"] = parsed_apply_result
            apply_result["action_results"] = (
                parsed_apply_result
                if isinstance(parsed_apply_result, list)
                else parsed_apply_result.get("action_results", [])
                if isinstance(parsed_apply_result, dict)
                else []
            )

        analysis_summary = self.get_analysis_explanation(request_id)
        return {
            "success": True,
            "request_id": request_id,
            "request": request,
            "actions": enriched_actions,
            "analysis_summary": analysis_summary,
            "candidate_evaluations": candidate_rows,
            "selected_candidate_details": selected_candidate_details,
            "impact_review": impact_review,
            "approvals": approvals,
            "preview": preview,
            "apply_result": apply_result,
            "report_stage": "COMPLETED",
            "production_bom_modified": True,
        }

    def get_result(self, request_id: str) -> dict:
        result = self.repository.get_request(request_id)
        if not result:
            raise ValueError("Change request not found")

        # History detail can resume a persisted Request without bypassing MCP.
        # Expose only workflow identifiers needed for the next allowed step.
        context = SQLiteMultiActionRepository(self.repository.database).get_apply_context(request_id) or {}
        approvals = context.get("approvals") or []
        final_approval = next(
            (
                approval for approval in reversed(approvals)
                if approval.get("approval_stage") == "FINAL_APPLY"
                and approval.get("decision") == "APPROVED"
            ),
            None,
        )
        result["final_approval_id"] = (
            final_approval.get("approval_id") if final_approval else None
        )
        preview = context.get("preview") or {}
        result["preview_id"] = preview.get("preview_id")
        return result
