from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, select

from ..extensions import db
from ..models import ServiceType, Tariff


@dataclass
class PriceQuote:
    total: Decimal
    chargeable_weight: Decimal
    days_min: int
    days_max: int
    tariff: Tariff


def as_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return Decimal(default)


def calculate_quote(origin, destination, service_type, weight_kg, volume_m3):
    today = date.today()
    if isinstance(service_type, str):
        service_type = ServiceType(service_type)

    tariff = db.session.scalar(
        select(Tariff)
        .where(
            Tariff.origin == origin,
            Tariff.destination == destination,
            Tariff.service_type == service_type,
            Tariff.is_active.is_(True),
            Tariff.valid_from <= today,
            or_(Tariff.valid_until.is_(None), Tariff.valid_until >= today),
        )
        .order_by(Tariff.valid_from.desc())
    )
    if tariff is None:
        return None

    weight = max(Decimal("0"), as_decimal(weight_kg))
    volume = max(Decimal("0"), as_decimal(volume_m3))
    chargeable_weight = max(weight, volume * tariff.volumetric_factor)
    raw_total = chargeable_weight * tariff.price_per_kg
    step = max(Decimal("1"), tariff.rounding_step)
    rounded_total = (raw_total / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    total = max(tariff.minimum_price, rounded_total)

    return PriceQuote(
        total=total,
        chargeable_weight=chargeable_weight,
        days_min=tariff.delivery_days_min,
        days_max=tariff.delivery_days_max,
        tariff=tariff,
    )

