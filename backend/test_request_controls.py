from fastapi import FastAPI
from fastapi.testclient import TestClient

from request_controls import RequestControlsMiddleware


def test_authentication_rate_limit_is_enforced_per_client_and_route():
    app = FastAPI()
    app.add_middleware(RequestControlsMiddleware)

    @app.post("/login")
    def login():
        return {"ok": True}

    client = TestClient(app)
    responses = [
        client.post("/login", json={"email": "test@example.invalid"})
        for _ in range(11)
    ]

    assert [response.status_code for response in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429
    assert responses[10].headers["retry-after"].isdigit()
