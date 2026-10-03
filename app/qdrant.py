from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
)

from app.core.config import get_settings

settings = get_settings()

qdrant_client = QdrantClient(
    url=settings.qdrant_url
)


def initialize_qdrant():
    collections = qdrant_client.get_collections().collections

    exists = any(
        collection.name == settings.qdrant_collection
        for collection in collections
    )

    if not exists:
        qdrant_client.create_collection(
            collection_name=settings.qdrant_collection,

            vectors_config={
                "dense": VectorParams(
                    size=settings.embed_dim,
                    distance=Distance.COSINE,
                ),
            },

            sparse_vectors_config={
                "bm25": SparseVectorParams(
                    index=SparseIndexParams(
                        on_disk=False
                    ),
                ),
            },
        )