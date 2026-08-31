# Display BOM Knowledge Layer

이 디렉터리는 Display BOM AI Agent의 외부 Knowledge Source를 관리합니다.

- `reasons/`: 설계변경 사유 코드, 자연어 Alias, 허용 Scope와 설명
- `rules/`: 설계변경 적합성 Rule의 구조화 조건과 설명
- `documents/`: 설계 Guide, Material Spec, Process/Change Policy, Supplier 기술문서, FAQ 등 일반 RAG 문서

구조화 Front Matter는 deterministic Runtime에서 사용하고, Markdown 본문과 일반 Knowledge 문서는 RAG 검색/근거 설명에 사용합니다.
LLM/RAG는 업무 Rule 판정 Authority가 아니며 PASS / CONDITIONAL / FAIL은 기존 RuleEngine이 결정합니다.

실제 사내/보안 문서는 `knowledge/documents/private/`에 두고 Git에 commit하지 않습니다.
