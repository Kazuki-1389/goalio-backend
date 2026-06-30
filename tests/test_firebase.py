from app.core import firebase


def test_render_secret_file_path_is_used(monkeypatch):
    secret_path = "/etc/secrets/firebase-service-account.json"
    sentinel = object()
    received_paths: list[str] = []

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", secret_path)
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(
        firebase.credentials,
        "Certificate",
        lambda path: received_paths.append(path) or sentinel,
    )

    assert firebase._load_credential() is sentinel
    assert received_paths == [secret_path]
