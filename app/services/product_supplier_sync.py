from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.product_master_item import ProductMasterItem
from app.models.product_supplier import ProductSupplier


@dataclass
class ProductSupplierSyncSummary:
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    conflict_count: int = 0
    candidate_count: int = 0
    skipped_samples: list[dict] = field(default_factory=list)
    conflict_samples: list[dict] = field(default_factory=list)
    changed_samples: list[dict] = field(default_factory=list)


def sync_product_suppliers_from_master_items(
    db: Session,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
    sample_limit: int = 10,
) -> ProductSupplierSyncSummary:
    sync_time = now or datetime.utcnow()
    summary = ProductSupplierSyncSummary()

    master_items = db.query(ProductMasterItem).order_by(ProductMasterItem.id.asc()).all()

    existing_by_supplier_sku = {
        (mapping.supplier_id, mapping.supplier_sku): mapping
        for mapping in db.query(ProductSupplier)
        .filter(ProductSupplier.supplier_sku.is_not(None))
        .all()
    }

    seen_candidate_keys: set[tuple[int, str]] = set()

    for item in master_items:
        if item.match_status != "matched":
            summary.skipped_count += 1
            append_sample(
                summary.skipped_samples,
                sample_limit,
                master_item_sample(item, "match_status is not matched"),
            )
            continue

        if item.product_id is None or item.supplier_id is None:
            summary.skipped_count += 1
            append_sample(
                summary.skipped_samples,
                sample_limit,
                master_item_sample(item, "missing product_id or supplier_id"),
            )
            continue

        summary.candidate_count += 1
        candidate_key = (item.supplier_id, item.sku)
        if candidate_key in seen_candidate_keys:
            summary.conflict_count += 1
            append_sample(
                summary.conflict_samples,
                sample_limit,
                master_item_sample(item, "duplicate supplier_id + supplier_sku candidate"),
            )
            continue
        seen_candidate_keys.add(candidate_key)

        existing = existing_by_supplier_sku.get(candidate_key)
        if existing:
            if existing.product_id != item.product_id:
                summary.conflict_count += 1
                append_sample(
                    summary.conflict_samples,
                    sample_limit,
                    {
                        **master_item_sample(item, "existing supplier_id + supplier_sku maps to another product"),
                        "existing_product_supplier_id": existing.id,
                        "existing_product_id": existing.product_id,
                    },
                )
                continue

            summary.updated_count += 1
            append_sample(summary.changed_samples, sample_limit, changed_sample(item, "update"))
            if not dry_run:
                update_product_supplier_from_master_item(existing, item, sync_time)
            continue

        summary.created_count += 1
        append_sample(summary.changed_samples, sample_limit, changed_sample(item, "create"))
        if not dry_run:
            mapping = ProductSupplier(
                product_id=item.product_id,
                supplier_id=item.supplier_id,
                supplier_sku=item.sku,
                supplier_product_name=item.name,
                purchase_price=item.cost_price,
                is_preferred=False,
                match_status=item.match_status,
                match_method=item.match_method,
                last_synced_at=sync_time,
                created_at=sync_time,
                updated_at=sync_time,
            )
            db.add(mapping)
            existing_by_supplier_sku[candidate_key] = mapping

    return summary


def update_product_supplier_from_master_item(
    mapping: ProductSupplier,
    item: ProductMasterItem,
    sync_time: datetime,
) -> None:
    mapping.supplier_product_name = item.name
    mapping.purchase_price = item.cost_price
    mapping.match_status = item.match_status
    mapping.match_method = item.match_method
    mapping.last_synced_at = sync_time
    mapping.updated_at = sync_time


def append_sample(samples: list[dict], sample_limit: int, sample: dict) -> None:
    if len(samples) < sample_limit:
        samples.append(sample)


def master_item_sample(item: ProductMasterItem, reason: str) -> dict:
    return {
        "id": item.id,
        "sku": item.sku,
        "product_id": item.product_id,
        "supplier_id": item.supplier_id,
        "match_status": item.match_status,
        "match_method": item.match_method,
        "reason": reason,
    }


def changed_sample(item: ProductMasterItem, action: str) -> dict:
    return {
        "action": action,
        "product_id": item.product_id,
        "supplier_id": item.supplier_id,
        "supplier_sku": item.sku,
        "supplier_product_name": item.name,
        "purchase_price": item.cost_price,
        "match_status": item.match_status,
        "match_method": item.match_method,
    }
