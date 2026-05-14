import argparse
import math
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import func

import app.models
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.product import Product
from app.models.product_master_item import ProductMasterItem
from app.models.supplier import Supplier
from app.models.supplier_alias import SupplierAlias


SUPPLIER_ALIASES = {
    "EDF MAN": "ED&F MAN",
    "PORTWEST": "CHARLES HUGHES LIMITED (PREVIOUSLY WESTARO HOSING)",
}

IGNORE_SUPPLIERS = {
    "MIX OF PRODUCTS",
}

INVALID_LEAD_TIME_THRESHOLD = 365


def clean_text(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def normalize_name(value):
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\s+", " ", text.strip())
    return text.upper()


def parse_float(value):
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None


def parse_int(value):
    f = parse_float(value)
    if f is None:
        return None
    return int(round(f))


def parse_lead_time(raw_value):
    raw_text = clean_text(raw_value)
    if raw_text is None:
        return {
            "lead_time_raw": None,
            "lead_time_days": None,
            "lead_time_min_days": None,
            "lead_time_max_days": None,
            "lead_time_needs_review": True,
        }

    numeric = parse_float(raw_value)
    if numeric is not None:
        if numeric <= INVALID_LEAD_TIME_THRESHOLD:
            days = int(round(numeric))
            return {
                "lead_time_raw": raw_text,
                "lead_time_days": days,
                "lead_time_min_days": days,
                "lead_time_max_days": days,
                "lead_time_needs_review": False,
            }

        return {
            "lead_time_raw": raw_text,
            "lead_time_days": None,
            "lead_time_min_days": None,
            "lead_time_max_days": None,
            "lead_time_needs_review": True,
        }

    match = re.search(r"(\d+)\s*-\s*(\d+)", raw_text)
    if match:
        low = int(match.group(1))
        high = int(match.group(2))
        return {
            "lead_time_raw": raw_text,
            "lead_time_days": high,
            "lead_time_min_days": low,
            "lead_time_max_days": high,
            "lead_time_needs_review": False,
        }

    match = re.search(r"(\d+)", raw_text)
    if match:
        days = int(match.group(1))
        return {
            "lead_time_raw": raw_text,
            "lead_time_days": days,
            "lead_time_min_days": days,
            "lead_time_max_days": days,
            "lead_time_needs_review": False,
        }

    return {
        "lead_time_raw": raw_text,
        "lead_time_days": None,
        "lead_time_min_days": None,
        "lead_time_max_days": None,
        "lead_time_needs_review": True,
    }


def canonical_supplier_name(raw_name):
    normalized = normalize_name(raw_name)
    if not normalized:
        return None

    if normalized in IGNORE_SUPPLIERS:
        return None

    return SUPPLIER_ALIASES.get(normalized, normalized)


def load_supplier_sheet(path: Path):
    df = pd.read_excel(path, sheet_name=0, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_product_master_sheet(path: Path):
    df = pd.read_excel(path, sheet_name=0, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def upsert_suppliers(db, suppliers_df: pd.DataFrame):
    existing_suppliers = {
        s.normalized_name: s
        for s in db.query(Supplier).all()
    }

    existing_aliases = {
        a.normalized_alias_name: a
        for a in db.query(SupplierAlias).all()
    }

    created = 0
    updated = 0

    for _, row in suppliers_df.iterrows():
        raw_name = clean_text(row.get("Supplier"))
        normalized = normalize_name(raw_name)
        if not raw_name or not normalized:
            continue

        lead = parse_lead_time(row.get("Lead Time"))

        supplier = existing_suppliers.get(normalized)
        if supplier is None:
            supplier = Supplier(
                name=raw_name,
                normalized_name=normalized,
                email=clean_text(row.get("Email")),
                phone=clean_text(row.get("Phone")),
                website=clean_text(row.get("Website")),
                contact_method=clean_text(row.get("Contact method")),
                payment_terms=clean_text(row.get("Payment Terms")),
                notes=clean_text(row.get("Notes")),
                active_skus=parse_int(row.get("Active SKUs")) or 0,
                **lead,
            )
            db.add(supplier)
            db.flush()
            existing_suppliers[normalized] = supplier
            created += 1
        else:
            supplier.name = raw_name
            supplier.email = clean_text(row.get("Email"))
            supplier.phone = clean_text(row.get("Phone"))
            supplier.website = clean_text(row.get("Website"))
            supplier.contact_method = clean_text(row.get("Contact method"))
            supplier.payment_terms = clean_text(row.get("Payment Terms"))
            supplier.notes = clean_text(row.get("Notes"))
            supplier.active_skus = parse_int(row.get("Active SKUs")) or 0
            supplier.lead_time_raw = lead["lead_time_raw"]
            supplier.lead_time_days = lead["lead_time_days"]
            supplier.lead_time_min_days = lead["lead_time_min_days"]
            supplier.lead_time_max_days = lead["lead_time_max_days"]
            supplier.lead_time_needs_review = lead["lead_time_needs_review"]
            updated += 1

    for alias_raw, target_raw in SUPPLIER_ALIASES.items():
        target_normalized = normalize_name(target_raw)
        alias_normalized = normalize_name(alias_raw)
        supplier = existing_suppliers.get(target_normalized)
        if not supplier:
            continue

        if alias_normalized not in existing_aliases:
            alias = SupplierAlias(
                supplier_id=supplier.id,
                alias_name=alias_raw,
                normalized_alias_name=alias_normalized,
            )
            db.add(alias)
            existing_aliases[alias_normalized] = alias

    db.commit()
    return created, updated


def resolve_supplier_id(db, supplier_raw_name):
    canonical = canonical_supplier_name(supplier_raw_name)
    if not canonical:
        return None

    supplier = (
        db.query(Supplier)
        .filter(Supplier.normalized_name == canonical)
        .first()
    )
    if supplier:
        return supplier.id

    alias = (
        db.query(SupplierAlias)
        .filter(SupplierAlias.normalized_alias_name == canonical)
        .first()
    )
    if alias:
        return alias.supplier_id

    return None


def match_master_item_to_product(db, sku, name):
    sku_norm = normalize_name(sku)
    name_norm = normalize_name(name)

    if sku_norm:
        barcode_matches = (
            db.query(Product)
            .filter(func.upper(Product.barcode) == sku_norm)
            .all()
        )
        if len(barcode_matches) == 1:
            return barcode_matches[0].id, "exact_barcode"

    if name_norm:
        name_matches = (
            db.query(Product)
            .filter(func.upper(Product.name) == name_norm)
            .all()
        )
        if len(name_matches) == 1:
            return name_matches[0].id, "exact_name"

        desc_matches = (
            db.query(Product)
            .filter(func.upper(Product.canonical_description) == name_norm)
            .all()
        )
        if len(desc_matches) == 1:
            return desc_matches[0].id, "exact_description"

    return None, None


def upsert_product_master_items(db, products_df: pd.DataFrame):
    existing = {
        item.sku: item
        for item in db.query(ProductMasterItem).all()
    }

    created = 0
    updated = 0

    for _, row in products_df.iterrows():
        sku = clean_text(row.get("Product SKU"))
        if not sku:
            continue

        supplier_raw = clean_text(row.get("Suppliers"))
        supplier_id = resolve_supplier_id(db, supplier_raw)
        product_id, match_method = match_master_item_to_product(
            db,
            sku=sku,
            name=clean_text(row.get("Name")),
        )

        if product_id is not None:
            match_status = "matched"
        elif supplier_raw and canonical_supplier_name(supplier_raw) is None:
            match_status = "ignored_supplier"
        else:
            match_status = "unmatched"

        item = existing.get(sku)
        if item is None:
            item = ProductMasterItem(
                sku=sku,
                name=clean_text(row.get("Name")) or sku,
                supplier_name_raw=supplier_raw,
                warehouse=clean_text(row.get("Warehouse")),
                cost_price=parse_float(row.get("Cost Price")),
                sales_price=parse_float(row.get("Sales Price")),
                total_cost=parse_float(row.get("Total Cost")),
                total_sales=parse_float(row.get("Total Sales")),
                tax_code=clean_text(row.get("Tax")),
                supplier_id=supplier_id,
                product_id=product_id,
                match_status=match_status,
                match_method=match_method,
            )
            db.add(item)
            created += 1
        else:
            item.name = clean_text(row.get("Name")) or sku
            item.supplier_name_raw = supplier_raw
            item.warehouse = clean_text(row.get("Warehouse"))
            item.cost_price = parse_float(row.get("Cost Price"))
            item.sales_price = parse_float(row.get("Sales Price"))
            item.total_cost = parse_float(row.get("Total Cost"))
            item.total_sales = parse_float(row.get("Total Sales"))
            item.tax_code = clean_text(row.get("Tax"))
            item.supplier_id = supplier_id
            item.product_id = product_id
            item.match_status = match_status
            item.match_method = match_method
            updated += 1

    db.commit()
    return created, updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suppliers_file", help="Path to Suppliers_Lead_times.xlsx")
    parser.add_argument("products_file", help="Path to Products_and_suppliers.xlsx")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    suppliers_path = Path(args.suppliers_file)
    products_path = Path(args.products_file)

    if not suppliers_path.exists():
        raise FileNotFoundError(f"Suppliers file not found: {suppliers_path}")

    if not products_path.exists():
        raise FileNotFoundError(f"Products file not found: {products_path}")

    suppliers_df = load_supplier_sheet(suppliers_path)
    products_df = load_product_master_sheet(products_path)

    db = SessionLocal()
    try:
        print("Importing suppliers...")
        suppliers_created, suppliers_updated = upsert_suppliers(db, suppliers_df)
        print(f"Suppliers created: {suppliers_created}, updated: {suppliers_updated}")

        print("Importing product master items...")
        items_created, items_updated = upsert_product_master_items(db, products_df)
        print(f"Product master items created: {items_created}, updated: {items_updated}")

        print("Import complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()