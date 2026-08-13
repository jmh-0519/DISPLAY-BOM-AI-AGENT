from services.bom_service import BomService


TEST_DATE = "2026-08-10"


def create_service() -> BomService:
    """
    테스트에서 공통으로 사용할
    BomService 인스턴스를 생성합니다.
    """

    return BomService()


def test_get_product() -> None:
    """
    제품 ID로 제품 정보를 조회할 수 있어야 합니다.
    """

    service = create_service()

    result = service.get_product(
        "LTA400HR01-0"
    )

    assert result is not None
    assert (
        result["product_id"]
        == "LTA400HR01-0"
    )


def test_get_product_returns_none_when_not_found() -> None:
    """
    존재하지 않는 제품을 조회하면
    None을 반환해야 합니다.
    """

    service = create_service()

    result = service.get_product(
        "UNKNOWN-MODEL"
    )

    assert result is None


def test_search_product() -> None:
    """
    제품 ID 또는 제품명으로 검색할 수 있어야 합니다.
    """

    service = create_service()

    result = service.search_product(
        "LTA400"
    )

    assert not result.empty

    product_ids = set(
        result["product_id"]
        .astype(str)
        .tolist()
    )

    assert "LTA400HR01-0" in product_ids
    assert "LTA400HR02-0" in product_ids


def test_list_products() -> None:
    """
    전체 제품 목록을 조회할 수 있어야 합니다.
    """

    service = create_service()

    result = service.list_products()

    assert not result.empty
    assert "product_id" in result.columns
    assert "product_name" in result.columns


def test_search_material() -> None:
    """
    자재 ID 또는 자재명으로 검색할 수 있어야 합니다.
    """

    service = create_service()

    result = service.search_material(
        "LJ94-100001"
    )

    assert not result.empty

    material_ids = set(
        result["material_id"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-100001" in material_ids


def test_list_materials() -> None:
    """
    전체 자재 목록을 조회할 수 있어야 합니다.
    """

    service = create_service()

    result = service.list_materials()

    assert not result.empty
    assert "material_id" in result.columns
    assert "material_name" in result.columns


def test_get_bom_returns_direct_children() -> None:
    """
    get_bom()은 해당 Parent의
    직계 하위 BOM만 반환해야 합니다.
    """

    service = create_service()

    result = service.get_bom(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    assert not result.empty

    child_ids = set(
        result["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LTA400HR01-001" in child_ids

    # 직계 하위가 아닌 OLB는 포함되면 안 됩니다.
    assert "LJ94-100001" not in child_ids


def test_get_bom_returns_children_in_sequence_order() -> None:
    """
    동일 Parent의 Child는
    sequence_no 순서로 반환되어야 합니다.
    """

    service = create_service()

    result = service.get_bom(
        "LJ94-100001",
        as_of_date=TEST_DATE,
    )

    assert not result.empty

    sequence_numbers = (
        result["sequence_no"]
        .astype(int)
        .tolist()
    )

    assert sequence_numbers == sorted(
        sequence_numbers
    )


def test_get_bom_contains_quantity() -> None:
    """
    BOM 관계에는 직접 소요수량 quantity가
    포함되어야 합니다.
    """

    service = create_service()

    result = service.get_bom(
        "LJ94-100001",
        as_of_date=TEST_DATE,
    )

    driver_ic = result[
        result["bom_child"]
        == "0001-200003"
    ].iloc[0]

    assert driver_ic["quantity"] == 6


def test_get_bom_explosion_returns_all_levels() -> None:
    """
    지정 모델의 전체 하위 BOM을
    최하위까지 조회할 수 있어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    assert not result.empty

    child_ids = set(
        result["bom_child"]
        .astype(str)
        .tolist()
    )

    # MODEL
    assert "LTA400HR01-0" in child_ids

    # FA
    assert "LTA400HR01-001" in child_ids

    # OLB
    assert "LJ94-100001" in child_ids

    # TFT
    assert "LJ94-100006" in child_ids

    # OLB 하위 Component
    assert "0001-200003" in child_ids

    # TFT 하위 Component
    assert "0001-200014" in child_ids


def test_get_bom_explosion_calculates_levels() -> None:
    """
    BOM Level은 CSV에 저장하지 않고
    Explosion 조회 시 동적으로 계산해야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    model_row = result[
        result["bom_child"]
        == "LTA400HR01-0"
    ].iloc[0]

    fa_row = result[
        result["bom_child"]
        == "LTA400HR01-001"
    ].iloc[0]

    olb_row = result[
        result["bom_child"]
        == "LJ94-100001"
    ].iloc[0]

    cp_row = result[
        result["bom_child"]
        == "LJ94-100002"
    ].iloc[0]

    tft_row = result[
        result["bom_child"]
        == "LJ94-100006"
    ].iloc[0]

    assert model_row["level"] == 1
    assert fa_row["level"] == 2
    assert olb_row["level"] == 3
    assert cp_row["level"] == 4
    assert tft_row["level"] == 8


def test_get_bom_explosion_calculates_root_model() -> None:
    """
    Explosion 결과의 모든 행은
    조회 기준 Root Model을 가져야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    assert (
        result["root_model"]
        .astype(str)
        .eq("LTA400HR01-0")
        .all()
    )


def test_get_bom_explosion_calculates_bom_path() -> None:
    """
    BOM Path가 Root Model부터
    현재 Child까지 생성되어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    tft_row = result[
        result["bom_child"]
        == "LJ94-100006"
    ].iloc[0]

    path = str(
        tft_row["bom_path"]
    )

    assert path.startswith(
        "LTA400HR01-0"
    )

    assert "LTA400HR01-001" in path
    assert "LJ94-100001" in path
    assert "LJ94-100006" in path


def test_get_bom_explosion_calculates_required_quantity() -> None:
    """
    required_quantity는 Root Model 기준
    누적 소요수량이어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    driver_ic = result[
        result["bom_child"]
        == "0001-200003"
    ].iloc[0]

    # 현재 샘플:
    #
    # MODEL -> MODEL      x1
    # MODEL -> FA         x1
    # FA -> OLB           x1
    # OLB -> DRIVER IC    x6
    #
    # 누적 소요수량 = 6
    assert (
        driver_ic["required_quantity"]
        == 6
    )


def test_get_bom_explosion_preserves_direct_quantity() -> None:
    """
    Explosion 조회를 하더라도 원본 관계의
    quantity 값은 그대로 유지되어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    driver_ic = result[
        result["bom_child"]
        == "0001-200003"
    ].iloc[0]

    assert driver_ic["quantity"] == 6


def test_get_bom_explosion_filters_expired_bom() -> None:
    """
    기준일이 지난 BOM 관계는
    Explosion 결과에서 제외되어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR02-0",
        as_of_date=TEST_DATE,
    )

    child_ids = set(
        result["bom_child"]
        .astype(str)
        .tolist()
    )

    # 2026-06-30에 종료된 과거 CF/TFT
    assert "LJ94-119905" not in child_ids
    assert "LJ94-119906" not in child_ids

    # 현재 유효한 CF/TFT
    assert "LJ94-110005" in child_ids
    assert "LJ94-110006" in child_ids


def test_get_bom_explosion_can_query_historical_bom() -> None:
    """
    과거 기준일로 조회하면 당시 유효했던
    BOM 관계도 조회할 수 있어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR02-0",
        as_of_date="2026-06-15",
    )

    child_ids = set(
        result["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-119905" in child_ids
    assert "LJ94-119906" in child_ids


def test_get_bom_explosion_returns_empty_for_unknown_model() -> None:
    """
    존재하지 않는 Model의 BOM Explosion은
    빈 DataFrame을 반환해야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "UNKNOWN-MODEL",
        as_of_date=TEST_DATE,
    )

    assert result.empty


def test_get_bom_explosion_has_dynamic_columns() -> None:
    """
    Explosion 결과에는 원본 bom.csv에는 없는
    동적 계산 컬럼이 포함되어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    assert "level" in result.columns
    assert "root_model" in result.columns
    assert "bom_path" in result.columns
    assert "required_quantity" in result.columns


def test_get_bom_explosion_keeps_source_columns() -> None:
    """
    Explosion 결과에는 bom.csv의
    원본 관계 컬럼도 그대로 포함되어야 합니다.
    """

    service = create_service()

    result = service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    expected_columns = {
        "bom_parent",
        "bom_parent_name",
        "bom_child",
        "bom_child_name",
        "location",
        "sequence_no",
        "quantity",
        "start_date",
        "end_date",
    }

    assert expected_columns.issubset(
        set(result.columns)
    )

def test_search_product_with_normalized_korean_query():
    service = BomService()

    result = service.search_product(
        "40인치 FHD 60Hz LCD 모델"
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["product_id"]
        == "LTA400HR01-0"
    )


def test_search_material_with_alias_query():
    service = BomService()

    result = service.search_material(
        "LC 실란트"
    )

    assert not result.empty

    assert all(
        result["material_name"]
        .astype(str)
        .str.upper()
        .eq("LC SEALANT")
    )


def test_search_product_exact_id_has_priority():
    service = BomService()

    result = service.search_product(
        "LTA400HR01-0"
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["product_id"]
        == "LTA400HR01-0"
    )


def test_search_material_exact_id_has_priority():
    service = BomService()

    result = service.search_material(
        "9000-290004"
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["material_id"]
        == "9000-290004"
    )    