"""Vector stores: OpenSearch Serverless (real) + in-memory demo store.

The OpenSearch path is genuinely implemented with opensearch-py and
SigV4 signing, but it is only constructed when not in demo mode. Demo
mode and tests use InMemoryVectorStore with cosine similarity.
"""

import math

from app.config import Settings

# Bedrock Titan Embed v2 default output size; the k-NN mapping must match.
TITAN_EMBED_DIM = 1024


def collection_host(collection: str, region: str) -> str:
    """AOSS endpoint host for a collection id.

    The stack passes the collection id (not the full endpoint), so build
    the regional hostname. Values that already look like hostnames pass
    through unchanged for local .env flexibility.
    """
    if "." in collection:
        return collection
    return f"{collection}.{region}.aoss.amazonaws.com"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Demo/test store: docs + embeddings, cosine-similarity search."""

    def __init__(self) -> None:
        self.docs: list[dict] = []

    def add(self, texts: list[str], embeddings: list[list[float]],
            metadatas: list[dict]) -> None:
        for text, emb, meta in zip(texts, embeddings, metadatas):
            self.docs.append({"text": text, "embedding": emb, "metadata": meta})

    def search(self, query_embedding: list[float], k: int = 4,
               ticker: str | None = None) -> list[dict]:
        scored = []
        for doc in self.docs:
            if ticker and doc["metadata"].get("ticker") != ticker.upper():
                continue
            scored.append((_cosine(query_embedding, doc["embedding"]), doc))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [doc for _, doc in scored[:k]]

    def has_ticker(self, ticker: str) -> bool:
        """True when at least one indexed doc belongs to the ticker."""
        wanted = ticker.upper()
        return any(
            doc["metadata"].get("ticker") == wanted for doc in self.docs
        )


class OpenSearchVectorStore:
    """Real OpenSearch Serverless vector store (SigV4, k-NN index)."""

    def __init__(self, settings: Settings):
        from opensearchpy import OpenSearch, RequestsHttpConnection
        from requests_aws4auth import AWS4Auth

        from app.config import boto_session

        session = boto_session(settings)
        creds = session.get_credentials()
        if creds is None:
            raise RuntimeError(
                "AWS credentials are required for live mode "
                "(set them via ~/.aws/credentials or AWS_PROFILE)."
            )
        auth = AWS4Auth(
            creds.access_key, creds.secret_key, settings.aws_region,
            "aoss", session_token=creds.token,
        )
        self.client = OpenSearch(
            hosts=[{
                "host": collection_host(
                    settings.opensearch_collection, settings.aws_region
                ),
                "port": 443,
            }],
            http_auth=auth,
            use_ssl=True,
            connection_class=RequestsHttpConnection,
        )
        self.index = settings.opensearch_index

    def ensure_index(self) -> None:
        """Create the k-NN index with the Titan-v2 mapping when missing."""
        if self.client.indices.exists(index=self.index):
            return
        self.client.indices.create(index=self.index, body={
            "settings": {"index.knn": True},
            "mappings": {"properties": {
                "text": {"type": "text"},
                "embedding": {
                    "type": "knn_vector", "dimension": TITAN_EMBED_DIM,
                },
                "ticker": {"type": "keyword"},
            }},
        })

    def add(self, texts: list[str], embeddings: list[list[float]],
            metadatas: list[dict]) -> None:
        self.ensure_index()
        for text, emb, meta in zip(texts, embeddings, metadatas):
            self.client.index(
                index=self.index,
                body={"text": text, "embedding": emb, **meta},
            )

    def search(self, query_embedding: list[float], k: int = 4,
               ticker: str | None = None) -> list[dict]:
        query: dict = {
            "size": k,
            "query": {
                "knn": {"embedding": {"vector": query_embedding, "k": k}}
            },
        }
        if ticker:
            query["query"] = {
                "bool": {
                    "must": query["query"],
                    "filter": {"term": {"ticker": ticker.upper()}},
                }
            }
        resp = self.client.search(index=self.index, body=query)
        return [
            {"text": hit["_source"].get("text", ""), "metadata": hit["_source"]}
            for hit in resp["hits"]["hits"]
        ]

    def has_ticker(self, ticker: str) -> bool:
        """True when the index holds at least one doc for the ticker."""
        self.ensure_index()
        resp = self.client.count(
            index=self.index,
            body={"query": {"term": {"ticker": ticker.upper()}}},
        )
        return resp.get("count", 0) > 0


def get_store(settings: Settings):
    if settings.demo:
        return InMemoryVectorStore()
    return OpenSearchVectorStore(settings)
