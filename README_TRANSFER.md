# Alleya Marketplace BI: перенос на другой компьютер

## Что внутри

- FastAPI backend: `backend`
- React/Vite frontend: `frontend`
- базы и рабочие данные: `data`
- юнитки Excel: `uploads`
- скрипты установки и запуска: `scripts`
- VS Code tasks: `.vscode/tasks.json`

## Что нужно установить на новом компьютере

- Python 3.11+
- Node.js 20+
- npm
- VS Code, если нужен запуск через задачи VS Code

## Первый запуск (один файл)

Открой папку проекта в Finder и дважды кликни:

```
Запустить Alleya BI.command
```

Файл сам сделает всё нужное:

- при первом запуске установит зависимости backend и frontend (venv, pip, npm, Playwright Chromium) — это может занять несколько минут;
- при последующих запусках сразу стартует backend и frontend;
- откроет браузер на готовом интерфейсе, как только frontend отдаст ответ.

Если Finder блокирует запуск («неизвестный разработчик») — кликни правой кнопкой → «Открыть», подтверди один раз.

Через терминал то же самое:

```bash
chmod +x "Запустить Alleya BI.command" scripts/*.sh
./"Запустить Alleya BI.command"
```

Чтобы остановить — закрой окно терминала или нажми `Ctrl+C`.

После запуска:

- frontend: http://127.0.0.1:5174
- backend: http://127.0.0.1:8010
- backend docs: http://127.0.0.1:8010/docs

## Запуск через VS Code

1. Открой папку проекта в VS Code.
2. Нажми `Cmd+Shift+P`.
3. Выбери `Tasks: Run Task`.
4. Для первого запуска выбери `Alleya: Setup`.
5. Затем выбери `Alleya: Run All`.

VS Code откроет отдельные терминалы для backend и frontend.

## Переменные окружения

Backend читает настройки из `backend/.env`.

Если в архиве есть `backend/.env`, API-ключи уже лежат внутри пакета. Если его нет, скрипт `setup.sh` создаст `backend/.env` из `backend/.env.example`, и ключи нужно будет заполнить вручную.

Основные ключи:

- `OZON_SELLER_CLIENT_ID`
- `OZON_SELLER_API_KEY`
- `OZON_PERFORMANCE_CLIENT_ID`
- `OZON_PERFORMANCE_CLIENT_SECRET`
- `DELOVYE_LINII_APPKEY`
- `DELOVYE_LINII_SESSION_ID`
- `VOZOVOZ_API_KEY`

## Если порты заняты

По умолчанию используются:

- backend: `8010`
- frontend: `5174`

Закрой старые терминалы или процессы на этих портах и запусти снова.

## Проверка после переноса

```bash
curl -I http://127.0.0.1:8010/docs
```

Frontend должен открыться на http://127.0.0.1:5174.
