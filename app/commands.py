import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import click
from sqlalchemy import select

from .extensions import db
from .models import (
    Application, ApplicationStatus, CityTariff, Client, CompanySetting, Role,
    SeoSetting, ServiceType, Shipment, ShipmentStatus, Tariff, TrackingEvent, User,
)


INTERCITY_TARIFFS = [
    ("Караганда", 1100, 2, 3, 600000, 120, 6000),
    ("Астана", 1250, 3, 4, 650000, None, None),
    ("Кокшетау", 1600, 3, 5, 700000, None, None),
    ("Петропавловск", 1900, 4, 5, 750000, None, None),
    ("Костанай", 2050, 4, 5, 750000, None, None),
    ("Жезказган", 1500, 3, 4, 800000, None, None),
    ("Талдыкорган", 270, 1, 2, 300000, None, None),
    ("Усть-Каменогорск", 1150, 3, 4, 600000, None, None),
    ("Семей", 1250, 3, 4, 600000, None, None),
    ("Павлодар", 1500, 2, 3, 700000, None, None),
    ("Тараз", 550, 1, 2, 400000, None, None),
    ("Шымкент", 750, 1, 2, 450000, None, None),
    ("Кызылорда", 1250, 2, 3, 600000, None, None),
    ("Актобе", 2400, 5, 6, 1000000, None, None),
    ("Уральск", 2720, 7, 8, 1000000, None, None),
    ("Актау", 3550, 8, 9, 1000000, None, None),
    ("Атырау", 2800, 7, 8, 1000000, None, None),
    ("Жаркент", 350, 1, 2, 250000, None, None),
    ("Экибастуз", 1250, 1, 2, 750000, None, None),
    ("Балхаш", 550, 1, 2, 500000, None, None),
    ("Кордай", 214, 1, 2, 300000, None, None),
    ("Шу", 316, 1, 2, 380000, None, None),
    ("Туркестан", 894, 2, 3, 550000, None, None),
    ("Мерке", 414, 1, 2, 350000, None, None),
    ("Конаев (Капчагай)", 60, 1, 1, 150000, None, None),
]

CITY_TARIFFS = [
    ("Еврофура", "86 м³, 20 тонн", 2, 80000),
    ("Услуги спецтехники — автокран", None, 2, 30000),
    ("Манипулятор", "7 тонн", 3, 80000),
    ("Газель", "16 м³, 3 тонны", 2, 20000),
    ("Грузчики", None, 2, 7000),
]

LEGACY_TARIFF_NAMES = {
    "Алматы — Астана · Сборный", "Алматы — Астана · Авто",
    "Астана — Алматы · Сборный", "Шымкент — Алматы · Сборный",
    "Алматы — Москва · Сборный", "Астана — Москва · Авто",
    "Франкфурт — Алматы · Авиа", "Варшава — Алматы · Авиа",
    "Милан — Алматы · Авиа", "Париж — Алматы · Авиа",
}


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

    company = db.session.scalar(select(CompanySetting).limit(1))
    if company is None:
        company = CompanySetting(
            legal_name='ТОО «IC STROY GROUP»', brand_name="icstroy", bin="251140024698",
            address="г. Алматы, пр. Рыскулова 140/4, кабинет 416",
            phone="+7 777 008 77 77", website="https://icstroy.kz/",
            director_name="Касымова Гаухар Булатовна", experience_years=25,
            proposal_title="Международные грузоперевозки",
            proposal_intro="Компания более 25 лет предоставляет безопасные и своевременные логистические услуги, обеспечивая ответственность и контроль на каждом этапе доставки.",
            vat_note="Все цены указаны без НДС",
        )
        db.session.add(company)

    for tariff in db.session.scalars(select(Tariff).where(Tariff.name.in_(LEGACY_TARIFF_NAMES))):
        tariff.is_active = False

    for destination, distance, days_min, days_max, truck_price, kg_price, m3_price in INTERCITY_TARIFFS:
        name = "Алматы — {} · Фура 20 т".format(destination)
        tariff = db.session.scalar(select(Tariff).where(Tariff.name == name))
        if tariff is None:
            tariff = Tariff(name=name, origin="Алматы", destination=destination, service_type=ServiceType.AUTO, price_per_kg=Decimal("0"))
            db.session.add(tariff)
        tariff.distance_km = distance
        tariff.full_truck_price = Decimal(truck_price)
        tariff.delivery_days_min = days_min
        tariff.delivery_days_max = days_max
        tariff.minimum_price = Decimal("0")
        tariff.vat_included = False
        tariff.notes = "Крытый автотранспорт, 20 тонн"
        tariff.is_active = True

        if kg_price or m3_price:
            groupage_name = "Алматы — {} · Сборный груз".format(destination)
            groupage = db.session.scalar(select(Tariff).where(Tariff.name == groupage_name))
            if groupage is None:
                groupage = Tariff(name=groupage_name, origin="Алматы", destination=destination, service_type=ServiceType.GROUPAGE, price_per_kg=Decimal("0"))
                db.session.add(groupage)
            groupage.distance_km = distance
            groupage.price_per_kg = Decimal(kg_price or 0)
            groupage.price_per_m3 = Decimal(m3_price or 0)
            groupage.minimum_price = Decimal("0")
            groupage.delivery_days_min = days_min
            groupage.delivery_days_max = days_max
            groupage.vat_included = False
            groupage.is_active = True

    for service_name, specifications, minimum_units, price in CITY_TARIFFS:
        item = db.session.scalar(select(CityTariff).where(CityTariff.service_name == service_name))
        if item is None:
            item = CityTariff(service_name=service_name, price=Decimal(price))
            db.session.add(item)
        item.specifications = specifications
        item.minimum_units = minimum_units
        item.price = Decimal(price)
        item.vat_included = False
        item.is_active = True

    seo = db.session.scalar(select(SeoSetting).where(SeoSetting.page_key == "home"))
    if seo is None:
        seo = SeoSetting(
            page_key="home",
            title="IC STROY GROUP — международные грузоперевозки",
            description="25 лет в логистике. Авиадоставка из Европы, доставка из России и грузоперевозки собственным транспортом по Казахстану.",
            keywords="международные грузоперевозки, грузоперевозки Казахстан, доставка из России, авиадоставка из Европы, логистика Алматы",
            canonical_url="https://icstroy.kz/",
            robots="index,follow",
        )
        db.session.add(seo)
    else:
        seo.title = "IC STROY GROUP — международные грузоперевозки"
        seo.description = "25 лет в логистике. Авиадоставка из Европы, доставка из России и грузоперевозки собственным транспортом по Казахстану."
        seo.keywords = "международные грузоперевозки, грузоперевозки Казахстан, доставка из России, авиадоставка из Европы, логистика Алматы"
        seo.canonical_url = "https://icstroy.kz/"

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
