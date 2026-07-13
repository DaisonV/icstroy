import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import click
from sqlalchemy import select

from .extensions import db
from .models import (
    Application, ApplicationStatus, Client, Role, SeoSetting, ServiceType,
    Shipment, ShipmentStatus, Tariff, TrackingEvent, User,
)


DEFAULT_TARIFFS = [
    ("Алматы — Астана · Сборный", "Алматы", "Астана", ServiceType.GROUPAGE, 95, 5000, 3, 6),
    ("Алматы — Астана · Авто", "Алматы", "Астана", ServiceType.AUTO, 120, 12000, 2, 3),
    ("Астана — Алматы · Сборный", "Астана", "Алматы", ServiceType.GROUPAGE, 95, 5000, 3, 6),
    ("Шымкент — Алматы · Сборный", "Шымкент", "Алматы", ServiceType.GROUPAGE, 90, 5000, 2, 4),
    ("Алматы — Москва · Сборный", "Алматы", "Москва", ServiceType.GROUPAGE, 285, 18000, 6, 10),
    ("Астана — Москва · Авто", "Астана", "Москва", ServiceType.AUTO, 350, 35000, 5, 8),
    ("Франкфурт — Алматы · Авиа", "Франкфурт", "Алматы", ServiceType.AIR, 1180, 85000, 3, 6),
    ("Варшава — Алматы · Авиа", "Варшава", "Алматы", ServiceType.AIR, 1050, 75000, 3, 6),
    ("Милан — Алматы · Авиа", "Милан", "Алматы", ServiceType.AIR, 1240, 90000, 4, 7),
    ("Париж — Алматы · Авиа", "Париж", "Алматы", ServiceType.AIR, 1280, 95000, 4, 7),
]


def seed_data(include_demo=True):
    admin_email = os.getenv("ADMIN_EMAIL", "admin@icstroy.kz").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD")
    is_production = os.getenv("FLASK_ENV") == "production"
    if not admin_password and not is_production:
        admin_password = "ChangeMe!2026"

    admin = db.session.scalar(select(User).where(User.email == admin_email))
    if admin is None and admin_password:
        admin = User(email=admin_email, full_name="Администратор icstroy", role=Role.ADMIN)
        admin.set_password(admin_password)
        db.session.add(admin)

    for name, origin, destination, service, rate, minimum, days_min, days_max in DEFAULT_TARIFFS:
        exists = db.session.scalar(select(Tariff).where(Tariff.name == name))
        if exists is None:
            db.session.add(Tariff(
                name=name,
                origin=origin,
                destination=destination,
                service_type=service,
                price_per_kg=Decimal(rate),
                minimum_price=Decimal(minimum),
                delivery_days_min=days_min,
                delivery_days_max=days_max,
            ))

    seo = db.session.scalar(select(SeoSetting).where(SeoSetting.page_key == "home"))
    if seo is None:
        db.session.add(SeoSetting(
            page_key="home",
            title="icstroy — перевозки по Казахстану, СНГ и авиадоставка из Европы",
            description="Сборные грузы, перевозки по Казахстану и СНГ, авиадоставка из Европы. Персональный менеджер и контроль доставки.",
            keywords="грузоперевозки Казахстан, сборные грузы, авиадоставка из Европы, логистика Алматы",
            robots="index,follow",
        ))

    if include_demo:
        client = db.session.scalar(select(Client).where(Client.company_name == "TOO TransStroy"))
        if client is None:
            client = Client(company_name="TOO TransStroy", contact_name="Алихан С.", phone="+7 700 123 45 67")
            db.session.add(client)
            db.session.flush()
        shipment = db.session.scalar(select(Shipment).where(Shipment.tracking_number == "IC-2048"))
        if shipment is None:
            application = Application(
                number="IC-1048",
                client_id=client.id,
                manager_id=admin.id if admin else None,
                contact_name="Алихан С.",
                company_name=client.company_name,
                phone=client.phone,
                origin="Алматы",
                destination="Астана",
                cargo_name="Строительные материалы",
                weight_kg=Decimal("1240"),
                volume_m3=Decimal("5.2"),
                service_type=ServiceType.AUTO,
                status=ApplicationStatus.IN_WORK,
                estimated_price=Decimal("148800"),
                final_price=Decimal("148800"),
                source="seed",
            )
            db.session.add(application)
            db.session.flush()
            shipment = Shipment(
                tracking_number="IC-2048",
                application_id=application.id,
                client_id=client.id,
                origin="Алматы",
                destination="Астана",
                cargo_name=application.cargo_name,
                weight_kg=application.weight_kg,
                volume_m3=application.volume_m3,
                status=ShipmentStatus.IN_TRANSIT,
                current_location="Караганда",
                driver_name="Марат С.",
                vehicle_number="777 KZ 02",
                estimated_delivery_at=datetime.now(timezone.utc) + timedelta(hours=8),
            )
            db.session.add(shipment)
            db.session.flush()
            db.session.add_all([
                TrackingEvent(shipment_id=shipment.id, status=ShipmentStatus.LOADING, location="Алматы", description="Груз принят и подготовлен к отправке", happened_at=datetime.now(timezone.utc) - timedelta(hours=18)),
                TrackingEvent(shipment_id=shipment.id, status=ShipmentStatus.IN_TRANSIT, location="Караганда", description="Груз следует по маршруту", happened_at=datetime.now(timezone.utc) - timedelta(hours=4)),
            ])

    db.session.commit()
    return admin_email, bool(admin_password)


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed")
    @click.option("--without-demo", is_flag=True, default=False)
    def seed(without_demo):
        db.create_all()
        email, has_password = seed_data(include_demo=not without_demo)
        click.echo("Seed complete. Admin: {}. Password configured: {}".format(email, has_password))

