from fastapi import FastAPI
from contextlib import asynccontextmanager
from .qdrant import initialize_qdrant

from .routers import auth, documents, products, cart, user

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_qdrant()

    yield

app = FastAPI(lifespan= lifespan)



app.include_router(auth.router)
app.include_router(documents.router)

@app.get("/health", tags=["health"])
def health():   
    return {"status": "ok"}