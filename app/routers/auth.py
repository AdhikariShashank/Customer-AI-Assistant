"""Auth endpoints: register, sign in (get a JWT), read current user."""
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, Token, LoginDTO
from ..security import hash_password, verify_password, get_current_user

router = APIRouter(tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: AsyncSession = Depends(get_db)):
    existing = (await session.scalars(select(User).where(User.email == data.email))).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    role = "admin" if data.role == "admin" else "user"
    user = User(email=data.email, hashed_password=hash_password(data.password), role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/signin", response_model=Token)
async def signin(data: LoginDTO, session: AsyncSession = Depends(get_db)):
    user = (await session.scalars(select(User).where(User.email == data.username))).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password")

    exp = datetime.now() + timedelta(minutes=settings.jwt_expire_minutes)
    token = jwt.encode({"_id": user.id, "exp": exp}, settings.jwt_secret, settings.jwt_algorithm)
    return {"access_token": token}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
