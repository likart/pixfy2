# 🚀 Пошаговая инструкция по развертыванию Pixfy на хостинге

## 📋 Предварительные требования
- Ubuntu/Debian сервер с root доступом
- Домен pixfy.ru, указанный на IP сервера

## 🔧 1. Подготовка сервера

### Обновление системы
```bash
apt update && apt upgrade -y
```

### Установка необходимых пакетов
```bash
apt install -y nginx python3-pip python3-venv git supervisor certbot python3-certbot-nginx
apt install -y postgresql postgresql-contrib  # Опционально для PostgreSQL
```

### Создание пользователя для веб-приложения
```bash
useradd --system --shell /bin/bash --home /var/www --create-home www-data
```

## 🗄️ 2. Настройка базы данных (опционально PostgreSQL)

```bash
sudo -u postgres createuser --interactive --pwprompt pixfy_user
sudo -u postgres createdb --owner=pixfy_user pixfy_db
```

Обновите settings_production.py:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pixfy_db',
        'USER': 'pixfy_user',
        'PASSWORD': 'your_secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

## 🌐 3. Настройка Nginx

### Копирование конфигурации
```bash
cp /root/pixfy/nginx_pixfy.conf /etc/nginx/sites-available/pixfy.ru
ln -s /etc/nginx/sites-available/pixfy.ru /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default  # Удалить дефолтный сайт
```

### Проверка конфигурации
```bash
nginx -t
```

## 🔐 4. Получение SSL сертификата

```bash
certbot --nginx -d pixfy.ru -d www.pixfy.ru
```

## 🐍 5. Настройка Django приложения

### Права доступа
```bash
chown -R www-data:www-data /root/pixfy
chmod -R 755 /root/pixfy
chmod -R 775 /root/pixfy/media
```

### Миграции и статика
```bash
cd /root/pixfy
source venv/bin/activate
python manage.py migrate --settings=photobank.settings_production
python manage.py collectstatic --noinput --settings=photobank.settings_production
```

### Создание суперпользователя
```bash
python manage.py createsuperuser --settings=photobank.settings_production
```

## 🚀 6. Настройка Systemd служб

### Копирование файлов служб
```bash
cp /root/pixfy/pixfy.service /etc/systemd/system/
cp /root/pixfy/pixfy-worker.service /etc/systemd/system/
```

### Редактирование секретного ключа
```bash
# Генерировать новый секретный ключ
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Вставить в оба файла службы вместо "your-production-secret-key-here"
nano /etc/systemd/system/pixfy.service
nano /etc/systemd/system/pixfy-worker.service
```

### Запуск служб
```bash
systemctl daemon-reload
systemctl enable pixfy pixfy-worker nginx
systemctl start pixfy pixfy-worker nginx
```

### Проверка статуса
```bash
systemctl status pixfy
systemctl status pixfy-worker
systemctl status nginx
```

## 🔍 7. Проверка работы

### Логи для диагностики
```bash
# Django приложение
journalctl -u pixfy -f

# Обработчик файлов
journalctl -u pixfy-worker -f

# Nginx
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log

# Gunicorn
tail -f /root/pixfy/logs/gunicorn_error.log
```

### Тестирование
```bash
# Проверка доступности
curl -I https://pixfy.ru

# Проверка статики
curl -I https://pixfy.ru/static/

# Проверка медиа
curl -I https://pixfy.ru/media/
```

## 🔧 8. Дополнительные настройки

### Автоматическое продление SSL
```bash
crontab -e
# Добавить строку:
0 12 * * * /usr/bin/certbot renew --quiet
```

### Ротация логов
```bash
nano /etc/logrotate.d/pixfy
```

```
/root/pixfy/logs/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    postrotate
        systemctl reload pixfy
    endscript
}
```

### Очистка медиа файлов (еженедельно)
```bash
crontab -e
# Добавить строку:
0 3 * * 0 cd /root/pixfy && /root/pixfy/venv/bin/python manage.py cleanup_media --remove-empty-dirs --settings=photobank.settings_production
```

## ⚡ 9. Оптимизации производительности

### Настройка PostgreSQL (если используется)
```bash
nano /etc/postgresql/*/main/postgresql.conf
```

### Настройка кэширования в Django
Установить Redis:
```bash
apt install redis-server
pip install django-redis
```

Добавить в settings_production.py:
```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

## 🚨 10. Мониторинг и безопасность

### Установка fail2ban
```bash
apt install fail2ban
systemctl enable fail2ban
```

### Настройка файрвола
```bash
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable
```

## 🎉 Готово!

Ваш сайт должен быть доступен по адресу: https://pixfy.ru

### Полезные команды для управления:
```bash
# Перезапуск приложения
systemctl restart pixfy

# Перезапуск обработчика файлов  
systemctl restart pixfy-worker

# Перезагрузка Nginx
systemctl reload nginx

# Просмотр логов
journalctl -u pixfy -n 50
```
