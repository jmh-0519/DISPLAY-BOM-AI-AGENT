from mcp_server.capabilities.query import (
    get_bom_data,
    list_materials_data,
    list_products_data,
    search_material_data,
    search_product_data,
)


def test_get_bom_data_returns_bom_rows() -> None:
    result = get_bom_data(
        product_id="LTA400HR01-0",
        as_of_date="2026-08-11",
    )

    assert isinstance(
        result,
        list,
    )

    assert len(result) > 0

    first_row = result[0]

    assert (
        first_row["root_model"]
        == "LTA400HR01-0"
    )

    assert "bom_child" in first_row
    assert "bom_path" in first_row
    assert "level" in first_row


def test_get_bom_data_contains_root_model() -> None:
    result = get_bom_data(
        product_id="LTA400HR01-0",
        as_of_date="2026-08-11",
    )

    root_rows = [
        row
        for row in result
        if row["level"] == 1
    ]

    assert len(root_rows) == 1

    assert (
        root_rows[0]["bom_child"]
        == "LTA400HR01-0"
    )

def test_list_products_data_returns_products() -> None:
    result = list_products_data()

    assert isinstance(
        result,
        list,
    )

    assert len(result) > 0

    assert "product_id" in result[0]


def test_search_product_data_returns_matching_product() -> None:
    result = search_product_data(
        "LTA400HR01"
    )

    assert isinstance(
        result,
        list,
    )

    assert len(result) > 0

    assert any(
        "LTA400HR01"
        in str(
            row.get(
                "product_id",
                "",
            )
        )
        for row in result
    )


def test_list_materials_data_returns_materials() -> None:
    result = list_materials_data()

    assert isinstance(
        result,
        list,
    )

    assert len(result) > 0

    assert "material_id" in result[0]


def test_search_material_data_returns_matching_material() -> None:
    result = search_material_data(
        "9000-290004"
    )

    assert isinstance(
        result,
        list,
    )

    assert len(result) > 0

    assert any(
        str(
            row.get(
                "material_id",
                "",
            )
        )
        == "9000-290004"
        for row in result
    )