# Leto SM Dashboard

Платформа управления маркетплейсом «Лето СМ» (Ozon FBS + Центр СМ).  
Симбиоз Alleya BI + существующего сервиса остатков.

## Что внутри

- **Backend** — FastAPI (Python 3.11+), порт `8010`
- **Frontend** — React + Vite, порт `5174`
- **Разделы:** Заказы, Остатки, Аналитика

## Быстрый старт

### 1. Установка зависимостей

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2. Настройка окружения

```bash
cd backend
cp .env.example .env
# Отредактируй .env — вставь свои ключи Ozon API
```

### 3. Запуск

```bash
# Терминал 1 — backend
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# Терминал 2 — frontend
cd frontend
npm run dev
```

Открой: http://localhost:5174

## API ключи (Ozon)

- **Client-ID:** 5528045
- **API Key:** см. в `backend/.env`
- **Токен Яндекс.Диска:** для хостинга изображений

## Деплой на Рег.ру

1. Собери frontend: `cd frontend && npm run build`
2. Загрузи `frontend/dist/` и `backend/` на хостинг
3. Настрой supervisor для backend (uvicorn)
4. Настрой nginx: статика из `dist/`, API проксируется на `:8010`

## Отличия от Alleya

| Функция | Alleya | Leto SM |
|---------|--------|---------|
| Логистика (Деловые Линии) | ✅ | ❌ (FBS) |
| Остатки | ❌ | ✅ |
| WB / Яндекс Маркет | ✅ | ❌ (только Ozon) |
| Дизайн | Светлый | Тёмный |

## Лицензия

Приватный проект.
