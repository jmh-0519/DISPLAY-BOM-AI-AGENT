from scripts.run_design_change_demo_acceptance import _run


def test_design_change_demo_acceptance_harness_passes_on_rebuilt_isolated_db(tmp_path):
    results = _run(tmp_path / "demo-acceptance.db")

    assert len(results) == 10
    failures = [
        f"{result.scenario}: {result.detail}"
        for result in results
        if not result.passed
    ]
    assert failures == []
