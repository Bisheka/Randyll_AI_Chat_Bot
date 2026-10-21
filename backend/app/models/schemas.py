from pydantic import BaseModel, Field
from typing import Optional

class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    document_version: str
    university_id: str
    university_name: str
    academic_year: Optional[int] = None
    semester: Optional[str] = None
    admission_type: Optional[str] = None
    degree_level: Optional[str] = None
    program_id: Optional[str] = None
    category_code: str
    category_name: Optional[str] = None
    source_pdf: str
    source_page: int                 # page inside the categorized PDF
    original_source_pages: Optional[str] = None  # pages in the original guideline
    content: str
    heading: Optional[str] = None
    verification_status: str = "pending_review"  # pending_review|approved|rejected
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

class DocumentRecord(BaseModel):
    document_id: str
    document_version: str
    sha256: str
    source_pdf: str
    university_id: str
    university_name: Optional[str] = None
    category_code: Optional[str] = None
    pages: int = 0
    chunk_count: int = 0
    status: str = "pending_review"
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    error: Optional[str] = None

class SourceRef(BaseModel):
    chunk_id: str
    university_name: str
    category_code: str
    source_pdf: str
    source_page: int
    original_source_pages: Optional[str] = None
    excerpt: str

class CreateSession(BaseModel):
    university_id: Optional[str] = None

class ChatMessageIn(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    university_id: Optional[str] = None

class FollowUp(BaseModel):
    label: str      # human title shown on the button, e.g. "Scholarships"
    question: str   # full question sent when the button is clicked

class ChatMessageOut(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceRef] = []
    follow_ups: list[FollowUp] = []
    needs_counsellor: bool = False
    missing_information: list[str] = []
    intent_category: Optional[str] = None

class FeedbackIn(BaseModel):
    session_id: str
    helpful: bool
    comment: Optional[str] = Field(default=None, max_length=1000)

class IngestIn(BaseModel):
    directory: Optional[str] = None
    approve: bool = False

class ReviewIn(BaseModel):
    status: str  # approved|rejected
