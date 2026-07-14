from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Response, current_app, jsonify, render_template, request, url_for
from sqlalchemy import select, text

from . import bp
from ..extensions import db
from ..models import Application, ApplicationActivity, CompanySetting, CrmTask, SeoSetting, ServiceType, Shipment, ShipmentStatus, Tariff
from ..services.notifications import create_application_notifications, send_telegram_application
from ..services.pricing import calculate_quote


STATUS_LABELS = {
    ShipmentStatus.PLANNED: "Ожидает отправки",
    ShipmentStatus.LOADING: "Погрузка",
    ShipmentStatus.IN_TRANSIT: "В пути",
    ShipmentStatus.DELIVERED: "Доставлено",
    ShipmentStatus.DELAYED: "Задержка",
    ShipmentStatus.CANCELLED: "Отменено",
}


def page_seo(page_key, defaults):
    setting = db.session.scalar(select(SeoSetting).where(SeoSetting.page_key == page_key))
    if setting:
        return setting
    return type("SeoDefaults", (), defaults)()


@bp.get("/")
def index():
    seo = page_seo("home", {
        "title": "IC STROY GROUP — международные грузоперевозки",
        "description": "25 лет в логистике. Авиадоставка из Европы, доставка из России и перевозки собственным транспортом по Казахстану.",
        "keywords": "международные грузоперевозки, грузоперевозки Казахстан, доставка из России, авиадоставка Европа, логистика Алматы",
        "canonical_url": current_app.config["SITE_URL"] + "/",
        "og_image": current_app.config["SITE_URL"] + url_for("static", filename="assets/icstroy-mark.svg"),
        "robots": "index,follow",
    })
    company = db.session.scalar(select(CompanySetting).limit(1))
    destinations = db.session.scalars(
        select(Tariff.destination).where(Tariff.is_active.is_(True), Tariff.origin == "Алматы").distinct().order_by(Tariff.destination)
    ).all()
    return render_template("public/index.html", seo=seo, company=company, destinations=destinations)


@bp.get("/brandbook")
def brandbook():
    return render_template("public/brandbook.html")


@bp.get("/privacy")
def privacy():
    company = db.session.scalar(select(CompanySetting).limit(1))
    return render_template("public/privacy.html", company=company)


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify({"ok": False, "database": "unavailable"}), 503
    return jsonify({"ok": True, "database": "ready"})


@bp.post("/api/applications")
def create_application():
    data = request.get_json(silent=True) or request.form
    contact_name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    if len(contact_name) < 2 or len(phone) < 7:
        return jsonify({"ok": False, "error": "Укажите имя и корректный телефон."}), 422

    route = str(data.get("route", "")).strip()
    origin, separator, destination = route.partition("—")
    application = Application(
        number=Application.make_number(),
        contact_name=contact_name,
        company_name=str(data.get("company", "")).strip() or None,
        phone=phone,
        email=str(data.get("email", "")).strip() or None,
        origin=origin.strip() or None,
        destination=destination.strip() if separator else None,
        message=str(data.get("message", "")).strip() or None,
        source="website",
    )
    db.session.add(application)
    db.session.flush()
    db.session.add(ApplicationActivity(
        application_id=application.id,
        kind="created",
        message="Заявка поступила с сайта.",
    ))
    db.session.add(CrmTask(
        application=application,
        title="Связаться с клиентом по новой заявке",
        notes="Первичный ответ клиенту после обращения с сайта.",
        due_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    create_application_notifications(application)
    db.session.commit()
    send_telegram_application(application)
    return jsonify({"ok": True, "number": application.number}), 201


@bp.post("/api/calculate")
def calculate():
    data = request.get_json(silent=True) or {}
    try:
        quote = calculate_quote(
            str(data.get("from", "")).strip(),
            str(data.get("to", "")).strip(),
            str(data.get("transport", "groupage")),
            data.get("weight", 0),
            data.get("volume", 0),
        )
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Некорректные параметры расчёта."}), 422
    if quote is None:
        return jsonify({"ok": False, "error": "Для этого направления требуется индивидуальный расчёт."}), 404
    return jsonify({
        "ok": True,
        "price": int(quote.total),
        "chargeable_weight": float(quote.chargeable_weight),
        "days_min": quote.days_min,
        "days_max": quote.days_max,
        "tariff": quote.tariff.name,
        "basis": quote.basis,
        "vat_included": quote.tariff.vat_included,
    })


@bp.get("/api/tracking/<tracking_number>")
def tracking(tracking_number):
    shipment = db.session.scalar(
        select(Shipment).where(Shipment.tracking_number == tracking_number.strip().upper())
    )
    if shipment is None:
        return jsonify({"ok": False, "error": "Отправление не найдено."}), 404
    return jsonify({
        "ok": True,
        "tracking_number": shipment.tracking_number,
        "status": shipment.status.value,
        "status_label": STATUS_LABELS[shipment.status],
        "origin": shipment.origin,
        "destination": shipment.destination,
        "current_location": shipment.current_location,
        "estimated_delivery_at": shipment.estimated_delivery_at.isoformat() if shipment.estimated_delivery_at else None,
        "events": [{
            "status": event.status.value,
            "description": event.description,
            "location": event.location,
            "happened_at": event.happened_at.isoformat(),
        } for event in shipment.events],
    })


@bp.get("/robots.txt")
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /crm\nDisallow: /auth\nSitemap: {}/sitemap.xml\n".format(current_app.config["SITE_URL"])
    return Response(content, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    base = current_app.config["SITE_URL"]
    now = datetime.now(timezone.utc).date().isoformat()
    xml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
  <url><loc>{base}/</loc><lastmod>{now}</lastmod><priority>1.0</priority></url>
  <url><loc>{base}/brandbook</loc><lastmod>{now}</lastmod><priority>0.3</priority></url>
  <url><loc>{base}/privacy</loc><lastmod>{now}</lastmod><priority>0.2</priority></url>
</urlset>""".format(base=base, now=now)
    return Response(xml, mimetype="application/xml")
