from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.routes.health import router as health_router
from app.routes.products import router as products_router
from app.routes.inventory import router as inventory_router
from app.routes.product_suppliers import router as product_suppliers_router
from app.routes.purchase_orders import router as purchase_orders_router
from app.routes.recommendations import router as recommendations_router
from app.routes.seasonality import router as seasonality_router
from app.routes.suppliers import router as suppliers_router
from app.routes.forecast_readiness import router as forecast_readiness_router

import app.models  # noqa: F401


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

if settings.database_auto_create_tables:
    Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(seasonality_router)
app.include_router(forecast_readiness_router)
app.include_router(products_router)
app.include_router(inventory_router)
app.include_router(product_suppliers_router)
app.include_router(purchase_orders_router)
app.include_router(recommendations_router)
app.include_router(suppliers_router)

@app.get("/")
def root():
    return {"message": "Purchasing AI backend is running"}
