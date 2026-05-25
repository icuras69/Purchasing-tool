from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.product import Product
from app.models.product_supplier import ProductSupplier
from app.schemas.product import ProductCreate, ProductResponse
from app.schemas.forecast import ForecastResponse
from app.services.forecasting import build_forecast

router = APIRouter(prefix="/products", tags=["products"])


def serialize_product(product: Product) -> dict:
    supplier_mappings = sorted(
        product.product_suppliers,
        key=lambda mapping: (not mapping.is_preferred, mapping.id),
    )
    display_mapping = supplier_mappings[0] if supplier_mappings else None

    return {
        "id": product.id,
        "name": product.name,
        "supplier": product.supplier,
        "current_stock": product.current_stock,
        "safety_stock": product.safety_stock,
        "lead_time_days": product.lead_time_days,
        "min_order_qty": product.min_order_qty,
        "supplier_count": len(supplier_mappings),
        "preferred_supplier": (
            display_mapping.supplier.name
            if display_mapping and display_mapping.supplier
            else product.supplier
        ),
        "preferred_supplier_id": display_mapping.supplier_id if display_mapping else None,
        "preferred_supplier_sku": display_mapping.supplier_sku if display_mapping else None,
        "mapping_status": "mapped" if supplier_mappings else "unmapped",
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
def list_products(db: Session = Depends(get_db)):
    products = (
        db.query(Product)
        .options(
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
        )
        .order_by(Product.id.asc())
        .all()
    )
    return [serialize_product(product) for product in products]


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(
            selectinload(Product.product_suppliers).selectinload(ProductSupplier.supplier),
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
