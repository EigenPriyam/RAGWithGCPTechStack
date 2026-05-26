"""
Re-indexing script: reads already-processed JSON chunks from GCS and
builds the Qdrant collection from scratch. Skips upload and parsing.

Usage:
    python -m src.data_ingestion.index_from_processed
    python -m src.data_ingestion.index_from_processed --wipe
"""
import sys
import uuid
import json
import logfire
import vertexai

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from google.cloud import storage
from qdrant_client import QdrantClient
from qdrant_client.http import models

from src.config import settings
from src.services.embeddings import embed_texts

logfire.configure(service_name="reindex-from-processed")
vertexai.init(project=settings.PROJECT_ID, location=settings.LOCATION)

storage_client = storage.Client(project=settings.PROJECT_ID)
qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


def setup_collection(wipe: bool = False):
    if wipe and qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
        qdrant_client.delete_collection(settings.QDRANT_COLLECTION)
        logfire.info(f"🗑️ Wiped collection: {settings.QDRANT_COLLECTION}")

    if not qdrant_client.collection_exists(settings.QDRANT_COLLECTION):
        qdrant_client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )
        logfire.info(f"🆕 Created collection: {settings.QDRANT_COLLECTION}")


def index_file(blob):
    with logfire.span("📄 Indexing processed file", blob=blob.name):
        try:
            data = json.loads(blob.download_as_text())
            filename = data.get("filename", blob.name)
            source_type = data.get("source_type", "unknown")
            chunks = data.get("chunks", [])

            if not chunks:
                logfire.warning(f"⚠️ No chunks found in {blob.name}, skipping.")
                return

            with logfire.span("🧠 Embedding & Indexing", filename=filename, chunks=len(chunks)):
                embeddings = embed_texts(chunks)
                points = [
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "text": chunk,
                            "source": filename,
                            "source_type": source_type,
                        }
                    )
                    for chunk, vector in zip(chunks, embeddings)
                ]
                qdrant_client.upsert(
                    collection_name=settings.QDRANT_COLLECTION,
                    points=points
                )
                logfire.info(f"✅ Indexed {len(points)} points from {filename}")

        except Exception as e:
            logfire.error(f"💥 Failed to index {blob.name}: {e}")


def run(wipe: bool = False):
    with logfire.span("🚀 Re-index from GCS Processed Bucket"):
        setup_collection(wipe=wipe)

        bucket = storage_client.bucket(settings.PROCESSED_BUCKET)
        blobs = [b for b in bucket.list_blobs() if b.name.endswith(".json")]
        logfire.info(f"🔍 Found {len(blobs)} processed files in GCS")

        for blob in blobs:
            index_file(blob)

        count = qdrant_client.count(collection_name=settings.QDRANT_COLLECTION).count
        logfire.info(f"🏁 Done. Total vectors in collection: {count}")
        print(f"\n✅ Re-indexing complete. Total vectors: {count}")


if __name__ == "__main__":
    wipe_requested = "--wipe" in sys.argv
    run(wipe=wipe_requested)
