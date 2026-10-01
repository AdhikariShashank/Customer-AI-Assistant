from fastapi import FastAPI

app = FastAPI()


@app.get("/health", tags=["health"])
def health():   
    return {"status": "ok"}