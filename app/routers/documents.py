from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..security import require_admin
from ..models import User, Document
from ..config import get_settings
from pathlib import Path
import hashlib
import fitz
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI


router = APIRouter(tags=["documents"])

settings = get_settings()
STORAGE_DIR =  Path(settings.temp_documents_path)
STORAGE_DIR.mkdir(parents= True, exist_ok= True)

_extract_limiter = InMemoryRateLimiter(requests_per_second=0.4, check_every_n_seconds=0.2, max_bucket_size=2)
xllm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_retries=12,   # vision extraction (throttled)
                  rate_limiter=_extract_limiter)


def calculate_hash(file_path: Path):
    sha256 = hashlib.sha256()
    with file_path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()

def page_type(page: fitz.Page) -> str:
    text_ = page.get_text().strip()
    if len(text_) < 200:
        return "image"
    for it in page.get_image_info(xrefs=True):                 # big content image on a text page
        if it.get("width", 0) * it.get("height", 0) >= 200 * 200 and abs(fitz.Rect(it["bbox"])) / abs(page.rect) > 0.15:
            return "image"
    return "text"


def ingestDocument(file_path: Path):
    pdf = fitz.open(file_path)

    for i, page in enumerate(pdf, 1):
        pageType = page_type(page)
        if (pageType == "image"):
            



@router.post("/documents")
async def create_document(file: UploadFile = File(...), 
                          admin: User = Depends(require_admin), 
                          db: AsyncSession = Depends(get_db)):
    if not file.filename:
        raise HTTPException(
            status_code= 400,
            detail= "Filename is required"
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code= 400,
            detail="Only PDF files are suported"
        )

    temp_path = STORAGE_DIR / f"temp_{file.filename}"
    
    with temp_path.open("wb") as buffer:
        while chunk := await file.read(1024 * 1024):
            buffer.write(chunk)

    file_hash = calculate_hash(temp_path)
    result = await db.scalar(select(Document).where(Document.file_hash == file_hash))

    if result:
        print("Document already exists!")
        return {
            "status": "Document already present",
            "document_id": result.id
        }

    pdf = fitz.open(temp_path)
    page_count = len(pdf)
    pdf.close()

    ingestDocument(temp_path)

    

    document = Document(
        file_hash = file_hash,
        user_id = admin.id,
        filename = file.filename,
        path = str(temp_path),
        pages = page_count,
        status = "ready"
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    return {
        "status": "Document added",
        "document_id": document.id,
        "pages": document.pages
    }