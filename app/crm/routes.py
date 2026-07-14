from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from . import bp
from ..extensions import db
from ..models import (
    Application, ApplicationActivity, ApplicationStatus, CityTariff, Client,
    CompanySetting, CrmTask, Notification, Role, SeoSetting, ServiceType,
    Shipment, ShipmentStatus, Tariff, TaskStatus, TrackingEvent, User,
)
from ..permissions import roles_required
from ..services.audit import record_action
from ..services.notifications import create_task_notification


APPLICATION_LABELS = {
    ApplicationStatus.NEW: "Новая",
    ApplicationStatus.CALCULATION: "Расчёт",
    ApplicationStatus.APPROVAL: "Согласование",
    ApplicationStatus.IN_WORK: "В работе",
    ApplicationStatus.COMPLETED: "Завершена",
    ApplicationStatus.CANCELLED: "Отменена",
}
SHIPMENT_LABELS = {
    ShipmentStatus.PLANNED: "Запланирована",
    ShipmentStatus.LOADING: "Погрузка",
    ShipmentStatus.IN_TRANSIT: "В пути",
    ShipmentStatus.DELIVERED: "Доставлена",
    ShipmentStatus.DELAYED: "Задержка",
    ShipmentStatus.CANCELLED: "Отменена",
}
SERVICE_LABELS = {
    ServiceType.GROUPAGE: "Сборный груз",
    ServiceType.AUTO: "Авто — Казахстан / СНГ",
    ServiceType.AIR: "Авиа из Европы",
}
TASK_LABELS = {
    TaskStatus.OPEN: "Открыта",
    TaskStatus.DONE: "Выполнена",
    TaskStatus.CANCELLED: "Отменена",
}


@bp.before_request
@login_required
def protect_crm():
    pass


@bp.app_context_processor
def crm_labels():
    unread_notifications = 0
    if current_user.is_authenticated:
        unread_notifications = db.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == current_user.id,
                Notification.is_read.is_(False),
            )
        ) or 0
    return {
        "application_labels": APPLICATION_LABELS,
        "shipment_labels": SHIPMENT_LABELS,
        "service_labels": SERVICE_LABELS,
        "ApplicationStatus": ApplicationStatus,
        "ShipmentStatus": ShipmentStatus,
        "ServiceType": ServiceType,
        "task_labels": TASK_LABELS,
        "TaskStatus": TaskStatus,
        "Role": Role,
        "unread_notifications": unread_notifications,
        "local_datetime": local_datetime,
    }


def decimal_or_none(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def configured_timezone():
    try:
        return ZoneInfo(current_app.config.get("APP_TIMEZONE", "Asia/Almaty"))
    except ZoneInfoNotFoundError:
        return timezone.utc


def local_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(configured_timezone())


def datetime_from_form(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=configured_timezone())
    return parsed.astimezone(timezone.utc)


def crm_return_path(default):
    candidate = request.form.get("next", "")
    return candidate if candidate.startswith("/crm") else default


@bp.get("")
@bp.get("/")
def dashboard():
    application_count = db.session.scalar(select(func.count(Application.id))) or 0
    new_count = db.session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.NEW)) or 0
    active_shipments = db.session.scalar(select(func.count(Shipment.id)).where(Shipment.status.in_([ShipmentStatus.PLANNED, ShipmentStatus.LOADING, ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED]))) or 0
    client_count = db.session.scalar(select(func.count(Client.id)).where(Client.is_active.is_(True))) or 0
    revenue = db.session.scalar(select(func.coalesce(func.sum(Application.final_price), 0)).where(Application.status == ApplicationStatus.COMPLETED)) or 0
    recent = db.session.scalars(select(Application).order_by(Application.created_at.desc()).limit(8)).all()
    shipment_statuses = dict(db.session.execute(select(Shipment.status, func.count(Shipment.id)).group_by(Shipment.status)).all())
    task_scope = [CrmTask.status == TaskStatus.OPEN]
    if current_user.role != Role.ADMIN:
        task_scope.append(CrmTask.assignee_id == current_user.id)
    open_task_count = db.session.scalar(select(func.count(CrmTask.id)).where(*task_scope)) or 0
    overdue_task_count = db.session.scalar(
        select(func.count(CrmTask.id)).where(*task_scope, CrmTask.due_at < datetime.now(timezone.utc))
    ) or 0
    upcoming_tasks = db.session.scalars(
        select(CrmTask)
        .options(selectinload(CrmTask.application), selectinload(CrmTask.assignee))
        .where(*task_scope)
        .order_by(CrmTask.due_at)
        .limit(5)
    ).all()
    return render_template(
        "crm/dashboard.html",
        application_count=application_count,
        new_count=new_count,
        active_shipments=active_shipments,
        client_count=client_count,
        revenue=revenue,
        recent=recent,
        shipment_statuses=shipment_statuses,
        open_task_count=open_task_count,
        overdue_task_count=overdue_task_count,
        upcoming_tasks=upcoming_tasks,
    )


@bp.route("/applications", methods=["GET", "POST"])
def applications():
    if request.method == "POST":
        application = Application(
            number=Application.make_number(),
            contact_name=request.form.get("contact_name", "").strip(),
            company_name=request.form.get("company_name", "").strip() or None,
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip() or None,
            origin=request.form.get("origin", "").strip() or None,
            destination=request.form.get("destination", "").strip() or None,
            cargo_name=request.form.get("cargo_name", "").strip() or None,
            weight_kg=decimal_or_none(request.form.get("weight_kg")),
            volume_m3=decimal_or_none(request.form.get("volume_m3")),
            service_type=ServiceType(request.form.get("service_type", ServiceType.GROUPAGE.value)),
            manager_id=current_user.id,
            source="crm",
        )
        if not application.contact_name or not application.phone:
            flash("Имя и телефон обязательны.", "error")
        else:
            db.session.add(application)
            db.session.flush()
            db.session.add(ApplicationActivity(
                application_id=application.id,
                user_id=current_user.id,
                kind="created",
                message="Заявка создана сотрудником CRM.",
            ))
            record_action("create", "application", application.id, application.number)
            db.session.commit()
            flash("Заявка {} создана.".format(application.number), "success")
            return redirect(url_for("crm.application_detail", application_id=application.id))

    query = select(Application).options(selectinload(Application.client), selectinload(Application.manager)).order_by(Application.created_at.desc())
    status = request.args.get("status")
    search = request.args.get("q", "").strip()
    if status:
        try:
            query = query.where(Application.status == ApplicationStatus(status))
        except ValueError:
            pass
    if search:
        pattern = "%{}%".format(search)
        query = query.where(or_(Application.number.ilike(pattern), Application.company_name.ilike(pattern), Application.contact_name.ilike(pattern), Application.phone.ilike(pattern)))
    items = db.session.scalars(query).all()
    return render_template("crm/applications.html", applications=items, selected_status=status, search=search)


@bp.route("/applications/<int:application_id>", methods=["GET", "POST"])
def application_detail(application_id):
    application = db.get_or_404(Application, application_id)
    if request.method == "POST":
        previous_status = application.status
        previous_manager_id = application.manager_id
        application.status = ApplicationStatus(request.form.get("status", application.status.value))
        application.manager_id = int(request.form["manager_id"]) if request.form.get("manager_id") else None
        application.client_id = int(request.form["client_id"]) if request.form.get("client_id") else None
        application.estimated_price = decimal_or_none(request.form.get("estimated_price"))
        application.final_price = decimal_or_none(request.form.get("final_price"))
        application.message = request.form.get("message", "").strip() or None
        if previous_status != application.status:
            db.session.add(ApplicationActivity(
                application_id=application.id,
                user_id=current_user.id,
                kind="status",
                message="Статус изменён: {} → {}.".format(
                    APPLICATION_LABELS[previous_status], APPLICATION_LABELS[application.status]
                ),
            ))
        if previous_manager_id != application.manager_id:
            manager = db.session.get(User, application.manager_id) if application.manager_id else None
            db.session.add(ApplicationActivity(
                application_id=application.id,
                user_id=current_user.id,
                kind="manager",
                message="Ответственный: {}.".format(manager.full_name if manager else "не назначен"),
            ))
            if manager is not None:
                unassigned_tasks = db.session.scalars(
                    select(CrmTask).where(
                        CrmTask.application_id == application.id,
                        CrmTask.assignee_id.is_(None),
                        CrmTask.status == TaskStatus.OPEN,
                    )
                ).all()
                for task in unassigned_tasks:
                    task.assignee_id = manager.id
                    create_task_notification(task)
        record_action("update", "application", application.id, application.status.value)
        db.session.commit()
        flash("Заявка обновлена.", "success")
        return redirect(url_for("crm.application_detail", application_id=application.id))
    managers = db.session.scalars(select(User).where(User.is_active_user.is_(True)).order_by(User.full_name)).all()
    clients = db.session.scalars(select(Client).where(Client.is_active.is_(True)).order_by(Client.company_name)).all()
    default_task_due = (datetime.now(configured_timezone()) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    phone_digits = "".join(character for character in application.phone if character.isdigit())
    return render_template(
        "crm/application_detail.html",
        application=application,
        managers=managers,
        clients=clients,
        default_task_due=default_task_due.strftime("%Y-%m-%dT%H:%M"),
        phone_digits=phone_digits,
    )


@bp.post("/applications/<int:application_id>/activities")
def add_application_activity(application_id):
    application = db.get_or_404(Application, application_id)
    message = request.form.get("message", "").strip()
    if not message:
        flash("Введите комментарий.", "error")
    else:
        db.session.add(ApplicationActivity(
            application_id=application.id,
            user_id=current_user.id,
            kind="note",
            message=message,
        ))
        record_action("comment", "application", application.id, message[:200])
        db.session.commit()
        flash("Комментарий добавлен.", "success")
    return redirect(url_for("crm.application_detail", application_id=application.id) + "#activity")


@bp.post("/applications/<int:application_id>/tasks")
def add_application_task(application_id):
    application = db.get_or_404(Application, application_id)
    title = request.form.get("title", "").strip()
    due_at = datetime_from_form(request.form.get("due_at"))
    assignee_id = int(request.form["assignee_id"]) if request.form.get("assignee_id") else current_user.id
    if not title or due_at is None:
        flash("Укажите задачу и срок выполнения.", "error")
    else:
        task = CrmTask(
            application=application,
            assignee_id=assignee_id,
            created_by_id=current_user.id,
            title=title,
            notes=request.form.get("notes", "").strip() or None,
            due_at=due_at,
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(ApplicationActivity(
            application_id=application.id,
            user_id=current_user.id,
            kind="task",
            message="Создана задача: {}.".format(task.title),
        ))
        create_task_notification(task)
        record_action("create", "task", task.id, task.title)
        db.session.commit()
        flash("Задача создана.", "success")
    return redirect(url_for("crm.application_detail", application_id=application.id) + "#tasks")


@bp.post("/tasks/<int:task_id>/status")
def task_status(task_id):
    task = db.get_or_404(CrmTask, task_id)
    try:
        new_status = TaskStatus(request.form.get("status", TaskStatus.DONE.value))
    except ValueError:
        new_status = TaskStatus.DONE
    task.status = new_status
    task.completed_at = datetime.now(timezone.utc) if new_status == TaskStatus.DONE else None
    db.session.add(ApplicationActivity(
        application_id=task.application_id,
        user_id=current_user.id,
        kind="task",
        message="Задача «{}» — {}.".format(task.title, TASK_LABELS[new_status].lower()),
    ))
    record_action("status", "task", task.id, new_status.value)
    db.session.commit()
    flash("Статус задачи обновлён.", "success")
    return redirect(crm_return_path(url_for("crm.application_detail", application_id=task.application_id) + "#tasks"))


@bp.get("/tasks")
def tasks():
    selected_status = request.args.get("status", TaskStatus.OPEN.value)
    scope = request.args.get("scope", "all" if current_user.role == Role.ADMIN else "mine")
    query = select(CrmTask).options(
        selectinload(CrmTask.application), selectinload(CrmTask.assignee)
    )
    if selected_status != "all":
        try:
            query = query.where(CrmTask.status == TaskStatus(selected_status))
        except ValueError:
            selected_status = TaskStatus.OPEN.value
            query = query.where(CrmTask.status == TaskStatus.OPEN)
    if scope == "mine":
        query = query.where(CrmTask.assignee_id == current_user.id)
    items = db.session.scalars(query.order_by(CrmTask.due_at, CrmTask.created_at.desc())).all()
    return render_template("crm/tasks.html", tasks=items, selected_status=selected_status, scope=scope)


@bp.get("/notifications")
def notifications():
    items = db.session.scalars(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    ).all()
    return render_template("crm/notifications.html", notifications=items)


@bp.post("/notifications/<int:notification_id>/open")
def open_notification(notification_id):
    item = db.session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if item is None:
        abort(404)
    item.is_read = True
    item.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return redirect(item.link or url_for("crm.notifications"))


@bp.post("/notifications/read-all")
def read_all_notifications():
    items = db.session.scalars(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    ).all()
    now = datetime.now(timezone.utc)
    for item in items:
        item.is_read = True
        item.read_at = now
    db.session.commit()
    flash("Все уведомления отмечены прочитанными.", "success")
    return redirect(url_for("crm.notifications"))


@bp.route("/clients", methods=["GET", "POST"])
def clients():
    if request.method == "POST":
        client = Client(
            company_name=request.form.get("company_name", "").strip(),
            bin=request.form.get("bin", "").strip() or None,
            contact_name=request.form.get("contact_name", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
        )
        if not client.company_name:
            flash("Название клиента обязательно.", "error")
        else:
            db.session.add(client)
            db.session.flush()
            record_action("create", "client", client.id, client.company_name)
            db.session.commit()
            flash("Клиент добавлен.", "success")
            return redirect(url_for("crm.clients"))
    search = request.args.get("q", "").strip()
    query = select(Client).order_by(Client.created_at.desc())
    if search:
        pattern = "%{}%".format(search)
        query = query.where(or_(Client.company_name.ilike(pattern), Client.contact_name.ilike(pattern), Client.phone.ilike(pattern)))
    return render_template("crm/clients.html", clients=db.session.scalars(query).all(), search=search)


@bp.route("/shipments", methods=["GET", "POST"])
def shipments():
    if request.method == "POST":
        shipment = Shipment(
            tracking_number=request.form.get("tracking_number", "").strip().upper(),
            application_id=int(request.form["application_id"]) if request.form.get("application_id") else None,
            client_id=int(request.form["client_id"]) if request.form.get("client_id") else None,
            origin=request.form.get("origin", "").strip(),
            destination=request.form.get("destination", "").strip(),
            cargo_name=request.form.get("cargo_name", "").strip() or None,
            weight_kg=decimal_or_none(request.form.get("weight_kg")),
            volume_m3=decimal_or_none(request.form.get("volume_m3")),
            driver_name=request.form.get("driver_name", "").strip() or None,
            vehicle_number=request.form.get("vehicle_number", "").strip() or None,
        )
        if not shipment.tracking_number or not shipment.origin or not shipment.destination:
            flash("Номер, пункт отправления и назначения обязательны.", "error")
        else:
            db.session.add(shipment)
            db.session.flush()
            db.session.add(TrackingEvent(shipment_id=shipment.id, status=ShipmentStatus.PLANNED, location=shipment.origin, description="Перевозка создана"))
            record_action("create", "shipment", shipment.id, shipment.tracking_number)
            db.session.commit()
            flash("Перевозка создана.", "success")
            return redirect(url_for("crm.shipment_detail", shipment_id=shipment.id))
    items = db.session.scalars(select(Shipment).options(selectinload(Shipment.client)).order_by(Shipment.created_at.desc())).all()
    clients_list = db.session.scalars(select(Client).where(Client.is_active.is_(True)).order_by(Client.company_name)).all()
    available_apps = db.session.scalars(
        select(Application).where(~Application.shipment.has()).order_by(Application.created_at.desc())
    ).all()
    return render_template("crm/shipments.html", shipments=items, clients=clients_list, available_apps=available_apps)


@bp.route("/shipments/<int:shipment_id>", methods=["GET", "POST"])
def shipment_detail(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    if request.method == "POST":
        new_status = ShipmentStatus(request.form.get("status", shipment.status.value))
        description = request.form.get("description", "").strip() or SHIPMENT_LABELS[new_status]
        location = request.form.get("location", "").strip() or shipment.current_location
        shipment.status = new_status
        shipment.current_location = location
        if new_status == ShipmentStatus.DELIVERED:
            shipment.delivered_at = datetime.now(timezone.utc)
        db.session.add(TrackingEvent(shipment_id=shipment.id, status=new_status, location=location, description=description))
        record_action("status", "shipment", shipment.id, new_status.value)
        db.session.commit()
        flash("Статус перевозки обновлён.", "success")
        return redirect(url_for("crm.shipment_detail", shipment_id=shipment.id))
    return render_template("crm/shipment_detail.html", shipment=shipment)


@bp.route("/tariffs", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def tariffs():
    if request.method == "POST":
        tariff = Tariff(
            name=request.form.get("name", "").strip(),
            origin=request.form.get("origin", "").strip(),
            destination=request.form.get("destination", "").strip(),
            service_type=ServiceType(request.form.get("service_type")),
            distance_km=int(request.form["distance_km"]) if request.form.get("distance_km") else None,
            price_per_kg=decimal_or_none(request.form.get("price_per_kg")) or Decimal("0"),
            price_per_m3=decimal_or_none(request.form.get("price_per_m3")),
            full_truck_price=decimal_or_none(request.form.get("full_truck_price")),
            minimum_price=decimal_or_none(request.form.get("minimum_price")) or Decimal("0"),
            volumetric_factor=decimal_or_none(request.form.get("volumetric_factor")) or Decimal("167"),
            rounding_step=decimal_or_none(request.form.get("rounding_step")) or Decimal("500"),
            delivery_days_min=int(request.form.get("delivery_days_min", 1)),
            delivery_days_max=int(request.form.get("delivery_days_max", 3)),
            valid_from=date.fromisoformat(request.form.get("valid_from") or date.today().isoformat()),
            vat_included=bool(request.form.get("vat_included")),
            notes=request.form.get("notes", "").strip() or None,
        )
        if not tariff.name or not tariff.origin or not tariff.destination or not any((tariff.price_per_kg, tariff.price_per_m3, tariff.full_truck_price)):
            flash("Заполните маршрут и хотя бы одну ставку.", "error")
        else:
            db.session.add(tariff)
            db.session.flush()
            record_action("create", "tariff", tariff.id, tariff.name)
            db.session.commit()
            flash("Тариф добавлен и доступен калькулятору.", "success")
            return redirect(url_for("crm.tariffs"))
    items = db.session.scalars(select(Tariff).order_by(Tariff.is_active.desc(), Tariff.updated_at.desc())).all()
    return render_template("crm/tariffs.html", tariffs=items, today=date.today().isoformat())


@bp.post("/tariffs/<int:tariff_id>/toggle")
@roles_required(Role.ADMIN)
def tariff_toggle(tariff_id):
    tariff = db.get_or_404(Tariff, tariff_id)
    tariff.is_active = not tariff.is_active
    record_action("toggle", "tariff", tariff.id, str(tariff.is_active))
    db.session.commit()
    flash("Статус тарифа изменён.", "success")
    return redirect(url_for("crm.tariffs"))


@bp.route("/tariffs/<int:tariff_id>", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def tariff_detail(tariff_id):
    tariff = db.get_or_404(Tariff, tariff_id)
    if request.method == "POST":
        tariff.name = request.form.get("name", "").strip()
        tariff.origin = request.form.get("origin", "").strip()
        tariff.destination = request.form.get("destination", "").strip()
        tariff.service_type = ServiceType(request.form.get("service_type"))
        tariff.distance_km = int(request.form["distance_km"]) if request.form.get("distance_km") else None
        tariff.price_per_kg = decimal_or_none(request.form.get("price_per_kg")) or Decimal("0")
        tariff.price_per_m3 = decimal_or_none(request.form.get("price_per_m3"))
        tariff.full_truck_price = decimal_or_none(request.form.get("full_truck_price"))
        tariff.minimum_price = decimal_or_none(request.form.get("minimum_price")) or Decimal("0")
        tariff.volumetric_factor = decimal_or_none(request.form.get("volumetric_factor")) or Decimal("167")
        tariff.rounding_step = decimal_or_none(request.form.get("rounding_step")) or Decimal("1")
        tariff.delivery_days_min = int(request.form.get("delivery_days_min", 1))
        tariff.delivery_days_max = int(request.form.get("delivery_days_max", 1))
        tariff.valid_from = date.fromisoformat(request.form.get("valid_from") or date.today().isoformat())
        tariff.valid_until = date.fromisoformat(request.form["valid_until"]) if request.form.get("valid_until") else None
        tariff.vat_included = bool(request.form.get("vat_included"))
        tariff.notes = request.form.get("notes", "").strip() or None
        if not tariff.name or not tariff.origin or not tariff.destination or not any((tariff.price_per_kg, tariff.price_per_m3, tariff.full_truck_price)):
            flash("Заполните маршрут и хотя бы одну ставку.", "error")
        elif tariff.delivery_days_min > tariff.delivery_days_max:
            flash("Минимальный срок не может быть больше максимального.", "error")
        else:
            record_action("update", "tariff", tariff.id, tariff.name)
            db.session.commit()
            flash("Тариф обновлён. Новые расчёты уже используют эти значения.", "success")
            return redirect(url_for("crm.tariffs"))
    return render_template("crm/tariff_detail.html", tariff=tariff)


@bp.route("/city-tariffs", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def city_tariffs():
    if request.method == "POST":
        item_id = request.form.get("item_id")
        item = db.session.get(CityTariff, int(item_id)) if item_id else CityTariff(service_name="", price=Decimal("0"))
        item.service_name = request.form.get("service_name", "").strip()
        item.specifications = request.form.get("specifications", "").strip() or None
        item.unit = request.form.get("unit", "час").strip() or "час"
        item.minimum_units = int(request.form.get("minimum_units", 1))
        item.price = decimal_or_none(request.form.get("price")) or Decimal("0")
        item.vat_included = bool(request.form.get("vat_included"))
        item.notes = request.form.get("notes", "").strip() or None
        item.is_active = bool(request.form.get("is_active", "1"))
        if not item.service_name or item.price <= 0:
            flash("Укажите услугу и положительную стоимость.", "error")
        else:
            if item.id is None:
                db.session.add(item)
            db.session.flush()
            record_action("update" if item_id else "create", "city_tariff", item.id, item.service_name)
            db.session.commit()
            flash("Городской тариф сохранён.", "success")
            return redirect(url_for("crm.city_tariffs"))
    items = db.session.scalars(select(CityTariff).order_by(CityTariff.is_active.desc(), CityTariff.service_name)).all()
    return render_template("crm/city_tariffs.html", tariffs=items)


@bp.route("/company", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def company():
    setting = db.session.scalar(select(CompanySetting).limit(1))
    if setting is None:
        abort(404)
    if request.method == "POST":
        setting.legal_name = request.form.get("legal_name", "").strip()
        setting.brand_name = request.form.get("brand_name", "").strip()
        setting.bin = request.form.get("bin", "").strip()
        setting.address = request.form.get("address", "").strip()
        setting.phone = request.form.get("phone", "").strip()
        setting.website = request.form.get("website", "").strip()
        setting.director_name = request.form.get("director_name", "").strip() or None
        setting.experience_years = int(request.form.get("experience_years", 25))
        setting.proposal_title = request.form.get("proposal_title", "").strip()
        setting.proposal_intro = request.form.get("proposal_intro", "").strip()
        setting.vat_note = request.form.get("vat_note", "").strip()
        record_action("update", "company", setting.id, setting.legal_name)
        db.session.commit()
        flash("Реквизиты компании обновлены.", "success")
        return redirect(url_for("crm.company"))
    return render_template("crm/company.html", company=setting)


@bp.route("/commercial-proposal", methods=["GET", "POST"])
def commercial_proposal():
    company = db.session.scalar(select(CompanySetting).limit(1))
    tariffs_list = db.session.scalars(
        select(Tariff).where(Tariff.is_active.is_(True), Tariff.service_type == ServiceType.AUTO).order_by(Tariff.destination)
    ).all()
    groupage = db.session.scalars(
        select(Tariff).where(Tariff.is_active.is_(True), Tariff.service_type == ServiceType.GROUPAGE).order_by(Tariff.destination)
    ).all()
    city = db.session.scalars(select(CityTariff).where(CityTariff.is_active.is_(True)).order_by(CityTariff.service_name)).all()
    recipient = request.form.get("recipient", "").strip() if request.method == "POST" else ""
    contact = request.form.get("contact", "").strip() if request.method == "POST" else ""
    subject = request.form.get("subject", "Коммерческое предложение по грузоперевозкам").strip() if request.method == "POST" else "Коммерческое предложение по грузоперевозкам"
    return render_template(
        "crm/commercial_proposal.html", company=company, tariffs=tariffs_list,
        groupage=groupage, city_tariffs=city, recipient=recipient, contact=contact,
        subject=subject, generated=date.today(),
    )


@bp.route("/seo", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def seo():
    setting = db.session.scalar(select(SeoSetting).where(SeoSetting.page_key == "home"))
    if setting is None:
        setting = SeoSetting(page_key="home", title="icstroy", description="Логистика icstroy")
        db.session.add(setting)
        db.session.commit()
    if request.method == "POST":
        setting.title = request.form.get("title", "").strip()
        setting.description = request.form.get("description", "").strip()
        setting.keywords = request.form.get("keywords", "").strip() or None
        setting.canonical_url = request.form.get("canonical_url", "").strip() or None
        setting.og_image = request.form.get("og_image", "").strip() or None
        setting.robots = request.form.get("robots", "index,follow").strip()
        record_action("update", "seo", setting.id, "home")
        db.session.commit()
        flash("SEO-настройки опубликованы.", "success")
        return redirect(url_for("crm.seo"))
    return render_template("crm/seo.html", setting=setting)


@bp.route("/users", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def users():
    if request.method == "POST":
        user = User(
            email=request.form.get("email", "").strip().lower(),
            full_name=request.form.get("full_name", "").strip(),
            role=Role(request.form.get("role", Role.MANAGER.value)),
        )
        password = request.form.get("password", "")
        if not user.email or not user.full_name or len(password) < 10:
            flash("Укажите имя, email и пароль не короче 10 символов.", "error")
        else:
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            record_action("create", "user", user.id, user.email)
            db.session.commit()
            flash("Сотрудник добавлен.", "success")
            return redirect(url_for("crm.users"))
    return render_template("crm/users.html", users=db.session.scalars(select(User).order_by(User.created_at)).all())
