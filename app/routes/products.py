from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.models.supplier import Supplier
from app.schemas.product import ProductCreate, ProductResponse
from app.schemas.product_supplier import ProductSupplierMappingResponse, WeakMappingResponse
from app.schemas.forecast import ForecastResponse
from app.services.forecasting import build_forecast
from app.services.inbound_stock import get_product_inbound_stock as get_product_inbound_stock_context
from app.services.perf_logging import perf_timer
from app.services.product_search import normalize_search_query, parse_exact_product_id
from app.routes.product_suppliers import serialize_product_supplier

router = APIRouter(prefix="/products", tags=["products"])


def serialize_product(product: Product) -> dict:
    supplier_mappings = sorted(
        product.product_suppliers,
        key=lambda mapping: (not mapping.is_preferred, mapping.id),
    )
    display_mapping = supplier_mappings[0] if supplier_mappings else None
    supplier_record = product.supplier_record

    return {
        "id": product.id,
        "name": product.name,
        "supplier": product.supplier,
        "description": product.description,
        "barcode": product.barcode,
        "orderpro_sku": product.orderpro_sku,
        "supplier_id": product.supplier_id,
        "supplier_name": supplier_record.name if supplier_record else None,
        "supplier_code": supplier_record.orderpro_code if supplier_record else None,
        "supplier_sku": product.supplier_sku,
        "current_stock": product.current_stock,
        "safety_stock": product.safety_stock,
        "lead_time_days": product.lead_time_days,
        "min_order_qty": product.min_order_qty,
        "supplier_count": len(supplier_mappings),
        "preferred_supplier": (
            supplier_record.name
            if supplier_record
            else display_mapping.supplier.name
            if display_mapping and display_mapping.supplier
            else product.supplier
        ),
        "preferred_supplier_id": product.supplier_id if product.supplier_id else display_mapping.supplier_id if display_mapping else None,
        "preferred_supplier_sku": product.supplier_sku if product.supplier_id else display_mapping.supplier_sku if display_mapping else None,
        "mapping_status": "mapped" if product.supplier_id or supplier_mappings else "unmapped",
        "supplier_mappings": [
            {
                "id": mapping.id,
                "supplier_id": mapping.supplier_id,
                "supplier_name": mapping.supplier.name if mapping.supplier else None,
                "supplier_sku": mapping.supplier_sku,
                "supplier_product_name": mapping.supplier_product_name,
                "purchase_price": mapping.purchase_price,
                "currency": mapping.currency,
                "minimum_order_quantity": mapping.minimum_order_quantity,
                "pack_size": mapping.pack_size,
                "lead_time_days": mapping.lead_time_days,
                "is_preferred": mapping.is_preferred,
                "match_status": mapping.match_status,
                "match_method": mapping.match_method,
                "match_confidence": mapping.match_confidence,
                "last_synced_at": mapping.last_synced_at,
            }
            for mapping in supplier_mappings
        ],
    }


def product_list_query(db: Session):
    return (
        db.query(Product)
        .options(
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.supplier_record),
        )
        .filter(Product.is_active.is_(True))
    )


def apply_product_search(db: Session, query, search: str | None):
    normalized = normalize_search_query(search)
    if not normalized:
        return query

    exact_product_id = parse_exact_product_id(normalized)
    if exact_product_id is not None:
        exact_id_exists = query.filter(Product.id == exact_product_id).first()
        if exact_id_exists:
            return query.filter(Product.id == exact_product_id)

    query = query.outerjoin(Supplier, Product.supplier_id == Supplier.id)
    exact_conditions = [
        func.lower(Product.orderpro_sku) == normalized,
        func.lower(Product.barcode) == normalized,
        func.lower(Product.supplier_sku) == normalized,
    ]
    exact_query = query.filter(or_(*exact_conditions))
    if exact_query.first():
        return exact_query

    like_pattern = f"%{normalized}%"
    return query.filter(
        or_(
            func.lower(Product.name).like(like_pattern),
            func.lower(Product.description).like(like_pattern),
            func.lower(Supplier.name).like(like_pattern),
            func.lower(Supplier.orderpro_code).like(like_pattern),
        )
    )


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    existing_product = db.query(Product).filter(Product.name == payload.name).first()
    if existing_product:
        raise HTTPException(status_code=400, detail="Product with this name already exists.")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return serialize_product(product)


@router.get("/", response_model=list[ProductResponse])
def list_products(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    with perf_timer("products.list", search=search) as perf:
        products = (
            apply_product_search(db, product_list_query(db), search)
            .order_by(Product.id.asc())
            .all()
        )
        perf["returned"] = len(products)
        return [serialize_product(product) for product in products]


@router.get("/unmapped", response_model=list[ProductResponse])
def list_unmapped_products(
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    with perf_timer("products.unmapped", search=search) as perf:
        products = (
            apply_product_search(db, product_list_query(db).filter(Product.supplier_id.is_(None)), search)
            .order_by(Product.id.asc())
            .all()
        )
        perf["returned"] = len(products)
        return [serialize_product(product) for product in products]


@router.get("/weak-mappings", response_model=list[WeakMappingResponse])
def list_weak_mappings(
    confidence_threshold: float = Query(0.8, ge=0, le=1),
    db: Session = Depends(get_db),
):
    weak_rows = []

    unmapped_products = (
        db.query(Product)
        .filter(Product.is_active.is_(True), ~Product.product_suppliers.any())
        .order_by(Product.id.asc())
        .all()
    )
    for product in unmapped_products:
        weak_rows.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "reason": "no_supplier_mappings",
            }
        )

    weak_mappings = (
        db.query(ProductSupplier)
        .options(
            selectinload(ProductSupplier.product),
            selectinload(ProductSupplier.supplier),
        )
        .filter(
            ProductSupplier.product.has(Product.is_active.is_(True)),
            or_(
                ProductSupplier.match_status != "matched",
                ProductSupplier.match_status.is_(None),
                ProductSupplier.match_confidence < confidence_threshold,
            )
        )
        .order_by(ProductSupplier.product_id.asc(), ProductSupplier.id.asc())
        .all()
    )
    for mapping in weak_mappings:
        if mapping.match_status != "matched":
            reason = "match_status_not_matched"
        elif mapping.match_confidence is not None and mapping.match_confidence < confidence_threshold:
            reason = "match_confidence_below_threshold"
        else:
            reason = "needs_review"

        weak_rows.append(
            {
                "product_id": mapping.product_id,
                "product_name": mapping.product.name if mapping.product else "",
                "reason": reason,
                "mapping_id": mapping.id,
                "supplier_id": mapping.supplier_id,
                "supplier_name": mapping.supplier.name if mapping.supplier else None,
                "supplier_sku": mapping.supplier_sku,
                "supplier_product_name": mapping.supplier_product_name,
                "match_status": mapping.match_status,
                "match_method": mapping.match_method,
                "match_confidence": mapping.match_confidence,
            }
        )

    return weak_rows


@router.get("/{product_id}/supplier-mappings", response_model=list[ProductSupplierMappingResponse])
def list_product_supplier_mappings(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    mappings = (
        db.query(ProductSupplier)
        .options(
            selectinload(ProductSupplier.product),
            selectinload(ProductSupplier.supplier),
        )
        .filter(ProductSupplier.product_id == product_id)
        .order_by(ProductSupplier.is_preferred.desc(), ProductSupplier.id.asc())
        .all()
    )
    return [serialize_product_supplier(mapping) for mapping in mappings]


@router.get("/{product_id}/inbound-stock")
def get_product_inbound_stock(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return get_product_inbound_stock_context(db, product_id)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
            selectinload(Product.supplier_record),
        )
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    return serialize_product(product)


@router.get("/{product_id}/forecast", response_model=ForecastResponse)
def forecast_product(product_id: int, db: Session = Depends(get_db)):
    print(f"Forecast request received for product_id={product_id}")

    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    print(f"Resolved product: id={product.id}, name={product.name}")
    return build_forecast(db, product)
