# Git настройки для PixFy

## ✅ Что уже настроено:

### Базовая конфигурация:
- **Пользователь:** PixFy Developer <developer@pixfy.local>
- **Ветка по умолчанию:** main
- **Редактор:** nano
- **Цветовая подсветка:** включена
- **Pull стратегия:** merge (без rebase)

### Полезные алиасы:
- `git st` → `git status` 
- `git co` → `git checkout`
- `git br` → `git branch`
- `git ci` → `git commit`
- `git lg` → красивый лог с графом и цветами

### Репозиторий:
- **GitHub:** https://github.com/likart/pixfy2.git
- **Ветка:** main
- **Статус:** 1 коммит готов к push

## 🔄 Для синхронизации с GitHub нужно:

### Вариант 1: Personal Access Token
1. Перейдите в GitHub Settings → Developer settings → Personal access tokens
2. Создайте новый token с правами на репозиторий
3. При push используйте token вместо пароля

### Вариант 2: SSH ключи (рекомендуется)
```bash
# Генерация SSH ключа
ssh-keygen -t ed25519 -C "developer@pixfy.local"

# Добавление ключа в ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Добавьте публичный ключ в GitHub Settings → SSH keys
cat ~/.ssh/id_ed25519.pub

# Изменение remote на SSH
git remote set-url origin git@github.com:likart/pixfy2.git
```

## 🚀 Готовые команды:

```bash
# Проверка статуса
git st

# Красивый лог
git lg

# Push после настройки аутентификации
git push origin main

# Pull обновлений
git pull origin main
```

## 📁 .gitignore настроен для:
- Python (__pycache__, *.pyc)
- Django (db.sqlite3, media/, staticfiles/)
- IDE (.vscode/, .idea/)
- OS файлы (.DS_Store, Thumbs.db)
- Виртуальное окружение (venv/)
