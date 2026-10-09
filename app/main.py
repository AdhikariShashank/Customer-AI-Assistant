from fastapi import FastAPI
from contextlib import asynccontextmanager
from .qdrant import initialize_qdrant
from .db import create_tables

from .routers import auth, documents, products, cart, user

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    initialize_qdrant()

    yield

app = FastAPI(lifespan= lifespan)


from .routers import auth, documents, products, cart, user

# Keep your existing lifespan and FastAPI initialization.

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(user.router)

@app.get("/health", tags=["health"])
def health():   
    return {"status": "ok"}