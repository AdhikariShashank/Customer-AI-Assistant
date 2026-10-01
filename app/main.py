from fastapi import FastAPI

from .routers import auth, products, cart, user

app = FastAPI()



app.include_router(auth.router)

@app.get("/health", tags=["health"])
def health():   
    return {"status": "ok"}