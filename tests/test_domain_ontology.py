from ontology.domain_ontology import (
    DEFAULT_DOMAIN_ONTOLOGY,
    DomainEntityType,
    DomainRelationType,
)


def test_default_ontology_is_valid_and_contains_core_entities():
    DEFAULT_DOMAIN_ONTOLOGY.validate()

    assert set(DEFAULT_DOMAIN_ONTOLOGY.entity_types) == {
        DomainEntityType.PRODUCT,
        DomainEntityType.VERSION,
        DomainEntityType.PLANT,
        DomainEntityType.BOM,
        DomainEntityType.ITEM,
        DomainEntityType.ASSEMBLY,
        DomainEntityType.MATERIAL,
        DomainEntityType.SUPPLIER,
        DomainEntityType.RULE,
        DomainEntityType.DESIGN_CHANGE,
    }


def test_material_and_assembly_are_item_subtypes():
    assert DEFAULT_DOMAIN_ONTOLOGY.is_subtype(
        DomainEntityType.MATERIAL,
        DomainEntityType.ITEM,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.is_subtype(
        DomainEntityType.ASSEMBLY,
        DomainEntityType.ITEM,
    )


def test_item_relations_are_subtype_aware():
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.MATERIAL,
        DomainRelationType.SUPPLIED_BY,
        DomainEntityType.SUPPLIER,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.BOM,
        DomainRelationType.CONTAINS,
        DomainEntityType.MATERIAL,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.DESIGN_CHANGE,
        DomainRelationType.TARGETS,
        DomainEntityType.ASSEMBLY,
    )


def test_invalid_business_relation_is_not_allowed():
    assert not DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.SUPPLIER,
        DomainRelationType.HAS_BOM,
        DomainEntityType.VERSION,
    )
