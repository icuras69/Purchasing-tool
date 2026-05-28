from pydantic import BaseModel, Field


class LLMRecommendationExplanationResponse(BaseModel):
    suggested_action: str
    summary: str
    explanation: str
    risk_flags: list[str]
    missing_data_warnings: list[str]
    confidence: float = Field(ge=0, le=1)
    structured_data_citations: list[str]
    model_name: str
    prompt_version: str
