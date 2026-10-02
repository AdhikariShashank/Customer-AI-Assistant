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


router = APIRouter(tags=["documents"])

settings = get_settings()
STORAGE_DIR =  Path(settings.temp_documents_path)
STORAGE_DIR.mkdir(parents= True, exist_ok= True)

def calculate_hash(file_path: Path):
    sha256 = hashlib.sha256()
    with file_path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()


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
    
    




    

    

    




    