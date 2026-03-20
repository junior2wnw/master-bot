"""Service catalog: professions, groups, items, shared operations.

Aligned with the Excel catalog structure (DB_Import sheet).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin


class Profession(Base, TimestampMixin):
    """Top-level direction: электрика, сантехника, сборка мебели."""
    __tablename__ = "professions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)  # EL, PL, FM
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(10))  # emoji
    sort_priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    groups: Mapped[list["ServiceGroup"]] = relationship(back_populates="profession")
    items: Mapped[list["ServiceItem"]] = relationship(back_populates="profession")


class ServiceGroup(Base):
    """Group within a profession: Освещение, Ванны, Корпусная мебель."""
    __tablename__ = "service_groups"
    __table_args__ = (
        Index("ix_service_groups_profession", "profession_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profession_id: Mapped[int] = mapped_column(ForeignKey("professions.id"))
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sort_priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    profession: Mapped["Profession"] = relationship(back_populates="groups")
    subgroups: Mapped[list["ServiceSubgroup"]] = relationship(back_populates="group")


class ServiceSubgroup(Base):
    """Subgroup: Люстры и бра, Герметизация, Комоды."""
    __tablename__ = "service_subgroups"
    __table_args__ = (
        Index("ix_service_subgroups_group", "group_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("service_groups.id"))
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sort_priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    group: Mapped["ServiceGroup"] = relationship(back_populates="subgroups")


class SharedOperation(Base):
    """Cross-profession operations: выезд, диагностика, штробление."""
    __tablename__ = "shared_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)  # #CALL_OUT, #DRILL_HOLE
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    typical_unit: Mapped[str | None] = mapped_column(String(30))
    pricing_strategy: Mapped[str | None] = mapped_column(String(30))  # per_unit, per_meter, hourly
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ServiceItem(Base, TimestampMixin):
    """Atomic work item or bundle in the catalog.

    Maps directly to DB_Import rows from the Excel catalog.
    """
    __tablename__ = "service_items"
    __table_args__ = (
        Index("ix_service_items_profession", "profession_id"),
        Index("ix_service_items_group", "group_id"),
        Index("ix_service_items_subgroup", "subgroup_id"),
        Index("ix_service_items_code", "code", unique=True),
        Index("ix_service_items_active_popular", "is_active", "is_popular"),
        Index("ix_service_items_search", "search_text"),  # for full-text later
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Taxonomy
    profession_id: Mapped[int] = mapped_column(ForeignKey("professions.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("service_groups.id"))
    subgroup_id: Mapped[int | None] = mapped_column(ForeignKey("service_subgroups.id"))

    # Identity
    code: Mapped[str] = mapped_column(String(40), unique=True)  # EL-PT-SOCKET-INNER
    slug: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))  # canonical display name
    description: Mapped[str | None] = mapped_column(Text)

    # Pricing
    unit: Mapped[str] = mapped_column(String(30))  # шт, м.п., компл., усл., час, пакет
    price_min: Mapped[int] = mapped_column(Integer, default=0)
    price_max: Mapped[int] = mapped_column(Integer, default=0)
    price_recommended: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(5), default="RUB")

    # Classification
    record_type: Mapped[str] = mapped_column(String(20))  # atomic, bundle, service, package
    calc_strategy: Mapped[str] = mapped_column(String(20), default="PER_UNIT")  # PER_UNIT, HOURLY, PACKAGE, MIN_ORDER, INFO
    selection_mode: Mapped[str] = mapped_column(String(20), default="quantity")  # single, quantity
    complexity: Mapped[str | None] = mapped_column(String(20))  # basic, std, complex, hard
    confidence: Mapped[str | None] = mapped_column(String(10))  # HIGH, MEDIUM, LOW
    labor_only: Mapped[bool] = mapped_column(Boolean, default=True)

    # Search
    aliases: Mapped[str | None] = mapped_column(Text)  # comma-separated synonyms
    hashtags: Mapped[str | None] = mapped_column(Text)  # #электрика #розетка
    search_text: Mapped[str | None] = mapped_column(Text)  # pre-built search string

    # Shared operations and exclusions
    shared_ops: Mapped[str | None] = mapped_column(Text)  # semicolon-separated op codes
    excludes: Mapped[str | None] = mapped_column(Text)  # semicolon-separated item codes

    # Estimator fields (which questions to ask)
    estimator_fields: Mapped[str | None] = mapped_column(Text)  # comma-separated field keys

    # Metadata
    note: Mapped[str | None] = mapped_column(Text)
    source_1: Mapped[str | None] = mapped_column(Text)
    source_2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    price_updated_at: Mapped[str | None] = mapped_column(String(20))

    # Flags
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    profession: Mapped["Profession"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<ServiceItem {self.code} '{self.name}' {self.price_recommended}₽>"
