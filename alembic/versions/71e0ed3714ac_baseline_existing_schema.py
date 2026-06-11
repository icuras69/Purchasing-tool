"""baseline existing schema

Revision ID: 71e0ed3714ac
Revises:
Create Date: 2026-05-25 13:42:22.735626+00:00

This baseline originally represented an already-existing local schema.  Render
staging starts from an empty PostgreSQL database, so the baseline must create
the pre-Alembic core tables that later migrations assume already exist.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "71e0ed3714ac"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _create_index(name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=500), nullable=True),
            sa.Column("phone", sa.String(length=255), nullable=True),
            sa.Column("website", sa.String(length=255), nullable=True),
            sa.Column("contact_method", sa.String(length=100), nullable=True),
            sa.Column("payment_terms", sa.String(length=255), nullable=True),
            sa.Column("lead_time_raw", sa.String(length=100), nullable=True),
            sa.Column("lead_time_days", sa.Integer(), nullable=True),
            sa.Column("lead_time_min_days", sa.Integer(), nullable=True),
            sa.Column("lead_time_max_days", sa.Integer(), nullable=True),
            sa.Column("notes", sa.String(length=1000), nullable=True),
            sa.Column("active_skus", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lead_time_needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="suppliers_name_key"),
            sa.UniqueConstraint("normalized_name", name="suppliers_normalized_name_key"),
        )
        _create_index("ix_suppliers_id", "suppliers", ["id"])
        _create_index("ix_suppliers_normalized_name", "suppliers", ["normalized_name"], unique=True)

    if not _has_table("products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_key", sa.String(length=255), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("canonical_description", sa.String(length=255), nullable=True),
            sa.Column("barcode", sa.String(length=255), nullable=True),
            sa.Column("supplier", sa.String(length=255), nullable=True),
            sa.Column("seasonality_tag", sa.String(length=100), nullable=True),
            sa.Column("product_type", sa.String(length=50), nullable=False, server_default="inventory"),
            sa.Column("is_non_inventory", sa.Boolean(), nullable=True, server_default=sa.false()),
            sa.Column("current_stock", sa.Float(), nullable=False, server_default="0"),
            sa.Column("safety_stock", sa.Float(), nullable=False, server_default="0"),
            sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_order_qty", sa.Float(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_key", name="products_source_key_key"),
        )
        _create_index("ix_products_id", "products", ["id"])
        _create_index("ix_products_source_key", "products", ["source_key"], unique=True)
        _create_index("ix_products_barcode", "products", ["barcode"])

    if not _has_table("supplier_aliases"):
        op.create_table(
            "supplier_aliases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("alias_name", sa.String(length=255), nullable=False),
            sa.Column("normalized_alias_name", sa.String(length=255), nullable=False),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("alias_name", name="supplier_aliases_alias_name_key"),
            sa.UniqueConstraint("normalized_alias_name", name="supplier_aliases_normalized_alias_name_key"),
        )
        _create_index("ix_supplier_aliases_id", "supplier_aliases", ["id"])
        _create_index("ix_supplier_aliases_supplier_id", "supplier_aliases", ["supplier_id"])
        _create_index(
            "ix_supplier_aliases_normalized_alias_name",
            "supplier_aliases",
            ["normalized_alias_name"],
            unique=True,
        )

    if not _has_table("product_master_items"):
        op.create_table(
            "product_master_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("supplier_name_raw", sa.String(length=255), nullable=True),
            sa.Column("warehouse", sa.String(length=255), nullable=True),
            sa.Column("cost_price", sa.Float(), nullable=True),
            sa.Column("sales_price", sa.Float(), nullable=True),
            sa.Column("total_cost", sa.Float(), nullable=True),
            sa.Column("total_sales", sa.Float(), nullable=True),
            sa.Column("tax_code", sa.String(length=100), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("match_status", sa.String(length=50), nullable=False, server_default="unmatched"),
            sa.Column("match_method", sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku", name="product_master_items_sku_key"),
        )
        _create_index("ix_product_master_items_id", "product_master_items", ["id"])
        _create_index("ix_product_master_items_sku", "product_master_items", ["sku"], unique=True)
        _create_index("ix_product_master_items_product_id", "product_master_items", ["product_id"])
        _create_index("ix_product_master_items_supplier_id", "product_master_items", ["supplier_id"])

    if not _has_table("inventory_snapshots"):
        op.create_table(
            "inventory_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("stock_on_hand", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        _create_index("ix_inventory_snapshots_id", "inventory_snapshots", ["id"])
        _create_index("ix_inventory_snapshots_product_id", "inventory_snapshots", ["product_id"])

    if not _has_table("inventory_positions"):
        op.create_table(
            "inventory_positions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("source_system", sa.String(length=50), nullable=False, server_default="orderpro"),
            sa.Column("location_code", sa.String(length=100), nullable=True),
            sa.Column("location_name", sa.String(length=255), nullable=True),
            sa.Column("on_hand", sa.Float(), nullable=False, server_default="0"),
            sa.Column("allocated", sa.Float(), nullable=False, server_default="0"),
            sa.Column("incoming", sa.Float(), nullable=False, server_default="0"),
            sa.Column("available", sa.Float(), nullable=False, server_default="0"),
            sa.Column("incoming_eta", sa.Date(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "product_id",
                "source_system",
                "location_code",
                name="uq_inventory_positions_product_source_location",
            ),
        )
        _create_index("ix_inventory_positions_id", "inventory_positions", ["id"])
        _create_index("ix_inventory_positions_product_id", "inventory_positions", ["product_id"])

    if not _has_table("usage_history"):
        op.create_table(
            "usage_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("qty_used", sa.Float(), nullable=False, server_default="0"),
            sa.Column("qty_returned", sa.Float(), nullable=False, server_default="0"),
            sa.Column("net_qty", sa.Float(), nullable=False, server_default="0"),
            sa.Column("gross_revenue", sa.Float(), nullable=False, server_default="0"),
            sa.Column("source_system", sa.String(length=50), nullable=False, server_default="historical_sales_excel"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("product_id", "date", "source_system", name="uq_usage_history_product_date_source"),
        )
        _create_index("ix_usage_history_id", "usage_history", ["id"])
        _create_index("ix_usage_history_product_id", "usage_history", ["product_id"])
        _create_index("ix_usage_history_date", "usage_history", ["date"])

    if not _has_table("sales_history_raw"):
        op.create_table(
            "sales_history_raw",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_workbook", sa.String(length=255), nullable=False),
            sa.Column("source_sheet", sa.String(length=20), nullable=False),
            sa.Column("source_row_number", sa.Integer(), nullable=False),
            sa.Column("customer_name", sa.String(length=255), nullable=True),
            sa.Column("barcode_raw", sa.String(length=255), nullable=True),
            sa.Column("barcode_clean", sa.String(length=255), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("batch", sa.String(length=255), nullable=True),
            sa.Column("invoice", sa.String(length=100), nullable=True),
            sa.Column("txn_date", sa.Date(), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("vat_rate", sa.Float(), nullable=True),
            sa.Column("gross", sa.Float(), nullable=True),
            sa.Column("code", sa.String(length=255), nullable=True),
            sa.Column("sales_person", sa.String(length=255), nullable=True),
            sa.Column("purchase_order_ref", sa.String(length=255), nullable=True),
            sa.Column("nett", sa.Float(), nullable=True),
            sa.Column("vat", sa.Float(), nullable=True),
            sa.Column("source_key", sa.String(length=255), nullable=False),
            sa.Column("row_type", sa.String(length=50), nullable=False, server_default="inventory"),
            sa.Column("is_non_inventory", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_return", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "source_workbook",
                "source_sheet",
                "source_row_number",
                name="uq_sales_history_raw_source_row",
            ),
        )
        _create_index("ix_sales_history_raw_id", "sales_history_raw", ["id"])
        _create_index("ix_sales_history_raw_source_sheet", "sales_history_raw", ["source_sheet"])
        _create_index("ix_sales_history_raw_barcode_clean", "sales_history_raw", ["barcode_clean"])
        _create_index("ix_sales_history_raw_txn_date", "sales_history_raw", ["txn_date"])
        _create_index("ix_sales_history_raw_source_key", "sales_history_raw", ["source_key"])
        _create_index("ix_sales_history_raw_product_id", "sales_history_raw", ["product_id"])

    if not _has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("order_date", sa.Date(), nullable=False),
            sa.Column("delivery_date", sa.Date(), nullable=True),
            sa.Column("qty_ordered", sa.Float(), nullable=False),
            sa.Column("unit_cost", sa.Float(), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        _create_index("ix_purchase_orders_id", "purchase_orders", ["id"])
        _create_index("ix_purchase_orders_product_id", "purchase_orders", ["product_id"])

    if not _has_table("recommendations"):
        op.create_table(
            "recommendations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            sa.Column("recommended_order_date", sa.Date(), nullable=True),
            sa.Column("recommended_qty", sa.Float(), nullable=False),
            sa.Column("risk_level", sa.String(length=50), nullable=False, server_default="low"),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        _create_index("ix_recommendations_id", "recommendations", ["id"])
        _create_index("ix_recommendations_product_id", "recommendations", ["product_id"])


def downgrade() -> None:
    for table_name in (
        "recommendations",
        "purchase_orders",
        "sales_history_raw",
        "usage_history",
        "inventory_positions",
        "inventory_snapshots",
        "product_master_items",
        "supplier_aliases",
        "products",
        "suppliers",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)
