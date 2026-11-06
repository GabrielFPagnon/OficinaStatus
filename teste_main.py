from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_status_api():
    # Testa se a documentação do FastAPI está a responder corretamente
    response = client.get("/docs")
    assert response.status_code == 200