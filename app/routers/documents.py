from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..security import require_admin
from ..models import User, Document
from ..core.config import get_settings
from pathlib import Path
import fitz, base64, hashlib, uuid
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
from ..prompts.ingestion import VISION_READER_PROMPT
from qdrant_client import models
from ..qdrant import qdrant_client
import cohere
import pymupdf4llm


router = APIRouter(tags=["documents"])
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

settings = get_settings()
STORAGE_DIR =  Path(settings.temp_documents_path)
STORAGE_DIR.mkdir(parents= True, exist_ok= True)

co = cohere.ClientV2(api_key=settings.cohere_api_key)




_extract_limiter = InMemoryRateLimiter(requests_per_second=0.4, check_every_n_seconds=0.2, max_bucket_size=2)
xllm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_retries=12,   # vision extraction (throttled)
                  rate_limiter=_extract_limiter)


def embed_texts(texts, input_type="search_document"):
    out = []
    for i in range(0, len(texts), 90):
        batch = texts[i:i+90]
        r = co.embed(model="embed-v4.0", input_type=input_type,
                embedding_types=["float"], output_dimension=settings.embed_dim, texts=batch)
        out += [list(v) for v in r.embeddings.float_]
    return out

def to_units(text_):
    if len(text_) <= 1800:
        return [text_]
    else:
        return splitter.split_text(text_)


def item_number(entry):
    e = entry.strip()
    if e.startswith("[") and "]" in e[:7] and e[1:e.index("]")].isdigit():
        return int(e[1:e.index("]")])
    
    "Hello".split(" ", )
    
    first = e.split(" ", 1)[0]                     # look at the first word only
    if first[:-1].isdigit() and first[-1] == ".":                  # "12."
        return int(first[:-1])
    
    if len(first) == 2 and first[0].isalpha() and first[1] in ".)": # "A." or "a)"
        return ord(first[0].upper()) - 64
    
    return None

def is_item(line):
    """A line is a list item if it starts with a markdown bullet OR with a number/letter marker."""
    return line.startswith(("- ", "* ")) or item_number(line) is not None

def split_page(lines):
    """ONE simple rule for every line: list item -> its own block, anything else -> text block."""
    blocks = []
    
    for line in lines:
        s = line.strip()
        if not s:
            continue
        
        if is_item(s):
            text = s[2:].strip() if s[:2] in ("- ", "* ") else s   # drop the bullet prefix
            blocks.append({"type": "item", "text": text})
        elif blocks and blocks[-1]["type"] == "text":
            blocks[-1]["text"] += "\n" + s                         # grow the current text block
        else:
            blocks.append({"type": "text", "text": s})
    print(blocks)
    return blocks

def page_data_url(page, zoom=2.0):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()

class VisionReader(BaseModel):
    extracted_text: str = Field(description= "All text visible on the page, transcribed vertabim; " \
    "tabular content as one line per row; '' if none")
    caption: str = Field(description= "details description of charts/diagram/layout/photos; '' if none")

vision_reader = xllm.with_structured_output(VisionReader)


def embed_image(page: fitz.Page):
    image_data_url = page_data_url(page)

    response = co.embed(
    model="embed-v4.0",
    images=[image_data_url],
    input_type="image",
    embedding_types=["float"],
    output_dimension=1536,
    )

    return response.embeddings.float_[0]


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
    pdf: fitz = fitz.open(file_path)

    pts = []
    last_no = None
    list_id = 0
    for i, page in enumerate(pdf, 1):
        pageType = page_type(page)
        if (pageType == "image"):
            native = page.get_text().strip()
            response: VisionReader = vision_reader.invoke([
                HumanMessage(content=[
                    {
                        "type": "text", 
                        "text": VISION_READER_PROMPT.format(native_text= native)
                    }, 
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": page_data_url(page)
                        }
                    }
                ])
            ])

            # response = VisionReader(
            #     extracted_text="This is some dummy extracted text from the PDF page.",
            #     caption="This page contains a sample diagram showing the relationship between products and customers."
            # )

            content = f"extracted_text: \n{response.extracted_text}\n\ncaption: \n{response.caption}"

            image_embed = embed_image(page)

            pts.append(models.PointStruct(
                id = str(uuid.uuid4()),
                vector = {
                    "dense": image_embed,
                    "bm25": models.Document(text = content or f"Page: {i}", model= "Qdrant/bm25")
                },
                payload= {
                    "path": file_path,
                    "page": i,
                    "filename": pdf.name,
                    "kind": "image",
                    "seq": -1,
                    "doc": pdf.name,
                    "text": content[:400]
                }
            ))

            lines = content.splitlines()

        else:
            lines = pymupdf4llm.to_markdown(pdf, pages = [i - 1]).splitlines()

        blocks = split_page(lines)

        units = []

        for block in blocks:
            if block["type"] == "item":
                no = item_number(block["text"])
            else:
                no = None

            if no is not None:
                if last_no is None or no <= last_no:
                    list_id += 1

                last_no = no
                units.append({
                    "payload": {
                        "kind": "item",
                        "list_id": list_id,
                        "item_no": no
                    }, 
                "text": block["text"]
                })
            else:
                for u in to_units(block["text"]):
                    units.append({
                        "payload":
                            {
                                "kind": "chunk"
                            },
                            "text": u
                        }
                    )

        if last_no is not None and not any(b["type"] == "item" for b in blocks):
            last_no = None                                     # a page with no items ends the list

        if units:
            vecs = embed_texts([u["text"] for u in units])
            for seq, vector in enumerate( vecs):
                unit = units[seq]
                pts.append(models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"dense": vector,
                            "bm25": models.Document(text=unit["text"] or " ", model="Qdrant/bm25")},
                    payload={"filename": pdf.name, "page": i, "seq": seq,
                             "text": unit["text"], **unit["payload"]}))

        if pts:
            qdrant_client.upsert(settings.qdrant_collection, points=pts)

            





            


            

            

            

            


            

            

            


            
            



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