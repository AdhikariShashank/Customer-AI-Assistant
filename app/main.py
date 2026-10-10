from fastapi import FastAPI
from contextlib import asynccontextmanager
from .qdrant import initialize_qdrant
from .db import create_tables
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.core.exception_handlers import (
    app_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    database_exception_handler,
    unhandled_exception_handler,
)

from .routers import auth, documents, products, cart, user


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    initialize_qdrant()

    yield

app = FastAPI(lifespan= lifespan)


# Keep your existing lifespan and FastAPI initialization.

app.add_exception_handler(
    AppException,
    app_exception_handler,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    SQLAlchemyError,
    database_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(products.router)
app.include_router(cart.router)
# app.include_router(user.router)

@app.get("/health", tags=["health"])
def health():   
    return {"status": "ok"}