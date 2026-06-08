from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.orderpro_order import OrderProOrder, OrderProOrderItem
from app.models.product import Product


DEFAULT_ORDERPRO_HISTORICAL_DEMAND_STATUSES = {"shipped"}
DEFAULT_ORDERPRO_OPEN_DEMAND_STATUSES = {"confirmed", "packed", "backorder"}
DEFAULT_ORDERPRO_EXCLUDED_DEMAND_STATUSES = {"cancelled", "canceled"}


@dataclass(frozen=True)
class DemandResult:
    avg_daily_usage: float
    demand_source: str
    demand_lookback_days: int | None
    demand_history_start: date | None
    demand_history_end: date | None
    observation_days: int | None
    shipped_units_in_window: float
    shipped_order_count: int
    open_confirmed_units: float
    open_packed_units: float
    open_backorder_units: float
    total_open_demand: float
    units_sold_in_window: float
    eligible_order_count: int
    excluded_order_count: int


def configured_historical_statuses() -> set[str]:
    configured = parse_statuses(settings.orderpro_historical_demand_statuses)
    return configured or DEFAULT_ORDERPRO_HISTORICAL_DEMAND_STATUSES


def configured_open_statuses() -> set[str]:
    configured = parse_statuses(settings.orderpro_open_demand_statuses)
    return configured or DEFAULT_ORDERPRO_OPEN_DEMAND_STATUSES


def configured_excluded_statuses() -> set[str]:
    configured = parse_statuses(settings.orderpro_excluded_demand_statuses)
    return configured or DEFAULT_ORDERPRO_EXCLUDED_DEMAND_STATUSES


def parse_statuses(value: str | None) -> set[str]:
    return {status.strip().lower() for status in (value or "").split(",") if status.strip()}


def calculate_orderpro_demand(
    db: Session,
    product: Product,
    *,
    lookback_days: int | None = None,
    historical_statuses: set[str] | None = None,
    open_statuses: set[str] | None = None,
    excluded_statuses: set[str] | None = None,
    today: date | None = None,
) -> DemandResult:
    lookback = lookback_days or settings.forecast_demand_lookback_days
    historical = historical_statuses or configured_historical_statuses()
    open_demand = open_statuses or configured_open_statuses()
    excluded = excluded_statuses or configured_excluded_statuses()
    today_value = today or datetime.now(timezone.utc).date()
    lookback_start = today_value - timedelta(days=max(lookback - 1, 0))

    rows = (
        db.query(OrderProOrderItem, OrderProOrder)
        .join(OrderProOrder, OrderProOrderItem.order_id == OrderProOrder.id)
        .filter(OrderProOrderItem.product_id == product.id)
        .all()
    )

    shipped_quantities: list[tuple[date, float, int]] = []
    shipped_order_ids: set[int] = set()
    excluded_order_ids: set[int] = set()
    open_units = {"confirmed": 0.0, "packed": 0.0, "backorder": 0.0}

    for item, order in rows:
        order_day = order_date(order)
        status = normalized_status(order.status)
        shipped_quantity = item.quantity_shipped if item.quantity_shipped is not None else item.quantity
        ordered_quantity = item.quantity_ordered
        if shipped_quantity is not None and shipped_quantity < 0:
            excluded_order_ids.add(order.id)
            continue

        if status in excluded:
            excluded_order_ids.add(order.id)
            continue

        if status in historical:
            if order_day is None or order_day < lookback_start or order_day > today_value:
                continue
            if shipped_quantity is None or shipped_quantity == 0:
                continue
            shipped_quantities.append((order_day, float(shipped_quantity), order.id))
            shipped_order_ids.add(order.id)
            continue

        if status in open_demand:
            if ordered_quantity is not None:
                shipped_for_open = shipped_quantity if shipped_quantity is not None else 0.0
                open_units[status] = open_units.get(status, 0.0) + max(float(ordered_quantity) - float(shipped_for_open), 0.0)
            continue

        if status:
            excluded_order_ids.add(order.id)

    shipped_units = round(sum(row[1] for row in shipped_quantities), 2)
    if shipped_quantities:
        start = min(row[0] for row in shipped_quantities)
        end = max(row[0] for row in shipped_quantities)
        observation_days = max((end - start).days + 1, 1)
        avg_daily_usage = round(shipped_units / observation_days, 2)
    else:
        start = None
        end = None
        observation_days = None
        avg_daily_usage = 0.0

    open_confirmed = round(open_units.get("confirmed", 0.0), 2)
    open_packed = round(open_units.get("packed", 0.0), 2)
    open_backorder = round(open_units.get("backorder", 0.0), 2)
    total_open = round(open_confirmed + open_packed + open_backorder, 2)

    return DemandResult(
        avg_daily_usage=avg_daily_usage,
        demand_source="orderpro_orders",
        demand_lookback_days=lookback,
        demand_history_start=start,
        demand_history_end=end,
        observation_days=observation_days,
        shipped_units_in_window=shipped_units,
        shipped_order_count=len(shipped_order_ids),
        open_confirmed_units=open_confirmed,
        open_packed_units=open_packed,
        open_backorder_units=open_backorder,
        total_open_demand=total_open,
        units_sold_in_window=shipped_units,
        eligible_order_count=len(shipped_order_ids),
        excluded_order_count=len(excluded_order_ids),
    )


def product_has_orderpro_history(db: Session, product_id: int) -> bool:
    return db.query(OrderProOrderItem.id).filter(OrderProOrderItem.product_id == product_id).first() is not None


def empty_demand_result(source: str) -> DemandResult:
    return DemandResult(
        avg_daily_usage=0.0,
        demand_source=source,
        demand_lookback_days=None,
        demand_history_start=None,
        demand_history_end=None,
        observation_days=None,
        shipped_units_in_window=0.0,
        shipped_order_count=0,
        open_confirmed_units=0.0,
        open_packed_units=0.0,
        open_backorder_units=0.0,
        total_open_demand=0.0,
        units_sold_in_window=0.0,
        eligible_order_count=0,
        excluded_order_count=0,
    )


def order_date(order: OrderProOrder) -> date | None:
    if order.order_date is None:
        return None
    if isinstance(order.order_date, datetime):
        return order.order_date.date()
    return order.order_date


def normalized_status(status: str | None) -> str:
    return (status or "").strip().lower()
