from html import escape

import pandas as pd
import streamlit as st


def render_bom_result_table(bom: pd.DataFrame) -> None:
    """Agent 채팅과 BOM 조회 메뉴가 공유하는 표준 BOM 결과 표입니다."""
    if bom is None or bom.empty:
        st.info("표시할 BOM 정보가 없습니다.")
        return

    first = bom.iloc[0]
    root_code = _clean_text(first.get("root_code")) or _clean_text(first.get("root_model"))
    root_type = _clean_text(first.get("root_type"))
    title = _clean_text(first.get("bom_title")) or (
        "ASSY BOM" if root_type == "ASSEMBLY" else "제품 BOM"
    )
    st.subheader(title)
    st.markdown(f"**BOM 조회 대상 코드:** `{escape(root_code)}`")

    headers = [
        "PARENT_CODE", "PARENT_NAME", "CHILD_CODE", "CHILD_NAME",
        "LOCATION", "수량", "소요수량",
    ]
    body = []
    for _, row in bom.iterrows():
        child_is_assy = _clean_text(row.get("bom_child_type")) == "ASSEMBLY"
        row_class = ' class="bom-assy-row"' if child_is_assy else ""
        values = [
            escape(_clean_text(row.get("bom_parent"))),
            escape(_clean_text(row.get("bom_parent_name"))),
            escape(_clean_text(row.get("bom_child"))),
            escape(_clean_text(row.get("bom_child_name"))),
            escape(_clean_text(row.get("location"))),
            escape(_format_quantity(row.get("quantity"))),
            escape(_format_quantity(row.get("required_quantity"))),
        ]
        cells = [f"<td>{value}</td>" for value in values]
        body.append(f"<tr{row_class}>" + "".join(cells) + "</tr>")

    st.markdown(
        """
        <style>
        .bom-result-table{width:100%;border-collapse:collapse;font-size:14px}
        .bom-result-table th,.bom-result-table td{padding:7px 9px;border-bottom:1px solid rgba(128,128,128,.22);text-align:left}
        .bom-result-table th{color:#6b7280;font-size:12px}
        .bom-result-table .bom-assy-row td{color:#1677d2;font-weight:700}
        </style>
        """ + '<table class="bom-result-table"><thead><tr>'
        + "".join(f"<th>{header}</th>" for header in headers)
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>",
        unsafe_allow_html=True,
    )


def _clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _format_quantity(value) -> str:
    if pd.isna(value):
        return ""

    try:
        number = float(value)

        if number.is_integer():
            return str(int(number))

        return str(number)

    except (TypeError, ValueError):
        return str(value)


def _sort_children(nodes: list[dict]) -> None:
    """
    동일 Parent의 직속 Child끼리만 정렬합니다.

    정렬 기준:
    1. 일반 자재
    2. Assembly
    3. 같은 종류에서는 자재코드 오름차순
    """

    def sort_key(node: dict) -> tuple:
        is_assembly = bool(
            node.get("children")
        )

        material_id = (
            str(
                node.get(
                    "material_id",
                    "",
                )
            )
            .strip()
            .upper()
        )

        return (
            1 if is_assembly else 0,
            material_id,
        )

    nodes.sort(
        key=sort_key
    )

    for node in nodes:
        children = node.get(
            "children",
            [],
        )

        if children:
            _sort_children(
                children
            )


def _build_bom_tree_data(
    bom: pd.DataFrame,
) -> list[dict]:
    """
    bom_path 기준으로 BOM을 Parent/Child Tree 구조로 변환합니다.
    """

    if bom is None or bom.empty:
        return []

    nodes: dict[str, dict] = {}

    for _, row in bom.iterrows():
        path = _clean_text(
            row.get("bom_path")
        )

        material_id = _clean_text(
            row.get("bom_child")
        )

        if not path or not material_id:
            continue

        nodes[path] = {
            "path": path,
            "material_id": material_id,
            "material_name": _clean_text(
                row.get(
                    "bom_child_name"
                )
            ),
            "location": _clean_text(
                row.get("location")
            ),
            "quantity": row.get(
                "quantity"
            ),
            "required_quantity": row.get(
                "required_quantity"
            ),
            "children": [],
        }

    roots: list[dict] = []

    for path, node in nodes.items():
        if "/" not in path:
            roots.append(node)
            continue

        parent_path = (
            path.rsplit("/", 1)[0]
        )

        parent = nodes.get(
            parent_path
        )

        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(
                node
            )

    # Root 순서는 보존하고 각 Root의 Child만 정렬
    for root in roots:
        children = root.get(
            "children",
            [],
        )

        if children:
            _sort_children(
                children
            )

    return roots


def _render_node_html(
    node: dict,
    depth: int = 0,
    is_last_child: bool = True,
    ancestor_last_flags: list[bool] | None = None,
    is_root: bool = False,
) -> str:
    """
    BOM Node를 HTML로 변환합니다.

    표현 규칙:
    - Parent / Assembly: 접기/펼치기 화살표
    - 일반 자재: ├─ / └─
    - 마지막 Child는 └─
    - 조상 Parent가 계속 이어지는 구간에는 세로선 표시
    - Parent 자재코드: 파란색 + Bold
    - Parent 자재명: Bold
    """

    if ancestor_last_flags is None:
        ancestor_last_flags = []

    material_id = escape(
        node.get(
            "material_id",
            "",
        )
    )

    material_name = escape(
        node.get(
            "material_name",
            "",
        )
    )

    location = escape(
        node.get(
            "location",
            "",
        )
    )

    quantity = escape(
        _format_quantity(
            node.get(
                "quantity"
            )
        )
    )

    children = node.get(
        "children",
        [],
    )

    is_parent = bool(children)

    # --------------------------------------
    # Tree prefix 구성
    # --------------------------------------

    prefix_parts = []

    # 상위 Level의 세로 연결선
    for ancestor_is_last in ancestor_last_flags:
        if ancestor_is_last:
            prefix_parts.append(
                '<span class="tree-gap"></span>'
            )
        else:
            prefix_parts.append(
                '<span class="tree-vertical"></span>'
            )

    # 현재 노드 연결부
    if is_root:
        current_branch = (
            '<span class="tree-root-space"></span>'
        )

    elif is_parent:
        # Parent는 화살표가 branch 역할
        current_branch = (
            '<span class="tree-parent-branch"></span>'
        )

    elif is_last_child:
        current_branch = (
            '<span class="tree-last-branch"></span>'
        )

    else:
        current_branch = (
            '<span class="tree-mid-branch"></span>'
        )

    tree_prefix = (
        '<span class="tree-prefix">'
        + "".join(prefix_parts)
        + current_branch
        + '</span>'
    )

    code_html = (
        '<span class="bom-code">'
        f'{tree_prefix}'
        f'<span class="bom-code-text">{material_id}</span>'
        '</span>'
    )

    row_html = (
        f'{code_html}'
        '<span class="bom-name">'
        f'{material_name}'
        '</span>'
        '<span class="bom-location">'
        f'{location}'
        '</span>'
        '<span class="bom-quantity">'
        f'{quantity}'
        '</span>'
    )

    # --------------------------------------
    # Parent / Assembly
    # --------------------------------------

    if is_parent:
        child_html_parts = []

        total_children = len(children)

        for index, child in enumerate(
            children
        ):
            child_is_last = (
                index
                == total_children - 1
            )

            child_html_parts.append(
                _render_node_html(
                    child,
                    depth=depth + 1,
                    is_last_child=(
                        child_is_last
                    ),
                    ancestor_last_flags=(
                        ancestor_last_flags
                        + (
                            []
                            if is_root
                            else [
                                is_last_child
                            ]
                        )
                    ),
                    is_root=False,
                )
            )

        child_html = "".join(
            child_html_parts
        )

        open_attribute = (
            " open"
            if depth <= 1
            else ""
        )

        root_class = (
            " bom-root"
            if is_root
            else ""
        )

        return (
            f'<li class="bom-node bom-parent{root_class}">'
            f'<details{open_attribute}>'
            '<summary class="bom-tree-row">'
            f'{row_html}'
            '</summary>'
            '<ul class="bom-tree-children">'
            f'{child_html}'
            '</ul>'
            '</details>'
            '</li>'
        )

    # --------------------------------------
    # Leaf / 일반 자재
    # --------------------------------------

    return (
        '<li class="bom-node bom-leaf">'
        '<div class="bom-tree-row">'
        f'{row_html}'
        '</div>'
        '</li>'
    )


def render_bom_expandable_tree(
    bom: pd.DataFrame,
    title: str | None = None,
) -> None:
    """
    BOM을 접기/펼치기 가능한 Tree View로 표시합니다.

    UI 규칙:
    - Parent/Child 관계를 Tree 선으로 표현
    - Parent는 접기/펼치기 화살표
    - 일반 자재는 ├─ / └─ 형태
    - 마지막 Child는 └─
    - 자재코드 영역에만 Tree/들여쓰기 적용
    - 자재명/구분/수량은 고정 컬럼 정렬
    - Parent 자재코드: 파란색 + Bold
    - Parent 자재명: Bold
    - 동일 Parent의 Child만 정렬
    - 일반 자재 > Assembly > 자재코드 오름차순
    """

    if title:
        st.subheader(
            title
        )

    if bom is None or bom.empty:
        st.info(
            "표시할 BOM 정보가 없습니다."
        )
        return

    roots = _build_bom_tree_data(
        bom
    )

    if not roots:
        st.info(
            "BOM 계층 구조를 생성할 수 없습니다."
        )
        return

    tree_html_parts = []

    total_roots = len(
        roots
    )

    for index, root in enumerate(
        roots
    ):
        tree_html_parts.append(
            _render_node_html(
                root,
                depth=0,
                is_last_child=(
                    index
                    == total_roots - 1
                ),
                ancestor_last_flags=[],
                is_root=True,
            )
        )

    tree_html = "".join(
        tree_html_parts
    )

    html = (
        """
        <style>
        .bom-tree-wrap {
            --tree-step: 24px;
            --tree-line-color:
                rgba(107, 114, 128, 0.60);

            width: 100%;
            font-size: 14px;
        }

        .bom-tree-header,
        .bom-tree-row {
            display: grid;

            grid-template-columns:
                minmax(340px, 2.9fr)
                minmax(240px, 2fr)
                minmax(110px, 0.9fr)
                70px;

            column-gap: 16px;
            align-items: center;
        }

        .bom-tree-header {
            min-height: 34px;
            padding: 6px 10px 6px 8px;

            color: #6b7280;

            font-size: 12px;
            font-weight: 600;

            border-bottom:
                1px solid
                rgba(128, 128, 128, 0.25);
        }

        .bom-tree {
            margin: 0;
            padding: 0;

            list-style: none;
        }

        .bom-tree ul {
            margin: 0;
            padding: 0;

            list-style: none;
        }

        .bom-node {
            margin: 0;
            padding: 0;
        }

        .bom-tree-row {
            box-sizing: border-box;

            min-height: 34px;

            padding:
                4px 10px
                4px 8px;

            background: transparent;
        }

        .bom-tree-row:hover {
            background:
                rgba(128, 128, 128, 0.07);

            border-radius: 5px;
        }

        details {
            margin: 0;
            padding: 0;

            border: none;
            background: transparent;
        }

        /*
         * 브라우저 기본 marker는 유지합니다.
         * Parent Assembly의 ▼ / ▶ 역할을 합니다.
         */
        summary {
            cursor: pointer;
        }

        /*
         * Tree prefix는 자재코드 컬럼 안에서만 동작
         */
        .bom-code {
            display: flex;
            align-items: center;

            min-width: 0;

            overflow: hidden;

            white-space: nowrap;
        }

        .tree-prefix {
            display: inline-flex;
            align-items: stretch;

            height: 34px;

            flex-shrink: 0;
        }

        .tree-gap,
        .tree-vertical,
        .tree-root-space,
        .tree-parent-branch,
        .tree-mid-branch,
        .tree-last-branch {
            position: relative;

            display: inline-block;

            width: var(--tree-step);
            height: 34px;

            box-sizing: border-box;
        }

        /*
         * 상위 형제가 계속 이어지는 Level의 세로선
         */
        .tree-vertical::before {
            content: "";

            position: absolute;

            left: 11px;
            top: 0;
            bottom: 0;

            border-left:
                1px solid
                var(--tree-line-color);
        }

        /*
         * 일반 자재 - 중간 형제: ├─
         */
        .tree-mid-branch::before {
            content: "";

            position: absolute;

            left: 11px;
            top: 0;
            bottom: 0;

            border-left:
                1px solid
                var(--tree-line-color);
        }

        .tree-mid-branch::after {
            content: "";

            position: absolute;

            left: 11px;
            top: 17px;

            width: 13px;

            border-top:
                1px solid
                var(--tree-line-color);
        }

        /*
         * 일반 자재 - 마지막 형제: └─
         */
        .tree-last-branch::before {
            content: "";

            position: absolute;

            left: 11px;
            top: 0;
            height: 17px;

            border-left:
                1px solid
                var(--tree-line-color);
        }

        .tree-last-branch::after {
            content: "";

            position: absolute;

            left: 11px;
            top: 17px;

            width: 13px;

            border-top:
                1px solid
                var(--tree-line-color);
        }

        /*
         * Parent는 자체 화살표가 있으므로
         * 현재 Level에서는 짧은 연결 공간만 확보
         */
        .tree-parent-branch {
            width: 14px;
        }

        .tree-root-space {
            width: 4px;
        }

        /*
         * Parent / Assembly
         */
        .bom-parent > details > summary .bom-code-text {
            color: #2563eb;
            font-weight: 700;
        }

        .bom-parent > details > summary .bom-name {
            font-weight: 700;
        }

        /*
         * 일반 자재
         */
        .bom-leaf .bom-code-text {
            color: inherit;
            font-weight: 400;
        }

        .bom-leaf .bom-name {
            font-weight: 400;
        }

        .bom-code-text {
            min-width: 0;

            overflow: hidden;
            text-overflow: ellipsis;

            white-space: nowrap;
        }

        .bom-name,
        .bom-location,
        .bom-quantity {
            min-width: 0;

            overflow: hidden;
            text-overflow: ellipsis;

            white-space: nowrap;

            text-align: right;
        }

        .bom-name {
            color: #4b5563;
        }

        .bom-location {
            color: #6b7280;
        }

        .bom-quantity {
            font-variant-numeric:
                tabular-nums;

            font-weight: 500;
        }

        @media (prefers-color-scheme: dark) {
            .bom-tree-wrap {
                --tree-line-color:
                    rgba(
                        209,
                        213,
                        219,
                        0.55
                    );
            }

            .bom-name {
                color: #d1d5db;
            }

            .bom-location {
                color: #9ca3af;
            }

            .bom-parent > details > summary .bom-code-text {
                color: #60a5fa;
            }
        }
        </style>
        """
        '<div class="bom-tree-wrap">'
        '<div class="bom-tree-header">'
        '<span>자재코드</span>'
        '<span style="text-align:right;">자재명</span>'
        '<span style="text-align:right;">구분</span>'
        '<span style="text-align:right;">수량</span>'
        '</div>'
        '<ul class="bom-tree">'
        f'{tree_html}'
        '</ul>'
        '</div>'
    )

    st.html(
        html
    )
