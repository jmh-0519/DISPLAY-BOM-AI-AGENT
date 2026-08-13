from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


class QueryNormalizer:
    """
    사용자 자연어 검색어를 BOM 도메인의 표준 표현으로 정규화합니다.

    역할:
    - 대소문자 통일
    - 불필요한 공백 정리
    - 숫자+단위 표현 정규화
    - Alias / Synonym 치환
    - 검색용 Token 생성
    - 검색 점수 계산 지원
    """

    def __init__(
        self,
        alias_file: str | Path,
    ) -> None:
        self.alias_file = Path(alias_file)
        self.aliases = self._load_aliases()

    def _load_aliases(
        self,
    ) -> list[tuple[str, str]]:
        if not self.alias_file.exists():
            raise FileNotFoundError(
                f"Alias 파일을 찾을 수 없습니다: {self.alias_file}"
            )

        data = pd.read_csv(
            self.alias_file,
            encoding="utf-8-sig",
        )

        required_columns = {
            "alias",
            "normalized_value",
            "alias_type",
            "active_yn",
        }

        missing_columns = required_columns - set(data.columns)

        if missing_columns:
            raise ValueError(
                "Alias 파일에 필수 컬럼이 없습니다: "
                + ", ".join(sorted(missing_columns))
            )

        active = data[
            data["active_yn"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("Y")
        ]

        result: list[tuple[str, str]] = []

        for _, row in active.iterrows():
            alias = str(row["alias"]).strip()
            normalized = str(row["normalized_value"]).strip()

            if alias and normalized:
                result.append((alias, normalized))

        # 긴 표현을 먼저 치환
        result.sort(
            key=lambda item: len(item[0]),
            reverse=True,
        )

        return result

    @staticmethod
    def _normalize_spacing(
        text: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    @staticmethod
    def _normalize_common_units(
        text: str,
    ) -> str:
        """
        숫자와 결합된 단위를 우선 정규화합니다.

        예:
        40인치    -> 40IN
        40 inch   -> 40IN
        40 inches -> 40IN
        40IN      -> 40IN

        60Hz      -> 60HZ
        60 hz     -> 60HZ
        60헤르츠   -> 60HZ
        """

        # inch 계열
        text = re.sub(
            r"(\d+(?:\.\d+)?)\s*(?:인치|INCHES|INCH|IN)",
            r"\1IN",
            text,
            flags=re.IGNORECASE,
        )

        # Hz 계열
        text = re.sub(
            r"(\d+(?:\.\d+)?)\s*(?:HZ|헤르츠)",
            r"\1HZ",
            text,
            flags=re.IGNORECASE,
        )

        return text

    def normalize(
        self,
        query: str,
    ) -> str:
        if (
            not isinstance(query, str)
            or not query.strip()
        ):
            raise ValueError(
                "query는 비어 있지 않은 문자열이어야 합니다."
            )

        normalized = self._normalize_common_units(
            query.strip()
        )

        for alias, replacement in self.aliases:
            normalized = re.sub(
                re.escape(alias),
                replacement,
                normalized,
                flags=re.IGNORECASE,
            )

        normalized = normalized.upper()

        normalized = re.sub(
            r"[^0-9A-Z가-힣\-]+",
            " ",
            normalized,
        )

        return self._normalize_spacing(
            normalized
        )

    def tokenize(
        self,
        query: str,
    ) -> list[str]:
        return [
            token
            for token in self.normalize(query).split(" ")
            if token
        ]

    def match_score(
        self,
        query: str,
        *candidate_values: object,
    ) -> int:
        """
        Query와 Candidate 간 검색 점수를 계산합니다.

        우선순위:
        1. 전체 Exact Match
        2. 정규화 문자열 전체 포함
        3. 모든 Query Token 포함
        4. 일부 Token 포함
        """

        normalized_query = (
            self.normalize(
                query
            )
        )

        candidate_text = " ".join(
            ""
            if value is None
            else str(value)
            for value in candidate_values
        )

        normalized_candidate = (
            self.normalize(
                candidate_text
            )
        )

        # --------------------------------------
        # 1. 전체 Exact Match
        # --------------------------------------

        if (
            normalized_query
            == normalized_candidate
        ):
            return 1000

        # --------------------------------------
        # 2. Query 전체 문자열 포함
        #
        # 예:
        # LTA400HR01
        #   in
        # LTA400HR01-0 40IN FHD ...
        #
        # LC SEALANT
        #   in
        # 9000-290004 LC SEALANT
        # --------------------------------------

        if (
            normalized_query
            in normalized_candidate
        ):
            return 800

        # --------------------------------------
        # 3. Token Match
        # --------------------------------------

        query_tokens = (
            self.tokenize(
                query
            )
        )

        candidate_tokens = set(
            self.tokenize(
                candidate_text
            )
        )

        if not query_tokens:
            return 0

        matched_count = sum(
            1
            for token in query_tokens
            if token in candidate_tokens
        )

        # 모든 Token 일치
        if (
            matched_count
            == len(query_tokens)
        ):
            return (
                500
                + matched_count
            )

        # 일부 Token 일치
        return (
            matched_count
            * 10
        )
