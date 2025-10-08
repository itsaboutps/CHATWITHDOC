from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_out_of_scope_empty_index():
    r = client.post("/ask", json={"question": "What is the capital of France?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer_type"] == "out_of_scope"