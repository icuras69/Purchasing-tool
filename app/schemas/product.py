from pydantic import BaseModel, Field, ConfigDict


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    supplier: str | None = None
    current_stock: float = Field(ge=0)
    safety_stock: float = Field(ge=0, default=0)
    lead_time_days: int = Field(ge=0, default=0)
    min_order_qty: float = Field(ge=0, default=0)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    supplier: str | None
    current_stock: float
    safety_stock: float
    lead_time_days: int
    min_order_qty: float