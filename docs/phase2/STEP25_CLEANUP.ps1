$ErrorActionPreference = "Stop"

$targets = @(
    "repositories/csv_repository.py",
    "services/bom_service.py",
    "services/ai_design_change_workflow_service.py",
    "services/design_change_apply_service.py",
    "services/design_change_service.py",
    "services/review_service.py",
    "services/design_change_query_service.py",
    "services/design_change_report_service.py",
    "services/workflow_history_repository.py",
    "database/migration.py",
    "database/workflow_migration.py",
    "scripts/migrate_csv_to_sqlite.py",
    "scripts/migrate_workflow_to_sqlite.py",
    "tests/test_ai_design_change_workflow.py",
    "tests/test_bom_service.py",
    "tests/test_csv_to_sqlite_migration.py",
    "tests/test_design_change_apply_service.py",
    "tests/test_design_change_query_service.py",
    "tests/test_design_change_report_service.py",
    "tests/test_design_change_service.py",
    "tests/test_download_capability.py",
    "tests/test_repository_bom_service.py",
    "tests/test_repository_contract.py",
    "tests/test_review_service.py",
    "tests/test_sqlite_production_bom_service.py",
    "tests/test_workflow_history.py",
    "tests/test_workflow_sqlite_migration.py",
    "tests/test_material_list_tool.py",
    "tests/test_product_list_tool.py",
    "data/README_DATASET.md",
    "data/README_DESIGN_CHANGE_DATA.md"
)

$csvTargets = Get-ChildItem -Path "data" -Filter "*.csv" -File -ErrorAction SilentlyContinue
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
        Write-Host "removed: $target"
    }
}
foreach ($target in $csvTargets) {
    Remove-Item -LiteralPath $target.FullName -Force
    Write-Host "removed: $($target.FullName)"
}

Write-Host "STEP25 CSV runtime cleanup completed. display_bom.db was preserved."
