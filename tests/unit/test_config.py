import pytest

from signal_app.config import Settings


def test_cors_origins_accepts_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, https://signal.example.com",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == (
        "http://localhost:3000",
        "https://signal.example.com",
    )
