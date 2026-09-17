from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Intent2Data API")

class AnalyzeRequest(BaseModel):
    question: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/v1/analyze")
def analyze(req: AnalyzeRequest):
    return {
        "status": "stub",
        "message": "Intent2Data backend skeleton is running"
    }
