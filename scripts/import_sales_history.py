import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.sales_history_raw import SalesHistoryRaw
from app.models.usage_history import UsageHistory

STANDARD_HEADERS = [
    "Name",
    "Barcode",
    "Description",
    "Batch",
    "Invoice",
    "Date",
    "Price",
    "Quantity",
    "VAT Rate",
    "Gross",
    "Code",
    "Sales Person",
    "Purchase Order",
    "Nett",
    "VAT",
]

YEAR_SHEETS = ["2022", "2023", "2024", "2025"]

NON_INVENTORY_BARCODES = {
    "SHIPPING": "shipping",
    "DISCOUNT": "discount",
    "PACKAGING": "packaging",
    "PACKAGING2": "packaging",
    "MISCELLANEOUS": "miscellaneous",
}

NON_INVENTORY_DESCRIPTION_RULES = {
    "FLAT RATE": "shipping",
    "STANDARD": "shipping",
    "DPD UK": "shipping",
    "SHIPPING": "shipping",
    "DISCOUNT": "discount",
    "PACKAGING": "packaging",
    "CARRIER BAG": "packaging",
}


def clean_scalar(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    return str(value).strip()


def normalize_barcode(value):
    s = clean_scalar(value)
    if not s:
        return None
    s = s.replace("\xa0", " ").strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s.upper()


def normalize_text(value):
    s = clean_scalar(value)
    if s is None:
        return None
    s = str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None

def normalize_token(value):
    s = clean_scalar(value)
    if s is None:
        return None
    token = re.sub(r"[^A-Z0-9]+", "", str(s).upper())
    return token or None
    if not value:
        return None
    token = re.sub(r"[^A-Z0-9]+", "", value.upper())
    return token or None


def build_source_key(barcode_clean, description_clean):
    barcode_part = normalize_token(barcode_clean) or "NOBC"
    desc_part = normalize_token(description_clean) or "NODESC"
    return f"{barcode_part}::{desc_part[:180]}"


def classify_row(barcode_clean, description_clean):
    barcode = (clean_scalar(barcode_clean) or "").upper()
    description = (clean_scalar(description_clean) or "").upper()

    if barcode in NON_INVENTORY_BARCODES:
        return NON_INVENTORY_BARCODES[barcode], True

    for phrase, row_type in NON_INVENTORY_DESCRIPTION_RULES.items():
        if phrase in description and barcode in {"", "SHIPPING", "DISCOUNT", "PACKAGING", "PACKAGING2", "MISCELLANEOUS", "LISTB"}:
            return row_type, True

    return "inventory", False
    barcode = (barcode_clean or "").upper()
    description = (description_clean or "").upper()

    if barcode in NON_INVENTORY_BARCODES:
        return NON_INVENTORY_BARCODES[barcode], True

    for phrase, row_type in NON_INVENTORY_DESCRIPTION_RULES.items():
        if phrase in description and barcode in {"", "SHIPPING", "DISCOUNT", "PACKAGING", "PACKAGING2", "MISCELLANEOUS", "LISTB"}:
            return row_type, True

    return "inventory", False


def parse_date(value):
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def parse_float(value):
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return 0.0
    return float(parsed)


def load_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    if sheet_name != "2023":
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
        df.columns = [str(c).strip() for c in df.columns]
        df = df[STANDARD_HEADERS].copy()
        df["source_sheet"] = sheet_name
        df["source_row_number"] = df.index + 2
        return df

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)

    header_idx = None
    for idx, row in raw.iterrows():
        first_three = [str(row[i]).strip() if row[i] is not None else None for i in range(3)]
        if first_three == ["Name", "Barcode", "Description"]:
            header_idx = idx
            break

    if header_idx is None:
        raise ValueError("Could not locate the embedded header row in sheet 2023.")

    top = raw.iloc[:header_idx, : len(STANDARD_HEADERS)].copy()
    top.columns = STANDARD_HEADERS
    top["source_sheet"] = sheet_name
    top["source_row_number"] = top.index + 1

    bottom = raw.iloc[header_idx + 1 :, : len(STANDARD_HEADERS)].copy()
    bottom.columns = STANDARD_HEADERS
    bottom["source_sheet"] = sheet_name
    bottom["source_row_number"] = bottom.index + 1

    df = pd.concat([top, bottom], ignore_index=True)
    return df


def load_all_years(path: Path) -> pd.DataFrame:
    frames = [load_sheet(path, sheet_name) for sheet_name in YEAR_SHEETS]
    return pd.concat(frames, ignore_index=True)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["customer_name"] = df["Name"].apply(normalize_text)
    df["barcode_raw"] = df["Barcode"].apply(clean_scalar)
    df["barcode_clean"] = df["Barcode"].apply(normalize_barcode)
    df["description_clean"] = df["Description"].apply(normalize_text)
    df["batch_clean"] = df["Batch"].apply(normalize_text)
    df["invoice_clean"] = df["Invoice"].apply(clean_scalar)
    df["txn_date"] = df["Date"].apply(parse_date)

    df["price_num"] = df["Price"].apply(parse_float)
    df["quantity_num"] = df["Quantity"].apply(parse_float)
    df["vat_rate_num"] = df["VAT Rate"].apply(parse_float)
    df["gross_num"] = df["Gross"].apply(parse_float)
    df["nett_num"] = df["Nett"].apply(parse_float)
    df["vat_num"] = df["VAT"].apply(parse_float)

    df["code_clean"] = df["Code"].apply(clean_scalar)
    df["sales_person_clean"] = df["Sales Person"].apply(normalize_text)
    df["purchase_order_ref_clean"] = df["Purchase Order"].apply(clean_scalar)

    row_meta = df.apply(
        lambda row: classify_row(row["barcode_clean"], row["description_clean"]),
        axis=1,
        result_type="expand",
    )
    df["row_type"] = row_meta[0]
    df["is_non_inventory"] = row_meta[1]
    df["is_return"] = df["quantity_num"] < 0

    df["source_key"] = df.apply(
        lambda row: build_source_key(row["barcode_clean"], row["description_clean"]),
        axis=1,
    )

    return df


def upsert_products(db, df: pd.DataFrame):
    working = (
        df[["source_key", "barcode_clean", "description_clean", "row_type", "is_non_inventory"]]
        .copy()
        .dropna(subset=["source_key"])
    )

    # Prefer rows that:
    # 1) are inventory
    # 2) have a barcode
    # 3) have a longer description
    working["inventory_rank"] = working["is_non_inventory"].apply(lambda x: 1 if x else 0)
    working["barcode_rank"] = working["barcode_clean"].apply(lambda x: 0 if x else 1)
    working["desc_len"] = working["description_clean"].apply(lambda x: len(str(x)) if x else 0)

    working = working.sort_values(
        by=["source_key", "inventory_rank", "barcode_rank", "desc_len"],
        ascending=[True, True, True, False],
    )

    # Keep exactly one row per source_key
    distinct_products = (
        working.drop_duplicates(subset=["source_key"], keep="first")
        .drop(columns=["inventory_rank", "barcode_rank", "desc_len"])
        .to_dict(orient="records")
    )

    existing = {
        p.source_key: p
        for p in db.query(Product).filter(Product.source_key.is_not(None)).all()
    }

    created = 0
    updated = 0

    for item in distinct_products:
        source_key = item["source_key"]
        product = existing.get(source_key)
        product_name = item["description_clean"] or source_key

        if product is None:
            product = Product(
                source_key=source_key,
                name=product_name,
                barcode=item["barcode_clean"],
                canonical_description=item["description_clean"],
                product_type=item["row_type"],
                is_non_inventory=bool(item["is_non_inventory"]),
                min_order_qty=1,
            )
            db.add(product)

        try:
            db.flush()
        except Exception:
            print(f"Failed inserting product: source_key={source_key}, name={product_name}")
            raise

            existing[source_key] = product
            created += 1
            product = Product(
                source_key=source_key,
                name=product_name,
                barcode=item["barcode_clean"],
                canonical_description=item["description_clean"],
                product_type=item["row_type"],
                is_non_inventory=bool(item["is_non_inventory"]),
                min_order_qty=1,
            )
            db.add(product)

            # Critical fix: register it immediately so duplicates in the same batch
            # do not get inserted again before commit
            existing[source_key] = product
            created += 1
        else:
            changed = False

            if not product.barcode and item["barcode_clean"]:
                product.barcode = item["barcode_clean"]
                changed = True

            if not product.canonical_description and item["description_clean"]:
                product.canonical_description = item["description_clean"]
                changed = True

            if product.product_type != item["row_type"]:
                product.product_type = item["row_type"]
                changed = True

            if product.is_non_inventory != bool(item["is_non_inventory"]):
                product.is_non_inventory = bool(item["is_non_inventory"])
                changed = True

            # Optional: if current name is weak, improve it
            if (not product.name or product.name == product.source_key) and product_name:
                product.name = product_name
                changed = True

            if changed:
                updated += 1

    db.commit()

    product_map = {
        p.source_key: p.id
        for p in db.query(Product).filter(Product.source_key.is_not(None)).all()
    }

    return created, updated, product_map
    distinct_products = (
        df[["source_key", "barcode_clean", "description_clean", "row_type", "is_non_inventory"]]
        .drop_duplicates()
        .to_dict(orient="records")
    )

    existing = {
        p.source_key: p
        for p in db.query(Product).filter(Product.source_key.is_not(None)).all()
    }

    created = 0
    updated = 0

    for item in distinct_products:
        product = existing.get(item["source_key"])
        product_name = item["description_clean"] or item["source_key"]

        if product is None:
            product = Product(
                source_key=item["source_key"],
                name=product_name,
                barcode=item["barcode_clean"],
                canonical_description=item["description_clean"],
                product_type=item["row_type"],
                is_non_inventory=bool(item["is_non_inventory"]),
                min_order_qty=1,
            )
            db.add(product)
            created += 1
        else:
            changed = False

            if not product.barcode and item["barcode_clean"]:
                product.barcode = item["barcode_clean"]
                changed = True

            if not product.canonical_description and item["description_clean"]:
                product.canonical_description = item["description_clean"]
                changed = True

            if not product.source_key and item["source_key"]:
                product.source_key = item["source_key"]
                changed = True

            if product.product_type != item["row_type"]:
                product.product_type = item["row_type"]
                changed = True

            if product.is_non_inventory != bool(item["is_non_inventory"]):
                product.is_non_inventory = bool(item["is_non_inventory"])
                changed = True

            if changed:
                updated += 1

    db.commit()

    product_map = {
        p.source_key: p.id
        for p in db.query(Product).filter(Product.source_key.is_not(None)).all()
    }

    return created, updated, product_map


def replace_raw_sales(db, df: pd.DataFrame, workbook_name: str, product_map: dict[str, int]):
    db.query(SalesHistoryRaw).filter(SalesHistoryRaw.source_workbook == workbook_name).delete(synchronize_session=False)
    db.commit()

    raw_rows = []
    for row in df.to_dict(orient="records"):
        raw_rows.append(
            {
                "source_workbook": workbook_name,
                "source_sheet": row["source_sheet"],
                "source_row_number": int(row["source_row_number"]),
                "customer_name": row["customer_name"],
                "barcode_raw": row["barcode_raw"],
                "barcode_clean": row["barcode_clean"],
                "description": row["description_clean"],
                "batch": row["batch_clean"],
                "invoice": row["invoice_clean"],
                "txn_date": row["txn_date"],
                "price": row["price_num"],
                "quantity": row["quantity_num"],
                "vat_rate": row["vat_rate_num"],
                "gross": row["gross_num"],
                "code": row["code_clean"],
                "sales_person": row["sales_person_clean"],
                "purchase_order_ref": row["purchase_order_ref_clean"],
                "nett": row["nett_num"],
                "vat": row["vat_num"],
                "source_key": row["source_key"],
                "row_type": row["row_type"],
                "is_non_inventory": bool(row["is_non_inventory"]),
                "is_return": bool(row["is_return"]),
                "product_id": product_map.get(row["source_key"]),
            }
        )

    db.bulk_insert_mappings(SalesHistoryRaw, raw_rows)
    db.commit()

    return len(raw_rows)


def rebuild_usage_history(db, df: pd.DataFrame, product_map: dict[str, int]):
    source_system = "historical_sales_excel"
    db.query(UsageHistory).filter(UsageHistory.source_system == source_system).delete(synchronize_session=False)
    db.commit()

    usage_agg = defaultdict(
        lambda: {
            "qty_used": 0.0,
            "qty_returned": 0.0,
            "net_qty": 0.0,
            "gross_revenue": 0.0,
        }
    )

    inventory_rows = df[df["row_type"] == "inventory"]

    for row in inventory_rows.to_dict(orient="records"):
        product_id = product_map.get(row["source_key"])
        txn_date = row["txn_date"]

        if not product_id or not txn_date:
            continue

        key = (product_id, txn_date)
        quantity = float(row["quantity_num"])
        gross = float(row["gross_num"])

        if quantity >= 0:
            usage_agg[key]["qty_used"] += quantity
        else:
            usage_agg[key]["qty_returned"] += abs(quantity)

        usage_agg[key]["net_qty"] += quantity
        usage_agg[key]["gross_revenue"] += gross

    usage_rows = []
    for (product_id, txn_date), metrics in usage_agg.items():
        usage_rows.append(
            {
                "product_id": product_id,
                "date": txn_date,
                "qty_used": round(metrics["qty_used"], 4),
                "qty_returned": round(metrics["qty_returned"], 4),
                "net_qty": round(metrics["net_qty"], 4),
                "gross_revenue": round(metrics["gross_revenue"], 4),
                "source_system": source_system,
            }
        )

    db.bulk_insert_mappings(UsageHistory, usage_rows)
    db.commit()

    return len(usage_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("excel_path", help="Path to the sales history workbook")
    args = parser.parse_args()

    excel_path = Path(args.excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"File not found: {excel_path}")

    workbook_name = excel_path.name

    print("Loading workbook...")
    df = load_all_years(excel_path)
    print(f"Loaded {len(df)} raw rows from yearly sheets.")

    print("Normalizing data...")
    df = normalize_dataframe(df)

    db = SessionLocal()
    try:
        print("Upserting products...")
        created, updated, product_map = upsert_products(db, df)
        print(f"Products created: {created}, updated: {updated}")

        print("Replacing raw sales history...")
        raw_count = replace_raw_sales(db, df, workbook_name, product_map)
        print(f"Inserted raw sales rows: {raw_count}")

        print("Rebuilding usage history...")
        usage_count = rebuild_usage_history(db, df, product_map)
        print(f"Inserted usage history rows: {usage_count}")

        print("Import complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()