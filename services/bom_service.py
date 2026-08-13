from datetime import date
from pathlib import Path

import pandas as pd

from services.query_normalizer import QueryNormalizer

class BomService:
    """
    Display BOM CSV 데이터를 조회하는 Service입니다.

    BOM 원천 데이터는 단순 Parent-Child 구조로 관리합니다.

    저장 컬럼:
    - bom_parent
    - bom_parent_name
    - bom_child
    - bom_child_name
    - location
    - sequence_no
    - quantity
    - start_date
    - end_date

    level, root_model, bom_path, required_quantity는
    BOM 조회 시 동적으로 계산합니다.
    """

    def __init__(
        self,
        data_dir: str = "data",
    ) -> None:
        self.data_dir = Path(data_dir)

        self.query_normalizer = (
            QueryNormalizer(
                self.data_dir
                / "query_aliases.csv"
            )
        )

        self.products = self._load_csv(
            "products.csv"
        )
        self.materials = self._load_csv(
            "materials.csv"
        )
        self.bom = self._load_csv(
            "bom.csv"
        )

        self._prepare_bom_data()

    def _load_csv(
        self,
        file_name: str,
    ) -> pd.DataFrame:
        """
        CSV 파일을 UTF-8 BOM 형식으로 로딩합니다.
        """

        file_path = (
            self.data_dir / file_name
        )

        if not file_path.exists():
            raise FileNotFoundError(
                "데이터 파일을 찾을 수 없습니다: "
                f"{file_path.resolve()}"
            )

        return pd.read_csv(
            file_path,
            encoding="utf-8-sig",
        )

    def _prepare_bom_data(self) -> None:
        """
        BOM 날짜/수량 컬럼을 조회하기 쉬운 형태로 변환합니다.
        """

        self.bom["start_date"] = pd.to_datetime(
            self.bom["start_date"],
            errors="coerce",
        )

        self.bom["end_date"] = pd.to_datetime(
            self.bom["end_date"],
            errors="coerce",
        )

        self.bom["quantity"] = pd.to_numeric(
            self.bom["quantity"],
            errors="coerce",
        ).fillna(1)

        self.bom["sequence_no"] = pd.to_numeric(
            self.bom["sequence_no"],
            errors="coerce",
        ).fillna(0)

    def get_product(
        self,
        product_id: str,
    ) -> dict | None:
        """
        제품 ID로 제품 정보를 조회합니다.
        """

        result = self.products[
            self.products["product_id"]
            .astype(str)
            .str.upper()
            .eq(product_id.upper())
        ]

        if result.empty:
            return None

        return result.iloc[0].to_dict()

    def search_product(
        self,
        keyword: str,
    ) -> pd.DataFrame:
        """
        제품 ID 또는 제품명으로
        제품을 검색합니다.
        """

        return self._rank_search_results(
            data=self.products,
            keyword=keyword,
            id_column="product_id",
            name_column="product_name",
        )

    def list_products(self) -> pd.DataFrame:
        """
        전체 제품 목록을 반환합니다.
        """

        return self.products.copy()

    def search_material(
        self,
        keyword: str,
    ) -> pd.DataFrame:
        """
        자재번호 또는 자재명으로
        자재를 검색합니다.
        """

        return self._rank_search_results(
            data=self.materials,
            keyword=keyword,
            id_column="material_id",
            name_column="material_name",
        )

    def list_materials(self) -> pd.DataFrame:
        """
        전체 자재 목록을 반환합니다.
        """

        return self.materials.copy()

    def _get_effective_bom(
        self,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        지정 기준일에 유효한 BOM 관계만 반환합니다.

        as_of_date가 없으면 오늘 날짜를 사용합니다.
        """

        if as_of_date is None:
            target_date = pd.Timestamp.today().normalize()
        else:
            target_date = pd.Timestamp(
                as_of_date
            ).normalize()

        condition = (
            (
                self.bom["start_date"].isna()
                |
                (
                    self.bom["start_date"]
                    <= target_date
                )
            )
            &
            (
                self.bom["end_date"].isna()
                |
                (
                    self.bom["end_date"]
                    >= target_date
                )
            )
        )

        return self.bom[
            condition
        ].copy()

    def get_bom(
        self,
        parent_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        제품 또는 Assembly의 직계 하위 BOM을 조회합니다.

        Oracle의 Parent-Child 관계 한 단계 조회에 해당합니다.
        """

        effective_bom = (
            self._get_effective_bom(
                as_of_date
            )
        )

        result = effective_bom[
            effective_bom["bom_parent"]
            .astype(str)
            .str.upper()
            .eq(parent_id.upper())
        ].copy()

        if result.empty:
            return result

        result = result.sort_values(
            by="sequence_no"
        ).reset_index(
            drop=True
        )

        return result

    def get_bom_explosion(
        self,
        model_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        지정 모델의 전체 하위 BOM을
        최하위까지 재귀적으로 조회합니다.

        Oracle의 다음 개념과 동일한 역할입니다.

        START WITH bom_parent = 'MODEL'
                   AND bom_child = :model_id

        CONNECT BY PRIOR bom_child = bom_parent

        동적으로 계산하는 값:
        - level
        - root_model
        - bom_path
        - required_quantity

        순환 참조가 존재할 경우
        무한 재귀를 방지합니다.
        """

        effective_bom = (
            self._get_effective_bom(
                as_of_date
            )
        )

        # MODEL -> 실제 모델 관계 확인
        root_rows = effective_bom[
            (
                effective_bom["bom_parent"]
                .astype(str)
                .str.upper()
                .eq("MODEL")
            )
            &
            (
                effective_bom["bom_child"]
                .astype(str)
                .str.upper()
                .eq(model_id.upper())
            )
        ].copy()

        if root_rows.empty:
            return self._empty_explosion_result()

        root_rows = root_rows.sort_values(
            by="sequence_no"
        )

        result_rows: list[dict] = []

        def explode(
            current_parent: str,
            current_level: int,
            parent_path: list[str],
            parent_required_quantity: float,
            path_nodes: set[str],
        ) -> None:
            """
            현재 Parent에서 시작하여
            모든 Child를 재귀적으로 탐색합니다.
            """

            current_parent_upper = (
                current_parent
                .strip()
                .upper()
            )

            if current_parent_upper in path_nodes:
                return

            current_path_nodes = set(
                path_nodes
            )

            current_path_nodes.add(
                current_parent_upper
            )

            children = effective_bom[
                effective_bom["bom_parent"]
                .astype(str)
                .str.upper()
                .eq(current_parent_upper)
            ].copy()

            if children.empty:
                return

            children = children.sort_values(
                by="sequence_no"
            )

            for _, row in children.iterrows():
                child_id = str(
                    row["bom_child"]
                )

                quantity = float(
                    row["quantity"]
                )

                required_quantity = (
                    parent_required_quantity
                    * quantity
                )

                path = (
                    parent_path
                    + [child_id]
                )

                result_row = (
                    row.to_dict()
                )

                result_row["level"] = (
                    current_level
                )

                result_row["root_model"] = (
                    model_id
                )

                result_row["bom_path"] = (
                    "/".join(path)
                )

                result_row[
                    "required_quantity"
                ] = required_quantity

                result_rows.append(
                    result_row
                )

                explode(
                    current_parent=child_id,
                    current_level=(
                        current_level + 1
                    ),
                    parent_path=path,
                    parent_required_quantity=(
                        required_quantity
                    ),
                    path_nodes=(
                        current_path_nodes
                    ),
                )

        #
        # Root MODEL → MODEL_ID 관계도
        # Explosion 결과에 포함합니다.
        #
        for _, root_row in root_rows.iterrows():
            root_quantity = float(
                root_row["quantity"]
            )

            root_result = (
                root_row.to_dict()
            )

            root_result["level"] = 1
            root_result["root_model"] = (
                model_id
            )
            root_result["bom_path"] = (
                model_id
            )
            root_result[
                "required_quantity"
            ] = root_quantity

            result_rows.append(
                root_result
            )

            explode(
                current_parent=model_id,
                current_level=2,
                parent_path=[model_id],
                parent_required_quantity=(
                    root_quantity
                ),
                path_nodes=set(),
            )

        if not result_rows:
            return (
                self._empty_explosion_result()
            )

        return pd.DataFrame(
            result_rows
        )

    def _empty_explosion_result(
        self,
    ) -> pd.DataFrame:
        """
        BOM Explosion 결과가 없을 때
        반환할 빈 DataFrame을 생성합니다.
        """

        columns = list(
            self.bom.columns
        ) + [
            "level",
            "root_model",
            "bom_path",
            "required_quantity",
        ]

        return pd.DataFrame(
            columns=columns
        )

    def _rank_search_results(
        self,
        data: pd.DataFrame,
        keyword: str,
        id_column: str,
        name_column: str,
    ) -> pd.DataFrame:
        """
        정규화된 검색어를 기준으로
        검색 후보를 Ranking합니다.

        우선순위:
        1. ID Exact Match
        2. All Token Match
        3. Partial Token Match
        """

        if (
            not isinstance(keyword, str)
            or not keyword.strip()
        ):
            return pd.DataFrame(
                columns=data.columns
            )

        keyword = keyword.strip()

        # --------------------------------------
        # 1. ID Exact Match
        # --------------------------------------

        exact_id = data[
            data[id_column]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(keyword.upper())
        ].copy()

        if not exact_id.empty:
            return exact_id.reset_index(
                drop=True
            )

        # --------------------------------------
        # 2. Normalized / Token Match
        # --------------------------------------

        scored_rows: list[
            tuple[int, int]
        ] = []

        for index, row in data.iterrows():

            score = (
                self.query_normalizer
                .match_score(
                    keyword,
                    row.get(
                        id_column,
                        "",
                    ),
                    row.get(
                        name_column,
                        "",
                    ),
                )
            )

            if score > 0:
                scored_rows.append(
                    (
                        index,
                        score,
                    )
                )

        if not scored_rows:
            return pd.DataFrame(
                columns=data.columns
            )

        # --------------------------------------
        # 3. All Token Match 우선
        # --------------------------------------

        full_matches = [
            (
                index,
                score,
            )
            for index, score
            in scored_rows
            if score >= 500
        ]

        if full_matches:
            selected_rows = (
                full_matches
            )
        else:
            selected_rows = (
                scored_rows
            )

        # --------------------------------------
        # 4. 점수 내림차순
        # --------------------------------------

        selected_rows.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        indexes = [
            index
            for index, _
            in selected_rows
        ]

        return (
            data
            .loc[indexes]
            .copy()
            .reset_index(
                drop=True
            )
        )    