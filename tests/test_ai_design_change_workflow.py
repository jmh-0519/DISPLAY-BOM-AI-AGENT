import hashlib
import shutil
from pathlib import Path

from services.ai_design_change_workflow_service import AiDesignChangeWorkflowService


def _copy_data(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "data"
    target = tmp_path / "data"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.zip"))
    return target


def _bom_hash(data_dir: Path) -> str:
    return hashlib.sha256((data_dir / "bom.csv").read_bytes()).hexdigest()


def test_pass_flow_changes_production_only_at_final_apply(tmp_path):
    data_dir = _copy_data(tmp_path)
    service = AiDesignChangeWorkflowService(str(data_dir))
    original = _bom_hash(data_dir)

    review = service.create_review_bom(
        "CHG-20260810-001", "BOM_AI_AGENT", "2026-08-12"
    )
    assert review["success"] is True
    assert _bom_hash(data_dir) == original

    ai_review = service.run_ai_review(
        review["review_id"], "BOM_AI_AGENT", "2026-08-12"
    )
    assert ai_review["workflow_result"] == "AI_REVIEW_COMPLETED"
    assert ai_review["ai_review_result"] == "PASS"
    assert _bom_hash(data_dir) == original

    report = service.generate_report("CHG-20260810-001")
    assert report["success"] is True
    assert report["report_stage"] == "PRE_APPLY"
    assert _bom_hash(data_dir) == original

    applied = service.apply_to_production(
        review["review_id"], "USER01", "2026-08-12"
    )
    assert applied["success"] is True
    assert applied["production_bom_modified"] is True
    assert _bom_hash(data_dir) != original


def test_conditional_review_does_not_change_production(tmp_path):
    data_dir = _copy_data(tmp_path)
    service = AiDesignChangeWorkflowService(str(data_dir))
    original = _bom_hash(data_dir)
    request = service.create_change_request(
        "LTA400HR01-0", "0001-200010", "9000-290004",
        "대체 자재 검토", "2026-08-20", "USER01", "2026-08-12",
    )
    assert request["success"] is True
    review = service.create_review_bom(
        request["change_id"], "BOM_AI_AGENT", "2026-08-12"
    )
    result = service.run_ai_review(
        review["review_id"], "BOM_AI_AGENT", "2026-08-12"
    )
    assert result["workflow_result"] == "REVIEW_NEEDS_CONFIRMATION"
    assert result["production_bom_modified"] is False
    assert _bom_hash(data_dir) == original


def test_mcp_server_exposes_only_new_design_change_workflow():
    from mcp_server import server

    assert callable(server.create_ai_change_request)
    assert callable(server.create_review_bom)
    assert callable(server.run_ai_bom_review)
    assert callable(server.generate_design_change_report)
    assert callable(server.export_bom_excel)
    assert callable(server.export_design_change_report)
    assert callable(server.apply_reviewed_bom)
    assert not hasattr(server, "evaluate_bom_review")
