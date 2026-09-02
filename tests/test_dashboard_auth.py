import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app.api import auth as auth_module
from app.core.config import Settings


def test_open_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(dashboard_user=None, dashboard_password=None),
    )
    # Не должно бросать исключение — пароль не настроен, доступ открыт.
    auth_module.require_dashboard_auth(credentials=None)


def test_rejects_missing_credentials_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(dashboard_user="leto", dashboard_password="secret"),
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_module.require_dashboard_auth(credentials=None)
    assert exc_info.value.status_code == 401


def test_rejects_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(dashboard_user="leto", dashboard_password="secret"),
    )
    with pytest.raises(HTTPException) as exc_info:
        auth_module.require_dashboard_auth(
            credentials=HTTPBasicCredentials(username="leto", password="wrong")
        )
    assert exc_info.value.status_code == 401


def test_accepts_correct_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: Settings(dashboard_user="leto", dashboard_password="secret"),
    )
    # Не должно бросать исключение.
    auth_module.require_dashboard_auth(
        credentials=HTTPBasicCredentials(username="leto", password="secret")
    )
