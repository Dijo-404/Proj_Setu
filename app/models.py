from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PURCHASE = "purchase"
    SALES = "sales"
    AUDITOR = "auditor"


class SerialStatus(str, Enum):
    GENERATED = "GENERATED"
    RECEIVED = "RECEIVED"
    IN_STOCK = "IN_STOCK"
    SOLD = "SOLD"
    RETURNED = "RETURNED"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    ISSUED = "ISSUED"
    AUDITED = "AUDITED"
    DAMAGED = "DAMAGED"
    MISSING = "MISSING"
    REPLACED = "REPLACED"


class BatchType(str, Enum):
    RECEIVE = "RECEIVE"
    SALE = "SALE"
    AUDIT = "AUDIT"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    SALES_RETURN = "SALES_RETURN"
    ISSUE = "ISSUE"


class BatchStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SYNCED = "SYNCED"
    PENDING_SYNC = "PENDING_SYNC"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    batches: Mapped[list["Batch"]] = relationship(back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hsn: Mapped[str] = mapped_column(String(40))
    gst_rate: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40), default="Pcs")
    default_rate: Mapped[float] = mapped_column(Float, default=0)
    tally_stock_item_name: Mapped[str] = mapped_column(String(180))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    serials: Mapped[list["Serial"]] = relationship(back_populates="product")


class Serial(Base):
    __tablename__ = "serials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    status: Mapped[str] = mapped_column(String(40), default=SerialStatus.GENERATED.value, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("serials.id"), nullable=True)

    product: Mapped[Product] = relationship(back_populates="serials")
    batch_items: Mapped[list["BatchItem"]] = relationship(back_populates="serial")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    batch_type: Mapped[str] = mapped_column(String(40), index=True)
    party_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), default=BatchStatus.DRAFT.value, index=True)
    tally_voucher_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tally_voucher_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tally_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="batches")
    items: Mapped[list["BatchItem"]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    scan_logs: Mapped[list["ScanLog"]] = relationship(back_populates="batch")
    sync_attempts: Mapped[list["SyncAttempt"]] = relationship(back_populates="batch")
    audit_findings: Mapped[list["AuditFinding"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class BatchItem(Base):
    __tablename__ = "batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "serial_id", name="uq_batch_serial"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    serial_id: Mapped[int] = mapped_column(ForeignKey("serials.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped[Batch] = relationship(back_populates="items")
    serial: Mapped[Serial] = relationship(back_populates="batch_items")


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_id: Mapped[int | None] = mapped_column(ForeignKey("serials.id"), nullable=True)
    serial_number_raw: Mapped[str] = mapped_column(String(140), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tally_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    batch: Mapped[Batch | None] = relationship(back_populates="scan_logs")
    serial: Mapped[Serial | None] = relationship()
    user: Mapped[User] = relationship()


class SyncAttempt(Base):
    __tablename__ = "sync_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    status: Mapped[str] = mapped_column(String(40), index=True)
    request_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    batch: Mapped[Batch] = relationship(back_populates="sync_attempts")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class LoginAudit(Base):
    __tablename__ = "login_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class TallyMasterConfirmation(Base):
    __tablename__ = "tally_master_confirmations"
    __table_args__ = (UniqueConstraint("master_type", "master_name", name="uq_tally_master_confirmation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    master_type: Mapped[str] = mapped_column(String(80), index=True)
    master_name: Mapped[str] = mapped_column(String(220), index=True)
    source: Mapped[str] = mapped_column(String(220))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    confirmed_by: Mapped[User] = relationship()


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    serial_id: Mapped[int | None] = mapped_column(ForeignKey("serials.id"), nullable=True)
    serial_number: Mapped[str] = mapped_column(String(140), index=True)
    product_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    finding_type: Mapped[str] = mapped_column(String(40), index=True)
    expected_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scanned_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    batch: Mapped[Batch] = relationship(back_populates="audit_findings")
    serial: Mapped[Serial | None] = relationship()
