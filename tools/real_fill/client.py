from __future__ import annotations


class FillClient:
    def __init__(self, client):
        self._client = client
        self._token: str | None = None
        self.last_login_status: int | None = None

    def login(self, username: str, password: str) -> None:
        response = self._client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        self.last_login_status = response.status_code
        if response.status_code != 200:
            raise AssertionError(response.text)
        self._token = response.json()["access_token"]

    def request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        if self._token:
            headers.setdefault("Authorization", f"Bearer {self._token}")
        return self._client.request(method, path, headers=headers, **kwargs)
