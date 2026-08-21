from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SupplierUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    contact_method: str | None = Field(default=None, max_length=100)
    payment_terms: str | None = Field(default=None, max_length=255)
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    lead_time_min_days: int | None = Field(default=None, ge=1, le=365)
    lead_time_max_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("email", "phone", "website", "contact_method", "payment_terms", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SupplierResponse(BaseModel):
    id: int
    name: str
    orderpro_id: str | None
    orderpro_code: str | None
    source_system: str | None
    is_active: bool
    local_profile_override: bool
    last_synced_at: datetime | None
    email: str | None
    phone: str | None
    website: str | None
    contact_method: str | None
    payment_terms: str | None
    lead_time_raw: str | None
    lead_time_days: int | None
    lead_time_min_days: int | None
    lead_time_max_days: int | None
    notes: str | None
    active_skus: int
    lead_time_needs_review: bool
    product_count: int
    active_product_count: int
    writes_to_orderpro: bool = False
