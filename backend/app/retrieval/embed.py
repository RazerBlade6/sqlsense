import json
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config

EMBEDDING_DIMENSIONS = 1024


class TitanEmbedder:
    """Amazon Titan Text Embeddings V2 on Bedrock: normalized 1024-dimension vectors."""

    def __init__(self, model_id: str, region: str, workers: int = 8):
        self.model_id = model_id
        self.workers = workers
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=Config(retries={"max_attempts": 8, "mode": "adaptive"}),
        )

    def embed(self, text: str) -> list[float]:
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(
                {"inputText": text, "dimensions": EMBEDDING_DIMENSIONS, "normalize": True}
            ),
        )
        return json.loads(response["body"].read())["embedding"]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(self.embed, texts))
