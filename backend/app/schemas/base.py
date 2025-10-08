from pydantic import BaseModel
from typing import List, Optional, Literal


class DocumentOut(BaseModel):
    id: int
    filename: str
    status: str
    class Config:
        orm_mode = True


class UploadResponse(BaseModel):
    document_id: int
    task_id: str
    status: str


class AskRequest(BaseModel):
    question: str
    document_ids: Optional[List[int]] = None


class Answer(BaseModel):
    answer: str
    answer_type: Literal["factual","contextual","analytical","descriptive","summarization","out_of_scope"]
    sources: List[str] = []
    latency_ms: Optional[int] = None
    retrieved: Optional[int] = None

class SummarizeResponse(Answer):
    pass


class HealthResponse(BaseModel):
    status: str
    components: dict
