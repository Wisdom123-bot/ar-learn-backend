from pydantic import BaseModel, Field


class AIQueryRequest(BaseModel):
    school_id: str = Field(..., description="UUID of the school")
    question: str = Field(..., example="Why did Grade 8 perform poorly?")


class AIQueryResponse(BaseModel):
    answer: str
    related_data: dict = {}