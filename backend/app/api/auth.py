"""HTTP Basic Auth на всю платформу — данные закрытые (реальные продажи/остатки).

Тот же принцип, что был в `projects/stock-monitor/app.py::requires_auth`: если
DASHBOARD_USER/DASHBOARD_PASSWORD не заданы — доступ открыт (удобно для локальной
разработки), если заданы — обязательны на каждый запрос. Сравнение через
`secrets.compare_digest`, чтобы не утекало время сравнения (тайминг-атака на пароль).
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import get_settings

security = HTTPBasic(auto_error=False)


def require_dashboard_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    settings = get_settings()
    if not settings.dashboard_user or not settings.dashboard_password:
        return  # пароль не настроен — открытый доступ (см. docstring модуля)

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Нужен пароль.",
            headers={"WWW-Authenticate": "Basic"},
        )

    user_ok = secrets.compare_digest(credentials.username, settings.dashboard_user)
    password_ok = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль.",
            headers={"WWW-Authenticate": "Basic"},
        )
