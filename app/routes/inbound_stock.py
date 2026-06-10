from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.inbound_stock import inbound_stock_summary


router = APIRouter(prefix="/inbound-stock", tags=["inbound-stock"])


@router.get("/summary")
def get_inbound_stock_summary(db: Session = Depends(get_db)):
    return inbound_stock_summary(db)
