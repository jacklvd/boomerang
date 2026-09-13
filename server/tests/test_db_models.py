from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect

from app.db.base import Base
from app.db.models import (
    ORM_ROWS,
    UNSCOPED_ROWS,
    AccountRow,
    AuthGrantRow,
    OrderRow,
    PairingRequestRow,
)

EXPECTED_TABLES = {
    "accounts",
    "orders",
    "order_items",
    "return_policies",
    "policy_rules",
    "preference_sets",
    "preference_values",
    "return_summaries",
    "pairing_requests",
    "auth_grants",
    "auth_credentials",
}


def test_metadata_contains_only_scoped_domain_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert {row.__tablename__ for row in ORM_ROWS} == EXPECTED_TABLES


def test_orders_primary_key_is_single_column_and_globally_unique() -> None:
    """orders.id anchors account isolation; see design/boomerang-account-scoping.md section 5.1.

    If this fails, two accounts can share an order_id, and a composite-keyed child can be UPDATEd
    from one account to another with its foreign key satisfied throughout.
    """
    pk_columns = [column.name for column in inspect(OrderRow).primary_key]
    assert pk_columns == ["id"]


def test_primary_key_one_to_one_boundaries_match_contract():
    # Column ORDER matters here: account_id must lead every composite primary key, since
    # an ORM identity lookup (session.get) matches tuple position against declaration
    # order, not name - a reversed tuple silently returns None instead of raising.
    assert [column.name for column in Base.metadata.tables["order_items"].primary_key] == [
        "account_id",
        "id",
    ]
    assert [column.name for column in Base.metadata.tables["return_policies"].primary_key] == [
        "account_id",
        "item_id",
    ]
    assert [column.name for column in Base.metadata.tables["policy_rules"].primary_key] == [
        "account_id",
        "item_id",
        "id",
    ]
    assert [column.name for column in Base.metadata.tables["return_summaries"].primary_key] == [
        "account_id",
        "item_id",
    ]
    assert [column.name for column in Base.metadata.tables["preference_sets"].primary_key] == [
        "account_id"
    ]
    assert {column.name for column in Base.metadata.tables["preference_values"].primary_key} == {
        "account_id",
        "value",
    }
    assert [column.name for column in Base.metadata.tables["auth_grants"].primary_key] == [
        "account_id",
        "id",
    ]
    assert [column.name for column in Base.metadata.tables["auth_credentials"].primary_key] == [
        "account_id",
        "id",
    ]


def test_every_foreign_key_avoids_unapproved_delete_cascade():
    foreign_keys = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert foreign_keys
    assert all(constraint.ondelete is None for constraint in foreign_keys)


def test_database_constraints_cover_intrinsic_invariants():
    check_names = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_order_items_quantity_positive",
        "ck_order_items_price_non_negative",
        "ck_order_items_price_columns_together",
        "ck_return_policies_version_positive",
        "ck_return_policies_return_by_columns_together",
        "ck_return_policies_fee_columns_together",
        "ck_return_summaries_system_initialization_state",
        "ck_return_summaries_handoff_evidence_state",
        "ck_auth_grants_revocation_pair",
        "ck_auth_credentials_generation_for_refresh",
        "ck_auth_credentials_rotation_is_refresh_only",
    } <= check_names


def test_settled_uniqueness_constraints_are_present():
    accounts = Base.metadata.tables["accounts"]
    orders = Base.metadata.tables["orders"]
    order_items = Base.metadata.tables["order_items"]

    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["google_subject"]
        for constraint in accounts.constraints
    )
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns]
        == ["account_id", "retailer_key", "retailer_order_reference"]
        for constraint in orders.constraints
    )
    # This is the target a composite child foreign key points at, and the reason
    # orders.id can stay a single-column primary key: see
    # design/boomerang-account-scoping.md section 5.1.
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["account_id", "id"]
        for constraint in orders.constraints
    )
    # order_items.id stays globally unique so the wire identifier still names at most
    # one item, even though it is no longer the table's primary key on its own.
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["id"]
        for constraint in order_items.constraints
    )


def test_composite_foreign_keys_are_match_full_and_not_deferrable():
    composite_foreign_keys = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and len(constraint.columns) > 1
    ]
    expected = {
        "fk_order_items_account_id_orders",
        "fk_return_policies_account_id_order_items",
        "fk_policy_rules_account_id_return_policies",
        "fk_return_summaries_account_id_order_items",
        "fk_auth_credentials_account_id_auth_grants",
    }
    assert {constraint.name for constraint in composite_foreign_keys} == expected
    for constraint in composite_foreign_keys:
        assert next(column.name for column in constraint.columns) == "account_id"
        assert constraint.match == "FULL"
        assert constraint.deferrable is False
        # Never ON UPDATE CASCADE on account_id: it would silently relabel a whole
        # subtree into another account. See design/boomerang-account-scoping.md section 5.
        assert constraint.onupdate is None
        assert constraint.ondelete is None


def test_database_schema_has_no_sensitive_or_deferred_columns():
    column_names = {
        column.name for table in Base.metadata.tables.values() for column in table.columns
    }
    prohibited = {
        "dom",
        "qr_code",
        "label",
        "address",
        "barcode",
        "protected_url",
        "calendar_token",
        "pickup_confirmation",
    }
    assert column_names.isdisjoint(prohibited)


def test_auth_grants_id_carries_its_own_global_uniqueness_constraint():
    """auth_grants has a composite primary key, so nothing else makes id globally unique.

    A credential row's foreign key targets (account_id, grant_id); without a separate
    global constraint on id alone, a second grant could reuse another account's grant id
    and the composite foreign key would still be satisfiable, which defeats account
    isolation entirely.
    """
    auth_grants = Base.metadata.tables["auth_grants"]
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["id"]
        and constraint.name == "uq_auth_grants_id"
        for constraint in auth_grants.constraints
    )


def test_auth_credentials_credential_hash_is_globally_unique():
    auth_credentials = Base.metadata.tables["auth_credentials"]
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["credential_hash"]
        for constraint in auth_credentials.constraints
    )


def test_pairing_requests_carries_no_account_scoped_primary_key():
    """This table is deliberately outside the account-scoped primary key scheme."""
    pairing_requests = Base.metadata.tables["pairing_requests"]

    assert [column.name for column in pairing_requests.primary_key] == ["id"]
    assert pairing_requests.columns["account_id"].nullable is True


def test_pairing_requests_carries_its_lifecycle_check_constraints_and_partial_unique_index():
    pairing_requests = Base.metadata.tables["pairing_requests"]
    check_names = {
        constraint.name
        for constraint in pairing_requests.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "ck_pairing_requests_account_binding",
        "ck_pairing_requests_redeemed_at_set",
    } <= check_names

    partial_unique_indexes = [
        index
        for index in pairing_requests.indexes
        if index.unique and index.dialect_options["postgresql"]["where"] is not None
    ]
    assert any(
        [column.name for column in index.columns] == ["user_code"]
        for index in partial_unique_indexes
    )


def test_unscoped_rows_registry_names_exactly_the_deliberately_unscoped_tables():
    """A row added to ORM_ROWS later must land in this set or the exhaustiveness check fails.

    See app.db.repository's registry, which is compared against this set for exact
    equality rather than subset - an unscoped table is meant to be a recorded exception,
    never a silent gap.
    """
    assert {AccountRow, PairingRequestRow} == UNSCOPED_ROWS
    assert AuthGrantRow not in UNSCOPED_ROWS
