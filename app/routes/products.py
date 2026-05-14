from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse
from app.schemas.forecast import ForecastResponse
from app.services.forecasting import build_forecast

router = APIRouter(prefix="/products", tags=["products"])


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    existing_product = db.query(Product).filter(Product.name == payload.name).first()
    if existing_product:
        raise HTTPException(status_code=400, detail="Product with this name already exists.")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.id.asc()).all()


@router.get("/{product_id}/forecast", response_model=ForecastResponse)
def forecast_product(product_id: int, db: Session = Depends(get_db)):
    print(f"Forecast request received for product_id={product_id}")

    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    print(f"Resolved product: id={product.id}, name={product.name}")
    return build_forecast(db, product)