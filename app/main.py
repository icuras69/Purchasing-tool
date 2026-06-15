from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.security import require_admin
from app.db.base import Base
from app.db.session import engine
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.products import router as products_router
from app.routes.inventory import router as inventory_router
from app.routes.inbound_stock import router as inbound_stock_router
from app.routes.product_suppliers import router as product_suppliers_router
from app.routes.purchase_orders import router as purchase_orders_router
from app.routes.recommendations import router as recommendations_router
from app.routes.seasonality import router as seasonality_router
from app.routes.suppliers import router as suppliers_router
from app.routes.forecast_readiness import router as forecast_readiness_router
from app.routes.supplier_assignment_review import router as supplier_assignment_review_router

import app.models  # noqa: F401


app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

if settings.database_auto_create_tables:
    Base.metadata.create_all(bind=engine)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


admin_dependencies = [Depends(require_admin)]

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(seasonality_router, dependencies=admin_dependencies)
app.include_router(forecast_readiness_router, dependencies=admin_dependencies)
app.include_router(supplier_assignment_review_router, dependencies=admin_dependencies)
app.include_router(products_router, dependencies=admin_dependencies)
app.include_router(inventory_router, dependencies=admin_dependencies)
app.include_router(inbound_stock_router, dependencies=admin_dependencies)
app.include_router(product_suppliers_router, dependencies=admin_dependencies)
app.include_router(purchase_orders_router, dependencies=admin_dependencies)
app.include_router(recommendations_router, dependencies=admin_dependencies)
app.include_router(suppliers_router, dependencies=admin_dependencies)

@app.get("/", dependencies=admin_dependencies)
def root():
    return {"message": "Purchasing AI backend is running"}
