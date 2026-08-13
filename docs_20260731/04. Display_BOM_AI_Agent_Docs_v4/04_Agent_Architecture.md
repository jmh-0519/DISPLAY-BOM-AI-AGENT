# Agent Architecture

현재는 Rule-based BomAgent가 Tool을 선택합니다.

향후 구조

User
→ AzureBomAgent
→ Azure OpenAI
→ Tool Calling
→ ToolExecutor
→ Tool
→ Service
→ Oracle
