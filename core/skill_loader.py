from pathlib import Path


class SkillLoader:
    """
    Agent Skill 파일을 로드합니다.
    """

    def __init__(
        self,
        skills_root: Path,
    ) -> None:
        self.skills_root = skills_root

    def load(
        self,
        skill_name: str,
    ) -> str:
        """
        지정한 Skill의 SKILL.md를 읽어 반환합니다.
        """

        skill_path = (
            self.skills_root
            / skill_name
            / "SKILL.md"
        )

        if not skill_path.exists():
            raise FileNotFoundError(
                f"Skill을 찾을 수 없습니다: "
                f"{skill_name}"
            )

        content = skill_path.read_text(
            encoding="utf-8"
        )

        if not content.strip():
            raise ValueError(
                f"Skill 내용이 비어 있습니다: "
                f"{skill_name}"
            )

        return content

    def load_many(
        self,
        skill_names: list[str],
    ) -> str:
        """
        여러 Skill을 지정한 순서대로 로드하여
        하나의 Agent Context로 결합합니다.
        """

        if (
            not isinstance(skill_names, list)
            or not skill_names
        ):
            raise ValueError(
                "skill_names는 하나 이상의 "
                "Skill 이름을 포함해야 합니다."
            )

        loaded_skills: list[str] = []

        for skill_name in skill_names:
            if (
                not isinstance(skill_name, str)
                or not skill_name.strip()
            ):
                raise ValueError(
                    "Skill 이름은 비어 있지 않은 "
                    "문자열이어야 합니다."
                )

            loaded_skills.append(
                self.load(skill_name.strip()).strip()
            )

        return "\n\n---\n\n".join(
            loaded_skills
        )
