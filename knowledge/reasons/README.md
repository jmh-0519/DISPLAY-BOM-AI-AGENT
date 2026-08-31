# Design Change Reason Knowledge Catalog

이 디렉터리는 설계변경 사유 코드, 자연어 Alias, 적용 Scope와 사람이 읽는 설명을 함께 관리합니다.

- TOML front matter는 Runtime Reason Resolver가 사용하는 구조화 메타데이터입니다.
- Markdown 본문은 향후 RAG 검색/설명에 사용하는 Knowledge Evidence입니다.
- Reason 문서가 Source of Truth이며, DB의 `change_reason_master`는 Request 이력 FK 보존을 위한 persistence projection입니다.
- 새 Reason은 Python 분기 없이 문서를 추가하여 확장할 수 있습니다.
- Rule 문서에서 사용하는 reason/action/target 조합은 반드시 해당 Reason scope에 포함되어야 합니다.
