from __future__ import annotations


class ImpactAnalysisService:
    """Design-change impact analysis for preview and pre-workflow shared BOM review."""

    def __init__(self, repository) -> None:
        self.repository = repository

    def analyze_action(
        self, action: dict, plant_code: str, as_of_date: str
    ) -> list[dict]:
        parent = self.repository.get_item(action["parent_item_code"])
        if not parent:
            raise ValueError("Action parent item not found")
        if parent["item_type"] == "VERSION" and action["target_type"] == "ASSY":
            return [{
                "action_id": action["action_id"],
                "plant_code": plant_code,
                "impacted_item_code": parent["item_code"],
                "impact_type": "MODEL_CONNECTION",
                "impact_path": f"{parent['item_code']}/{action.get('old_item_code') or action.get('new_item_code')}",
            }]

        impacts = [{
            "action_id": action["action_id"],
            "plant_code": plant_code,
            "impacted_item_code": parent["item_code"],
            "impact_type": "TARGET",
            "impact_path": parent["item_code"],
        }]
        if parent["item_type"] == "ASSEMBLY":
            for ancestor in self.repository.get_recursive_ancestors(
                parent["item_code"], plant_code, as_of_date
            ):
                impacts.append({
                    "action_id": action["action_id"],
                    "plant_code": plant_code,
                    "impacted_item_code": ancestor["item_code"],
                    "impact_type": "MODEL" if ancestor["item_type"] == "VERSION" else "PARENT_ASSY",
                    "impact_path": ancestor["path"],
                })
        unique = {}
        for impact in impacts:
            unique[(impact["impacted_item_code"], impact["impact_type"])] = impact
        return list(unique.values())

    @staticmethod
    def _spec_profile(profile: dict) -> dict:
        """Return technical/master attributes suitable for before/after comparison."""
        excluded = {
            "item_name", "material_name",
        }
        excluded_tokens = (
            "supplier", "cost", "price", "inventory", "stock", "quantity",
            "lead_time", "created_at", "updated_at",
        )
        return {
            key: value
            for key, value in profile.items()
            if key not in excluded
            and not any(token in key.lower() for token in excluded_tokens)
        }

    @classmethod
    def _compare_specs(cls, before_profile: dict, after_profile: dict) -> list[dict]:
        before = cls._spec_profile(before_profile)
        after = cls._spec_profile(after_profile)
        keys = sorted(set(before) | set(after))
        rows = []
        for key in keys:
            old_value = before.get(key)
            new_value = after.get(key)
            if old_value == new_value:
                change_status = "SAME"
            elif old_value in {None, ""}:
                change_status = "ADDED"
            elif new_value in {None, ""}:
                change_status = "REMOVED"
            else:
                change_status = "CHANGED"
            rows.append({
                "attribute": key,
                "before": old_value,
                "after": new_value,
                "change_status": change_status,
            })
        return rows

    def analyze_selection_context(self, *, request: dict, actions: list[dict]) -> dict:
        """Read-only shared-BOM impact analysis for an Analysis Session.

        This variant does not require change_requests/change_actions rows and therefore
        can run before the user decides to create a Design Change Request.
        """
        action_reviews: list[dict] = []
        requires_impact_approval = False
        impacted_models_by_code: dict[str, dict] = {}
        for action in actions:
            parent = self.repository.get_item(action["parent_item_code"])
            if not parent:
                raise ValueError("Action parent item not found")
            parent_profile = self.repository.get_item_profile(
                action["parent_item_code"], request["as_of_date"]
            )
            shared_parent = (
                parent["item_type"] == "ASSEMBLY"
                and str(parent_profile.get("usage_type") or "").upper() == "COMMON"
            )
            requires_impact_approval = requires_impact_approval or shared_parent

            old_code = action.get("old_item_code")
            new_code = action.get("new_item_code")
            if action["action_type"] == "QUANTITY_CHANGE":
                new_code = old_code
            old_item = self.repository.get_item(old_code) if old_code else None
            new_item = self.repository.get_item(new_code) if new_code else None
            before_profile = self.repository.get_item_profile(old_code, request["as_of_date"]) if old_code else {}
            after_profile = self.repository.get_item_profile(new_code, request["as_of_date"]) if new_code else {}
            spec_changes = self._compare_specs(before_profile, after_profile)
            if action["action_type"] == "QUANTITY_CHANGE":
                spec_changes.insert(0, {
                    "attribute": "quantity", "before": action.get("old_quantity"),
                    "after": action.get("new_quantity"),
                    "change_status": "SAME" if action.get("old_quantity") == action.get("new_quantity") else "CHANGED",
                })
            elif action["action_type"] == "DELETE":
                spec_changes.insert(0, {"attribute": "bom_relation", "before": old_code, "after": None, "change_status": "REMOVED"})
            elif action["action_type"] == "ADD":
                spec_changes.insert(0, {"attribute": "bom_relation", "before": None, "after": new_code, "change_status": "ADDED"})

            if shared_parent:
                ancestors = self.repository.get_recursive_ancestors(
                    action["parent_item_code"], request["plant_code"], request["as_of_date"]
                )
                model_ancestors = [value for value in ancestors if value["item_type"] == "VERSION"]
            else:
                model_ancestors = [{
                    "item_code": request["version_code"], "item_type": "VERSION",
                    "path": f"{request['version_code']}/{action['parent_item_code']}",
                }]

            changed_specs = [value for value in spec_changes if value.get("change_status") != "SAME"]
            models = []
            for ancestor in model_ancestors:
                model = self.repository.get_item(ancestor["item_code"]) or {}
                model_row = {
                    "model_code": ancestor["item_code"], "model_name": model.get("item_name"),
                    "model_description": model.get("description"), "plant_code": request["plant_code"],
                    "impact_path": ancestor.get("path"), "parent_item_code": action["parent_item_code"],
                    "parent_name": parent.get("item_name"), "parent_usage_type": parent_profile.get("usage_type"),
                    "location_code": action.get("location_code"), "old_item_code": old_code,
                    "old_item_name": old_item.get("item_name") if old_item else None,
                    "old_item_description": old_item.get("description") if old_item else None,
                    "new_item_code": new_code, "new_item_name": new_item.get("item_name") if new_item else None,
                    "new_item_description": new_item.get("description") if new_item else None,
                    "old_quantity": action.get("old_quantity"), "new_quantity": action.get("new_quantity"),
                    "spec_changes": [dict(value) for value in spec_changes],
                    "changed_specs": [dict(value) for value in changed_specs],
                    "changed_spec_count": len(changed_specs),
                }
                models.append(model_row)
                existing = impacted_models_by_code.get(ancestor["item_code"])
                impact_entry = {
                    "action_id": action["action_id"], "parent_item_code": action["parent_item_code"],
                    "old_item_code": old_code, "new_item_code": new_code,
                    "spec_changes": [dict(value) for value in spec_changes],
                    "changed_specs": [dict(value) for value in changed_specs],
                }
                if existing is None:
                    impacted_models_by_code[ancestor["item_code"]] = {**model_row, "action_impacts": [impact_entry]}
                else:
                    existing.setdefault("action_impacts", []).append(impact_entry)
            action_reviews.append({
                "action_id": action["action_id"], "action_type": action["action_type"],
                "target_type": action["target_type"], "parent_item_code": action["parent_item_code"],
                "parent_item_name": parent.get("item_name"), "parent_description": parent.get("description"),
                "parent_usage_type": parent_profile.get("usage_type"), "shared_bom_change": shared_parent,
                "old_item_code": old_code, "old_item_name": old_item.get("item_name") if old_item else None,
                "old_item_description": old_item.get("description") if old_item else None,
                "new_item_code": new_code, "new_item_name": new_item.get("item_name") if new_item else None,
                "new_item_description": new_item.get("description") if new_item else None,
                "spec_changes": spec_changes, "changed_specs": changed_specs,
                "changed_spec_count": len(changed_specs), "impacted_models": models,
            })
        return {
            "analysis_id": request.get("analysis_id"), "plant_code": request["plant_code"],
            "requires_impact_approval": requires_impact_approval,
            "impacted_model_count": len(impacted_models_by_code),
            "impacted_models": list(impacted_models_by_code.values()),
            "model_spec_impacts": [
                {
                    "model_code": model.get("model_code"), "plant_code": model.get("plant_code"),
                    "action_id": action_impact.get("action_id"), "parent_item_code": action_impact.get("parent_item_code"),
                    "old_item_code": action_impact.get("old_item_code"), "new_item_code": action_impact.get("new_item_code"),
                    "spec_changes": action_impact.get("spec_changes") or [],
                    "changed_specs": action_impact.get("changed_specs") or [],
                }
                for model in impacted_models_by_code.values()
                for action_impact in model.get("action_impacts", [])
            ],
            "actions": action_reviews, "production_bom_modified": False,
        }

    def analyze_selected_candidate_impact(self, request_id: str) -> dict:
        """Analyze candidate-selection impact before the design-change Workflow begins.

        A child change inside a COMMON parent assembly changes the shared assembly BOM,
        so all models using that assembly in the selected PLANT must be reviewed. Replacing
        a COMMON assembly connection directly under a VERSION only changes that model's
        connection and therefore does not trigger the shared-BOM approval gate.
        """
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")

        action_reviews: list[dict] = []
        requires_impact_approval = False
        impacted_models_by_code: dict[str, dict] = {}

        for action in request["actions"]:
            if action["action_type"] in {"REPLACE", "ADD"}:
                if not action.get("selected_candidate_id") or not action.get("new_item_code"):
                    raise ValueError("Candidate selection is required before impact analysis")

            parent = self.repository.get_item(action["parent_item_code"])
            if not parent:
                raise ValueError("Action parent item not found")
            parent_profile = self.repository.get_item_profile(
                action["parent_item_code"], request["as_of_date"]
            )
            shared_parent = (
                parent["item_type"] == "ASSEMBLY"
                and str(parent_profile.get("usage_type") or "").upper() == "COMMON"
            )
            requires_impact_approval = requires_impact_approval or shared_parent

            old_code = action.get("old_item_code")
            new_code = action.get("new_item_code")
            if action["action_type"] == "QUANTITY_CHANGE":
                new_code = old_code
            old_item = self.repository.get_item(old_code) if old_code else None
            new_item = self.repository.get_item(new_code) if new_code else None
            before_profile = (
                self.repository.get_item_profile(old_code, request["as_of_date"])
                if old_code else {}
            )
            after_profile = (
                self.repository.get_item_profile(new_code, request["as_of_date"])
                if new_code else {}
            )
            spec_changes = self._compare_specs(before_profile, after_profile)
            if action["action_type"] == "QUANTITY_CHANGE":
                spec_changes.insert(0, {
                    "attribute": "quantity",
                    "before": action.get("old_quantity"),
                    "after": action.get("new_quantity"),
                    "change_status": (
                        "SAME" if action.get("old_quantity") == action.get("new_quantity")
                        else "CHANGED"
                    ),
                })
            elif action["action_type"] == "DELETE":
                spec_changes.insert(0, {
                    "attribute": "bom_relation",
                    "before": old_code,
                    "after": None,
                    "change_status": "REMOVED",
                })
            elif action["action_type"] == "ADD":
                spec_changes.insert(0, {
                    "attribute": "bom_relation",
                    "before": None,
                    "after": new_code,
                    "change_status": "ADDED",
                })

            if shared_parent:
                ancestors = self.repository.get_recursive_ancestors(
                    action["parent_item_code"], request["plant_code"], request["as_of_date"]
                )
                model_ancestors = [
                    value for value in ancestors if value["item_type"] == "VERSION"
                ]
            else:
                model_ancestors = [{
                    "item_code": request["version_code"],
                    "item_type": "VERSION",
                    "path": f"{request['version_code']}/{action['parent_item_code']}",
                }]

            changed_specs = [
                value for value in spec_changes if value.get("change_status") != "SAME"
            ]
            models = []
            for ancestor in model_ancestors:
                model = self.repository.get_item(ancestor["item_code"]) or {}
                model_row = {
                    "model_code": ancestor["item_code"],
                    "model_name": model.get("item_name"),
                    "model_description": model.get("description"),
                    "plant_code": request["plant_code"],
                    "impact_path": ancestor.get("path"),
                    "parent_item_code": action["parent_item_code"],
                    "parent_name": parent.get("item_name"),
                    "parent_usage_type": parent_profile.get("usage_type"),
                    "location_code": action.get("location_code"),
                    "old_item_code": old_code,
                    "old_item_name": old_item.get("item_name") if old_item else None,
                    "old_item_description": old_item.get("description") if old_item else None,
                    "new_item_code": new_code,
                    "new_item_name": new_item.get("item_name") if new_item else None,
                    "new_item_description": new_item.get("description") if new_item else None,
                    "old_quantity": action.get("old_quantity"),
                    "new_quantity": action.get("new_quantity"),
                    "spec_changes": [dict(value) for value in spec_changes],
                    "changed_specs": [dict(value) for value in changed_specs],
                    "changed_spec_count": len(changed_specs),
                }
                models.append(model_row)
                # One model may be impacted by multiple actions. Keep a summary row with
                # action-specific impact details instead of silently overwriting it.
                existing = impacted_models_by_code.get(ancestor["item_code"])
                if existing is None:
                    impacted_models_by_code[ancestor["item_code"]] = {
                        **model_row,
                        "action_impacts": [{
                            "action_id": action["action_id"],
                            "parent_item_code": action["parent_item_code"],
                            "old_item_code": old_code,
                            "new_item_code": new_code,
                            "spec_changes": [dict(value) for value in spec_changes],
                            "changed_specs": [dict(value) for value in changed_specs],
                        }],
                    }
                else:
                    existing.setdefault("action_impacts", []).append({
                        "action_id": action["action_id"],
                        "parent_item_code": action["parent_item_code"],
                        "old_item_code": old_code,
                        "new_item_code": new_code,
                        "spec_changes": [dict(value) for value in spec_changes],
                        "changed_specs": [dict(value) for value in changed_specs],
                    })

            action_reviews.append({
                "action_id": action["action_id"],
                "action_type": action["action_type"],
                "target_type": action["target_type"],
                "parent_item_code": action["parent_item_code"],
                "parent_item_name": parent.get("item_name"),
                "parent_description": parent.get("description"),
                "parent_usage_type": parent_profile.get("usage_type"),
                "shared_bom_change": shared_parent,
                "old_item_code": old_code,
                "old_item_name": old_item.get("item_name") if old_item else None,
                "old_item_description": old_item.get("description") if old_item else None,
                "new_item_code": new_code,
                "new_item_name": new_item.get("item_name") if new_item else None,
                "new_item_description": new_item.get("description") if new_item else None,
                "spec_changes": spec_changes,
                "changed_specs": changed_specs,
                "changed_spec_count": len(changed_specs),
                "impacted_models": models,
            })

        return {
            "request_id": request_id,
            "plant_code": request["plant_code"],
            "requires_impact_approval": requires_impact_approval,
            "impacted_model_count": len(impacted_models_by_code),
            "impacted_models": list(impacted_models_by_code.values()),
            "model_spec_impacts": [
                {
                    "model_code": model.get("model_code"),
                    "plant_code": model.get("plant_code"),
                    "action_id": action_impact.get("action_id"),
                    "parent_item_code": action_impact.get("parent_item_code"),
                    "old_item_code": action_impact.get("old_item_code"),
                    "new_item_code": action_impact.get("new_item_code"),
                    "spec_changes": action_impact.get("spec_changes") or [],
                    "changed_specs": action_impact.get("changed_specs") or [],
                }
                for model in impacted_models_by_code.values()
                for action_impact in model.get("action_impacts", [])
            ],
            "actions": action_reviews,
            "production_bom_modified": False,
        }

    def create_preview(self, request_id: str, created_by: str) -> dict:
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        actions = request["actions"]
        if not actions:
            raise ValueError("Change request has no actions")
        statuses = {action["evaluation_status"] for action in actions}
        if "PENDING" in statuses:
            raise ValueError("PENDING action cannot be included in a preview")
        validation_status = (
            "FAIL" if "FAIL" in statuses else
            "CONDITIONAL" if "CONDITIONAL" in statuses else "PASS"
        )
        impacts = []
        for action in actions:
            impacts.extend(self.analyze_action(
                action, request["plant_code"], request["as_of_date"]
            ))
        snapshot_actions = []
        for action in actions:
            value = {key: action.get(key) for key in (
                "action_id", "action_type", "target_type", "parent_item_code",
                "plant_code",
                "old_item_code", "new_item_code", "old_quantity", "new_quantity",
                "location_code", "evaluation_status", "selected_candidate_id",
                "selected_supplier_item_id", "row_revision",
            )}
            if action["action_type"] == "ADD":
                duplicates = self.repository.get_active_bom_relations(
                    parent_item_code=action["parent_item_code"],
                    child_item_code=action["new_item_code"],
                    location_code=action["location_code"],
                    plant_code=request["plant_code"],
                    as_of_date=request["effective_date"],
                )
                if duplicates:
                    raise ValueError("ADD target is already active at the effective date")
            else:
                relations = self.repository.get_active_bom_relations(
                    parent_item_code=action["parent_item_code"],
                    child_item_code=action["old_item_code"],
                    location_code=action["location_code"],
                    plant_code=request["plant_code"],
                    as_of_date=request["effective_date"],
                )
                if len(relations) != 1:
                    raise ValueError("Preview source BOM relation must exist exactly once")
                value.update({
                    "source_bom_id": relations[0]["bom_id"],
                    "source_bom_row_revision": relations[0]["row_revision"],
                    "source_bom_quantity": relations[0]["quantity"],
                })
            snapshot_actions.append(value)
        snapshot = {
            "request_id": request_id,
            "plant_code": request["plant_code"],
            "request_revision": request["row_revision"],
            "actions": snapshot_actions,
            "impacts": impacts,
        }
        preview = self.repository.save_preview(
            request_id=request_id, validation_status=validation_status,
            snapshot=snapshot, impacts=impacts, created_by=created_by,
            plant_code=request["plant_code"],
        )
        return {**preview, "validation_status": validation_status, **snapshot}
