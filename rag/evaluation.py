from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from .knowledge_corpus import KnowledgeCorpus
from .retrieval_service import RagSearchResponse
from .vector_store import KnowledgeSearchFilter, KnowledgeSearchHit


class RagEvaluationError(ValueError):
    """The controlled RAG evaluation dataset or result is invalid."""


class RetrievalService(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: KnowledgeSearchFilter | None = None,
    ) -> RagSearchResponse: ...


@dataclass(frozen=True)
class RagEvaluationGate:
    hit_rate_at_5_min: float = 0.90
    mean_recall_at_5_min: float = 0.90
    mrr_min: float = 0.70
    filter_accuracy_min: float = 0.95

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "RagEvaluationGate":
        raw = raw or {}
        values = {
            "hit_rate_at_5_min": float(raw.get("hit_rate_at_5_min", 0.90)),
            "mean_recall_at_5_min": float(raw.get("mean_recall_at_5_min", 0.90)),
            "mrr_min": float(raw.get("mrr_min", 0.70)),
            "filter_accuracy_min": float(raw.get("filter_accuracy_min", 0.95)),
        }
        if any(value < 0.0 or value > 1.0 for value in values.values()):
            raise RagEvaluationError("evaluation gate values must be between 0 and 1")
        return cls(**values)


@dataclass(frozen=True)
class RagEvaluationCase:
    case_id: str
    query: str
    expected_document_ids: tuple[str, ...]
    category: str
    top_k: int = 5
    filters: KnowledgeSearchFilter | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RagEvaluationCase":
        case_id = str(raw.get("case_id") or "").strip()
        query = str(raw.get("query") or "").strip()
        category = str(raw.get("category") or "").strip().upper()
        expected = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in raw.get("expected_document_ids", [])
                if str(value).strip()
            )
        )
        try:
            top_k = int(raw.get("top_k", 5))
        except (TypeError, ValueError) as exc:
            raise RagEvaluationError(f"{case_id or '<unknown>'}: top_k must be an integer") from exc

        missing = [
            name
            for name, value in (
                ("case_id", case_id),
                ("query", query),
                ("category", category),
            )
            if not value
        ]
        if missing:
            raise RagEvaluationError(f"evaluation case missing fields: {missing}")
        if not expected:
            raise RagEvaluationError(f"{case_id}: expected_document_ids must not be empty")
        if top_k < 5 or top_k > 50:
            raise RagEvaluationError(f"{case_id}: top_k must be between 5 and 50")

        filters_raw = raw.get("filters")
        filters = None
        if filters_raw is not None:
            if not isinstance(filters_raw, dict):
                raise RagEvaluationError(f"{case_id}: filters must be an object")
            filters = KnowledgeSearchFilter(
                document_type=filters_raw.get("document_type"),
                status=filters_raw.get("status", "ACTIVE"),
                language=filters_raw.get("language"),
                product_family=filters_raw.get("product_family"),
                material_type=filters_raw.get("material_type"),
                tag=filters_raw.get("tag"),
            ).normalized()

        return cls(
            case_id=case_id,
            query=query,
            expected_document_ids=expected,
            category=category,
            top_k=top_k,
            filters=filters,
        )


@dataclass(frozen=True)
class RagEvaluationDataset:
    dataset_id: str
    version: str
    description: str
    gate: RagEvaluationGate
    cases: tuple[RagEvaluationCase, ...]

    @classmethod
    def load(cls, path: str | Path) -> "RagEvaluationDataset":
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RagEvaluationError(f"evaluation dataset not found: {source}") from exc
        except json.JSONDecodeError as exc:
            raise RagEvaluationError(f"invalid evaluation dataset JSON: {source}: {exc}") from exc

        dataset_id = str(raw.get("dataset_id") or "").strip()
        version = str(raw.get("version") or "").strip()
        description = str(raw.get("description") or "").strip()
        if not dataset_id or not version:
            raise RagEvaluationError("dataset_id and version are required")
        raw_cases = raw.get("cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise RagEvaluationError("cases must be a non-empty list")
        cases = tuple(RagEvaluationCase.from_dict(value) for value in raw_cases)
        case_ids = [case.case_id for case in cases]
        duplicates = sorted({value for value in case_ids if case_ids.count(value) > 1})
        if duplicates:
            raise RagEvaluationError(f"duplicate evaluation case ids: {duplicates}")
        return cls(
            dataset_id=dataset_id,
            version=version,
            description=description,
            gate=RagEvaluationGate.from_dict(raw.get("gates")),
            cases=cases,
        )


@dataclass(frozen=True)
class RagEvaluationCaseResult:
    case_id: str
    category: str
    query: str
    expected_document_ids: tuple[str, ...]
    retrieved_document_ids: tuple[str, ...]
    relevant_ranks: tuple[int, ...]
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    recall_at_5: float
    reciprocal_rank: float
    filter_applied: bool
    filter_pass: bool
    latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["expected_document_ids"] = list(self.expected_document_ids)
        value["retrieved_document_ids"] = list(self.retrieved_document_ids)
        value["relevant_ranks"] = list(self.relevant_ranks)
        return value


@dataclass(frozen=True)
class RagEvaluationSummary:
    dataset_id: str
    dataset_version: str
    case_count: int
    filter_case_count: int
    hit_rate_at_1: float
    hit_rate_at_3: float
    hit_rate_at_5: float
    mean_recall_at_5: float
    mrr: float
    filter_accuracy: float
    miss_rate_at_5: float
    latency_p50_ms: float
    latency_p95_ms: float
    gate_pass: bool
    gate_checks: dict[str, bool]
    category_metrics: dict[str, dict[str, float | int]]
    cases: tuple[RagEvaluationCaseResult, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "case_count": self.case_count,
            "filter_case_count": self.filter_case_count,
            "metrics": {
                "hit_rate_at_1": self.hit_rate_at_1,
                "hit_rate_at_3": self.hit_rate_at_3,
                "hit_rate_at_5": self.hit_rate_at_5,
                "mean_recall_at_5": self.mean_recall_at_5,
                "mrr": self.mrr,
                "filter_accuracy": self.filter_accuracy,
                "miss_rate_at_5": self.miss_rate_at_5,
                "latency_p50_ms": self.latency_p50_ms,
                "latency_p95_ms": self.latency_p95_ms,
            },
            "gate_pass": self.gate_pass,
            "gate_checks": dict(self.gate_checks),
            "category_metrics": dict(self.category_metrics),
            "cases": [case.as_dict() for case in self.cases],
        }


def validate_dataset_against_corpus(
    dataset: RagEvaluationDataset,
    corpus: KnowledgeCorpus,
    *,
    minimum_case_count: int = 40,
) -> None:
    if len(dataset.cases) < minimum_case_count:
        raise RagEvaluationError(
            f"evaluation dataset requires at least {minimum_case_count} cases; "
            f"actual={len(dataset.cases)}"
        )
    active_ids = {document.metadata.document_id for document in corpus.active_documents}
    missing: dict[str, list[str]] = {}
    for case in dataset.cases:
        unknown = [value for value in case.expected_document_ids if value not in active_ids]
        if unknown:
            missing[case.case_id] = unknown
    if missing:
        raise RagEvaluationError(f"evaluation cases reference missing active documents: {missing}")


def _decode_json_list(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).upper() for item in value}
    try:
        decoded = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(decoded, list):
        return set()
    return {str(item).upper() for item in decoded}


def _hit_matches_filter(hit: KnowledgeSearchHit, filters: KnowledgeSearchFilter) -> bool:
    normalized = filters.normalized()
    metadata = hit.metadata or {}
    if normalized.document_type and hit.document_type.upper() != normalized.document_type:
        return False
    if normalized.status and str(metadata.get("status") or "").upper() != normalized.status:
        return False
    if normalized.language and str(metadata.get("language") or "").upper() != normalized.language:
        return False
    if normalized.product_family:
        values = _decode_json_list(metadata.get("product_families_json"))
        if normalized.product_family not in values:
            return False
    if normalized.material_type:
        values = _decode_json_list(metadata.get("material_types_json"))
        if normalized.material_type not in values:
            return False
    if normalized.tag:
        values = _decode_json_list(metadata.get("tags_json"))
        if normalized.tag not in values:
            return False
    return True


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _category_metrics(
    results: Iterable[RagEvaluationCaseResult],
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[RagEvaluationCaseResult]] = {}
    for result in results:
        groups.setdefault(result.category, []).append(result)
    metrics: dict[str, dict[str, float | int]] = {}
    for category, values in sorted(groups.items()):
        count = len(values)
        metrics[category] = {
            "case_count": count,
            "hit_rate_at_1": sum(value.hit_at_1 for value in values) / count,
            "hit_rate_at_3": sum(value.hit_at_3 for value in values) / count,
            "hit_rate_at_5": sum(value.hit_at_5 for value in values) / count,
            "mean_recall_at_5": sum(value.recall_at_5 for value in values) / count,
            "mrr": sum(value.reciprocal_rank for value in values) / count,
            "latency_p95_ms": _percentile((value.latency_ms for value in values), 0.95),
        }
    return metrics


class RagRetrievalEvaluator:
    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    def evaluate(self, dataset: RagEvaluationDataset) -> RagEvaluationSummary:
        results = tuple(self._evaluate_case(case) for case in dataset.cases)
        case_count = len(results)
        if case_count == 0:
            raise RagEvaluationError("evaluation dataset produced no cases")
        filter_results = [result for result in results if result.filter_applied]

        hit_rate_at_1 = sum(result.hit_at_1 for result in results) / case_count
        hit_rate_at_3 = sum(result.hit_at_3 for result in results) / case_count
        hit_rate_at_5 = sum(result.hit_at_5 for result in results) / case_count
        mean_recall_at_5 = sum(result.recall_at_5 for result in results) / case_count
        mrr = sum(result.reciprocal_rank for result in results) / case_count
        filter_accuracy = (
            sum(result.filter_pass for result in filter_results) / len(filter_results)
            if filter_results
            else 1.0
        )
        latencies = [result.latency_ms for result in results]

        category_metrics = _category_metrics(results)

        gate_checks = {
            "hit_rate_at_5": hit_rate_at_5 >= dataset.gate.hit_rate_at_5_min,
            "mean_recall_at_5": mean_recall_at_5 >= dataset.gate.mean_recall_at_5_min,
            "mrr": mrr >= dataset.gate.mrr_min,
            "filter_accuracy": filter_accuracy >= dataset.gate.filter_accuracy_min,
        }
        return RagEvaluationSummary(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            case_count=case_count,
            filter_case_count=len(filter_results),
            hit_rate_at_1=hit_rate_at_1,
            hit_rate_at_3=hit_rate_at_3,
            hit_rate_at_5=hit_rate_at_5,
            mean_recall_at_5=mean_recall_at_5,
            mrr=mrr,
            filter_accuracy=filter_accuracy,
            miss_rate_at_5=1.0 - hit_rate_at_5,
            latency_p50_ms=_percentile(latencies, 0.50),
            latency_p95_ms=_percentile(latencies, 0.95),
            gate_pass=all(gate_checks.values()),
            gate_checks=gate_checks,
            category_metrics=category_metrics,
            cases=results,
        )

    def _evaluate_case(self, case: RagEvaluationCase) -> RagEvaluationCaseResult:
        started = time.perf_counter()
        response = self.retrieval_service.search(
            case.query,
            top_k=case.top_k,
            filters=case.filters,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        hits = tuple(response.hits)
        retrieved = tuple(hit.document_id for hit in hits)
        expected = set(case.expected_document_ids)
        relevant_ranks = tuple(
            hit.rank for hit in hits if hit.document_id in expected
        )
        hit_at_1 = any(value in expected for value in retrieved[:1])
        hit_at_3 = any(value in expected for value in retrieved[:3])
        hit_at_5 = any(value in expected for value in retrieved[:5])
        retrieved_at_5 = set(retrieved[:5])
        recall_at_5 = len(expected.intersection(retrieved_at_5)) / len(expected)
        reciprocal_rank = 1.0 / min(relevant_ranks) if relevant_ranks else 0.0
        filter_applied = case.filters is not None
        filter_pass = True
        if case.filters is not None:
            filter_pass = bool(hits) and all(
                _hit_matches_filter(hit, case.filters) for hit in hits
            )

        return RagEvaluationCaseResult(
            case_id=case.case_id,
            category=case.category,
            query=case.query,
            expected_document_ids=case.expected_document_ids,
            retrieved_document_ids=retrieved,
            relevant_ranks=relevant_ranks,
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            hit_at_5=hit_at_5,
            recall_at_5=recall_at_5,
            reciprocal_rank=reciprocal_rank,
            filter_applied=filter_applied,
            filter_pass=filter_pass,
            latency_ms=latency_ms,
        )


__all__ = [
    "RagEvaluationCase",
    "RagEvaluationCaseResult",
    "RagEvaluationDataset",
    "RagEvaluationError",
    "RagEvaluationGate",
    "RagEvaluationSummary",
    "RagRetrievalEvaluator",
    "validate_dataset_against_corpus",
]
