# icstroy — сайт и CRM

Рабочее веб-приложение логистической компании: публичный сайт, приём заявок, тарифный калькулятор, трекинг грузов и закрытая CRM.

## Возможности

- заявки с сайта сразу сохраняются в CRM;
- клиенты, заявки, перевозки и история статусов;
- роли `admin`, `manager`, `logistician`;
- тарифы из админки управляют расчётом на сайте;
- публичный трекинг по номеру отправления;
- редактируемые title, description, canonical, Open Graph и robots;
- `sitemap.xml`, `robots.txt`, структурированные данные и страница политики;
- CSRF-защита, безопасные cookie, аудит действий и security headers;
- PostgreSQL в production, SQLite для локальной разработки.

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app wsgi:app db upgrade
.venv/bin/flask --app wsgi:app seed
.venv/bin/flask --app wsgi:app run --debug
```

- Сайт: http://127.0.0.1:5000/
- CRM: http://127.0.0.1:5000/crm
- Локальный администратор: `admin@icstroy.kz`
- Локальный пароль: `ChangeMe!2026`
- Демо-трекинг: `IC-2048`

Локальный пароль создаётся только вне production. После первого входа его следует заменить перед публикацией.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | PostgreSQL URL; локально используется SQLite |
| `SECRET_KEY` | секрет сессий и CSRF |
| `SITE_URL` | публичный адрес без завершающего `/` |
| `ADMIN_EMAIL` | email первого администратора |
| `ADMIN_PASSWORD` | пароль первого администратора, минимум 10 символов |
| `FLASK_ENV` | значение `production` включает secure-cookie и HSTS |

## Render

`render.yaml` создаёт Python Web Service и PostgreSQL. Перед первым деплоем в Render необходимо указать секретные значения `SITE_URL` (например, `https://icstroy.onrender.com`) и `ADMIN_PASSWORD`. При запуске автоматически применяются миграции и идемпотентно создаются базовые тарифы, SEO и первый администратор.

Статические файлы из корня оставлены как история визуального прототипа. Рабочее приложение находится в `app/`.
