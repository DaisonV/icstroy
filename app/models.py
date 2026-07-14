import enum
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    LOGISTICIAN = "logistician"


class ApplicationStatus(str, enum.Enum):
    NEW = "new"
    CALCULATION = "calculation"
    APPROVAL = "approval"
    IN_WORK = "in_work"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ShipmentStatus(str, enum.Enum):
    PLANNED = "planned"
    LOADING = "loading"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class ServiceType(str, enum.Enum):
    GROUPAGE = "groupage"
    AUTO = "auto"
    AIR = "air"


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), default=Role.MANAGER, nullable=False)
    is_active_user: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    managed_applications: Mapped[list["Application"]] = relationship(back_populates="manager", foreign_keys="Application.manager_id")
    assigned_tasks: Mapped[list["CrmTask"]] = relationship(back_populates="assignee", foreign_keys="CrmTask.assignee_id")
    created_tasks: Mapped[list["CrmTask"]] = relationship(back_populates="created_by", foreign_keys="CrmTask.created_by_id")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="recipient", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return self.is_active_user

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles


class Client(TimestampMixin, db.Model):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    bin: Mapped[str] = mapped_column(String(20), unique=True, nullable=True)
    contact_name: Mapped[str] = mapped_column(String(160), nullable=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    address: Mapped[str] = mapped_column(String(300), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    applications: Mapped[list["Application"]] = relationship(back_populates="client")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="client")


class Application(TimestampMixin, db.Model):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    contact_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    origin: Mapped[str] = mapped_column(String(160), nullable=True)
    destination: Mapped[str] = mapped_column(String(160), nullable=True)
    cargo_name: Mapped[str] = mapped_column(String(200), nullable=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    volume_m3: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, native_enum=False), default=ServiceType.GROUPAGE, nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus, native_enum=False), default=ApplicationStatus.NEW, nullable=False, index=True)
    estimated_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    final_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="website", nullable=False)

    client: Mapped[Client] = relationship(back_populates="applications")
    manager: Mapped[User] = relationship(back_populates="managed_applications", foreign_keys=[manager_id])
    shipment: Mapped["Shipment"] = relationship(back_populates="application", uselist=False)
    tasks: Mapped[list["CrmTask"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="CrmTask.due_at")
    activities: Mapped[list["ApplicationActivity"]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ApplicationActivity.created_at.desc()")

    @staticmethod
    def make_number():
        return "IC-" + datetime.now().strftime("%y%m") + "-" + secrets.token_hex(2).upper()


class CrmTask(TimestampMixin, db.Model):
    __tablename__ = "crm_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, native_enum=False), default=TaskStatus.OPEN, nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped[Application] = relationship(back_populates="tasks")
    assignee: Mapped[User] = relationship(back_populates="assigned_tasks", foreign_keys=[assignee_id])
    created_by: Mapped[User] = relationship(back_populates="created_tasks", foreign_keys=[created_by_id])

    @property
    def is_overdue(self):
        if self.status != TaskStatus.OPEN:
            return False
        deadline = self.due_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline < utcnow()


class ApplicationActivity(db.Model):
    __tablename__ = "application_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), default="note", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    application: Mapped[Application] = relationship(back_populates="activities")
    user: Mapped[User] = relationship()


class Notification(db.Model):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    recipient: Mapped[User] = relationship(back_populates="notifications")
    application: Mapped[Application] = relationship()


class Tariff(TimestampMixin, db.Model):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    destination: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType, native_enum=False), nullable=False, index=True)
    distance_km: Mapped[int] = mapped_column(nullable=True)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_per_m3: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    full_truck_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    minimum_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=5000, nullable=False)
    volumetric_factor: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=167, nullable=False)
    rounding_step: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=500, nullable=False)
    delivery_days_min: Mapped[int] = mapped_column(default=2, nullable=False)
    delivery_days_max: Mapped[int] = mapped_column(default=5, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=True)
    vat_included: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CityTariff(TimestampMixin, db.Model):
    __tablename__ = "city_tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    specifications: Mapped[str] = mapped_column(String(300), nullable=True)
    unit: Mapped[str] = mapped_column(String(80), default="час", nullable=False)
    minimum_units: Mapped[int] = mapped_column(default=1, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    vat_included: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CompanySetting(TimestampMixin, db.Model):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(250), nullable=False)
    brand_name: Mapped[str] = mapped_column(String(120), default="icstroy", nullable=False)
    bin: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(String(350), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    website: Mapped[str] = mapped_column(String(250), nullable=False)
    director_name: Mapped[str] = mapped_column(String(200), nullable=True)
    experience_years: Mapped[int] = mapped_column(default=25, nullable=False)
    proposal_title: Mapped[str] = mapped_column(String(250), default="Международные грузоперевозки", nullable=False)
    proposal_intro: Mapped[str] = mapped_column(Text, nullable=False)
    vat_note: Mapped[str] = mapped_column(String(120), default="Все цены указаны без НДС", nullable=False)


class Shipment(TimestampMixin, db.Model):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True, nullable=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    destination: Mapped[str] = mapped_column(String(160), nullable=False)
    cargo_name: Mapped[str] = mapped_column(String(200), nullable=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    volume_m3: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=True)
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus, native_enum=False), default=ShipmentStatus.PLANNED, nullable=False, index=True)
    current_location: Mapped[str] = mapped_column(String(200), nullable=True)
    driver_name: Mapped[str] = mapped_column(String(160), nullable=True)
    vehicle_number: Mapped[str] = mapped_column(String(40), nullable=True)
    estimated_delivery_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    application: Mapped[Application] = relationship(back_populates="shipment")
    client: Mapped[Client] = relationship(back_populates="shipments")
    events: Mapped[list["TrackingEvent"]] = relationship(back_populates="shipment", cascade="all, delete-orphan", order_by="TrackingEvent.happened_at.desc()")


class TrackingEvent(db.Model):
    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ShipmentStatus] = mapped_column(Enum(ShipmentStatus, native_enum=False), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    shipment: Mapped[Shipment] = relationship(back_populates="events")


class SeoSetting(TimestampMixin, db.Model):
    __tablename__ = "seo_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(String(320), nullable=False)
    keywords: Mapped[str] = mapped_column(String(500), nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(500), nullable=True)
    og_image: Mapped[str] = mapped_column(String(500), nullable=True)
    robots: Mapped[str] = mapped_column(String(80), default="index,follow", nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
