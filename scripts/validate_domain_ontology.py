from ontology.context_contract import CONTEXT_FIELD_POLICIES
from ontology.domain_ontology import DEFAULT_DOMAIN_ONTOLOGY


def main() -> None:
    DEFAULT_DOMAIN_ONTOLOGY.validate()

    print("CTX-01 Domain Ontology validation PASS")
    print(f"entity_type_count={len(DEFAULT_DOMAIN_ONTOLOGY.entity_types)}")
    print(f"relation_count={len(DEFAULT_DOMAIN_ONTOLOGY.relations)}")
    print(f"context_policy_count={len(CONTEXT_FIELD_POLICIES)}")


if __name__ == "__main__":
    main()
