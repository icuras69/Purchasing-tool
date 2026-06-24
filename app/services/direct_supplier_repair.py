from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier
from app.models.product_supplier_assignment_review import ProductSupplierAssignmentReview
from app.models.supplier import Supplier


TRUSTED_MATCH_STATUSES = {"matched", "confirmed"}
TRUSTED_MATCH_METHODS = {"exact_barcode", "exact_sku", "exact_name", "manual_supplier_cleanup", "preferred"}
REPORT_COLUMNS = [
    "product_id",
    "product_name",
    "product_barcode",
    "current_supplier_id",
    "promoted_supplier_id",
    "promoted_supplier_name",
    "promoted_supplier_code",
    "supplier_sku",
    "purchase_price",
    "lead_time_days",
    "source_tables",
    "match_methods",
    "status",
    "reason",
]


@dataclass
class SupplierPromotionCandidate:
    source_table: str
    source_id: int
    supplier_id: int | None
    supplier_sku: str | None = None
    purchase_price: float | None = None
    sell_price: float | None = None
    minimum_order_quantity: float | None = None
    match_status: str | None = None
    match_method: str | None = None
    is_preferred: bool = False

    @property
    def effective_match_method(self) -> str | None:
        if self.is_preferred:
            return "preferred"
        return self.match_method


@dataclass
class DirectSupplierRepairItem:
    product_id: int
    product_name: str
    product_barcode: str | None
    current_supplier_id: int | None
    promoted_supplier_id: int | None = None
    promoted_supplier_name: str | None = None
    promoted_supplier_code: str | None = None
    supplier_sku: str | None = None
    purchase_price: float | None = None
    sell_price: float | None = None
    lead_time_days: int | None = None
    min_order_qty: float | None = None
    source_tables: list[str] = field(default_factory=list)
    match_methods: list[str] = field(default_factory=list)
    source_candidates: list[dict[str, Any]] = field(default_factory=list)
    status: str = "skipped"
    reason: str = ""
    updated: bool = False

    def csv_row(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_barcode": self.product_barcode,
            "current_supplier_id": self.current_supplier_id,
            "promoted_supplier_id": self.promoted_supplier_id,
            "promoted_supplier_name": self.promoted_supplier_name,
            "promoted_supplier_code": self.promoted_supplier_code,
            "supplier_sku": self.supplier_sku,
            "purchase_price": self.purchase_price,
            "lead_time_days": self.lead_time_days,
            "source_tables": ";".join(self.source_tables),
            "match_methods": ";".join(self.match_methods),
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class DirectSupplierRepairPlan:
    mode: str
    total_products_scanned: int = 0
    products_missing_direct_supplier: int = 0
    safe_promotions: int = 0
    conflicts: int = 0
    skipped_no_candidate: int = 0
    skipped_inactive_supplier: int = 0
    skipped_untrusted_match: int = 0
    skipped_existing_supplier: int = 0
    products_updated: int = 0
    items: list[DirectSupplierRepairItem] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "total_products_scanned": self.total_products_scanned,
            "products_missing_direct_supplier": self.products_missing_direct_supplier,
            "safe_promotions": self.safe_promotions,
            "conflicts": self.conflicts,
            "skipped_no_candidate": self.skipped_no_candidate,
            "skipped_inactive_supplier": self.skipped_inactive_supplier,
            "skipped_untrusted_match": self.skipped_untrusted_match,
            "skipped_existing_supplier": self.skipped_existing_supplier,
            "products_updated": self.products_updated,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "items": [asdict(item) for item in self.items],
        }


def plan_direct_supplier_repair(
    db: Session,
    *,
    product_id: int | None = None,
    apply: bool = False,
    now: datetime | None = None,
) -> DirectSupplierRepairPlan:
    now = now or datetime.utcnow()
    mode = "apply" if apply else "dry_run"
    products = _load_products_for_repair(db, product_id=product_id)
    product_ids = [product.id for product in products]
    candidates_by_product = _load_candidates(db, product_ids)
    suppliers = _load_suppliers(db, candidates_by_product)

    plan = DirectSupplierRepairPlan(mode=mode, total_products_scanned=len(products))
    for product in products:
        if product.supplier_id is not None:
            plan.skipped_existing_supplier += 1
            plan.items.append(
                DirectSupplierRepairItem(
                    product_id=product.id,
                    product_name=product.name,
                    product_barcode=product.barcode,
                    current_supplier_id=product.supplier_id,
                    status="skipped_existing_supplier",
                    reason="Product already has a direct supplier assignment.",
                )
            )
            continue

        plan.products_missing_direct_supplier += 1
        item = _evaluate_product(product, candidates_by_product.get(product.id, []), suppliers)
        plan.items.append(item)

        if item.status == "safe_promotion":
            plan.safe_promotions += 1
            if apply:
                _apply_promotion(db, product, item, now)
                item.updated = True
                plan.products_updated += 1
        elif item.status == "conflict":
            plan.conflicts += 1
        elif item.status == "skipped_inactive_supplier":
            plan.skipped_inactive_supplier += 1
        elif item.status == "skipped_untrusted_match":
            plan.skipped_untrusted_match += 1
        else:
            plan.skipped_no_candidate += 1

    if apply:
        db.commit()
    return plan


def save_direct_supplier_repair_report(
    plan: DirectSupplierRepairPlan,
    *,
    output_dir: str | Path = "tmp/direct_supplier_repair_reports",
    timestamp: str | None = None,
) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    json_path = output / f"direct_supplier_repair_{plan.mode}_{stamp}.json"
    csv_path = output / f"direct_supplier_repair_{plan.mode}_{stamp}.csv"

    json_path.write_text(json.dumps(plan.as_dict(), indent=2, default=str), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for item in plan.items:
            writer.writerow(item.csv_row())

    return {"json_report": str(json_path), "csv_report": str(csv_path)}


def _load_products_for_repair(db: Session, *, product_id: int | None) -> list[Product]:
    query = db.query(Product).options(selectinload(Product.supplier_record)).order_by(Product.id.asc())
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    return query.all()


def _load_candidates(db: Session, product_ids: list[int]) -> dict[int, list[SupplierPromotionCandidate]]:
    if not product_ids:
        return {}

    by_product: dict[int, list[SupplierPromotionCandidate]] = {product_id: [] for product_id in product_ids}
    mappings = (
        db.query(ProductSupplier)
        .filter(ProductSupplier.product_id.in_(product_ids))
        .order_by(ProductSupplier.id.asc())
        .all()
    )
    for mapping in mappings:
        by_product.setdefault(mapping.product_id, []).append(
            SupplierPromotionCandidate(
                source_table="product_suppliers",
                source_id=mapping.id,
                supplier_id=mapping.supplier_id,
                supplier_sku=mapping.supplier_sku,
                purchase_price=mapping.purchase_price,
                minimum_order_quantity=mapping.minimum_order_quantity,
                match_status=mapping.match_status,
                match_method=mapping.match_method,
                is_preferred=bool(mapping.is_preferred),
            )
        )

    master_items = (
        db.query(ProductMasterItem)
        .filter(ProductMasterItem.product_id.in_(product_ids))
        .order_by(ProductMasterItem.id.asc())
        .all()
    )
    for master_item in master_items:
        by_product.setdefault(master_item.product_id, []).append(
            SupplierPromotionCandidate(
                source_table="product_master_items",
                source_id=master_item.id,
                supplier_id=master_item.supplier_id,
                supplier_sku=master_item.sku,
                purchase_price=master_item.cost_price,
                sell_price=master_item.sales_price,
                match_status=master_item.match_status,
                match_method=master_item.match_method,
            )
        )
    return by_product


def _load_suppliers(
    db: Session,
    candidates_by_product: dict[int, list[SupplierPromotionCandidate]],
) -> dict[int, Supplier]:
    supplier_ids = {
        candidate.supplier_id
        for candidates in candidates_by_product.values()
        for candidate in candidates
        if candidate.supplier_id is not None
    }
    if not supplier_ids:
        return {}
    return {supplier.id: supplier for supplier in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}


def _evaluate_product(
    product: Product,
    candidates: list[SupplierPromotionCandidate],
    suppliers: dict[int, Supplier],
) -> DirectSupplierRepairItem:
    item = DirectSupplierRepairItem(
        product_id=product.id,
        product_name=product.name,
        product_barcode=product.barcode,
        current_supplier_id=product.supplier_id,
        source_candidates=[_candidate_dict(candidate) for candidate in candidates],
    )
    if not candidates:
        item.status = "skipped_no_candidate"
        item.reason = "No legacy supplier candidate found."
        return item

    trusted_candidates: list[SupplierPromotionCandidate] = []
    untrusted_candidates: list[SupplierPromotionCandidate] = []
    inactive_candidates: list[SupplierPromotionCandidate] = []
    missing_supplier_candidates: list[SupplierPromotionCandidate] = []

    for candidate in candidates:
        if not _is_trusted_candidate(candidate):
            untrusted_candidates.append(candidate)
            continue
        supplier = suppliers.get(candidate.supplier_id or -1)
        if not supplier:
            missing_supplier_candidates.append(candidate)
            continue
        if getattr(supplier, "is_active", True) is False:
            inactive_candidates.append(candidate)
            continue
        trusted_candidates.append(candidate)

    supplier_ids = {candidate.supplier_id for candidate in trusted_candidates if candidate.supplier_id is not None}
    if len(supplier_ids) > 1:
        item.status = "conflict"
        item.reason = "Conflicting trusted supplier candidates were found."
        _fill_item_from_candidates(item, trusted_candidates, suppliers)
        return item

    if len(supplier_ids) == 1:
        _fill_item_from_candidates(item, trusted_candidates, suppliers)
        item.status = "safe_promotion"
        item.reason = "One trusted legacy supplier candidate can be promoted."
        return item

    if inactive_candidates:
        item.status = "skipped_inactive_supplier"
        item.reason = "Trusted candidate supplier is inactive."
        _fill_item_from_candidates(item, inactive_candidates, suppliers)
        return item

    if untrusted_candidates:
        item.status = "skipped_untrusted_match"
        item.reason = "Legacy supplier candidates exist but their match status or method is not trusted."
        _fill_item_from_candidates(item, untrusted_candidates, suppliers)
        return item

    if missing_supplier_candidates:
        item.status = "skipped_no_candidate"
        item.reason = "Trusted legacy candidates reference suppliers that do not exist locally."
        _fill_item_from_candidates(item, missing_supplier_candidates, suppliers)
        return item

    item.status = "skipped_no_candidate"
    item.reason = "No trusted legacy supplier candidate found."
    return item


def _is_trusted_candidate(candidate: SupplierPromotionCandidate) -> bool:
    status = (candidate.match_status or "").strip().lower()
    method = (candidate.effective_match_method or "").strip().lower()
    return status in TRUSTED_MATCH_STATUSES and method in TRUSTED_MATCH_METHODS and candidate.supplier_id is not None


def _fill_item_from_candidates(
    item: DirectSupplierRepairItem,
    candidates: list[SupplierPromotionCandidate],
    suppliers: dict[int, Supplier],
) -> None:
    if not candidates:
        return
    supplier_id = next((candidate.supplier_id for candidate in candidates if candidate.supplier_id is not None), None)
    supplier = suppliers.get(supplier_id or -1)
    item.promoted_supplier_id = supplier_id
    item.promoted_supplier_name = supplier.name if supplier else None
    item.promoted_supplier_code = supplier.orderpro_code if supplier else None
    item.supplier_sku = _first_non_empty(candidate.supplier_sku for candidate in candidates)
    item.purchase_price = _first_positive(candidate.purchase_price for candidate in candidates)
    item.sell_price = _first_positive(candidate.sell_price for candidate in candidates)
    item.min_order_qty = _first_positive(candidate.minimum_order_quantity for candidate in candidates)
    item.lead_time_days = supplier.lead_time_days if supplier else None
    item.source_tables = sorted({candidate.source_table for candidate in candidates})
    item.match_methods = sorted(
        {candidate.effective_match_method for candidate in candidates if candidate.effective_match_method}
    )


def _apply_promotion(
    db: Session,
    product: Product,
    item: DirectSupplierRepairItem,
    now: datetime,
) -> None:
    product.supplier_id = item.promoted_supplier_id
    if not product.supplier_sku and item.supplier_sku:
        product.supplier_sku = item.supplier_sku
    if _missing_number(product.cost_price) and item.purchase_price is not None:
        product.cost_price = item.purchase_price
    if _missing_number(product.sell_price) and item.sell_price is not None:
        product.sell_price = item.sell_price
    if _missing_number(product.lead_time_days) and item.lead_time_days is not None:
        product.lead_time_days = int(item.lead_time_days)
    if _missing_number(product.min_order_qty) and item.min_order_qty is not None:
        product.min_order_qty = item.min_order_qty

    review = product.supplier_assignment_review
    if review is None:
        review = ProductSupplierAssignmentReview(product_id=product.id, created_at=now)
        db.add(review)
    review.suggested_supplier_id = item.promoted_supplier_id
    review.suggestion_source = "direct_supplier_repair"
    review.confidence_label = "high"
    review.confidence_score = 0.95
    review.status = "confirmed"
    review.evidence_summary = {
        "source": "direct_supplier_repair",
        "source_tables": item.source_tables,
        "match_methods": item.match_methods,
        "source_candidates": item.source_candidates,
        "supplier_sku": item.supplier_sku,
        "purchase_price": item.purchase_price,
        "sell_price": item.sell_price,
        "lead_time_days": item.lead_time_days,
        "min_order_qty": item.min_order_qty,
    }
    review.warnings = []
    review.reviewed_supplier_id = item.promoted_supplier_id
    review.reviewed_by = "direct_supplier_repair"
    review.reviewed_at = now
    review.notes = "Promoted legacy supplier mapping to direct products.supplier_id"
    review.updated_at = now


def _candidate_dict(candidate: SupplierPromotionCandidate) -> dict[str, Any]:
    return {
        "source_table": candidate.source_table,
        "source_id": candidate.source_id,
        "supplier_id": candidate.supplier_id,
        "supplier_sku": candidate.supplier_sku,
        "purchase_price": candidate.purchase_price,
        "sell_price": candidate.sell_price,
        "minimum_order_quantity": candidate.minimum_order_quantity,
        "match_status": candidate.match_status,
        "match_method": candidate.effective_match_method,
    }


def _first_non_empty(values) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _first_positive(values) -> float | None:
    for value in values:
        if value is not None and float(value) > 0:
            return float(value)
    return None


def _missing_number(value: Any) -> bool:
    return value is None or float(value) == 0
