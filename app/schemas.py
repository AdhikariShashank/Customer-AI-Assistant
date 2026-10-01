from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


# ---------------- Auth ----------------
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"          # allow creating an admin during signup for teaching/demo


class LoginDTO(BaseModel):
    username: str               # we log in with email
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: str
    created_at: datetime


class Token(BaseModel):
    access_token: str


# ---------------- Product ----------------
class ProductCreate(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0
    stock: int = 0


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    price: float
    stock: int


# ---------------- Cart ----------------
class CartAdd(BaseModel):
    product_id: int
    quantity: int = 1


class CartUpdate(BaseModel):
    quantity: int


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: int


# ---------------- Order ----------------
class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    product_name: str
    price: float
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    total: float
    created_at: datetime
    items: list[OrderItemOut] = []


# ---------------- Ticket ----------------
class TicketCreate(BaseModel):
    subject: str
    message: str = ""


class TicketUpdate(BaseModel):
    subject: str | None = None
    message: str | None = None
    status: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subject: str
    message: str
    status: str
    created_at: datetime


# ---------------- Documents ----------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    pages: int
    status: str
    created_at: datetime


class ProcessResponse(BaseModel):
    processed: list[str]
    skipped: list[str]


# ---------------- Chat ----------------
class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    route: str                  # which node answered: "db" | "rag" | "ticket"
    sources: list[str] = []
    cached: bool = False
