"""Tests: Lambda API entry-point routing (no network)."""

import json

import lambda_api


def _event(path, method="GET", body=None):
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "queryStringParameters": None,
        "body": body,
    }


def test_lambda_root(monkeypatch):
    monkeypatch.setenv("DEMO", "1")
    resp = lambda_api.lambda_handler(_event("/"), None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])
    assert data["status"] == "ok"
    assert "POST /ask" in data["endpoints"]


def test_lambda_health_needs_no_store(monkeypatch):
    # Routing happens before store creation, so /health works without
    # any vector-store credentials or configuration.
    monkeypatch.delenv("DEMO", raising=False)
    resp = lambda_api.lambda_handler(_event("/health"), None)
    assert resp["statusCode"] == 200


def test_lambda_unknown_path_404(monkeypatch):
    monkeypatch.setenv("DEMO", "1")
    resp = lambda_api.lambda_handler(_event("/nope"), None)
    assert resp["statusCode"] == 404
