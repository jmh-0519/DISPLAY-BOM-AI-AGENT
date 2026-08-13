from app.streamlit_app import sanitize_agent_download_links


def test_sanitize_agent_download_links_when_real_artifact_exists():
    answer = "[보고서 다운로드](sandbox:/mnt/data/report.docx)"
    cleaned = sanitize_agent_download_links(answer, True)
    assert cleaned == "보고서 다운로드"
    assert "sandbox:" not in cleaned


def test_keep_normal_answer_without_artifact():
    answer = "일반 조회 결과입니다."
    assert sanitize_agent_download_links(answer, False) == answer
