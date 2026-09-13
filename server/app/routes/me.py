"""The signed-in account's own profile.

The account is never named by the caller: the repository this handler receives is
already bound to the principal's account, so there is no id to read and no ownership
check to forget.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ScopedRepositoryDep
from app.api.errors import not_found_error

router = APIRouter(tags=["me"])


class AccountProfile(BaseModel):
    """The account profile as it goes on the wire.

    An explicit response model rather than the ORM row, because the row is a storage
    mapping and the wire shape is a contract: the two are allowed to drift, and a column
    added to storage must not become a response field by accident. ``google_subject`` is
    the case that matters — it is stored, it is never exposed, and the only thing keeping
    it off the wire is that this model does not list it.

    ``email``, ``display_name`` and ``avatar_url`` are each nullable.
    """

    id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None


@router.get("/me")
async def read_me(repository: ScopedRepositoryDep) -> AccountProfile:
    """Return the profile of the account this request's principal resolves to."""
    account = await repository.get_account()
    if account is None:
        # An authenticated principal whose account row is gone should not happen, but
        # "absent" and "belongs to someone else" are deliberately indistinguishable here
        # for the same reason they are everywhere else — see not_found_error's docstring.
        raise not_found_error()
    return AccountProfile(
        id=account.id,
        email=account.email,
        display_name=account.display_name,
        avatar_url=account.avatar_url,
    )
