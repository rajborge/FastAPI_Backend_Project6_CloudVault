from functools import lru_cache

from app.core.config import settings


def model_name() -> str:
    return settings.EMBEDDING_MODEL or "lexical-v1"


@lru_cache(maxsize=1)
def load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.EMBEDDING_MODEL, trust_remote_code=False)


def embed_text(value: str) -> list[float]:
    if not settings.EMBEDDING_MODEL:
        from app.services.search_service import hashed_text_vector

        return hashed_text_vector(value)
    # Average overlapping chunks so matches near the end of a document are not
    # lost to a transformer's maximum input length. Models must emit 384 values.
    import numpy as np

    words = value.split()
    chunks = [" ".join(words[i : i + 180]) for i in range(0, max(1, len(words)), 140)]
    vectors = load_model().encode(chunks, normalize_embeddings=True)
    vector = np.mean(vectors, axis=0)
    if vector.shape != (384,):
        raise ValueError("The embedding model must produce 384 dimensions.")
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).tolist()
