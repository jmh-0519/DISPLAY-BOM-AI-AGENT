from services.workflow_history_repository import WorkflowHistoryRepository


def list_design_changes_data() -> list[dict]:
    return WorkflowHistoryRepository().list_design_changes()


def get_design_change_data(change_id: str) -> dict:
    return WorkflowHistoryRepository().get_design_change(change_id)


def list_bom_reviews_data() -> list[dict]:
    return WorkflowHistoryRepository().list_bom_reviews()


def get_bom_review_data(review_id: str) -> dict:
    return WorkflowHistoryRepository().get_bom_review(review_id)
