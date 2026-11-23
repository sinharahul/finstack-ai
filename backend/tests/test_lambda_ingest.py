"""Tests: S3-triggered ingestion Lambda (mocked S3/embeddings, no net)."""

import io
import json

import lambda_ingest
from app import embeddings


def test_lambda_ingest_writes_keyed_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEMO", "1")

    class FakeS3:
        def get_object(self, Bucket, Key):
            assert Key == "raw/TSLA/2026-01-29.txt"
            return {"Body": io.BytesIO(
                b"Tesla risk factors and growth. " * 500
            )}

    class FakeSession:
        def client(self, name):
            assert name == "s3"
            return FakeS3()

    monkeypatch.setattr(
        lambda_ingest, "boto_session", lambda settings: FakeSession()
    )
    monkeypatch.setattr(
        lambda_ingest.embeddings, "embed_texts",
        lambda texts, settings: embeddings.embed_texts_demo(texts),
    )

    event = {"Records": [{"s3": {
        "bucket": {"name": "b"},
        "object": {"key": "raw/TSLA/2026-01-29.txt"},
    }}]}
    resp = lambda_ingest.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])[0]["ticker"] == "TSLA"

    # Every metadata row must carry the table's HASH+RANGE keys.
    rows = [
        json.loads(line)
        for line in open(tmp_path / "filing_meta.jsonl", encoding="utf-8")
    ]
    assert rows
    assert all(r["ticker"] == "TSLA" for r in rows)
    assert all(r["filing_date"] == "2026-01-29" for r in rows)
