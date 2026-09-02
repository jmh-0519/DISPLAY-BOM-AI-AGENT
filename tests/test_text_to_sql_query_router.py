from text_to_sql.query_router import TextToSqlQueryRouter


ROUTER = TextToSqlQueryRouter()


def test_r1_analytics_questions_are_high_confidence_text_to_sql():
    questions = (
        "활성 자재를 자재 그룹별로 몇 개씩 가지고 있는지 많은 순서대로 알려줘.",
        "현재 활성 자재는 전체 몇 개인지 알려줘.",
        "자재 단위별 등록 자재 수를 많은 순서대로 보여줘.",
        "ASSY를 공정명별로 몇 개씩 등록했는지 알려줘.",
        "ASSY의 COMMON과 DEDICATED 사용 유형별 개수를 알려줘.",
        "공급사 등급별 공급사 수를 알려줘.",
        "품질 점수가 높은 공급사 상위 5개를 보여줘.",
        "공급사별 평균 자재 단가를 낮은 순서대로 알려줘.",
        "공급사별 평균 납기를 짧은 순서대로 알려줘.",
        "공급 상태별 공급사-자재 관계 등록 건수를 알려줘.",
        "단가가 가장 높은 공급사 자재 5건의 자재코드와 공급사코드, 단가를 보여줘.",
        "PLANT별 생산계획 수량 합계를 많은 순서대로 알려줘.",
        "제품 버전별 생산계획 수량 합계를 많은 순서대로 알려줘.",
        "PLANT별 BOM 구성 행 수를 많은 순서대로 알려줘.",
        "PLANT별 BOM 수량 합계를 많은 순서대로 알려줘.",
    )
    for question in questions:
        decision = ROUTER.route(question)
        assert decision.eligible is True, (question, decision)


def test_known_structured_and_workflow_queries_do_not_enter_text_to_sql():
    questions = (
        "LTA400HR01-001 P01 BOM 보여줘",
        "P01에서 0001-310901 포함한 모델 알려줘",
        "현재 SEALANT 수량이 몇이야?",
        "단종 자재 교체 기준이 뭐야?",
        "LTA400HR01-001 P01 DRIVE-IC 교체해줘",
        "LTA400HR01-001 P01 DRIVE-IC 대체 후보 추천해줘",
        "설계변경 승인 이력을 보여줘",
        "안녕하세요",
    )
    for question in questions:
        assert ROUTER.route(question).eligible is False, question


def test_plain_detail_or_search_wording_without_analytics_signal_stays_out():
    assert ROUTER.route("DRIVE-IC 자재 찾아줘").eligible is False
    assert ROUTER.route("등록된 공급사 보여줘").eligible is False
    assert ROUTER.route("LTA400HR01-001 제품 정보 알려줘").eligible is False
