"""Typed SQLAlchemy mappings for Boomerang's durable account domain."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - SQLAlchemy resolves mapped annotations.
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models import (
    FactOrigin,
    HandoffEvidence,
    PolicyEligibility,
    Preference,
    ReturnState,
    ReturnSummaryUpdateSource,
)

if TYPE_CHECKING:
    from enum import Enum


def _enum_values(enum_type: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_type]


FACT_ORIGIN_ENUM = SqlEnum(
    FactOrigin,
    name="fact_origin",
    values_callable=_enum_values,
)
HANDOFF_EVIDENCE_ENUM = SqlEnum(
    HandoffEvidence,
    name="handoff_evidence",
    values_callable=_enum_values,
)
POLICY_ELIGIBILITY_ENUM = SqlEnum(
    PolicyEligibility,
    name="policy_eligibility",
    values_callable=_enum_values,
)
PREFERENCE_ENUM = SqlEnum(
    Preference,
    name="preference",
    values_callable=_enum_values,
)
RETURN_STATE_ENUM = SqlEnum(
    ReturnState,
    name="return_state",
    values_callable=_enum_values,
)
RETURN_SUMMARY_UPDATE_SOURCE_ENUM = SqlEnum(
    ReturnSummaryUpdateSource,
    name="return_summary_update_source",
    values_callable=_enum_values,
)


class AccountRow(Base):
    """Stored Google-linked account."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    google_subject: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list[OrderRow]] = relationship(
        back_populates="account",
        cascade="save-update, merge",
        lazy="raise",
    )
    preference_set: Mapped[PreferenceSetRow | None] = relationship(
        back_populates="account",
        cascade="save-update, merge",
        lazy="raise",
        uselist=False,
    )


class OrderRow(Base):
    """Stored normalized retailer order."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "retailer_key",
            "retailer_order_reference",
            name="uq_orders_retailer_reference",
        ),
        Index("ix_orders_account_id", "account_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    retailer_key: Mapped[str] = mapped_column(Text)
    retailer_name: Mapped[str] = mapped_column(Text)
    retailer_order_reference: Mapped[str | None] = mapped_column(Text)
    ordered_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    account: Mapped[AccountRow] = relationship(back_populates="orders", lazy="raise")
    items: Mapped[list[OrderItemRow]] = relationship(
        back_populates="order",
        cascade="save-update, merge",
        lazy="raise",
    )


class OrderItemRow(Base):
    """Stored item-level return candidate."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "price_amount_minor IS NULL OR price_amount_minor >= 0",
            name="price_non_negative",
        ),
        CheckConstraint(
            "(price_amount_minor IS NULL AND price_currency IS NULL) OR "
            "(price_amount_minor IS NOT NULL AND price_currency IS NOT NULL)",
            name="price_columns_together",
        ),
        CheckConstraint(
            "price_currency IS NULL OR price_currency ~ '^[A-Z]{3}$'",
            name="price_currency_format",
        ),
        Index("ix_order_items_order_id", "order_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    description: Mapped[str] = mapped_column(Text)
    variant: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    price_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    price_currency: Mapped[str | None] = mapped_column(String(3))
    delivered_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[OrderRow] = relationship(back_populates="items", lazy="raise")
    return_policy: Mapped[ReturnPolicyRow | None] = relationship(
        back_populates="item",
        cascade="save-update, merge",
        lazy="raise",
        uselist=False,
    )
    return_summary: Mapped[ReturnSummaryRow | None] = relationship(
        back_populates="item",
        cascade="save-update, merge",
        lazy="raise",
        uselist=False,
    )


class ReturnPolicyRow(Base):
    """Stored current policy for one order item."""

    __tablename__ = "return_policies"
    __table_args__ = (
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "return_by_confidence IS NULL OR "
            "(return_by_confidence >= 0 AND return_by_confidence <= 1)",
            name="return_by_confidence_range",
        ),
        CheckConstraint(
            "(return_by_value IS NULL AND return_by_origin IS NULL "
            "AND return_by_confidence IS NULL) OR "
            "(return_by_value IS NOT NULL AND return_by_origin IS NOT NULL)",
            name="return_by_columns_together",
        ),
        CheckConstraint(
            "fee_amount_minor IS NULL OR fee_amount_minor >= 0",
            name="fee_non_negative",
        ),
        CheckConstraint(
            "fee_currency IS NULL OR fee_currency ~ '^[A-Z]{3}$'",
            name="fee_currency_format",
        ),
        CheckConstraint(
            "fee_confidence IS NULL OR (fee_confidence >= 0 AND fee_confidence <= 1)",
            name="fee_confidence_range",
        ),
        CheckConstraint(
            "(fee_amount_minor IS NULL AND fee_currency IS NULL AND fee_origin IS NULL "
            "AND fee_confidence IS NULL) OR "
            "(fee_amount_minor IS NOT NULL AND fee_currency IS NOT NULL "
            "AND fee_origin IS NOT NULL)",
            name="fee_columns_together",
        ),
    )

    item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"), primary_key=True)
    eligibility: Mapped[PolicyEligibility] = mapped_column(POLICY_ELIGIBILITY_ENUM)
    return_by_value: Mapped[date | None] = mapped_column(Date)
    return_by_origin: Mapped[FactOrigin | None] = mapped_column(FACT_ORIGIN_ENUM)
    return_by_confidence: Mapped[float | None] = mapped_column(Float)
    fee_amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    fee_currency: Mapped[str | None] = mapped_column(String(3))
    fee_origin: Mapped[FactOrigin | None] = mapped_column(FACT_ORIGIN_ENUM)
    fee_confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    item: Mapped[OrderItemRow] = relationship(back_populates="return_policy", lazy="raise")
    rules: Mapped[list[PolicyRuleRow]] = relationship(
        back_populates="policy",
        cascade="save-update, merge",
        lazy="raise",
    )


class PolicyRuleRow(Base):
    """Stored normalized rule belonging to the current item policy."""

    __tablename__ = "policy_rules"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    item_id: Mapped[str] = mapped_column(
        ForeignKey("return_policies.item_id"),
        primary_key=True,
    )
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    origin: Mapped[FactOrigin] = mapped_column(FACT_ORIGIN_ENUM)
    confidence: Mapped[float | None] = mapped_column(Float)

    policy: Mapped[ReturnPolicyRow] = relationship(back_populates="rules", lazy="raise")


class PreferenceSetRow(Base):
    """Stored owner row for one account's complete preference set."""

    __tablename__ = "preference_sets"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    account: Mapped[AccountRow] = relationship(back_populates="preference_set", lazy="raise")
    values: Mapped[list[PreferenceValueRow]] = relationship(
        back_populates="preference_set",
        cascade="save-update, merge",
        lazy="raise",
    )


class PreferenceValueRow(Base):
    """One unique value within an account preference set."""

    __tablename__ = "preference_values"

    account_id: Mapped[str] = mapped_column(
        ForeignKey("preference_sets.account_id"),
        primary_key=True,
    )
    value: Mapped[Preference] = mapped_column(PREFERENCE_ENUM, primary_key=True)

    preference_set: Mapped[PreferenceSetRow] = relationship(
        back_populates="values",
        lazy="raise",
    )


class ReturnSummaryRow(Base):
    """Stored minimal return milestone for one order item."""

    __tablename__ = "return_summaries"
    __table_args__ = (
        CheckConstraint(
            "update_source <> 'system_initialization' OR state = 'not_started'",
            name="system_initialization_state",
        ),
        CheckConstraint(
            "(state = 'handed_to_carrier' AND handoff_evidence IS NOT NULL) OR "
            "(state <> 'handed_to_carrier' AND handoff_evidence IS NULL)",
            name="handoff_evidence_state",
        ),
    )

    item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id"), primary_key=True)
    state: Mapped[ReturnState] = mapped_column(RETURN_STATE_ENUM)
    update_source: Mapped[ReturnSummaryUpdateSource] = mapped_column(
        RETURN_SUMMARY_UPDATE_SOURCE_ENUM,
    )
    handoff_evidence: Mapped[HandoffEvidence | None] = mapped_column(HANDOFF_EVIDENCE_ENUM)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    item: Mapped[OrderItemRow] = relationship(back_populates="return_summary", lazy="raise")


ORM_ROWS: tuple[type[Base], ...] = (
    AccountRow,
    OrderRow,
    OrderItemRow,
    ReturnPolicyRow,
    PolicyRuleRow,
    PreferenceSetRow,
    PreferenceValueRow,
    ReturnSummaryRow,
)

__all__: list[str] = [row.__name__ for row in ORM_ROWS]
