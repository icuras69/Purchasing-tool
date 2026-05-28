from dataclasses import dataclass
from math import ceil
from datetime import datetime

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.supplier import Supplier
from app.services.forecasting import build_forecast


DRAFT_STATUS = "draft"
VALID_MAPPING_STATUSES = {"confirmed", "matched"}
REJECTED_MAPPING_STATUS = "rejected"


@dataclass
class SkippedProduct:
    product_id: int
    product_name: str | None
    reason: str


@dataclass
class DraftPurchaseOrderResult:
    purchase_order: PurchaseOrder
    created_line_count: int
    skipped_products: list[SkippedProduct]


class DraftPurchaseOrderError(Exception):
    def __init__(self, message: str, skipped_products: list[SkippedProduct] | None = None):
        super().__init__(message)
        self.message = message
        self.skipped_products = skipped_products or []


def create_draft_purchase_order_from_products(
    db: Session,
    *,
    supplier_id: int,
    product_ids: list[int],
    created_by: str | None = None,
    notes: str | None = None,
) -> DraftPurchaseOrderResult:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise DraftPurchaseOrderError("Supplier not found.")

    skipped_products: list[SkippedProduct] = []
    line_inputs: list[tuple[Product, ProductSupplier, float]] = []

    for product_id in product_ids:
        product = load_product_for_draft(db, product_id)
        if not product:
            skipped_products.append(
                SkippedProduct(product_id=product_id, product_name=None, reason="Product not found.")
            )
            continue

        product_supplier, skip_reason = select_product_supplier_for_po(product, supplier_id)
        if not product_supplier:
            skipped_products.append(
                SkippedProduct(product_id=product.id, product_name=product.name, reason=skip_reason)
            )
            continue

        quantity = suggested_purchase_quantity(db, product, product_supplier)
        if quantity <= 0:
            skipped_products.append(
                SkippedProduct(
                    product_id=product.id,
                    product_name=product.name,
                    reason="Calculated quantity was not greater than zero.",
                )
            )
            continue

        line_inputs.append((product, product_supplier, quantity))

    if not line_inputs:
        raise DraftPurchaseOrderError(
            "No valid purchase order lines could be created.",
            skipped_products=skipped_products,
        )

    now = datetime.utcnow()
    po = PurchaseOrder(
        supplier_id=supplier_id,
        status=DRAFT_STATUS,
        created_at=now,
        updated_at=now,
        notes=notes,
        created_by=created_by,
    )
    db.add(po)
    db.flush()

    for _product, product_supplier, quantity in line_inputs:
        po.lines.append(snapshot_purchase_order_line(po, product_supplier, quantity))

    db.flush()
    recalculate_purchase_order_total(po)
    po.updated_at = now
    db.commit()
    db.refresh(po)

    return DraftPurchaseOrderResult(
        purchase_order=po,
        created_line_count=len(line_inputs),
        skipped_products=skipped_products,
    )


def load_product_for_draft(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.master_items),
            selectinload(Product.inventory_positions),
        )
        .filter(Product.id == product_id)
        .first()
    )


def select_product_supplier_for_po(
    product: Product,
    supplier_id: int,
) -> tuple[ProductSupplier | None, str]:
    supplier_mappings = [
        mapping for mapping in product.product_suppliers if mapping.supplier_id == supplier_id
    ]
    if not supplier_mappings:
        if product.product_suppliers:
            return None, "ProductSupplier mapping belongs to a different supplier."
        return None, "No ProductSupplier mapping exists for this product."

    usable_mappings = [
        mapping for mapping in supplier_mappings if mapping.match_status != REJECTED_MAPPING_STATUS
    ]
    if not usable_mappings:
        return None, "ProductSupplier mapping is rejected."

    preferred = next(
        (
            mapping
            for mapping in usable_mappings
            if mapping.is_preferred and mapping.match_status in VALID_MAPPING_STATUSES
        ),
        None,
    )
    if preferred:
        return preferred, ""

    confirmed_or_matched = [
        mapping for mapping in usable_mappings if mapping.match_status in VALID_MAPPING_STATUSES
    ]
    if confirmed_or_matched:
        return sorted(confirmed_or_matched, key=lambda mapping: mapping.id or 0)[0], ""

    return None, "No confirmed or matched ProductSupplier mapping exists for this supplier."


def suggested_purchase_quantity(
    db: Session,
    product: Product,
    product_supplier: ProductSupplier,
) -> float:
    forecast = build_forecast(db, product)
    quantity = float(forecast.get("recommended_qty") or 0)

    if quantity <= 0:
        quantity = float(product_supplier.minimum_order_quantity or 1)

    if product_supplier.minimum_order_quantity and quantity < product_supplier.minimum_order_quantity:
        quantity = float(product_supplier.minimum_order_quantity)

    if product_supplier.pack_size and product_supplier.pack_size > 0:
        pack_size = float(product_supplier.pack_size)
        quantity = ceil(quantity / pack_size) * pack_size

    return float(ceil(quantity)) if quantity > 0 else 0.0


def snapshot_purchase_order_line(
    po: PurchaseOrder,
    product_supplier: ProductSupplier,
    quantity: float,
) -> PurchaseOrderLine:
    line_total = None
    if product_supplier.purchase_price is not None:
        line_total = round(quantity * product_supplier.purchase_price, 2)

    return PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_supplier.product_id,
        product_supplier_id=product_supplier.id,
        supplier_sku=product_supplier.supplier_sku,
        supplier_product_name=product_supplier.supplier_product_name,
        quantity=quantity,
        unit_cost=product_supplier.purchase_price,
        currency=product_supplier.currency,
        line_total=line_total,
        minimum_order_quantity=product_supplier.minimum_order_quantity,
        pack_size=product_supplier.pack_size,
        lead_time_days=product_supplier.lead_time_days,
        notes="Drafted from product recommendation.",
    )


def recalculate_purchase_order_total(po: PurchaseOrder) -> None:
    totals = [line.line_total for line in po.lines if line.line_total is not None]
    po.total_amount = round(sum(totals), 2) if totals else None
    currencies = {line.currency for line in po.lines if line.currency}
    if len(currencies) == 1:
        po.currency = currencies.pop()
