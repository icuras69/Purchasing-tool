from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_pack_rule import ProductPackRule


EPSILON = 0.000001


@dataclass(frozen=True)
class PackRoundingResult:
    raw_required_quantity: float
    pre_pack_quantity: float
    final_quantity: float
    order_multiple: float
    rule_id: int | None
    rule_name: str
    rule_source: str
    pack_type: str | None
    units_per_box: float | None
    units_per_pallet: float | None
    pallet_only: bool
    display: str
    explanation: str
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_required_quantity": self.raw_required_quantity,
            "pre_pack_quantity": self.pre_pack_quantity,
            "final_quantity": self.final_quantity,
            "order_multiple": self.order_multiple,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_source": self.rule_source,
            "pack_type": self.pack_type,
            "units_per_box": self.units_per_box,
            "units_per_pallet": self.units_per_pallet,
            "pallet_only": self.pallet_only,
            "display": self.display,
            "explanation": self.explanation,
            "warnings": list(self.warnings),
        }


def parse_positive(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def resolve_product_pack_rule(db: Session, product: Product) -> ProductPackRule | None:
    active_rules = (
        db.query(ProductPackRule)
        .filter(ProductPackRule.is_active.is_(True))
        .filter(
            (ProductPackRule.product_id == product.id)
            | (
                (ProductPackRule.product_id.is_(None))
                & (ProductPackRule.canonical_sku.isnot(None))
                & (ProductPackRule.canonical_sku == product.orderpro_sku)
            )
        )
        .all()
    )
    if not active_rules:
        return None

    def priority(rule: ProductPackRule) -> tuple[int, int]:
        supplier_match = 1 if rule.supplier_id is None or rule.supplier_id == product.supplier_id else 0
        if rule.product_id == product.id:
            return (3, supplier_match)
        if product.orderpro_sku and rule.canonical_sku == product.orderpro_sku:
            return (2, supplier_match)
        return (0, supplier_match)

    candidates = [rule for rule in active_rules if priority(rule)[1] > 0]
    if not candidates:
        return None
    return sorted(candidates, key=priority, reverse=True)[0]


def round_up_to_multiple(quantity: float, order_multiple: float) -> float:
    if quantity <= 0:
        return 0.0
    if order_multiple <= 0:
        order_multiple = 1.0
    return float(ceil(quantity / order_multiple - EPSILON) * order_multiple)


def round_required_quantity(
    *,
    raw_required_quantity: float,
    minimum_order_quantity: float | None = None,
    rule: ProductPackRule | None = None,
    legacy_pack_size: float | None = None,
) -> PackRoundingResult:
    raw = round(max(float(raw_required_quantity or 0), 0.0), 6)
    minimum = parse_positive(minimum_order_quantity) or 0.0
    pre_pack = round(max(raw, minimum), 6) if raw > 0 else 0.0
    warnings: list[str] = []

    if rule is not None and parse_positive(rule.order_multiple):
        order_multiple = float(rule.order_multiple)
        rule_id = rule.id
        rule_name = rule.rule_name
        rule_source = "product_pack_rule"
        pack_type = rule.pack_type
        units_per_box = parse_positive(rule.units_per_box)
        units_per_pallet = parse_positive(rule.units_per_pallet)
        pallet_only = bool(rule.pallet_only)
    else:
        legacy_multiple = parse_positive(legacy_pack_size)
        if legacy_multiple:
            order_multiple = legacy_multiple
            rule_id = None
            rule_name = "Legacy pack size"
            rule_source = "legacy_pack_size"
            pack_type = "pack"
            units_per_box = None
            units_per_pallet = None
            pallet_only = False
            warnings.append("No active pack rule configured; legacy pack size was used for compatibility.")
        else:
            order_multiple = 1.0
            rule_id = None
            rule_name = "No pack rule configured"
            rule_source = "default_order_multiple"
            pack_type = None
            units_per_box = None
            units_per_pallet = None
            pallet_only = False
            if raw > 0:
                warnings.append("No active pack rule configured; order multiple defaults to 1.")

    final = round(round_up_to_multiple(pre_pack, order_multiple), 6)
    display = pack_display(
        final,
        order_multiple=order_multiple,
        pack_type=pack_type,
        units_per_box=units_per_box,
        units_per_pallet=units_per_pallet,
    )
    explanation = f"{format_quantity(raw)} raw -> {format_quantity(final)} final using {format_quantity(order_multiple)} order multiple"
    return PackRoundingResult(
        raw_required_quantity=raw,
        pre_pack_quantity=pre_pack,
        final_quantity=final,
        order_multiple=order_multiple,
        rule_id=rule_id,
        rule_name=rule_name,
        rule_source=rule_source,
        pack_type=pack_type,
        units_per_box=units_per_box,
        units_per_pallet=units_per_pallet,
        pallet_only=pallet_only,
        display=display,
        explanation=explanation,
        warnings=warnings,
    )


def pack_display(
    quantity: float,
    *,
    order_multiple: float,
    pack_type: str | None,
    units_per_box: float | None = None,
    units_per_pallet: float | None = None,
) -> str:
    if quantity <= 0:
        return "0 units"

    unit_label = "units"
    normalized_type = (pack_type or "").lower()
    parts: list[str] = []
    if normalized_type == "pallet" and order_multiple > 0:
        parts.append(f"{format_quantity(quantity / order_multiple)} pallets ({format_quantity(order_multiple)} each)")
    elif normalized_type == "box" and order_multiple > 0:
        parts.append(f"{format_quantity(quantity / order_multiple)} boxes ({format_quantity(order_multiple)} each)")
    elif units_per_box and units_per_box > 0 and normalized_type != "pallet":
        parts.append(f"{format_quantity(quantity / units_per_box)} boxes ({format_quantity(units_per_box)} each)")

    if units_per_pallet and units_per_pallet > 0 and normalized_type != "pallet":
        parts.append(f"{format_quantity(quantity / units_per_pallet)} pallets ({format_quantity(units_per_pallet)} each)")

    if parts:
        return f"{format_quantity(quantity)} {unit_label} = {'; '.join(parts)}"
    return f"{format_quantity(quantity)} {unit_label}"


def format_quantity(value: float) -> str:
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < EPSILON:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")
