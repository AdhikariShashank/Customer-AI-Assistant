from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import Settings

qdrant_client = QdrantClient(
    url= Settings.qdrant_url
)


def initialize_qdrant():
    collections = qdrant_client.get_collections().collections

    exists = any(
        collection.name == Settings.qdrant_collection
        for collection in collections
    )

    if not exists:
        qdrant_client.create_collection(
            collection_name=Settings.qdrant_collection,
            vectors_config=VectorParams(
                size=Settings.embed_dim,
                distance=Distance.COSINE,
            ),
        )