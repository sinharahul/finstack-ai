"""FastAPI RAG API: /ask, /ask/stream (SSE), /memo (PDF), /eval, /feedback.

Run locally in demo mode (no keys, no AWS):
    cd backend && DEMO=1 PYTHONPATH=. uvicorn app.main:app --reload

Run locally in live mode (AWS credentials + Bedrock model access):
    cd backend && PYTHONPATH=. uvicorn app.main:app --reload
"""

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app import demo_store, ingestion, memo as memo_mod, observability, rag
from app.config import Settings
from app.eval import get_dashboard
from app.history import get_history_store
from app.vectorstore import get_store


class AskRequest(BaseModel):
    query: str
    ticker: str | None = None
    chat_history: list[dict] = []
    session_id: str = "default"


class MemoRequest(BaseModel):
    ticker: str | None = None
    query: str = "Summarize this company's latest 10-K."


class FeedbackRequest(BaseModel):
    value: str
    run_id: str | None = None
    comment: str = ""


class IngestRequest(BaseModel):
    ticker: str


def create_app(settings: Settings | None = None,
               store=None, history_store=None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store if store is not None else (
        demo_store.seeded_demo_store() if settings.demo else None
    )
    history = history_store if history_store is not None \
        else get_history_store(settings)
    app = FastAPI(title="FinStack AI - Equity Research Copilot")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _live_store():
        # Live mode resolves the OpenSearch client per request so the app
        # still starts (and serves /health) without AWS credentials.
        return store if store is not None else get_store(settings)

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "demo" if settings.demo else "bedrock"}

    @app.get("/")
    def root():
        return {
            "status": "ok",
            "service": "FinStack AI - Equity Research Copilot",
            "mode": "demo" if settings.demo else "bedrock",
            "endpoints": [
                "POST /ask", "GET /ask/stream", "POST /memo",
                "POST /ingest", "GET /eval", "POST /feedback",
                "GET /health",
            ],
        }

    @app.post("/ask")
    def ask(req: AskRequest):
        history.append(req.session_id, "user", req.query)
        result = rag.answer_question(
            req.query, req.ticker, req.chat_history, settings,
            store=_live_store(),
        )
        history.append(req.session_id, "assistant", result["answer"])
        return {
            "answer": result["answer"],
            "sources": result["sources"],
            "latency_ms": result["latency_ms"],
            "cost": result["cost_usd"],
            "cost_usd": result["cost_usd"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "ingest_started": result.get("ingest_started", False),
        }

    @app.get("/ask/stream")
    def ask_stream(query: str, ticker: str | None = None):
        def gen():
            result = rag.answer_question(
                query, ticker, [], settings, store=_live_store()
            )
            text = result["answer"]
            for i in range(0, len(text), 120):
                yield f"data: {json.dumps({'token': text[i:i + 120]})}\n\n"
            yield f"data: {json.dumps({'sources': result['sources'], 'latency_ms': result['latency_ms'], 'cost': result['cost_usd'], 'ingest_started': result.get('ingest_started', False)})}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/memo")
    def make_memo(req: MemoRequest):
        result = rag.answer_question(
            req.query, req.ticker, [], settings, store=_live_store()
        )
        pdf = memo_mod.build_memo_pdf(
            req.ticker or "", req.query, result["answer"], result["sources"]
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=memo.pdf"},
        )

    @app.post("/ingest")
    def ingest(req: IngestRequest):
        """Pull one ticker's latest 10-K through the pipeline on demand."""
        ticker = (req.ticker or "").strip().upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="ticker is required")
        try:
            return ingestion.ingest_ticker(
                ticker, settings, store=_live_store()
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/eval")
    def eval_dashboard():
        return get_dashboard()

    @app.post("/feedback")
    def feedback(req: FeedbackRequest):
        return observability.log_feedback(req.value, req.run_id, req.comment)

    return app


app = create_app()
