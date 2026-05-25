from fastapi import FastAPI

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.routes.health import router as health_router
from app.routes.products import router as products_router
from app.routes.inventory import router as inventory_router

import app.models  # noqa: F401


app = FastAPI(title=settings.app_name)

if settings.database_auto_create_tables:
    Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(products_router)
app.include_router(inventory_router)

@app.get("/")
def root():
    return {"message": "Purchasing AI backend is running"}
