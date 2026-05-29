"""add orderpro source of truth fields

Revision ID: d4f7a2c9e8b1
Revises: c8f2a91d4b77
Create Date: 2026-05-29 00:00:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f7a2c9e8b1"
down_revision: Union[str, None] = "c8f2a91d4b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("orderpro_id", sa.String(length=100), nullable=True))
    op.add_column("suppliers", sa.Column("orderpro_code", sa.String(length=100), nullable=True))
    op.add_column("suppliers", sa.Column("source_system", sa.String(length=50), nullable=True))
    op.add_column("suppliers", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("suppliers", sa.Column("last_synced_at", sa.DateTime(), nullable=True))
    op.create_index("ix_suppliers_orderpro_id", "suppliers", ["orderpro_id"], unique=True)
    op.create_index("ix_suppliers_orderpro_code", "suppliers", ["orderpro_code"], unique=True)

    op.add_column("products", sa.Column("source_system", sa.String(length=50), nullable=True))
    op.add_column("products", sa.Column("orderpro_id", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("orderpro_sku", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("supplier_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("supplier_sku", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("description", sa.String(length=1000), nullable=True))
    op.add_column("products", sa.Column("brand", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("category", sa.String(length=255), nullable=True))
    op.add_column("products", sa.Column("uom", sa.String(length=50), nullable=True))
    op.add_column("products", sa.Column("weight_kg", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("cost_price", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("sell_price", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("hs_code", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("country_of_origin", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.String(length=1000), nullable=True))
    op.add_column("products", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("products", sa.Column("last_synced_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_products_supplier_id_suppliers", "products", "suppliers", ["supplier_id"], ["id"])
    op.create_index("ix_products_orderpro_id", "products", ["orderpro_id"], unique=True)
    op.create_index("ix_products_orderpro_sku", "products", ["orderpro_sku"], unique=True)
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("orderpro_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warehouses_id", "warehouses", ["id"], unique=False)
    op.create_index("ix_warehouses_orderpro_id", "warehouses", ["orderpro_id"], unique=True)
    op.create_index("ix_warehouses_code", "warehouses", ["code"], unique=False)

    op.add_column("inventory_positions", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    op.add_column("inventory_positions", sa.Column("orderpro_inventory_id", sa.String(length=100), nullable=True))
    op.add_column("inventory_positions", sa.Column("orderpro_product_id", sa.String(length=100), nullable=True))
    op.add_column("inventory_positions", sa.Column("orderpro_warehouse_id", sa.String(length=100), nullable=True))
    op.add_column("inventory_positions", sa.Column("location_id", sa.String(length=100), nullable=True))
    op.add_column("inventory_positions", sa.Column("lot_id", sa.String(length=100), nullable=True))
    op.add_column("inventory_positions", sa.Column("lot", sa.String(length=255), nullable=True))
    op.add_column(
        "inventory_positions",
        sa.Column("quantity_on_hand", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("inventory_positions", sa.Column("quantity_available", sa.Float(), nullable=True))
    op.add_column("inventory_positions", sa.Column("quantity_allocated", sa.Float(), nullable=True))
    op.add_column("inventory_positions", sa.Column("quantity_incoming", sa.Float(), nullable=True))
    op.add_column(
        "inventory_positions",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "inventory_positions",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column(
        "inventory_positions",
        "last_synced_at",
        existing_type=sa.DateTime(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_inventory_positions_warehouse_id_warehouses",
        "inventory_positions",
        "warehouses",
        ["warehouse_id"],
        ["id"],
    )
    op.create_index("ix_inventory_positions_warehouse_id", "inventory_positions", ["warehouse_id"], unique=False)
    op.create_index(
        "ix_inventory_positions_orderpro_inventory_id",
        "inventory_positions",
        ["orderpro_inventory_id"],
        unique=True,
    )
    op.create_index(
        "ix_inventory_positions_orderpro_product_id",
        "inventory_positions",
        ["orderpro_product_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_positions_orderpro_warehouse_id",
        "inventory_positions",
        ["orderpro_warehouse_id"],
        unique=False,
    )
    op.create_index("ix_inventory_positions_location_id", "inventory_positions", ["location_id"], unique=False)
    op.create_index("ix_inventory_positions_lot_id", "inventory_positions", ["lot_id"], unique=False)
    op.create_index(
        "ix_inventory_positions_product_warehouse_location_lot",
        "inventory_positions",
        ["product_id", "warehouse_id", "location_id", "lot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_positions_product_warehouse_location_lot", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_lot_id", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_location_id", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_orderpro_warehouse_id", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_orderpro_product_id", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_orderpro_inventory_id", table_name="inventory_positions")
    op.drop_index("ix_inventory_positions_warehouse_id", table_name="inventory_positions")
    op.drop_constraint(
        "fk_inventory_positions_warehouse_id_warehouses",
        "inventory_positions",
        type_="foreignkey",
    )
    op.alter_column("inventory_positions", "last_synced_at", existing_type=sa.DateTime(), nullable=False)
    op.drop_column("inventory_positions", "updated_at")
    op.drop_column("inventory_positions", "created_at")
    op.drop_column("inventory_positions", "quantity_incoming")
    op.drop_column("inventory_positions", "quantity_allocated")
    op.drop_column("inventory_positions", "quantity_available")
    op.drop_column("inventory_positions", "quantity_on_hand")
    op.drop_column("inventory_positions", "lot")
    op.drop_column("inventory_positions", "lot_id")
    op.drop_column("inventory_positions", "location_id")
    op.drop_column("inventory_positions", "orderpro_warehouse_id")
    op.drop_column("inventory_positions", "orderpro_product_id")
    op.drop_column("inventory_positions", "orderpro_inventory_id")
    op.drop_column("inventory_positions", "warehouse_id")

    op.drop_index("ix_warehouses_code", table_name="warehouses")
    op.drop_index("ix_warehouses_orderpro_id", table_name="warehouses")
    op.drop_index("ix_warehouses_id", table_name="warehouses")
    op.drop_table("warehouses")

    op.drop_index("ix_products_supplier_id", table_name="products")
    op.drop_index("ix_products_orderpro_sku", table_name="products")
    op.drop_index("ix_products_orderpro_id", table_name="products")
    op.drop_constraint("fk_products_supplier_id_suppliers", "products", type_="foreignkey")
    op.drop_column("products", "last_synced_at")
    op.drop_column("products", "is_active")
    op.drop_column("products", "image_url")
    op.drop_column("products", "country_of_origin")
    op.drop_column("products", "hs_code")
    op.drop_column("products", "sell_price")
    op.drop_column("products", "cost_price")
    op.drop_column("products", "weight_kg")
    op.drop_column("products", "uom")
    op.drop_column("products", "category")
    op.drop_column("products", "brand")
    op.drop_column("products", "description")
    op.drop_column("products", "supplier_sku")
    op.drop_column("products", "supplier_id")
    op.drop_column("products", "orderpro_sku")
    op.drop_column("products", "orderpro_id")
    op.drop_column("products", "source_system")

    op.drop_index("ix_suppliers_orderpro_code", table_name="suppliers")
    op.drop_index("ix_suppliers_orderpro_id", table_name="suppliers")
    op.drop_column("suppliers", "last_synced_at")
    op.drop_column("suppliers", "is_active")
    op.drop_column("suppliers", "source_system")
    op.drop_column("suppliers", "orderpro_code")
    op.drop_column("suppliers", "orderpro_id")
