# Leto SM Dashboard — Deploy Instructions

## Структура проекта

```
leto-sm-dashboard/
├── backend/           # FastAPI + Python
│   ├── app/
│   ├── venv/         # virtual environment
│   └── requirements.txt
├── frontend/          # React + Vite
│   ├── dist/         # production build
│   └── src/
├── start-production.sh
├── nginx-leto-sm.conf
└── .env.example
```

## Деплой на Рег.ру (VDS / Shared Hosting with SSH)

### 1. Подготовка сервера

```bash
# Зайти на сервер по SSH
ssh user@leto-sm-platform.ru

# Создать директорию проекта
mkdir -p /home/leto-sm
cd /home/leto-sm

# Скопировать файлы проекта (через scp, rsync или git)
```

### 2. Backend

```bash
cd /home/leto-sm/backend

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Создать .env файл
cp ../.env.example .env
# Отредактировать .env, добавить API ключи Ozon
```

### 3. Frontend

```bash
cd /home/leto-sm/frontend

# Установить зависимости (если нужно пересобрать)
npm install
npm run build

# Или просто скопировать готовую dist/
```

### 4. Запуск

```bash
cd /home/leto-sm
chmod +x start-production.sh

# Запуск в фоне через nohup или screen
nohup ./start-production.sh > backend.log 2>&1 &
```

### 5. Nginx (если есть доступ)

```bash
# Скопировать конфиг
sudo cp nginx-leto-sm.conf /etc/nginx/sites-available/leto-sm
sudo ln -s /etc/nginx/sites-available/leto-sm /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Автозапуск (systemd)

Создать файл `/etc/systemd/system/leto-sm.service`:

```ini
[Unit]
Description=Leto SM Dashboard
After=network.target

[Service]
Type=simple
User=leto-sm
WorkingDirectory=/home/leto-sm
ExecStart=/home/leto-sm/start-production.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable leto-sm
sudo systemctl start leto-sm
```

## Проверка

- Frontend: http://leto-sm-platform.ru
- API: http://leto-sm-platform.ru/api/ozon/status
