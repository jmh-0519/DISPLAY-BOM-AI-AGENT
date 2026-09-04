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
        DomainEntityType.BOM_EDGE,
        DomainEntityType.ITEM,
        DomainEntityType.ASSEMBLY,
        DomainEntityType.MATERIAL,
        DomainEntityType.SUPPLIER,
        DomainEntityType.RULE,
        DomainEntityType.ANALYSIS_SESSION,
        DomainEntityType.CHANGE_REQUEST,
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


def test_bom_edge_models_exact_parent_child_relation():
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.BOM,
        DomainRelationType.HAS_EDGE,
        DomainEntityType.BOM_EDGE,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.BOM_EDGE,
        DomainRelationType.PARENT_ITEM,
        DomainEntityType.ASSEMBLY,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.BOM_EDGE,
        DomainRelationType.CHILD_ITEM,
        DomainEntityType.MATERIAL,
    )


def test_analysis_session_and_change_request_are_distinct_authority_entities():
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.ANALYSIS_SESSION,
        DomainRelationType.TARGETS,
        DomainEntityType.BOM_EDGE,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
        DomainEntityType.CHANGE_REQUEST,
        DomainRelationType.BASED_ON,
        DomainEntityType.ANALYSIS_SESSION,
    )
    assert DEFAULT_DOMAIN_ONTOLOGY.is_subtype(
        DomainEntityType.CHANGE_REQUEST,
        DomainEntityType.DESIGN_CHANGE,
    )
    assert not DEFAULT_DOMAIN_ONTOLOGY.is_subtype(
        DomainEntityType.ANALYSIS_SESSION,
        DomainEntityType.DESIGN_CHANGE,
    )
