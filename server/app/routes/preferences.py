"""The signed-in account's complete return-method preference set.

There is no partial-patch form in v1: ``PUT`` always replaces the whole set, and an empty
array is a valid replacement (clearing every preference). The stored representation and
the wire representation are allowed to disagree on order — ``ScopedRepository`` neither
sorts on write nor on read, so normalizing the response to the data model's canonical
vocabulary order is this module's job, not the repository's.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Self

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, model_validator

from app.api.auth import AccountScopeDep
from app.api.deps import ScopedRepositoryDep
from app.db.mappers import preference_set_from_row
from app.models import Preference

router = APIRouter(tags=["preferences"])

# dev-note: the canonical order is the Preference enum's own declaration order, which
# mirrors the data-model vocabulary list. Iterating the enum class, rather than hand
# maintaining a second list here, means the two can never drift out of step.
_CANONICAL_ORDER: tuple[Preference, ...] = tuple(Preference)


class PreferencesResponse(BaseModel):
    """The preference set as it goes on the wire.

    An explicit response model rather than the ORM row or the domain record, for the
    same reason ``app/routes/me.py`` builds one: the wire shape is a contract, and
    ``account_id`` here is always the authenticated principal's id, never a value read
    back from storage or supplied by the caller.
    """

    account_id: str
    values: list[Preference]
    # dev-note: null exactly when the account has never written a preference set. The
    # contract's own example always shows a set that has been written, and says nothing
    # about a brand-new account's timestamp; synthesizing "now" (or any other value) for
    # an account with zero writes would assert a write happened when it did not, so a
    # missing set is the one case this field is allowed to be null.
    updated_at: datetime | None


class PreferencesUpdateRequest(BaseModel):
    """The request body for a full preference-set replacement.

    Deliberately not built on ``app.models.domain.DomainModel``: that base's
    ``strict=True`` changes datetime and enum coercion in ways appropriate for an
    internal domain record but not for a wire request body. ``extra="forbid"`` is kept
    here directly, establishing the convention this codebase's first request bodies use
    for rejecting unknown fields.
    """

    model_config = ConfigDict(extra="forbid")

    values: list[Preference]

    @model_validator(mode="after")
    def _reject_duplicate_values(self) -> Self:
        """Reject duplicate values rather than silently collapsing them.

        Mirrors ``PreferenceSet.validate_unique_values`` in the domain layer, but must
        be re-declared here: this model is intentionally not a ``DomainModel``, and the
        wire-layer 422 needs to fire before a domain record is ever constructed.
        """
        if len(self.values) != len(set(self.values)):
            msg = "preference values must be unique"
            raise ValueError(msg)
        return self


def _normalized_values(values: Iterable[Preference]) -> list[Preference]:
    """Return ``values`` deduplicated and ordered per the data-model vocabulary."""
    present = set(values)
    return [preference for preference in _CANONICAL_ORDER if preference in present]


@router.get("/preferences")
async def read_preferences(
    account: AccountScopeDep,
    repository: ScopedRepositoryDep,
) -> PreferencesResponse:
    """Return the signed-in account's complete preference set.

    A brand-new account — one that has never called ``PUT`` — gets ``200`` with an
    empty array rather than ``404``: an absent preference set is a valid, default state,
    not a missing resource.
    """
    row = await repository.get_preference_set()
    if row is None:
        return PreferencesResponse(account_id=account.account_id, values=[], updated_at=None)

    preferences = preference_set_from_row(row)
    return PreferencesResponse(
        account_id=account.account_id,
        values=_normalized_values(preferences.values),
        updated_at=preferences.updated_at,
    )


@router.put("/preferences")
async def replace_preferences(
    body: PreferencesUpdateRequest,
    account: AccountScopeDep,
    repository: ScopedRepositoryDep,
) -> PreferencesResponse:
    """Replace the signed-in account's complete preference set and return the result.

    Array order on the request is ignored — ``replace_preference_set`` stores exactly
    the values it is given with no ordering guarantee, so the response is normalized the
    same way a read is.
    """
    updated_at = datetime.now(UTC)
    row = await repository.replace_preference_set(body.values, updated_at)
    preferences = preference_set_from_row(row)
    return PreferencesResponse(
        account_id=account.account_id,
        values=_normalized_values(preferences.values),
        updated_at=preferences.updated_at,
    )
