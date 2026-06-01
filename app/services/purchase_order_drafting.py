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
REJECTED_MAPPING_STATUS = "rejected"


@dataclass
class SkippedProduct:
    product_id: int
    product_name: str | None
    reason: str


@dataclass
class DraftPurchaseOrderResult:
    purchase_orders: list[PurchaseOrder]
    created_line_count: int
    skipped_products: list[SkippedProduct]
    grouped_by_supplier: dict[int, int]

    @property
    def purchase_order(self) -> PurchaseOrder:
        return self.purchase_orders[0]


class DraftPurchaseOrderError(Exception):
    def __init__(self, message: str, skipped_products: list[SkippedProduct] | None = None):
        super().__init__(message)
        self.message = message
        self.skipped_products = skipped_products or []


def create_draft_purchase_order_from_products(
    db: Session,
    *,
    product_ids: list[int],
    supplier_id: int | None = None,
    created_by: str | None = None,
    notes: str | None = None,
    only_reorder_needed: bool = False,
) -> DraftPurchaseOrderResult:
    if supplier_id is not None and not db.get(Supplier, supplier_id):
        raise DraftPurchaseOrderError("Supplier not found.")

    skipped_products: list[SkippedProduct] = []
    grouped_line_inputs: dict[int, list[tuple[Product, float]]] = {}

    for product_id in product_ids:
        product = load_product_for_draft(db, product_id)
        if not product:
            skipped_products.append(
                SkippedProduct(product_id=product_id, product_name=None, reason="Product not found.")
            )
            continue

        skip_reason = validate_orderpro_product_supplier(product, supplier_id)
        if skip_reason:
            skipped_products.append(
                SkippedProduct(product_id=product.id, product_name=product.name, reason=skip_reason)
            )
            continue

        quantity = suggested_purchase_quantity(db, product, only_reorder_needed=only_reorder_needed)
        if quantity <= 0:
            skipped_products.append(
                SkippedProduct(
                    product_id=product.id,
                    product_name=product.name,
                    reason="No reorder recommendation for this product.",
                )
            )
            continue

        grouped_line_inputs.setdefault(product.supplier_id, []).append((product, quantity))

    if not grouped_line_inputs:
        raise DraftPurchaseOrderError(
            "No valid purchase order lines could be created.",
            skipped_products=skipped_products,
        )

    now = datetime.utcnow()
    purchase_orders: list[PurchaseOrder] = []
    created_line_count = 0
    grouped_by_supplier: dict[int, int] = {}

    for group_supplier_id, line_inputs in grouped_line_inputs.items():
        po = PurchaseOrder(
            supplier_id=group_supplier_id,
            status=DRAFT_STATUS,
            created_at=now,
            updated_at=now,
            notes=notes,
            created_by=created_by,
        )
        db.add(po)
        db.flush()

        for product, quantity in line_inputs:
            po.lines.append(snapshot_purchase_order_line_from_product(po, product, quantity))
            created_line_count += 1

        db.flush()
        recalculate_purchase_order_total(po)
        po.updated_at = now
        purchase_orders.append(po)
        grouped_by_supplier[group_supplier_id] = len(line_inputs)

    db.commit()
    for po in purchase_orders:
        db.refresh(po)

    return DraftPurchaseOrderResult(
        purchase_orders=purchase_orders,
        created_line_count=created_line_count,
        skipped_products=skipped_products,
        grouped_by_supplier=grouped_by_supplier,
    )


def load_product_for_draft(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.inventory_positions),
        )
        .filter(Product.id == product_id)
        .first()
    )


def validate_orderpro_product_supplier(product: Product, supplier_id: int | None = None) -> str | None:
    if product.supplier_id is None:
        return "Product is missing an OrderPro supplier mapping."
    if supplier_id is not None and product.supplier_id != supplier_id:
        return "Product belongs to a different OrderPro supplier."
    return None


def suggested_purchase_quantity(
    db: Session,
    product: Product,
    *,
    only_reorder_needed: bool = False,
) -> float:
    forecast = build_forecast(db, product)
    quantity = float(forecast.get("recommended_qty") or 0)

    if only_reorder_needed and quantity <= 0:
        return 0.0

    if quantity <= 0:
        quantity = float(product.min_order_qty or 1)

    if product.min_order_qty and quantity < product.min_order_qty:
        quantity = float(product.min_order_qty)

    return float(ceil(quantity)) if quantity > 0 else 0.0


def snapshot_purchase_order_line_from_product(
    po: PurchaseOrder,
    product: Product,
    quantity: float,
    *,
    notes: str | None = "Drafted from OrderPro product supplier.",
) -> PurchaseOrderLine:
    unit_cost = product.cost_price
    line_total = round(quantity * unit_cost, 2) if unit_cost is not None else None
    lead_time_days = product.lead_time_days or None
    if lead_time_days is None and product.supplier_record:
        lead_time_days = product.supplier_record.lead_time_days

    return PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product.id,
        product_supplier_id=None,
        supplier_sku=product.supplier_sku,
        supplier_product_name=product.name,
        quantity=quantity,
        unit_cost=unit_cost,
        currency=None,
        line_total=line_total,
        minimum_order_quantity=product.min_order_qty,
        pack_size=None,
        lead_time_days=lead_time_days,
        notes=notes,
    )


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


def build_supplier_forecast(db: Session, supplier_id: int) -> dict:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise DraftPurchaseOrderError("Supplier not found.")

    products = (
        db.query(Product)
        .options(
            selectinload(Product.supplier_record),
            selectinload(Product.inventory_positions),
        )
        .filter(Product.supplier_id == supplier_id, Product.is_active.is_(True))
        .order_by(Product.id.asc())
        .all()
    )
    forecasts = [build_forecast(db, product) for product in products]
    products_needing_reorder = [
        forecast["product_id"] for forecast in forecasts if float(forecast.get("recommended_qty") or 0) > 0
    ]
    products_missing_data = [
        forecast["product_id"]
        for forecast in forecasts
        if forecast.get("recommended_action") in {"needs_supplier_mapping", "needs_inventory_sync"}
    ]
    total_recommended_quantity = round(
        sum(float(forecast.get("recommended_qty") or 0) for forecast in forecasts),
        2,
    )
    estimated_costs = [
        float(forecast.get("recommended_qty") or 0) * float(product.cost_price)
        for forecast, product in zip(forecasts, products)
        if product.cost_price is not None and float(forecast.get("recommended_qty") or 0) > 0
    ]

    return {
        "supplier_id": supplier.id,
        "supplier_name": supplier.name,
        "product_count": len(products),
        "forecasts": forecasts,
        "products_needing_reorder": products_needing_reorder,
        "products_missing_data": products_missing_data,
        "total_recommended_quantity": total_recommended_quantity,
        "total_estimated_cost": round(sum(estimated_costs), 2) if estimated_costs else None,
    }


def create_draft_po_from_supplier_forecast(
    db: Session,
    *,
    supplier_id: int,
    created_by: str | None = None,
    notes: str | None = None,
    only_reorder_needed: bool = True,
) -> DraftPurchaseOrderResult:
    supplier_forecast = build_supplier_forecast(db, supplier_id)
    product_ids = [
        forecast["product_id"]
        for forecast in supplier_forecast["forecasts"]
        if not only_reorder_needed or float(forecast.get("recommended_qty") or 0) > 0
    ]
    if not product_ids:
        raise DraftPurchaseOrderError("No products need reorder for this supplier.")

    return create_draft_purchase_order_from_products(
        db,
        supplier_id=supplier_id,
        product_ids=product_ids,
        created_by=created_by,
        notes=notes,
        only_reorder_needed=only_reorder_needed,
    )


def recalculate_purchase_order_total(po: PurchaseOrder) -> None:
    totals = [line.line_total for line in po.lines if line.line_total is not None]
    po.total_amount = round(sum(totals), 2) if totals else None
    currencies = {line.currency for line in po.lines if line.currency}
    if len(currencies) == 1:
        po.currency = currencies.pop()
