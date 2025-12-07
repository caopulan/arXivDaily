import json
from typing import List, Optional

from .. import db
from . import paper_store, recommendations


def _mean_vector(vectors: List[List[float]]) -> Optional[List[float]]:
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


def list_favorites(user_id: int):
    return (
        db.get_db()
        .execute(
            "SELECT id, name, embedding FROM Favorites WHERE user_id = ? ORDER BY name",
            (user_id,),
        )
        .fetchall()
    )


def get_favorite(db_conn, favorite_id: int):
    return (
        db_conn.execute(
            "SELECT id, name, embedding FROM Favorites WHERE id = ?", (favorite_id,)
        ).fetchone()
    )


def ensure_favorite(user_id: int, name: str) -> int:
    db_conn = db.get_db()
    existing = (
        db_conn.execute(
            "SELECT id FROM Favorites WHERE user_id = ? AND name = ?", (user_id, name)
        ).fetchone()
    )
    if existing:
        return existing["id"]
    cursor = db_conn.execute(
        "INSERT INTO Favorites (user_id, name) VALUES (?, ?)", (user_id, name)
    )
    db_conn.commit()
    return cursor.lastrowid


def add_paper_to_favorite(favorite_id: int, paper_id: str) -> bool:
    db_conn = db.get_db()
    cursor = db_conn.execute(
        "INSERT OR IGNORE INTO FavoritePapers (favorite_id, paper_id) VALUES (?, ?)",
        (favorite_id, paper_id),
    )
    db_conn.commit()
    return bool(cursor.rowcount)


def remove_paper_from_favorite(favorite_id: int, paper_id: str) -> None:
    db.get_db().execute(
        "DELETE FROM FavoritePapers WHERE favorite_id = ? AND paper_id = ?",
        (favorite_id, paper_id),
    )
    db.get_db().commit()


def recompute_favorite_embedding(favorite_id: int) -> Optional[List[float]]:
    main_db = db.get_db()
    paper_rows = main_db.execute(
        "SELECT paper_id FROM FavoritePapers WHERE favorite_id = ?",
        (favorite_id,),
    ).fetchall()
    paper_ids = [row["paper_id"] for row in paper_rows]
    if not paper_ids:
        main_db.execute("UPDATE Favorites SET embedding = NULL WHERE id = ?", (favorite_id,))
        main_db.commit()
        return None

    embeddings = []
    for pid in paper_ids:
        paper, _ = paper_store.find_by_id(pid)
        if not paper:
            continue
        emb = recommendations.parse_embedding(paper.get("embedding"))
        if emb:
            embeddings.append(emb)
    mean_vec = _mean_vector(embeddings)
    if mean_vec is None:
        main_db.execute(
            "UPDATE Favorites SET embedding = NULL WHERE id = ?", (favorite_id,)
        )
        main_db.commit()
        return None

    main_db.execute(
        "UPDATE Favorites SET embedding = ? WHERE id = ?",
        (json.dumps(mean_vec), favorite_id),
    )
    main_db.commit()
    return mean_vec


def favorites_with_similarity(user_id: int, paper_id: Optional[str]):
    """Return favorites sorted by similarity to the given paper (if embeddings exist)."""
    db_conn = db.get_db()
    favorites = list_favorites(user_id)

    paper_embedding = None
    if paper_id:
        paper, _ = paper_store.find_by_id(paper_id)
        if paper:
            paper_embedding = recommendations.parse_embedding(paper.get("embedding"))

    fav_ids = [fav["id"] for fav in favorites]
    membership = set()
    if paper_id and fav_ids:
        placeholders = ",".join("?" for _ in fav_ids)
        rows = db_conn.execute(
            f"""
            SELECT favorite_id FROM FavoritePapers
            WHERE paper_id = ? AND favorite_id IN ({placeholders})
            """,
            [paper_id, *fav_ids],
        ).fetchall()
        membership = {row["favorite_id"] for row in rows}

    enriched = []
    for fav in favorites:
        fav_emb = recommendations.parse_embedding(fav["embedding"])
        sim = None
        if paper_embedding and fav_emb:
            sim = recommendations.cosine_similarity(paper_embedding, fav_emb)
        enriched.append(
            {
                "id": fav["id"],
                "name": fav["name"],
                "has_paper": fav["id"] in membership,
                "similarity": sim,
                "is_top": False,
            }
        )

    sims = [f["similarity"] for f in enriched if f["similarity"] is not None]
    max_sim = max(sims) if sims else None
    if max_sim is not None:
        for fav in enriched:
            if fav["similarity"] == max_sim:
                fav["is_top"] = True

    enriched.sort(key=lambda f: f["name"].lower())
    enriched.sort(
        key=lambda f: f["similarity"] if f["similarity"] is not None else -1,
        reverse=True,
    )
    return enriched
