# Design Change Rule Knowledge Catalog

이 디렉터리는 설계변경의 **업무 Rule 정의와 사람이 읽는 정책 설명을 함께 관리**합니다.

핵심 원칙:

- Rule 문서의 TOML front matter가 RuleEngine이 사용할 수 있는 구조화 정의입니다.
- Markdown 본문은 RAG 검색/근거 설명에 사용하는 Knowledge Evidence입니다.
- RAG/LLM은 Rule을 찾아 설명할 수 있지만 PASS / CONDITIONAL / FAIL의 최종 판정 Authority가 아닙니다.
- 새로운 Rule은 Python 분기를 추가하지 않고 이 디렉터리에 문서를 추가하는 방식으로 확장할 수 있습니다.
- Runtime 적용 전 `python -m scripts.validate_rule_catalog` 검증을 통과해야 합니다.
- 특정 테스트 MODEL/자재코드를 Rule 선택 조건으로 사용하지 않습니다. Rule applicability는 reason/action/target/evaluation item 및 업무 속성으로 정의합니다.

현재 10개 문서는 기존 설계변경 Rule baseline을 구조화 Knowledge Contract로 전환한 초기 Catalog입니다. `v4.0.0`에서는 이 Catalog와 Reason Knowledge가 Runtime 후보 평가 및 RAG Evidence에 통합되어 있으며, Rule 문서의 구조화 정의와 Markdown 설명을 같은 Source에서 관리합니다.
