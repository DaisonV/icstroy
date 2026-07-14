from urllib import parse, request

from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import Application, CrmTask, Notification, Role, User


def create_application_notifications(application: Application):
    recipients = db.session.scalars(
        select(User).where(
            User.is_active_user.is_(True),
            User.role.in_([Role.ADMIN, Role.MANAGER]),
        )
    ).all()
    route = "{} → {}".format(application.origin or "Маршрут не указан", application.destination or "уточнить")
    for user in recipients:
        db.session.add(Notification(
            user_id=user.id,
            application_id=application.id,
            title="Новая заявка {}".format(application.number),
            message="{} · {} · {}".format(application.contact_name, application.phone, route),
            link="/crm/applications/{}".format(application.id),
        ))
    return recipients


def create_task_notification(task: CrmTask):
    if task.assignee_id is None:
        return
    db.session.add(Notification(
        user_id=task.assignee_id,
        application_id=task.application_id,
        title="Новая задача по {}".format(task.application.number),
        message=task.title,
        link="/crm/applications/{}#tasks".format(task.application_id),
    ))


def send_telegram_application(application: Application):
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    chat_id = current_app.config.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    crm_url = "{}/crm/applications/{}".format(current_app.config["SITE_URL"], application.id)
    text = (
        "Новая заявка {}\n"
        "Клиент: {}\n"
        "Телефон: {}\n"
        "Маршрут: {} → {}\n"
        "Открыть: {}"
    ).format(
        application.number,
        application.company_name or application.contact_name,
        application.phone,
        application.origin or "не указан",
        application.destination or "уточнить",
        crm_url,
    )
    payload = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    telegram_request = request.Request(
        "https://api.telegram.org/bot{}/sendMessage".format(token),
        data=payload,
        method="POST",
    )
    try:
        with request.urlopen(telegram_request, timeout=4) as response:
            return 200 <= response.status < 300
    except Exception as error:
        current_app.logger.warning("Telegram notification failed: %s", error)
        return False
