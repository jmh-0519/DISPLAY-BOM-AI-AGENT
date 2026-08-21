from core.database_config import sqlite_database_path
from database import SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.rule_management_service import RuleManagementService
from services.training_export_service import TrainingExportService


def _repository():
    return SQLiteDesignChangeRepository(SQLiteDatabase(sqlite_database_path()))


def list_rules_data(as_of_date: str | None = None) -> list[dict]:
    return RuleManagementService(_repository()).list_rules(as_of_date)


def create_rule_data(rule: dict, conditions: list[dict]) -> dict:
    return RuleManagementService(_repository()).create_revision(rule, conditions)


def update_rule_data(rule: dict, conditions: list[dict]) -> dict:
    return create_rule_data(rule, conditions)


def deactivate_rule_data(rule_id: str, revision_no: int) -> dict:
    return RuleManagementService(_repository()).deactivate(rule_id, revision_no)


def list_phase3_change_history_data() -> list[dict]:
    return _repository().list_change_requests()


def record_performance_outcome_data(request_id: str, measurement_day: int,
                                    outcome: dict, user_rating: int | None,
                                    measured_at: str) -> dict:
    return _repository().record_performance(
        request_id, measurement_day, outcome, user_rating, measured_at,
    )


def export_training_dataset_data(date_from: str | None, date_to: str | None,
                                 created_by: str) -> dict:
    return TrainingExportService(_repository()).export_jsonl(
        date_from=date_from, date_to=date_to, created_by=created_by,
    )
