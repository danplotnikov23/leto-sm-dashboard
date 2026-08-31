# Деплой Leto SM Dashboard на Railway + Рег.ру

## Архитектура

- **Backend** (FastAPI) → Railway (бесплатный тариф Hobby)
- **Frontend** (React) → Рег.ру shared hosting (статика)

---

## Шаг 1: Деплой Backend на Railway

### 1.1 Создай аккаунт на Railway
- Перейди на https://railway.app
- Зарегистрируйся через GitHub

### 1.2 Создай новый проект
- **New Project** → **Deploy from GitHub repo**
- Выбери свой репозиторий с `leto-sm-dashboard`
- Railway автоматически найдёт `Dockerfile` и `railway.toml`

### 1.3 Добавь переменные окружения
В панели Railway перейди в **Variables** и добавь:

```
OZON_CLIENT_ID=5528045
OZON_API_KEY=b988b85d-bd95-4553-a251-e1368f42b14d
CORS_ORIGINS=https://leto-sm-platform.ru,https://www.leto-sm-platform.ru
```

### 1.4 Получи домен Railway
После деплоя Railway даст тебе URL типа:
```
https://leto-sm-backend.up.railway.app
```

Сохрани этот URL — он понадобится для фронтенда.

### 1.5 Проверь работу API
Открой в браузере:
```
https://leto-sm-backend.up.railway.app/api/ozon/status
```

Должен вернуть:
```json
{"seller_credentials_configured":true,"performance_credentials_configured":true}
```

---

## Шаг 2: Сборка Frontend

### 2.1 Укажи URL бэкенда
```bash
cd /Users/daniilplotnikov/leto-sm-dashboard/frontend
```

Создай файл `.env.production`:
```bash
echo 'VITE_API_BASE=https://ТВОЙ-URL.railway.app' > .env.production
```

### 2.2 Собери фронтенд
```bash
npm run build
```

Готовые файлы появятся в папке `frontend/dist/`.

---

## Шаг 3: Загрузка на Рег.ру

### 3.1 Открой Менеджер файлов
В панели ISPmanager → **Менеджер файлов**

### 3.2 Перейди в директорию сайта
```
/www/leto-sm-platform.ru
```

### 3.3 Удали старые файлы
Удали всё содержимое папки (кроме `.htaccess` если нужен).

### 3.4 Загрузи новые файлы
Загрузи содержимое папки `frontend/dist/`:
- `index.html`
- `assets/` (CSS и JS)
- `logo.png`

### 3.5 Проверь
Открой https://leto-sm-platform.ru — должен открыться дашборд.

---

## Проверка работы

1. Открой https://leto-sm-platform.ru
2. Перейди в раздел **Остатки**
3. Данные должны подгружаться с Railway backend

---

## Обновление после изменений

**Backend:** Просто push в GitHub → Railway автоматически пересоберёт.

**Frontend:**
```bash
cd frontend
npm run build
# Загрузи dist/ на Рег.ру через Менеджер файлов
```

---

## Возможные проблемы

### CORS ошибки
Убедись, что `CORS_ORIGINS` в Railway Variables содержит твой домен `https://leto-sm-platform.ru`.

### Railway "засыпает"
На бесплатном тарифе Railway может останавливать сервис при отсутствии трафика. Первый запрос после "сна" может занять 10-30 секунд. Для production рассмотри платный тариф ($5/мес).

### 502 Bad Gateway
Проверь, что backend запущен (healthcheck на `/` должен возвращать 200).
