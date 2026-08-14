import pytest

from database import SQLiteDatabase
from services.query_normalizer import QueryNormalizer


@pytest.fixture
def normalizer(tmp_path) -> QueryNormalizer:
    import shutil
    target = tmp_path / "display_bom.db"
    shutil.copy2("data/display_bom.db", target)
    return QueryNormalizer(SQLiteDatabase(target))


def test_normalize_product_query(
    normalizer: QueryNormalizer,
) -> None:
    assert normalizer.normalize(
        "40인치 FHD 60Hz LCD 모델"
    ) == "40IN FHD 60HZ LCD MODEL"


def test_normalize_english_product_query(
    normalizer: QueryNormalizer,
) -> None:
    assert normalizer.normalize(
        "40 inch fhd 60 hz lcd model"
    ) == "40IN FHD 60HZ LCD MODEL"


def test_normalize_material_alias(
    normalizer: QueryNormalizer,
) -> None:
    assert normalizer.normalize(
        "LC 실란트"
    ) == "LC SEALANT"


def test_normalize_assembly_alias(
    normalizer: QueryNormalizer,
) -> None:
    assert normalizer.normalize(
        "assy"
    ) == "ASSEMBLY"


def test_tokenize_query(
    normalizer: QueryNormalizer,
) -> None:
    assert normalizer.tokenize(
        "40인치 FHD 60Hz LCD 모델"
    ) == [
        "40IN",
        "FHD",
        "60HZ",
        "LCD",
        "MODEL",
    ]


def test_match_score_all_tokens(
    normalizer: QueryNormalizer,
) -> None:
    score = normalizer.match_score(
        "40인치 FHD 60Hz LCD 모델",
        "40IN FHD 60HZ LCD MODEL",
    )

    assert score >= 500


def test_match_score_partial_tokens(
    normalizer: QueryNormalizer,
) -> None:
    score = normalizer.match_score(
        "40인치 FHD LCD",
        "40IN FHD 60HZ LCD MODEL",
    )

    assert score > 0


def test_empty_query_raises_error(
    normalizer: QueryNormalizer,
) -> None:
    with pytest.raises(
        ValueError
    ):
        normalizer.normalize("")


@pytest.mark.parametrize(
    "query",
    [
        "40인치",
        "40 inch",
        "40 inches",
        "40inch",
        "40in",
        "40IN",
    ],
)
def test_normalize_inch_variations(
    normalizer: QueryNormalizer,
    query: str,
) -> None:
    assert (
        normalizer.normalize(query)
        == "40IN"
    )

@pytest.mark.parametrize(
    "query",
    [
        "60Hz",
        "60 hz",
        "60HZ",
        "60헤르츠",
    ],
)
def test_normalize_hz_variations(
    normalizer: QueryNormalizer,
    query: str,
) -> None:
    assert (
        normalizer.normalize(query)
        == "60HZ"
    )

def test_match_score_partial_product_id(
    normalizer: QueryNormalizer,
) -> None:
    score = normalizer.match_score(
        "LTA400HR01",
        "LTA400HR01-0",
        "40IN FHD 60HZ LCD MODEL",
    )

    assert score >= 800    

def test_match_score_product_id_prefix(
    normalizer: QueryNormalizer,
) -> None:
    score = normalizer.match_score(
        "LTA400",
        "LTA400HR01-0",
        "40IN FHD 60HZ LCD MODEL",
    )

    assert score >= 800
