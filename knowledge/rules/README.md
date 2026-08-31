# Design Change Rule Knowledge Catalog

이 디렉터리는 설계변경의 **업무 Rule 정의와 사람이 읽는 정책 설명을 함께 관리**합니다.

핵심 원칙:

- Rule 문서의 TOML front matter가 RuleEngine이 사용할 수 있는 구조화 정의입니다.
- Markdown 본문은 RAG 검색/근거 설명에 사용하는 Knowledge Evidence입니다.
- RAG/LLM은 Rule을 찾아 설명할 수 있지만 PASS / CONDITIONAL / FAIL의 최종 판정 Authority가 아닙니다.
- 새로운 Rule은 Python 분기를 추가하지 않고 이 디렉터리에 문서를 추가하는 방식으로 확장할 수 있습니다.
- Runtime 적용 전 `python -m scripts.validate_rule_catalog` 검증을 통과해야 합니다.
- 특정 테스트 MODEL/자재코드를 Rule 선택 조건으로 사용하지 않습니다. Rule applicability는 reason/action/target/evaluation item 및 업무 속성으로 정의합니다.

현재 10개 문서는 v3.1.1의 기존 설계변경 Rule baseline을 문서 계약으로 옮긴 **초기 Catalog**입니다. 이 단계에서는 기존 DB Rule Runtime을 교체하지 않으며, 다음 RAG 단계에서 Catalog와 Runtime을 안전하게 연결합니다.
