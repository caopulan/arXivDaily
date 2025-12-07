import json
import math
from typing import List, Optional, Sequence

from .. import db


def parse_embedding(raw: Optional[object]) -> Optional[List[float]]:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, (list, tuple)):
            return [float(x) for x in parsed]
    return None


def _mean_vector(vectors: List[List[float]]) -> Optional[List[float]]:
    """Return the coordinate-wise mean or None if vectors are empty/mismatched."""
    if not vectors:
        return None
    length = len(vectors[0])
    totals = [0.0] * length
    count = 0
    for vec in vectors:
        if len(vec) != length:
            continue
        for idx, val in enumerate(vec):
            totals[idx] += float(val)
        count += 1
    if count == 0:
        return None
    return [val / count for val in totals]


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))


def get_user_interest_vector(user_id: int) -> Optional[List[float]]:
    rows = (
        db.get_db()
        .execute(
            "SELECT embedding FROM Favorites WHERE user_id = ? AND embedding IS NOT NULL",
            (user_id,),
        )
        .fetchall()
    )
    vectors = []
    for row in rows:
        emb = parse_embedding(row["embedding"])
        if emb:
            vectors.append(emb)
    return _mean_vector(vectors)


def get_favorite_embeddings(
    user_id: int, favorite_ids: Optional[Sequence[int]] = None
) -> List[List[float]]:
    db_conn = db.get_db()
    params: List = [user_id]
    query = "SELECT id, embedding FROM Favorites WHERE user_id = ?"
    if favorite_ids:
        placeholders = ",".join("?" for _ in favorite_ids)
        query += f" AND id IN ({placeholders})"
        params.extend(favorite_ids)
    rows = db_conn.execute(query, params).fetchall()
    vectors: List[List[float]] = []
    for row in rows:
        vec = parse_embedding(row["embedding"])
        if vec:
            vectors.append(vec)
    return vectors


def attach_similarity(papers: List[dict], interest_vectors: List[List[float]]) -> List[dict]:
    if not interest_vectors:
        return papers
    for paper in papers:
        emb = parse_embedding(paper.get("embedding"))
        if emb:
            scores = [cosine_similarity(emb, vec) for vec in interest_vectors]
            paper["similarity"] = max(scores) if scores else None
    return papers
