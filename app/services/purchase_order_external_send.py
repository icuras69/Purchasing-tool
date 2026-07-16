from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.purchase_order import PurchaseOrder
from app.services.purchase_order_preflight import purchase_order_preflight


EXTERNAL_SEND_SYSTEM = "OrderPro"
EXTERNAL_SEND_NOT_IMPLEMENTED_MESSAGE = (
    "This purchase order is local-only. External OrderPro sending is not implemented yet."
)
REQUIRED_LOCAL_STATUS_FOR_EXTERNAL_SEND = "issued"


def purchase_order_external_send_readiness(
    db: Session,
    purchase_order: PurchaseOrder,
) -> dict[str, Any]:
    preflight = purchase_order_preflight(db, purchase_order)
    blockers = ["External OrderPro sending is not implemented yet."]
    warnings: list[str] = []

    if purchase_order.status != REQUIRED_LOCAL_STATUS_FOR_EXTERNAL_SEND:
        warnings.append(
            "Future external sending should require the PO to be locally issued first."
        )
    if preflight["blockers"]:
        warnings.append("Local PO preflight still has blockers.")
    if preflight["warnings"]:
        warnings.append("Local PO preflight has review warnings.")

    return {
        "purchase_order_id": purchase_order.id,
        "status": purchase_order.status,
        "supplier_id": purchase_order.supplier_id,
        "supplier_name": purchase_order.supplier.name if purchase_order.supplier else None,
        "can_send_externally": False,
        "external_send_supported": False,
        "external_send_system": EXTERNAL_SEND_SYSTEM,
        "blockers": blockers,
        "warnings": warnings,
        "required_local_status": REQUIRED_LOCAL_STATUS_FOR_EXTERNAL_SEND,
        "preflight_summary": {
            "overall_status": preflight["overall_status"],
            "can_submit": preflight["can_submit"],
            "can_approve": preflight["can_approve"],
            "can_issue_if_applicable": preflight["can_issue_if_applicable"],
            "blocker_count": len(preflight["blockers"]),
            "warning_count": len(preflight["warnings"]),
            "line_count": preflight["summary_counts"]["line_count"],
            "blockers": preflight["blockers"],
            "warnings": preflight["warnings"],
        },
        "message": EXTERNAL_SEND_NOT_IMPLEMENTED_MESSAGE,
    }
