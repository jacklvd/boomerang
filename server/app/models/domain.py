"""Validated domain records shared by persistence and future application services."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "timestamp must include a UTC offset"
        raise ValueError(msg)
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_utc_datetime)]
OpaqueId = Annotated[str, StringConstraints(min_length=1)]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeInteger = Annotated[int, Field(ge=0)]
PositiveInteger = Annotated[int, Field(gt=0)]


class DomainModel(BaseModel):
    """Base configuration for uncoerced, closed domain records."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ReturnState(StrEnum):
    """Durable dashboard return states."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    QR_READY = "qr_ready"
    LABEL_READY = "label_ready"
    HANDED_TO_CARRIER = "handed_to_carrier"
    COMPLETE = "complete"


class Preference(StrEnum):
    """Supported return-method ranking preferences."""

    LOWEST_COST = "lowest_cost"
    FASTEST_REFUND_OR_REPLACEMENT = "fastest_refund_or_replacement"
    NO_PRINTER = "no_printer"
    MORE_SUSTAINABLE = "more_sustainable"


class PolicyEligibility(StrEnum):
    """Known return-policy eligibility states."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class FactOrigin(StrEnum):
    """Provenance of a normalized fact."""

    RETAILER_STATED = "retailer_stated"
    DERIVED = "derived"
    USER_CONFIRMED = "user_confirmed"


class ReturnSummaryUpdateSource(StrEnum):
    """Trusted source that published a return summary."""

    SYSTEM_INITIALIZATION = "system_initialization"
    EXTENSION_LIVE_PAGE = "extension_live_page"
    USER_CONFIRMED = "user_confirmed"


class HandoffEvidence(StrEnum):
    """Evidence available for a carrier handoff summary."""

    USER_CONFIRMED = "user_confirmed"
    RETAILER_OBSERVED = "retailer_observed"


class UrgencyLevel(StrEnum):
    """Derived deadline urgency levels used by later projections."""

    EXPIRED = "expired"
    CRITICAL = "critical"
    SOON = "soon"
    LATER = "later"
    UNKNOWN = "unknown"


class Money(DomainModel):
    """A non-negative monetary amount in integer minor units."""

    amount_minor: NonNegativeInteger
    currency: CurrencyCode


class SourcedDate(DomainModel):
    """A date together with its normalized provenance."""

    value: date
    origin: FactOrigin
    confidence: Confidence | None


class SourcedMoney(DomainModel):
    """A monetary fact together with its normalized provenance."""

    value: Money
    origin: FactOrigin
    confidence: Confidence | None


class Account(DomainModel):
    """A Google-linked Boomerang account."""

    id: OpaqueId
    google_subject: NonEmptyString
    email: str | None
    display_name: str | None
    avatar_url: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def validate_avatar_url(self) -> Self:
        """Require an absolute HTTPS avatar URL when one is present."""
        if self.avatar_url is None:
            return self
        parsed = urlsplit(self.avatar_url)
        if parsed.scheme != "https" or not parsed.netloc:
            msg = "avatar_url must be an absolute HTTPS URL"
            raise ValueError(msg)
        return self


class Order(DomainModel):
    """A normalized retailer order owned by one account."""

    id: OpaqueId
    account_id: OpaqueId
    retailer_key: NonEmptyString
    retailer_name: NonEmptyString
    retailer_order_reference: str | None
    ordered_on: date | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class OrderItem(DomainModel):
    """One return-candidate row within a normalized order."""

    id: OpaqueId
    order_id: OpaqueId
    description: NonEmptyString
    variant: str | None
    quantity: PositiveInteger
    price: Money | None
    delivered_on: date | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class PolicyRule(DomainModel):
    """A concise normalized return-policy fact."""

    id: OpaqueId
    text: NonEmptyString
    origin: FactOrigin
    confidence: Confidence | None


class ReturnPolicy(DomainModel):
    """The current normalized return policy for one item."""

    item_id: OpaqueId
    eligibility: PolicyEligibility
    return_by: SourcedDate | None
    fee: SourcedMoney | None
    rules: tuple[PolicyRule, ...]
    version: PositiveInteger
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def validate_rule_ids(self) -> Self:
        """Reject duplicate rule identifiers within the current policy version."""
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            msg = "policy rule identifiers must be unique within a policy version"
            raise ValueError(msg)
        return self


class PreferenceSet(DomainModel):
    """The complete, unordered preference set for an account."""

    account_id: OpaqueId
    values: tuple[Preference, ...]
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def validate_unique_values(self) -> Self:
        """Reject duplicates rather than silently treating array order as priority."""
        if len(self.values) != len(set(self.values)):
            msg = "preference values must be unique"
            raise ValueError(msg)
        return self


class ReturnSummary(DomainModel):
    """The minimal durable return milestone for one item."""

    item_id: OpaqueId
    state: ReturnState
    update_source: ReturnSummaryUpdateSource
    handoff_evidence: HandoffEvidence | None
    observed_at: UtcDatetime
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def validate_source_and_evidence(self) -> Self:
        """Enforce intrinsic initialization and carrier-evidence invariants."""
        if (
            self.update_source is ReturnSummaryUpdateSource.SYSTEM_INITIALIZATION
            and self.state is not ReturnState.NOT_STARTED
        ):
            msg = "system_initialization may create only a not_started summary"
            raise ValueError(msg)
        if self.state is ReturnState.HANDED_TO_CARRIER:
            if self.handoff_evidence is None:
                msg = "handed_to_carrier requires handoff evidence"
                raise ValueError(msg)
        elif self.handoff_evidence is not None:
            msg = "handoff evidence is valid only for handed_to_carrier"
            raise ValueError(msg)
        return self
