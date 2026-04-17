# Astroproxy Referral Monitor Bot

Простой Telegram-бот для мониторинга реферального баланса в сервисе Astroproxy с уведомлениями при достижении $50 и выше.

## Возможности
- **Ручная проверка баланса**: Кнопка в меню для мгновенного получения текущего баланса.
- **Автоматический мониторинг**: Бот проверяет баланс каждые 10 минут.
- **Push-уведомления**: Бот пришлет сообщение, как только ваш баланс станет $\ge$ $50.
- **Безопасность**: Доступ ограничен только вашим Telegram ID.

## Предварительные требования
- Python 3.8 или выше.
- Токен Telegram бота (можно получить у [@BotFather](https://t.me/BotFather)).
- API ключ Astroproxy.
- Ваш Telegram user ID (можно узнать у [@userinfobot](https://t.me/userinfobot)).

---

## Установка и настройка на сервере Ubuntu

### 1. Обновление системы и установка зависимостей
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y
```

### 2. Клонирование репозитория
```bash
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
cd astroproxy-bot
```

### 3. Настройка виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Конфигурация
Создайте файл `.env` на основе примера:
```bash
cp .env.example .env
nano .env
```
Заполните ваши данные:
- `BOT_TOKEN`: Токен вашего Telegram бота.
- `ASTROPROXY_API_KEY`: Ваш API ключ Astroproxy.
- `TELEGRAM_USER_ID`: Ваш числовой Telegram ID.

### 5. Настройка автозапуска через Systemd
Чтобы бот работал в фоновом режиме и автоматически перезапускался, создайте файл службы:

```bash
sudo nano /etc/systemd/system/astro-bot.service
```

Вставьте следующее содержимое (замените `/home/ubuntu/astroproxy-bot` на ваш реальный путь к папке бота):

```ini
[Unit]
Description=Astroproxy Referral Bot
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/astroproxy-bot
ExecStart=/home/ubuntu/astroproxy-bot/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Примечание:** Если ваше имя пользователя отличается от `ubuntu`, измените его в строках `User`, `Group` и путях.

### 6. Включение и запуск службы
```bash
sudo systemctl daemon-reload
sudo systemctl enable astro-bot
sudo systemctl start astro-bot
```

### 7. Управление службой
- **Проверить статус**: `sudo systemctl status astro-bot`
- **Просмотреть логи**: `journalctl -u astro-bot -f`
- **Перезапустить**: `sudo systemctl restart astro-bot`
- **Остановить**: `sudo systemctl stop astro-bot`

---

## Автор
[Alex](https://github.com/yourusername)
