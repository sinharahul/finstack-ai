"""Tests: realtime ingestion for arbitrary tickers (mocked EDGAR, no net)."""

import pytest
from fastapi.testclient import TestClient

from app import demo_store, ingestion, rag
from app.config import Settings
from app.history import InMemoryHistoryStore
from app.main import create_app
from app.vectorstore import InMemoryVectorStore

FAKE_TEXT = "Fake 10-K text about growth and risk factors. " * 200


@pytest.fixture
def fake_edgar(monkeypatch):
    monkeypatch.setattr(
        ingestion.edgar, "resolve_ticker", lambda t, s: (1234567, "Fake Corp")
    )
    monkeypatch.setattr(
        ingestion.edgar, "latest_10k",
        lambda cik, s: {
            "filing_date": "2024-02-01", "url": "https://example.invalid/fake",
        },
    )
    monkeypatch.setattr(
        ingestion.edgar, "download_filing_text", lambda url, s: FAKE_TEXT
    )


def _client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(demo=True)
    app = create_app(
        settings=settings,
        store=demo_store.seeded_demo_store(),
        history_store=InMemoryHistoryStore(),
    )
    return TestClient(app)


def test_ingest_arbitrary_ticker(fake_edgar, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(demo=True)
    store = InMemoryVectorStore()
    result = ingestion.ingest_ticker(
        "TSLA", settings, store=store,
        meta=ingestion.MetadataStore(settings, path=str(tmp_path / "m.jsonl")),
    )
    assert result["ticker"] == "TSLA"
    assert result["company"] == "Fake Corp"
    assert result["chunks"] > 0
    assert store.has_ticker("TSLA")
    assert store.has_ticker("tsla")
    assert not store.has_ticker("AAPL")


def test_start_ticker_ingest_stores_raw_only(
    fake_edgar, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    def _fail(*args, **kwargs):
        raise AssertionError("background start must not embed")

    monkeypatch.setattr(ingestion.embeddings, "embed_texts", _fail)
    result = ingestion.start_ticker_ingest("tsla", Settings(demo=True))
    assert result["ingest_started"] is True
    assert result["ticker"] == "TSLA"
    assert result["company"] == "Fake Corp"
    assert result["filing_date"] == "2024-02-01"
    assert result["raw_location"].endswith("TSLA_2024-02-01.txt")


def test_ingest_endpoint(fake_edgar, tmp_path, monkeypatch):
    resp = _client(monkeypatch, tmp_path).post("/ingest", json={"ticker": "tsla"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "TSLA"
    assert data["chunks"] > 0


def test_ingest_unknown_ticker_404(monkeypatch, tmp_path):
    def _missing(ticker, settings):
        raise ValueError(f"Ticker {ticker!r} not found in SEC company tickers")

    monkeypatch.setattr(ingestion.edgar, "resolve_ticker", _missing)
    resp = _client(monkeypatch, tmp_path).post("/ingest", json={"ticker": "NOPE"})
    assert resp.status_code == 404


def test_ingest_missing_ticker_400(monkeypatch, tmp_path):
    resp = _client(monkeypatch, tmp_path).post("/ingest", json={"ticker": " "})
    assert resp.status_code == 400


def test_ask_demo_unknown_ticker_stays_offline(monkeypatch, tmp_path):
    def _fail(*args, **kwargs):
        raise AssertionError("demo mode must not touch the network")

    monkeypatch.setattr(ingestion, "start_ticker_ingest", _fail)
    resp = _client(monkeypatch, tmp_path).post("/ask", json={
        "query": "What are the risk factors?",
        "ticker": "TSLA",
        "chat_history": [],
    })
    assert resp.status_code == 200
    assert "No demo answer for this ticker" in resp.json()["answer"]


def test_answer_unknown_ticker_graceful_live(monkeypatch):
    def _missing(ticker, settings):
        raise ValueError("no 10-K")

    monkeypatch.setattr(rag.ingestion, "start_ticker_ingest", _missing)
    result = rag.answer_question(
        "What are the risks?", "NOPE", [], Settings(demo=False),
        store=InMemoryVectorStore(),
    )
    assert result["sources"] == []
    assert "NOPE" in result["answer"]
    assert result["mode"] == "bedrock"


def test_opensearch_ensure_index_creates_knn_mapping():
    from app.vectorstore import OpenSearchVectorStore

    calls = {}

    class FakeIndices:
        def exists(self, index):
            calls["exists"] = index
            return False

        def create(self, index, body):
            calls["create"] = (index, body)

    class FakeClient:
        indices = FakeIndices()

    vs = OpenSearchVectorStore.__new__(OpenSearchVectorStore)
    vs.client = FakeClient()
    vs.index = "filings"
    vs.ensure_index()
    assert calls["exists"] == "filings"
    body = calls["create"][1]
    assert body["settings"] == {"index.knn": True}
    assert body["mappings"]["properties"]["embedding"]["type"] == "knn_vector"
    assert body["mappings"]["properties"]["ticker"]["type"] == "keyword"


def test_opensearch_has_ticker_uses_count():
    from app.vectorstore import OpenSearchVectorStore

    seen = {}

    class FakeIndices:
        def exists(self, index):
            return True

    class FakeClient:
        indices = FakeIndices()

        def count(self, index, body):
            seen["body"] = body
            return {"count": 2}

    vs = OpenSearchVectorStore.__new__(OpenSearchVectorStore)
    vs.client = FakeClient()
    vs.index = "filings"
    assert vs.has_ticker("aapl") is True
    assert seen["body"]["query"]["term"] == {"ticker": "AAPL"}


def test_collection_host_builds_endpoint():
    from app.vectorstore import collection_host

    assert collection_host("abc123", "us-east-1") == \
        "abc123.us-east-1.aoss.amazonaws.com"
    assert collection_host(
        "abc123.us-east-1.aoss.amazonaws.com", "us-west-2"
    ) == "abc123.us-east-1.aoss.amazonaws.com"


def test_answer_starts_background_load_when_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    started = {}

    def _fake_start(ticker, settings):
        started["ticker"] = ticker
        return {"ticker": "TSLA", "company": "Tesla, Inc.",
                "filing_date": "2026-01-29", "raw_location": "x",
                "ingest_started": True}

    monkeypatch.setattr(rag.ingestion, "start_ticker_ingest", _fake_start)
    result = rag.answer_question(
        "What are the risks?", "TSLA", [], Settings(demo=False),
        store=InMemoryVectorStore(),
    )
    assert started["ticker"] == "TSLA"
    assert result["ingest_started"] is True
    assert result["sources"] == []
    assert "few minutes" in result["answer"]


def test_answer_skips_start_when_present(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("should not start a load for indexed ticker")

    monkeypatch.setattr(rag.ingestion, "start_ticker_ingest", _fail)

    class FakeChain:
        def invoke(self, _input):
            return {"answer": "Seeded answer [AAPL 10-K 2024 p.12]",
                    "context": []}

    monkeypatch.setattr(
        rag, "build_chain", lambda settings, retriever: FakeChain()
    )
    result = rag.answer_question(
        "What are the risks?", "AAPL", [], Settings(demo=False),
        store=demo_store.seeded_demo_store(),
    )
    assert result.get("ingest_started", False) is False
    assert "Seeded answer" in result["answer"]
