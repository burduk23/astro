# Astro Monitor Bot (Astroproxy + TronGrid)

Телеграм-бот для автоматического мониторинга баланса **Astroproxy** и поступлений **USDT (TRC20)** на кошелек Tron.

---

## 🚀 Установка на Ubuntu Server (Рекомендуется)

### Шаг 1: Подготовка системы
Обновите пакеты и установите необходимые зависимости:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git python3-pip python3-venv -y
```

### Шаг 2: Клонирование репозитория
```bash
git clone https://github.com/ВАШ_ЛОГИН/astro.git 
cd astro
```

### Шаг 3: Создание виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Шаг 4: Настройка конфигурации (.env и message.json)

1.  **Создайте файл `.env`**:
    ```bash
    nano .env
    ```
    **Заполните следующие поля:**
       `BOT_TOKEN`: Токен вашего бота от @BotFather.
       `TELEGRAM_USER_ID`: Ваш Chat ID телеграм(куда слать отчеты).
       `ASTRO_COOKIE`: Cookie сессии Astroproxy (из браузера).
       `TRON_WALLET_ADDRESS`: Адрес вашего кошелька USDT TRC20 (начинается на T).
       `TRONGRID_API_KEY`: (Опционально) Ключ API с trongrid.io.
       `API_ID`:
	   `API_HASH`: Получаются на [my.telegram.org](https://my.telegram.org).

2.  **Настройте сообщение для вывода (`message.json`)**:
    ```bash
    nano message.json
    ```
    **Пример содержания:**
    ```json
    {
      "ID": "",
      "Message": ""
    }
    ```

### Шаг 5: Первый запуск и Авторизация
**Важно!** Telethon требует разовой авторизации. Запустите бота вручную:
```bash
python3 bot.py
```
Введите номер телефона (в международном формате, например `+7999...`) и код подтверждения из Telegram. После появления сообщения "Бот запущен..." нажмите `Ctrl+C`.

### Шаг 6: Создание системного сервиса (astro)
Чтобы бот работал 24/7, создайте сервис:
```bash
sudo nano /etc/systemd/system/astro.service
```
**Вставьте текст (замените `user` на ваше имя пользователя):**
```ini
[Unit]
Description=Astro Monitor Bot
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/root/astro
ExecStart=/root/astro/venv/bin/python bot.py

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
**Обновите конфиги и запустите сервис:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable astro
sudo systemctl start astro
```
---

## 🛠 Управление ботом на сервере
*   `sudo systemctl daemon-reload` — обновить конфиги после создания файла.
*   `sudo systemctl enable astro` — включить автозапуск при старте сервера.
*   `sudo systemctl start astro` — запустить бота.
*   `sudo systemctl restart astro` — **перезагрузить бота** (использовать после обновлений).
*   `sudo systemctl status astro` — проверить, работает ли бот.
*   `journalctl -u astro -f` — смотреть логи (вывод бота) в реальном времени.

---

## 💻 Установка на Windows

1.  **Подготовка**: Установите [Python 3.8+](https://www.python.org/downloads/) и [Git](https://git-scm.com/download/win).
2.  **Клонирование**: `git clone https://github.com/ВАШ_ЛОГИН/ВАШ_РЕПОЗИТОРИЙ.git` в терминале.
3.  **Окружение**:
    ```powershell
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```
4.  **Конфигурация**: Создайте файлы `.env` и `message.json` в папке бота (см. описание в "Шаг 4" для Ubuntu).
5.  **Запуск**: `python bot.py`. При первом запуске введите код подтверждения от Telegram.

---

## 📋 Основной функционал
*   **Astroproxy**: Проверка баланса каждые 10 минут. При достижении $50 (или любой суммы больше 50) — уведомление в бота и однократная автоотправка сообщения через Telethon (с защитой от дублей).
*   **Tron**: Проверка поступлений USDT каждые 60 секунд. Уведомление при любом пополнении баланса.
*   **Кнопки**: Статистика, ручной тест автовывода, Настройки и Админка.
*   **Админка**: Владелец (TELEGRAM_USER_ID из `.env`) может добавлять новых пользователей, которым будет доступен функционал бота и получение уведомлений.
*   **Настройки**: Каждый добавленный пользователь может настроить ID получателя и текст для своего тестового сообщения (по умолчанию тестовое сообщение отправляется самому пользователю). Это позволяет тестировать вывод безопасно, не затрагивая реального получателя из `message.json`.
