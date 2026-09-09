from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.db.models import ORM_ROWS

EXPECTED_TABLES = {
    "accounts",
    "orders",
    "order_items",
    "return_policies",
    "policy_rules",
    "preference_sets",
    "preference_values",
    "return_summaries",
}


def test_metadata_contains_only_scoped_domain_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert {row.__tablename__ for row in ORM_ROWS} == EXPECTED_TABLES


def test_primary_key_one_to_one_boundaries_match_contract():
    assert [column.name for column in Base.metadata.tables["return_policies"].primary_key] == [
        "item_id"
    ]
    assert [column.name for column in Base.metadata.tables["return_summaries"].primary_key] == [
        "item_id"
    ]
    assert [column.name for column in Base.metadata.tables["preference_sets"].primary_key] == [
        "account_id"
    ]
    assert {column.name for column in Base.metadata.tables["preference_values"].primary_key} == {
        "account_id",
        "value",
    }


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
    } <= check_names


def test_settled_uniqueness_constraints_are_present():
    accounts = Base.metadata.tables["accounts"]
    orders = Base.metadata.tables["orders"]

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
