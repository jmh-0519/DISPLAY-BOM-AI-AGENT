# STEP40-E — Confirmed Analysis / Workflow Presentation UX

## Changes
- After candidate analysis is confirmed, the full original analysis/candidate table is no longer rendered.
- Only the confirmed selected material(s) and their evaluation evidence are shown before Request creation.
- Removed the `Phase3 설계변경 Workflow` subtitle from the active workflow UI.
- Workflow / approval / apply statuses are displayed in Korean in both Agent chat and design-change history detail.
- `확정 변경 Action` visually emphasizes before values in blue bold and after values in red bold.
- Request detail renderer remains shared between Agent chat and `설계변경 이력`.

## Scope
UI/presentation only. No DB schema, Service, MCP, Apply, approval, or report business logic changed.
