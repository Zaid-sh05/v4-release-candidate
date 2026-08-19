from typing import Literal
from pydantic import BaseModel, Field

Language = Literal['ar', 'en']

class RouteResult(BaseModel):
    language: Language
    intent: str
    primary_domain: str
    domains: list[str]
    confidence: float = Field(ge=0, le=1)
    matched_terms: list[str] = []
    article_numbers: list[str] = []
    law_numbers: list[str] = []
    years: list[str] = []
    normalized_text: str

class SourceItem(BaseModel):
    id: str
    title: str
    authority: str
    domain: str
    source_url: str
    law_number: str | None = None
    year: str | None = None
    article: str | None = None
    excerpt: str = ''
    verified_at: str | None = None
    source_kind: str = ''
    score: float = 0

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    language: Literal['auto', 'ar', 'en'] = 'auto'
    force_domain: str | None = None
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    answer: str
    route: RouteResult
    sources: list[SourceItem]
    mode: str
    conversation_id: str
    disclaimer: str

class SearchResponse(BaseModel):
    query: str
    domains: list[str]
    results: list[SourceItem]

class FeedbackRequest(BaseModel):
    conversation_id: str | None = None
    rating: Literal['helpful', 'not_helpful']
    note: str | None = Field(default=None, max_length=1200)
