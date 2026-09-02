"""Canonical Display BOM business ontology.

CTX-01 intentionally defines business meaning, not a second database schema.
The ontology is small, deterministic, and framework-independent so later
Context/RAG/Text-to-SQL/Planning layers can share the same entity vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DomainEntityType(str, Enum):
    PRODUCT = "PRODUCT"
    VERSION = "VERSION"
    PLANT = "PLANT"
    BOM = "BOM"
    ITEM = "ITEM"
    ASSEMBLY = "ASSEMBLY"
    MATERIAL = "MATERIAL"
    SUPPLIER = "SUPPLIER"
    RULE = "RULE"
    DESIGN_CHANGE = "DESIGN_CHANGE"


class DomainRelationType(str, Enum):
    HAS_VERSION = "HAS_VERSION"
    VERSION_OF = "VERSION_OF"
    HAS_BOM = "HAS_BOM"
    VALID_AT = "VALID_AT"
    CONTAINS = "CONTAINS"
    IS_A = "IS_A"
    SUPPLIED_BY = "SUPPLIED_BY"
    TARGETS = "TARGETS"
    APPLIES_TO = "APPLIES_TO"
    APPLIES_AT = "APPLIES_AT"
    EVALUATED_BY = "EVALUATED_BY"


@dataclass(frozen=True, order=True)
class OntologyRelation:
    subject: DomainEntityType
    relation: DomainRelationType
    object: DomainEntityType


@dataclass(frozen=True)
class DomainOntology:
    """Immutable business-meaning contract.

    Relation checks are subtype-aware.  For example, MATERIAL is an ITEM, so
    ITEM -> SUPPLIED_BY -> SUPPLIER also permits MATERIAL -> SUPPLIED_BY ->
    SUPPLIER without duplicating the relation definition.
    """

    entity_types: tuple[DomainEntityType, ...]
    relations: tuple[OntologyRelation, ...]

    def validate(self) -> None:
        if len(set(self.entity_types)) != len(self.entity_types):
            raise ValueError("duplicate ontology entity type")

        relation_keys = {
            (value.subject, value.relation, value.object)
            for value in self.relations
        }
        if len(relation_keys) != len(self.relations):
            raise ValueError("duplicate ontology relation")

        for relation in self.relations:
            if relation.subject not in self.entity_types:
                raise ValueError(f"unknown subject entity: {relation.subject}")
            if relation.object not in self.entity_types:
                raise ValueError(f"unknown object entity: {relation.object}")
            if (
                relation.relation == DomainRelationType.IS_A
                and relation.subject == relation.object
            ):
                raise ValueError("ontology IS_A self-cycle is not allowed")

        for entity in self.entity_types:
            if self._has_subtype_cycle(entity, entity, set()):
                raise ValueError(f"ontology subtype cycle detected at {entity.value}")

    def is_subtype(
        self,
        child: DomainEntityType,
        parent: DomainEntityType,
    ) -> bool:
        if child == parent:
            return True

        direct_parents = {
            relation.object
            for relation in self.relations
            if relation.relation == DomainRelationType.IS_A
            and relation.subject == child
        }
        return any(self.is_subtype(value, parent) for value in direct_parents)

    def relation_allowed(
        self,
        subject: DomainEntityType,
        relation: DomainRelationType,
        object_: DomainEntityType,
    ) -> bool:
        return any(
            spec.relation == relation
            and self.is_subtype(subject, spec.subject)
            and self.is_subtype(object_, spec.object)
            for spec in self.relations
            if spec.relation != DomainRelationType.IS_A
        ) or any(
            spec.relation == DomainRelationType.IS_A
            and relation == DomainRelationType.IS_A
            and spec.subject == subject
            and spec.object == object_
            for spec in self.relations
        )

    def _has_subtype_cycle(
        self,
        origin: DomainEntityType,
        current: DomainEntityType,
        visited: set[DomainEntityType],
    ) -> bool:
        if current in visited:
            return current == origin
        next_visited = set(visited)
        next_visited.add(current)
        parents = {
            relation.object
            for relation in self.relations
            if relation.relation == DomainRelationType.IS_A
            and relation.subject == current
        }
        return any(
            parent == origin
            or self._has_subtype_cycle(origin, parent, next_visited)
            for parent in parents
        )


DEFAULT_DOMAIN_ONTOLOGY = DomainOntology(
    entity_types=tuple(DomainEntityType),
    relations=(
        OntologyRelation(
            DomainEntityType.PRODUCT,
            DomainRelationType.HAS_VERSION,
            DomainEntityType.VERSION,
        ),
        OntologyRelation(
            DomainEntityType.VERSION,
            DomainRelationType.VERSION_OF,
            DomainEntityType.PRODUCT,
        ),
        OntologyRelation(
            DomainEntityType.VERSION,
            DomainRelationType.HAS_BOM,
            DomainEntityType.BOM,
        ),
        OntologyRelation(
            DomainEntityType.BOM,
            DomainRelationType.VALID_AT,
            DomainEntityType.PLANT,
        ),
        OntologyRelation(
            DomainEntityType.BOM,
            DomainRelationType.CONTAINS,
            DomainEntityType.ITEM,
        ),
        OntologyRelation(
            DomainEntityType.ASSEMBLY,
            DomainRelationType.IS_A,
            DomainEntityType.ITEM,
        ),
        OntologyRelation(
            DomainEntityType.MATERIAL,
            DomainRelationType.IS_A,
            DomainEntityType.ITEM,
        ),
        OntologyRelation(
            DomainEntityType.ASSEMBLY,
            DomainRelationType.CONTAINS,
            DomainEntityType.ITEM,
        ),
        OntologyRelation(
            DomainEntityType.ITEM,
            DomainRelationType.SUPPLIED_BY,
            DomainEntityType.SUPPLIER,
        ),
        OntologyRelation(
            DomainEntityType.DESIGN_CHANGE,
            DomainRelationType.TARGETS,
            DomainEntityType.ITEM,
        ),
        OntologyRelation(
            DomainEntityType.DESIGN_CHANGE,
            DomainRelationType.APPLIES_TO,
            DomainEntityType.VERSION,
        ),
        OntologyRelation(
            DomainEntityType.DESIGN_CHANGE,
            DomainRelationType.APPLIES_AT,
            DomainEntityType.PLANT,
        ),
        OntologyRelation(
            DomainEntityType.DESIGN_CHANGE,
            DomainRelationType.EVALUATED_BY,
            DomainEntityType.RULE,
        ),
    ),
)

DEFAULT_DOMAIN_ONTOLOGY.validate()


__all__ = [
    "DEFAULT_DOMAIN_ONTOLOGY",
    "DomainEntityType",
    "DomainOntology",
    "DomainRelationType",
    "OntologyRelation",
]
