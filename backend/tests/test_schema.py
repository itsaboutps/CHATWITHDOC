from app.schemas.base import Answer, SummarizeResponse


def test_answer_schema():
    a = Answer(answer="test", answer_type="factual", sources=["doc1"])
    assert a.answer == "test"

def test_summary_schema():
    s = SummarizeResponse(answer="summary", answer_type="summarization", sources=[])
    assert s.answer_type == "summarization"
