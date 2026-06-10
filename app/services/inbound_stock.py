from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.orderpro_purchase_order import OrderProPurchaseOrder, OrderProPurchaseOrderLine
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.services.orderpro_purchase_order_sync import (
    EXCLUDED_ORDERPRO_PURCHASE_ORDER_STATUSES,
    OPEN_ORDERPRO_PURCHASE_ORDER_STATUSES,
    is_open_orderpro_purchase_order_status,
)


INCLUDED_LOCAL_PO_STATUSES = {"approved", "issued"}
EXCLUDED_LOCAL_PO_STATUSES = {"draft", "pending_approval", "cancelled", "received"}


def get_product_inbound_stock(db: Session, product_id: int) -> dict[str, Any]:
    return get_bulk_inbound_stock(db, [product_id]).get(product_id, empty_inbound_context(product_id))


def get_bulk_inbound_stock(db: Session, product_ids: list[int]) -> dict[int, dict[str, Any]]:
    contexts = {product_id: empty_inbound_context(product_id) for product_id in product_ids}
    if not product_ids:
        return contexts

    lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .options(selectinload(PurchaseOrderLine.purchase_order))
        .filter(PurchaseOrderLine.product_id.in_(product_ids))
        .all()
    )
    orderpro_lines = (
        db.query(OrderProPurchaseOrderLine)
        .join(OrderProPurchaseOrder, OrderProPurchaseOrder.id == OrderProPurchaseOrderLine.orderpro_purchase_order_id)
        .options(selectinload(OrderProPurchaseOrderLine.purchase_order))
        .filter(OrderProPurchaseOrderLine.product_id.in_(product_ids))
        .all()
    )

    supplier_ids_by_product: dict[int, set[int]] = defaultdict(set)
    expected_dates_by_product: dict[int, list[date]] = defaultdict(list)
    po_ids_by_product: dict[int, set[int]] = defaultdict(set)
    orderpro_po_ids_by_product: dict[int, set[int]] = defaultdict(set)
    source_totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    source_line_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    warnings_by_product: dict[int, set[str]] = defaultdict(set)

    for line in lines:
        po = line.purchase_order
        if po is None:
            warnings_by_product[line.product_id].add("Purchase order line is missing its header.")
            continue
        status = po.status
        if status not in INCLUDED_LOCAL_PO_STATUSES:
            continue

        remaining_quantity = max(float(line.quantity or 0), 0.0)
        if remaining_quantity <= 0:
            warnings_by_product[line.product_id].add("Open purchase order line has non-positive quantity.")
            continue

        source = "local_purchase_orders"
        source_totals[line.product_id][source] += remaining_quantity
        source_line_counts[line.product_id][source] += 1
        po_ids_by_product[line.product_id].add(po.id)
        if po.supplier_id is not None:
            supplier_ids_by_product[line.product_id].add(po.supplier_id)
        if po.delivery_date is not None:
            expected_dates_by_product[line.product_id].append(po.delivery_date)
        else:
            warnings_by_product[line.product_id].add(
                "Expected delivery date is unavailable for one or more inbound purchase order lines."
            )
        warnings_by_product[line.product_id].add(
            "Line-level received/cancelled quantities are unavailable; full open line quantity is counted."
        )

    for line in orderpro_lines:
        if line.product_id is None:
            continue
        po = line.purchase_order
        if po is None:
            warnings_by_product[line.product_id].add("OrderPro purchase order line is missing its header.")
            continue
        if not is_open_orderpro_purchase_order_status(po.status):
            continue

        remaining_quantity = max(float(line.quantity_open or 0), 0.0)
        if remaining_quantity <= 0:
            warnings_by_product[line.product_id].add("Open OrderPro purchase order line has non-positive open quantity.")
            continue

        source = "orderpro_purchase_orders"
        source_totals[line.product_id][source] += remaining_quantity
        source_line_counts[line.product_id][source] += 1
        orderpro_po_ids_by_product[line.product_id].add(po.id)
        if po.supplier_id is not None:
            supplier_ids_by_product[line.product_id].add(po.supplier_id)
        if line.expected_date is not None:
            expected_dates_by_product[line.product_id].append(line.expected_date.date())
        elif po.expected_date is not None:
            expected_dates_by_product[line.product_id].append(po.expected_date.date())
        else:
            warnings_by_product[line.product_id].add(
                "Expected delivery date is unavailable for one or more OrderPro inbound purchase order lines."
            )
        if line.quantity_received is None:
            warnings_by_product[line.product_id].add("OrderPro received quantity was missing; open quantity used fallback data.")
        if line.quantity_cancelled is None:
            warnings_by_product[line.product_id].add("OrderPro cancelled quantity was missing; open quantity used fallback data.")

    for product_id, context in contexts.items():
        source_breakdown = {
            source: {
                "incoming_qty": round(quantity, 2),
                "open_po_line_count": source_line_counts[product_id][source],
            }
            for source, quantity in source_totals[product_id].items()
        }
        incoming_qty = round(sum(source_totals[product_id].values()), 2)
        dates = sorted(expected_dates_by_product[product_id])
        context.update(
            {
                "incoming_qty": incoming_qty,
                "incoming_qty_local": round(source_totals[product_id].get("local_purchase_orders", 0.0), 2),
                "incoming_qty_orderpro": round(source_totals[product_id].get("orderpro_purchase_orders", 0.0), 2),
                "incoming_qty_total": incoming_qty,
                "source_breakdown": source_breakdown,
                "incoming_qty_by_source": {
                    source: data["incoming_qty"] for source, data in source_breakdown.items()
                },
                "open_po_count": len(po_ids_by_product[product_id]) + len(orderpro_po_ids_by_product[product_id]),
                "open_po_line_count": sum(source_line_counts[product_id].values()),
                "earliest_expected_date": dates[0] if dates else None,
                "latest_expected_date": dates[-1] if dates else None,
                "supplier_ids": sorted(supplier_ids_by_product[product_id]),
                "warnings": sorted(warnings_by_product[product_id]),
            }
        )
    return contexts


def empty_inbound_context(product_id: int) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "incoming_qty": 0.0,
        "incoming_qty_local": 0.0,
        "incoming_qty_orderpro": 0.0,
        "incoming_qty_total": 0.0,
        "incoming_qty_by_source": {},
        "source_breakdown": {},
        "open_po_count": 0,
        "open_po_line_count": 0,
        "earliest_expected_date": None,
        "latest_expected_date": None,
        "supplier_ids": [],
        "warnings": [],
    }


def inbound_stock_summary(db: Session) -> dict[str, Any]:
    lines = (
        db.query(PurchaseOrderLine)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .options(selectinload(PurchaseOrderLine.purchase_order))
        .all()
    )
    orderpro_lines = (
        db.query(OrderProPurchaseOrderLine)
        .join(OrderProPurchaseOrder, OrderProPurchaseOrder.id == OrderProPurchaseOrderLine.orderpro_purchase_order_id)
        .options(selectinload(OrderProPurchaseOrderLine.purchase_order))
        .all()
    )
    product_ids = sorted(
        {
            line.product_id
            for line in [*lines, *orderpro_lines]
            if line.product_id is not None
        }
    )
    contexts = get_bulk_inbound_stock(db, product_ids)
    open_line_ids = {
        line.id
        for line in lines
        if line.purchase_order is not None and line.purchase_order.status in INCLUDED_LOCAL_PO_STATUSES
    }
    open_orderpro_line_ids = {
        line.id
        for line in orderpro_lines
        if line.purchase_order is not None and is_open_orderpro_purchase_order_status(line.purchase_order.status)
    }
    products_with_local = {
        product_id
        for product_id, context in contexts.items()
        if context["source_breakdown"].get("local_purchase_orders", {}).get("incoming_qty", 0) > 0
    }
    products_with_orderpro = {
        product_id
        for product_id, context in contexts.items()
        if context["source_breakdown"].get("orderpro_purchase_orders", {}).get("incoming_qty", 0) > 0
    }
    return {
        "products_with_inbound_stock": sum(1 for context in contexts.values() if context["incoming_qty"] > 0),
        "products_with_local_inbound": len(products_with_local),
        "products_with_orderpro_inbound": len(products_with_orderpro),
        "products_with_any_inbound": sum(1 for context in contexts.values() if context["incoming_qty"] > 0),
        "total_inbound_units": round(sum(context["incoming_qty"] for context in contexts.values()), 2),
        "total_local_inbound_units": round(sum(context["incoming_qty_local"] for context in contexts.values()), 2),
        "total_orderpro_inbound_units": round(sum(context["incoming_qty_orderpro"] for context in contexts.values()), 2),
        "open_po_count": len(
            {
                line.purchase_order_id
                for line in lines
                if line.purchase_order is not None and line.purchase_order.status in INCLUDED_LOCAL_PO_STATUSES
            }
        )
        + len(
            {
                line.orderpro_purchase_order_id
                for line in orderpro_lines
                if line.purchase_order is not None and is_open_orderpro_purchase_order_status(line.purchase_order.status)
            }
        ),
        "open_orderpro_po_count": len(
            {
                line.orderpro_purchase_order_id
                for line in orderpro_lines
                if line.purchase_order is not None and is_open_orderpro_purchase_order_status(line.purchase_order.status)
            }
        ),
        "open_po_line_count": len(open_line_ids) + len(open_orderpro_line_ids),
        "lines_missing_product_match": sum(1 for line in lines if line.product_id is None),
        "orderpro_po_lines_missing_product_match": sum(1 for line in orderpro_lines if line.product_id is None),
        "orderpro_po_lines_missing_supplier_match": sum(
            1
            for line in orderpro_lines
            if line.purchase_order is not None
            and is_open_orderpro_purchase_order_status(line.purchase_order.status)
            and line.purchase_order.supplier_id is None
        ),
        "lines_missing_expected_date": sum(
            1
            for line in lines
            if line.id in open_line_ids and line.purchase_order is not None and line.purchase_order.delivery_date is None
        )
        + sum(
            1
            for line in orderpro_lines
            if line.id in open_orderpro_line_ids
            and line.purchase_order is not None
            and line.expected_date is None
            and line.purchase_order.expected_date is None
        ),
        "lines_with_missing_quantity_fallback_warnings": sum(
            1
            for line in orderpro_lines
            if line.id in open_orderpro_line_ids
            and (line.quantity_received is None or line.quantity_cancelled is None)
        ),
        "lines_with_suspicious_quantities": sum(
            1 for line in lines if line.id in open_line_ids and float(line.quantity or 0) <= 0
        )
        + sum(1 for line in orderpro_lines if line.id in open_orderpro_line_ids and float(line.quantity_open or 0) <= 0),
        "included_local_statuses": sorted(INCLUDED_LOCAL_PO_STATUSES),
        "excluded_local_statuses": sorted(EXCLUDED_LOCAL_PO_STATUSES),
        "included_orderpro_statuses": sorted(OPEN_ORDERPRO_PURCHASE_ORDER_STATUSES),
        "excluded_orderpro_statuses": sorted(EXCLUDED_ORDERPRO_PURCHASE_ORDER_STATUSES),
        "orderpro_purchase_order_mirror_available": True,
    }
