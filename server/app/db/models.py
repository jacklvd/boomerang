"""Typed SQLAlchemy mappings for Boomerang's durable account domain."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 - SQLAlchemy resolves mapped annotations.
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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


class PairingStatus(StrEnum):
    """Lifecycle status of a browser-linking pairing request.

    ``expired`` is deliberately not a member. Expiry is evaluated against
    ``expires_at`` at read time by every statement that touches this table, never
    stored as a transition of its own.

    ``rejected`` is deliberately not a member either. Only the authenticated
    dashboard principal - the same person who started the pairing - can ever
    approve one, so a pairing nobody acts on is not a hanging risk: it stays
    ``pending``, approvable by nobody else, and expires on its own within
    minutes. There is no decline route to produce a rejected state; the
    approval page's copy says to close the page, not to decline.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REDEEMED = "redeemed"


class BrowserLabel(StrEnum):
    """Closed, server-controlled vocabulary for the browser shown on a grant or pairing.

    Never the raw user-agent string and never free text supplied by the extension:
    the extension is the untrusted party in the phishing scenario this label
    exists to defend against, so what it reports must map onto a small declared
    set rather than be stored as received. Adding a browser is a schema change.
    """

    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"
    SAFARI = "safari"
    OTHER = "other"


class AuthClientKind(StrEnum):
    """The two kinds of client an authorization grant can belong to."""

    EXTENSION = "extension"
    DASHBOARD = "dashboard"


class AuthCredentialKind(StrEnum):
    """The two kinds of bearer credential resolved through ``auth_credentials``.

    A dashboard session cookie's value is stored as an ``access`` credential
    pointing at a grant with ``client_kind = dashboard`` - there is no separate
    kind for it.
    """

    ACCESS = "access"
    REFRESH = "refresh"


class GrantRevocationReason(StrEnum):
    """Why a grant's ``revoked_at`` was set.

    Only reasons a row can actually carry. ``idle_expired`` and
    ``absolute_expired`` are never stored - both limits are evaluated against
    the grant's timestamps at read time, never written as a transition of
    their own. ``account_deleted`` is not a member either: account deletion
    removes the grant row outright rather than marking it revoked, so no row
    would ever carry that reason.
    """

    USER_DISCONNECTED = "user_disconnected"
    DASHBOARD_SIGN_OUT = "dashboard_sign_out"
    REFRESH_REUSE = "refresh_reuse"


PAIRING_STATUS_ENUM = SqlEnum(
    PairingStatus,
    name="pairing_status",
    values_callable=_enum_values,
)
BROWSER_LABEL_ENUM = SqlEnum(
    BrowserLabel,
    name="browser_label",
    values_callable=_enum_values,
)
AUTH_CLIENT_KIND_ENUM = SqlEnum(
    AuthClientKind,
    name="auth_client_kind",
    values_callable=_enum_values,
)
AUTH_CREDENTIAL_KIND_ENUM = SqlEnum(
    AuthCredentialKind,
    name="auth_credential_kind",
    values_callable=_enum_values,
)
GRANT_REVOCATION_REASON_ENUM = SqlEnum(
    GrantRevocationReason,
    name="grant_revocation_reason",
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
        # retailer_order_reference is nullable ("when available"). PostgreSQL treats NULLs
        # in a unique constraint as distinct by default, so without nulls_not_distinct two
        # rescans of an order whose reference could not be read would silently insert two
        # orders for the same (account_id, retailer_key) - the same physical order shown
        # twice, with its own fresh item ids, policies and not-started summaries. Requiring
        # NULLS NOT DISTINCT instead makes a second unreadable-reference rescan collide and
        # raise IntegrityError: a loud, visible rescan failure instead of silent duplication.
        # This does give something up: two accounts' orders from the same retailer that are
        # both genuinely unreadable are indistinguishable from a rescan of the same order and
        # are rejected too - there is no available fact to tell them apart with, so a loud
        # failure is the honest outcome rather than a guess.
        #
        # PostgreSQL-only (requires PostgreSQL 15+; this dialect kwarg is silently ignored on
        # any other backend, which matters here because the whole ORM schema already requires
        # real PostgreSQL - see the CHECK constraints below and test_db_integration.py).
        UniqueConstraint(
            "account_id",
            "retailer_key",
            "retailer_order_reference",
            name="uq_orders_retailer_reference",
            postgresql_nulls_not_distinct=True,
        ),
        # The target a composite child foreign key points at. Not a new uniqueness
        # claim - id is already unique - it exists so children can carry the account.
        # See design/boomerang-account-scoping.md section 3 and section 5.1: this
        # constraint, combined with id staying a single-column primary key below,
        # is what makes an account-hop through a shared id unrepresentable.
        UniqueConstraint("account_id", "id", name="uq_orders_account_id_id"),
        # dev-note: ix_orders_account_id is dropped here. uq_orders_account_id_id
        # above creates a unique index leading with account_id, so a lookup or
        # filter on account_id alone still uses that index as a prefix; a second,
        # separate single-column index would be redundant.
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
        Index("ix_order_items_account_id_order_id", "account_id", "order_id"),
        # id stays globally unique so the wire identifier still names at most one item.
        UniqueConstraint("id", name="uq_order_items_id"),
        # MATCH FULL + NOT DEFERRABLE: see design/boomerang-account-scoping.md
        # section 5 and 5.2. NOT DEFERRABLE rejects a mismatched child at the
        # INSERT/UPDATE statement itself rather than at COMMIT. MATCH FULL is
        # defense in depth so the guarantee does not depend on order_id staying
        # NOT NULL forever. Never ON UPDATE CASCADE on account_id - it would
        # silently relabel this row into another account.
        ForeignKeyConstraint(
            ["account_id", "order_id"],
            ["orders.account_id", "orders.id"],
            name="fk_order_items_account_id_orders",
            match="FULL",
            deferrable=False,
        ),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[str] = mapped_column(Text)
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
        ForeignKeyConstraint(
            ["account_id", "item_id"],
            ["order_items.account_id", "order_items.id"],
            name="fk_return_policies_account_id_order_items",
            match="FULL",
            deferrable=False,
        ),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
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
        ForeignKeyConstraint(
            ["account_id", "item_id"],
            ["return_policies.account_id", "return_policies.item_id"],
            name="fk_policy_rules_account_id_return_policies",
            match="FULL",
            deferrable=False,
        ),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
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
        ForeignKeyConstraint(
            ["account_id", "item_id"],
            ["order_items.account_id", "order_items.id"],
            name="fk_return_summaries_account_id_order_items",
            match="FULL",
            deferrable=False,
        ),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    state: Mapped[ReturnState] = mapped_column(RETURN_STATE_ENUM)
    update_source: Mapped[ReturnSummaryUpdateSource] = mapped_column(
        RETURN_SUMMARY_UPDATE_SOURCE_ENUM,
    )
    handoff_evidence: Mapped[HandoffEvidence | None] = mapped_column(HANDOFF_EVIDENCE_ENUM)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    item: Mapped[OrderItemRow] = relationship(back_populates="return_summary", lazy="raise")


class PairingRequestRow(Base):
    """A browser-linking pairing, from creation to redemption.

    Deliberately NOT account-scoped. It exists before any account is bound to
    it - the extension creates it, and only a later, separate dashboard tab
    approves it - so there is nothing to put in a leading, NOT NULL account
    column at creation, and setting one later would mean updating a primary-key
    column's identity out from under the row. It holds no account-derived data
    of any kind: the only account-linked value on the row is the account id
    itself, entered as a plain nullable foreign key rather than as a scoped
    primary-key column. It is listed in ``UNSCOPED_ROWS`` below, not in the
    account-scoped registry - do not "fix" that inconsistency by adding it
    there, and do not give this table an account-scoped read path. See the
    persistence design document's account-scoping section for the full
    argument; the short version is that a nullable column in a composite
    foreign key silently skips the account check entirely under MATCH SIMPLE,
    which is precisely the failure mode this table would otherwise reintroduce.
    """

    __tablename__ = "pairing_requests"
    __table_args__ = (
        # A pairing that has never been approved has no account; one that has,
        # always does.
        CheckConstraint(
            "(status = 'pending' AND account_id IS NULL AND approved_at IS NULL)"
            " OR (status IN ('approved', 'redeemed')"
            "     AND account_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="account_binding",
        ),
        CheckConstraint(
            "(status = 'redeemed') = (redeemed_at IS NOT NULL)",
            name="redeemed_at_set",
        ),
        # The code is a comparison aid, not an input. Uniqueness matters only
        # among codes a user could be looking at simultaneously, which is why
        # the index is partial to pending rows.
        Index(
            "uq_pairing_requests_user_code_pending",
            "user_code",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_pairing_requests_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[PairingStatus] = mapped_column(PAIRING_STATUS_ENUM)

    # base64url(SHA-256(verifier)). The verifier itself is never stored, never
    # logged, and never leaves the extension until redemption. S256 is the only
    # accepted method; there is no method column, because a "plain" method is a
    # downgrade attack and adding a second method should cost a schema change.
    code_challenge: Mapped[str] = mapped_column(Text)

    # Displayed by the popup and by the approval page for visual comparison.
    # Never accepted as an input on any route, so this is not a credential and
    # is stored exactly as displayed.
    user_code: Mapped[str] = mapped_column(Text)

    # A closed vocabulary the server maps from what the extension declares,
    # never free text and never a raw user-agent string.
    browser_label: Mapped[BrowserLabel] = mapped_column(BROWSER_LABEL_ENUM)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Bound at approval, from the dashboard's authenticated principal, never
    # from a request body. Nullable for exactly as long as the pairing is
    # unapproved.
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))


class AuthGrantRow(Base):
    """One account's authorization to one client instance.

    A linked browser's extension, or a dashboard session. There is no
    ``status`` column, deliberately. A grant is live when
    ``revoked_at`` is null and neither expiry has passed; a status column
    alongside ``revoked_at`` would create representable-but-impossible rows
    (``status='revoked'`` with a null ``revoked_at``, and the reverse) that
    something would then have to reconcile.

    There is no ``chain_id``. A chain of rotated credentials never outlives its
    grant - re-linking mints a new grant - so ``grant_id`` already is the chain
    identifier; a second column would be a copy of it that can drift.
    """

    __tablename__ = "auth_grants"
    __table_args__ = (
        # The wire identifier names at most one grant, and - load-bearing for
        # account isolation - no second grant row can ever share this id under
        # another account, so a credential row can never be hopped onto a
        # same-id parent in a different account. This constraint is not merely
        # a convenience for the revoke route: it is the only thing that makes
        # the composite primary key's global uniqueness hold, since (unlike
        # orders.id) this primary key is composite rather than single-column.
        UniqueConstraint("id", name="uq_auth_grants_id"),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_reason IS NULL)",
            name="revocation_pair",
        ),
        Index("ix_auth_grants_account_id_client_kind", "account_id", "client_kind"),
    )

    account_id: Mapped[str] = mapped_column(Text, ForeignKey("accounts.id"), primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)

    client_kind: Mapped[AuthClientKind] = mapped_column(AUTH_CLIENT_KIND_ENUM)
    browser_label: Mapped[BrowserLabel] = mapped_column(BROWSER_LABEL_ENUM)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[GrantRevocationReason | None] = mapped_column(
        GRANT_REVOCATION_REASON_ENUM,
    )


class AuthCredentialRow(Base):
    """Every bearer credential in the system, in one table.

    Extension access credentials, extension refresh credentials, and dashboard
    session cookie values all live here, because resolving a presented string
    to an account must be one indexed lookup no matter which route received
    it, and because revoking a grant must be one statement across every
    credential it ever issued.
    """

    __tablename__ = "auth_credentials"
    __table_args__ = (
        # MATCH FULL + NOT DEFERRABLE: rejects a mismatched child at the
        # INSERT/UPDATE statement itself rather than at COMMIT, and does not
        # depend on grant_id staying NOT NULL forever. Never ON UPDATE CASCADE
        # on account_id - a grant does not change accounts, and the cascade
        # variant is the one that silently relabels a subtree.
        ForeignKeyConstraint(
            ["account_id", "grant_id"],
            ["auth_grants.account_id", "auth_grants.id"],
            name="fk_auth_credentials_account_id_auth_grants",
            match="FULL",
            deferrable=False,
        ),
        # The lookup index for an unauthenticated presentation. Global on
        # purpose: this is the one read that legitimately has no account
        # predicate, because it is the read that produces the account.
        UniqueConstraint("credential_hash", name="uq_auth_credentials_credential_hash"),
        CheckConstraint(
            "(kind = 'refresh') = (generation IS NOT NULL)",
            name="generation_for_refresh",
        ),
        CheckConstraint(
            "(rotated_at IS NULL) OR (kind = 'refresh')",
            name="rotation_is_refresh_only",
        ),
        Index("ix_auth_credentials_account_id_grant_id", "account_id", "grant_id"),
        Index("ix_auth_credentials_expires_at", "expires_at"),
    )

    account_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    grant_id: Mapped[str] = mapped_column(Text)

    kind: Mapped[AuthCredentialKind] = mapped_column(AUTH_CREDENTIAL_KIND_ENUM)

    # SHA-256 of the raw credential bytes, hex-encoded. The credential itself
    # exists in plaintext exactly once, in the response body that delivers it.
    # Unsalted and unpeppered on purpose: the input is 256 bits from a
    # cryptographic random source, never a user-chosen secret, so there is no
    # dictionary to defend against and a slow KDF would only cost every
    # authenticated request tens of milliseconds for no security benefit.
    credential_hash: Mapped[str] = mapped_column(Text)

    # Refresh credentials only. Monotonic within a grant, which is what keeps a
    # superseded credential attributable to its grant for reuse detection.
    generation: Mapped[int | None] = mapped_column(Integer)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


ORM_ROWS: tuple[type[Base], ...] = (
    AccountRow,
    OrderRow,
    OrderItemRow,
    ReturnPolicyRow,
    PolicyRuleRow,
    PreferenceSetRow,
    PreferenceValueRow,
    ReturnSummaryRow,
    PairingRequestRow,
    AuthGrantRow,
    AuthCredentialRow,
)

# Every row that is deliberately not account-scoped, and nothing else. A row
# added later lands in neither this set nor app.db.repository.ACCOUNT_COLUMN,
# and the exhaustiveness check built on both fails - which is the point: an
# unscoped table is an exception recorded here, in front of a reviewer, not a
# silent gap in the account-scoped registry.
UNSCOPED_ROWS: Final[frozenset[type[Base]]] = frozenset(
    {AccountRow, PairingRequestRow},
)

__all__: list[str] = [row.__name__ for row in ORM_ROWS] + [
    "AuthClientKind",
    "AuthCredentialKind",
    "BrowserLabel",
    "GrantRevocationReason",
    "PairingStatus",
    "UNSCOPED_ROWS",
]
