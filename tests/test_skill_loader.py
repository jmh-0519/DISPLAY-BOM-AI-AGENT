from pathlib import Path

import pytest

from core.skill_loader import SkillLoader


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


def test_load_bom_query_skill() -> None:
    loader = SkillLoader(
        PROJECT_ROOT / "skills"
    )

    content = loader.load(
        "bom-query"
    )

    assert "# BOM Query Skill" in content
    assert "get_bom" in content
    assert "search_product" in content
    assert "search_material" in content


def test_load_bom_design_change_skill() -> None:
    loader = SkillLoader(
        PROJECT_ROOT / "skills"
    )

    content = loader.load(
        "bom-design-change"
    )

    assert "# BOM Design Change Skill" in content
    assert "analyze_design_change_candidates" in content
    assert "FAIL" in content
    assert "Production BOM" in content


def test_load_many_skills_in_order() -> None:
    loader = SkillLoader(
        PROJECT_ROOT / "skills"
    )

    content = loader.load_many(
        [
            "bom-query",
            "bom-design-change",
        ]
    )

    query_position = content.index(
        "# BOM Query Skill"
    )
    design_change_position = content.index(
        "# BOM Design Change Skill"
    )

    assert query_position < design_change_position
    assert "\n\n---\n\n" in content


@pytest.mark.parametrize(
    "skill_names",
    [
        [],
        ["bom-query", ""],
        ["bom-query", "   "],
    ],
)
def test_load_many_rejects_invalid_names(
    skill_names: list[str],
) -> None:
    loader = SkillLoader(
        PROJECT_ROOT / "skills"
    )

    with pytest.raises(ValueError):
        loader.load_many(skill_names)


def test_load_unknown_skill_raises_error(
    tmp_path: Path,
) -> None:
    loader = SkillLoader(
        tmp_path
    )

    with pytest.raises(
        FileNotFoundError
    ):
        loader.load(
            "unknown-skill"
        )


def test_load_empty_skill_raises_error(
    tmp_path: Path,
) -> None:
    skill_dir = (
        tmp_path
        / "empty-skill"
    )

    skill_dir.mkdir()

    skill_file = (
        skill_dir
        / "SKILL.md"
    )

    skill_file.write_text(
        "",
        encoding="utf-8",
    )

    loader = SkillLoader(
        tmp_path
    )

    with pytest.raises(
        ValueError
    ):
        loader.load(
            "empty-skill"
        )
