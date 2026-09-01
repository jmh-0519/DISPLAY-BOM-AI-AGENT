from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY


def test_initial_allowlist_is_narrow_and_excludes_workflow_tables():
    policy = DEFAULT_TEXT_TO_SQL_POLICY
    assert len(policy.allowed_tables) == 15
    assert "bom_master" in policy.allowed_tables
    assert "inventory_balances" in policy.allowed_tables
    assert "production_plans" in policy.allowed_tables
    assert "change_requests" not in policy.allowed_tables
    assert "change_actions" not in policy.allowed_tables
    assert "change_approvals" not in policy.allowed_tables
    assert "rule_revisions" not in policy.allowed_tables
    assert "schema_versions" not in policy.allowed_tables
