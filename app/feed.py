import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    current_app,
    send_from_directory,
    abort,
)

from .auth import login_required
from .db import get_db
from .services import favorites as favorites_service
from .services import paper_store, recommendations

DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.CV", "cs.LG"]

bp = Blueprint("feed", __name__)
GITHUB_PATTERN = re.compile(r"https?://(?:www\.)?github\.com/[^\s\])>\]]+", re.IGNORECASE)

LANGUAGE_OPTIONS = ("en", "zh")
LANGUAGE_COPY = {
    "en": {
        "language_label": "Language",
        "language_helper": "Choose your display language (English / Chinese).",
        "language_option_en": "English",
        "language_option_zh": "Chinese",
        "settings_intro": "Configure categories, tag filters, similarity sources, and language preference.",
        "settings_back": "Back to feed",
        "settings_categories_hint": "Papers may have multiple categories; any selected category will show the paper.",
        "settings_similarity_heading": "Similarity source favorites",
        "settings_similarity_hint": "If none are selected, all favorites are used to compute similarity.",
        "settings_similarity_empty": "No favorites yet—save a few papers first.",
        "settings_whitelist_heading": "Tag whitelist",
        "settings_whitelist_hint": "Papers hitting any whitelist tag are marked as whitelist papers.",
        "settings_blacklist_heading": "Tag blacklist",
        "settings_blacklist_hint": "Papers hitting any blacklist tag are marked as blacklist papers (higher priority than whitelist).",
        "settings_save": "Save settings",
        "filters_categories_label": "Categories",
        "filters_whitelist_label": "Whitelist",
        "filters_blacklist_label": "Blacklist",
        "filters_similarity_label": "Similarity source",
        "filters_all": "All",
        "filters_not_set": "Not set",
        "filters_all_favorites": "All favorites",
        "filters_hint": "Tune filters in Settings.",
        "refresh": "Refresh",
        "badge_blacklist": "Blacklisted",
        "badge_whitelist": "Whitelisted",
        "favorite_saved": "★ Saved",
        "favorite_unsaved": "☆ Save",
        "untitled": "Untitled",
        "modal_title": "Save to favorites",
        "modal_loading": "Loading...",
        "modal_new_label": "New folder",
        "modal_create": "Create",
        "modal_save": "Save",
        "modal_empty": "No favorites yet, create one first.",
        "modal_error": "Unable to load favorites",
        "modal_new_placeholder": "e.g. Vision 2025",
        "one_liner_label": "One-line summary",
        "one_liner_secondary_prefix": "EN",
        "summary_missing": "No summary available.",
        "primary_abstract_label": "Abstract",
        "secondary_abstract_label": "Translation",
        "abstract_missing": "No abstract available.",
        "similarity_label": "Similarity",
        "group_white_title": "Whitelist priority",
        "group_white_subtitle": "Matches whitelist tags and avoids blacklist",
        "group_neutral_title": "Other picks",
        "group_neutral_subtitle": "Does not hit whitelist or blacklist",
        "group_black_title": "Blacklist filtered",
        "group_black_subtitle": "Hits blacklist tags (folded first)",
        "rename_hint": "Press Enter to save",
    },
    "zh": {
        "language_label": "语言",
        "language_helper": "切换显示语言（英文 / 中文）。",
        "language_option_en": "英文模式",
        "language_option_zh": "中文模式",
        "settings_intro": "在此配置分类、标签黑/白名单、相似度来源收藏夹和语言偏好。",
        "settings_back": "返回列表",
        "settings_categories_hint": "文章可能有多个分类，只要包含任意勾选分类即展示。",
        "settings_similarity_heading": "相似度来源收藏夹",
        "settings_similarity_hint": "未选择时默认使用全部收藏夹计算相似度。",
        "settings_similarity_empty": "暂无收藏夹，先去收藏几篇论文吧。",
        "settings_whitelist_heading": "Tag 白名单",
        "settings_whitelist_hint": "命中任意白名单标签的论文归为“白名单论文”。",
        "settings_blacklist_heading": "Tag 黑名单",
        "settings_blacklist_hint": "命中任意黑名单标签的论文将归为“黑名单论文”，优先级高于白名单。",
        "settings_save": "保存设置",
        "filters_categories_label": "分类",
        "filters_whitelist_label": "白名单",
        "filters_blacklist_label": "黑名单",
        "filters_similarity_label": "相似度来源",
        "filters_all": "全部",
        "filters_not_set": "未设置",
        "filters_all_favorites": "全部收藏夹",
        "filters_hint": "过滤条件在 Settings 中设置。",
        "refresh": "刷新",
        "badge_blacklist": "黑名单",
        "badge_whitelist": "白名单",
        "favorite_saved": "★ 已收藏",
        "favorite_unsaved": "☆ 收藏",
        "untitled": "未命名",
        "modal_title": "保存到收藏夹",
        "modal_loading": "加载中...",
        "modal_new_label": "新建收藏夹",
        "modal_create": "新建",
        "modal_save": "保存",
        "modal_empty": "暂无收藏夹，请新建一个。",
        "modal_error": "无法加载收藏夹列表",
        "modal_new_placeholder": "例如：Vision 2025",
        "one_liner_label": "一句话总结",
        "one_liner_secondary_prefix": "EN",
        "summary_missing": "暂无摘要",
        "primary_abstract_label": "摘要 (中文)",
        "secondary_abstract_label": "Abstract (English)",
        "abstract_missing": "暂无摘要",
        "similarity_label": "相似度",
        "group_white_title": "白名单优先",
        "group_white_subtitle": "命中白名单标签且未命中黑名单",
        "group_neutral_title": "其他推荐",
        "group_neutral_subtitle": "未命中白名单或黑名单",
        "group_black_title": "黑名单过滤",
        "group_black_subtitle": "命中黑名单标签（优先被折叠）",
        "rename_hint": "按 Enter 保存",
    },
}


def _copy_for_language(lang: str) -> dict:
    return LANGUAGE_COPY.get(lang, LANGUAGE_COPY["en"])


def _current_language() -> str:
    lang = getattr(g, "language_preference", None)
    if g.get("user") and not lang:
        lang = dict(g.user).get("language_preference")
    if lang not in LANGUAGE_OPTIONS:
        lang = "en"
    return lang


@bp.app_context_processor
def inject_language_context():
    lang = _current_language()
    return {"current_language": lang, "lang_copy": _copy_for_language(lang)}


def _latest_pub_date() -> dt.date:
    latest = paper_store.latest_date()
    if latest:
        return latest
    return dt.date.today()


def _format_paper(row) -> Dict[str, Any]:
    data = dict(row)
    tags = data.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        tags = [str(t).strip() for t in tags if str(t).strip()]
    image_path = _normalize_image_path(data.get("image_path"))
    thumb_small, thumb_full = _resolve_thumb_variants(image_path)
    image_url = _build_image_url(image_path)
    thumb_small_url = _build_image_url(thumb_small)
    thumb_full_url = _build_image_url(thumb_full)
    comment_val = data.get("comment")
    abstract_en = data.get("abstract_en") or ""
    github_url = _extract_github_url(comment_val, abstract_en)
    return {
        "id": data.get("id", ""),
        "title_en": data.get("title_en") or "",
        "title_zh": data.get("title_zh") or "",
        "abstract_en": abstract_en,
        "abstract_zh": data.get("abstract_zh") or "",
        "comment": comment_val or "",
        "summary_zh": data.get("summary_zh") or "",
        "summary_en": data.get("summary_en") or "",
        "category": data.get("category") or "",
        "tags": tags,
        "image_path": image_path,
        "thumb_small": thumb_small,
        "thumb_full": thumb_full,
        "image_url": image_url,
        "thumb_small_url": thumb_small_url,
        "thumb_full_url": thumb_full_url,
        "pdf_path": data.get("pdf_path"),
        "pub_date": data.get("pub_date"),
        "similarity": None,
        "embedding": data.get("embedding"),
        "github_url": github_url,
    }


def _apply_language_to_paper(paper: Dict[str, Any], language: str) -> Dict[str, Any]:
    lang = language if language in LANGUAGE_OPTIONS else "en"
    copy = _copy_for_language(lang)
    title_secondary = None
    if lang == "zh":
        title_primary = paper.get("title_zh") or paper.get("title_en") or copy["untitled"]
        if paper.get("title_en") and paper.get("title_en") != title_primary:
            title_secondary = paper.get("title_en")
    else:
        title_primary = paper.get("title_en") or copy["untitled"]
    summary = paper.get("summary_en") or paper.get("abstract_en")
    if lang == "zh":
        summary = (
            paper.get("summary_zh")
            or paper.get("abstract_zh")
            or paper.get("summary_en")
            or paper.get("abstract_en")
        )
    if not summary:
        summary = copy["summary_missing"]
    one_liner_primary = paper.get("summary_en") if lang == "en" else paper.get("summary_zh")
    one_liner_secondary = None
    if lang == "zh" and paper.get("summary_en") and paper.get("summary_en") != one_liner_primary:
        one_liner_secondary = paper.get("summary_en")
    abstract_primary = paper.get("abstract_en") if lang == "en" else paper.get("abstract_zh")
    abstract_secondary = None
    if lang == "zh":
        abstract_secondary = paper.get("abstract_en") or None
    paper.update(
        {
            "display_title": title_primary or copy["untitled"],
            "display_subtitle": title_secondary,
            "display_summary": summary,
            "display_one_liner": one_liner_primary,
            "display_one_liner_secondary": one_liner_secondary,
            "display_abstract_primary": abstract_primary or copy["abstract_missing"],
            "display_abstract_secondary": abstract_secondary,
        }
    )
    return paper


def _localize_papers(papers: list[Dict[str, Any]], language: str) -> list[Dict[str, Any]]:
    return [_apply_language_to_paper(paper, language) for paper in papers]


def _strip_images_if_missing(papers: list[Dict[str, Any]], target_date: dt.date) -> list[Dict[str, Any]]:
    """
    If the date-specific images directory does not exist, avoid showing thumbnails.
    """
    images_dir = _data_dir() / "images" / target_date.isoformat()
    if images_dir.exists():
        return papers
    for paper in papers:
        paper["thumb_small_url"] = None
        paper["thumb_full_url"] = None
        paper["image_url"] = None
    return papers


def _normalize_image_path(raw_path: Optional[str]) -> Optional[str]:
    if not raw_path:
        return None
    path_obj = Path(raw_path)
    parts = path_obj.parts
    if "static" in parts:
        idx = parts.index("static")
        rel = Path(*parts[idx + 1 :])
        return str(rel)
    return raw_path


def _data_dir() -> Path:
    base_cfg = current_app.config.get("PAPERS_DATA_DIR", "arXivDaily-data")
    base = Path(base_cfg).expanduser()
    if not base.is_absolute():
        base = (Path(current_app.root_path).parent / base).resolve()
    else:
        base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _build_image_url(rel_path: Optional[str]) -> Optional[str]:
    if not rel_path:
        return None
    static_dir = Path(current_app.root_path) / "static"
    data_dir = _data_dir()
    path_obj = Path(rel_path)

    def _rel_to(base: Path, candidate: Path) -> Optional[str]:
        try:
            return str(candidate.resolve().relative_to(base.resolve()))
        except Exception:
            return None

    # Absolute path handling
    if path_obj.is_absolute():
        rel_static = _rel_to(static_dir, path_obj)
        if rel_static:
            return url_for("static", filename=rel_static)
        rel_data = _rel_to(data_dir, path_obj)
        if rel_data:
            rel_path_obj = Path(rel_data)
            if rel_path_obj.parts and rel_path_obj.parts[0] == "images":
                try:
                    rel_path_obj = rel_path_obj.relative_to(Path("images"))
                except ValueError:
                    pass
            return url_for("feed.data_image", path=str(rel_path_obj))
        return None

    if (static_dir / path_obj).exists():
        return url_for("static", filename=str(path_obj))
    rel_path_obj = path_obj
    if rel_path_obj.parts and rel_path_obj.parts[0] == "images":
        try:
            rel_path_obj = rel_path_obj.relative_to(Path("images"))
        except ValueError:
            pass
    return url_for("feed.data_image", path=str(rel_path_obj))


def _parse_date_value(value) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _resolve_thumb_variants(image_path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (small_variant, full_variant) relative paths (static or data dir)."""
    if not image_path:
        return None, None
    full_rel = image_path
    small_rel = _make_variant_path(image_path, suffix="_small")
    static_dir = Path(current_app.root_path) / "static"
    data_dir = _data_dir()

    def _exists(rel: str) -> bool:
        path_obj = Path(rel)
        return (static_dir / path_obj).exists() or (data_dir / path_obj).exists()

    if not _exists(small_rel):
        small_rel = full_rel
    return small_rel, full_rel


def _make_variant_path(rel_path: str, suffix: str) -> str:
    path_obj = Path(rel_path)
    new_name = f"{path_obj.stem}{suffix}{path_obj.suffix}"
    return str(path_obj.with_name(new_name))


def _extract_github_url(*candidates) -> Optional[str]:
    """Return the first GitHub URL found in the given text snippets."""
    for text in candidates:
        if not text:
            continue
        matches = GITHUB_PATTERN.findall(str(text))
        for url in matches:
            cleaned = url.rstrip(").,;]\"'")
            if cleaned:
                return cleaned
    return None


def _load_filters(user_id: int):
    db_conn = get_db()
    row = db_conn.execute(
        """
        SELECT categories, tags, sim_favorites, last_date, last_paper_id, last_position
        FROM UserFilters WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    has_record = bool(row)
    if not row:
        return {
            "categories": [],
            "tags": {"whitelist": [], "blacklist": []},
            "sim_favorites": [],
            "last_date": None,
            "last_paper_id": None,
            "last_position": 0,
            "has_record": False,
        }
    def _parse(value):
        if not value:
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    def _parse_tags(value):
        base = {"whitelist": [], "blacklist": []}
        if not value:
            return base
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return base
        if isinstance(parsed, dict):
            wl = parsed.get("whitelist") or []
            bl = parsed.get("blacklist") or []
            return {
                "whitelist": [str(t).strip() for t in wl if str(t).strip()],
                "blacklist": [str(t).strip() for t in bl if str(t).strip()],
            }
        if isinstance(parsed, list):
            cleaned = [str(t).strip() for t in parsed if str(t).strip()]
            return {"whitelist": cleaned, "blacklist": []}
        return base
    return {
        "categories": _parse(row["categories"]),
        "tags": _parse_tags(row["tags"]),
        "sim_favorites": _parse(row["sim_favorites"]),
        "last_date": _parse_date_value(row["last_date"]),
        "last_paper_id": row["last_paper_id"],
        "last_position": row["last_position"] or 0,
        "has_record": has_record,
    }


def _save_filters(
    user_id: int,
    categories=None,
    tags=None,
    sim_favorites=None,
    last_date: Optional[str] = None,
    last_paper_id: Optional[str] = None,
    last_position: Optional[int] = None,
):
    db_conn = get_db()
    current = _load_filters(user_id)
    def _clean_tags(payload):
        base = {"whitelist": [], "blacklist": []}
        if payload is None:
            payload = current.get("tags", base)
        if isinstance(payload, list):
            payload = {"whitelist": payload, "blacklist": []}
        if not isinstance(payload, dict):
            return base
        wl = payload.get("whitelist") or []
        bl = payload.get("blacklist") or []
        return {
            "whitelist": [str(t).strip() for t in wl if str(t).strip()],
            "blacklist": [str(t).strip() for t in bl if str(t).strip()],
        }
    tags_payload = _clean_tags(tags)
    categories = categories if categories is not None else current.get("categories", [])
    categories = [str(c).strip() for c in categories if str(c).strip()]
    sim_favorites = (
        sim_favorites if sim_favorites is not None else current.get("sim_favorites", [])
    )
    sim_favorites = [
        int(fid) if isinstance(fid, int) or str(fid).isdigit() else fid
        for fid in sim_favorites
    ]
    sim_favorites = [int(fid) for fid in sim_favorites if isinstance(fid, int)]
    if last_date is None:
        last_date_val = current.get("last_date")
    else:
        last_date_val = last_date
    if isinstance(last_date_val, dt.date):
        last_date_val = last_date_val.isoformat()
    last_paper_id_val = (
        last_paper_id if last_paper_id is not None else current.get("last_paper_id")
    )
    last_position_val = (
        last_position if last_position is not None else current.get("last_position")
    )

    payload = {
        "categories": json.dumps(categories or []),
        "tags": json.dumps(tags_payload or {}),
        "sim_favorites": json.dumps(sim_favorites or []),
        "last_date": last_date_val,
        "last_paper_id": last_paper_id_val,
        "last_position": last_position_val,
    }
    db_conn.execute(
        """
        INSERT INTO UserFilters (user_id, categories, tags, sim_favorites, last_date, last_paper_id, last_position)
        VALUES (:user_id, :categories, :tags, :sim_favorites, :last_date, :last_paper_id, :last_position)
        ON CONFLICT(user_id) DO UPDATE SET
            categories = excluded.categories,
            tags = excluded.tags,
            sim_favorites = excluded.sim_favorites,
            last_date = excluded.last_date,
            last_paper_id = excluded.last_paper_id,
            last_position = excluded.last_position,
            updated_at = CURRENT_TIMESTAMP
        """,
        {"user_id": user_id, **payload},
    )
    db_conn.commit()


def _update_language_preference(user_id: int, language: str) -> str:
    lang = language if language in LANGUAGE_OPTIONS else "en"
    db_conn = get_db()
    db_conn.execute(
        "UPDATE Users SET language_preference = ? WHERE id = ?", (lang, user_id)
    )
    db_conn.commit()
    return lang


def _append_sim_favorite(user_id: int, favorite_id: int):
    filters = _load_filters(user_id)
    sim_favs = set(filters.get("sim_favorites") or [])
    sim_favs.add(int(favorite_id))
    _save_filters(
        user_id,
        categories=filters.get("categories"),
        tags=filters.get("tags"),
        sim_favorites=list(sim_favs),
        last_date=filters.get("last_date"),
        last_paper_id=filters.get("last_paper_id"),
        last_position=filters.get("last_position"),
    )


def _split_categories(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [c for c in re.split(r"[,\s]+", str(raw)) if c]


def _collect_tag_pool() -> list[str]:
    tag_pool = set()
    for date_val in paper_store.list_dates():
        for paper in paper_store.load_date(date_val):
            raw = paper.get("tags")
            if not raw:
                continue
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = [t.strip() for t in raw.split(",") if t.strip()]
            if isinstance(raw, list):
                tag_pool.update(str(t).strip() for t in raw if str(t).strip())
    return sorted(tag_pool)


@bp.route("/")
@login_required
def index():
    db_conn = get_db()
    language = _current_language()
    copy = _copy_for_language(language)
    date_str = request.args.get("date")
    target_date = None
    last_history_row = None
    saved_filters = None
    if g.user:
        saved_filters = _load_filters(g.user["id"])
        last_history_row = db_conn.execute(
            """
            SELECT date, paper_id, position
            FROM BrowsingHistory
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (g.user["id"],),
        ).fetchone()
    if date_str:
        try:
            target_date = dt.date.fromisoformat(date_str)
        except ValueError:
            flash("Invalid date format, using latest available.", "warning")
    if target_date is None and saved_filters:
        target_date = saved_filters.get("last_date")
    if target_date is None and last_history_row and last_history_row["date"]:
        target_date = _parse_date_value(last_history_row["date"])
    if target_date is None:
        target_date = _latest_pub_date()

    rows = paper_store.load_date(target_date)

    category_options = list(DEFAULT_CATEGORIES)

    user_favorites = favorites_service.list_favorites(g.user["id"]) if g.user else []
    favorites_lookup = {fav["id"]: fav for fav in user_favorites}
    saved_filters = saved_filters or {
        "categories": [],
        "tags": {"whitelist": [], "blacklist": []},
        "sim_favorites": [],
        "last_date": None,
        "last_paper_id": None,
        "last_position": 0,
    }

    selected_categories = request.args.getlist("category") or saved_filters.get("categories", [])
    selected_categories = [c for c in selected_categories if c in category_options]
    tag_filters = saved_filters.get("tags") or {"whitelist": [], "blacklist": []}
    whitelist_tags = set(tag_filters.get("whitelist") or [])
    blacklist_tags = set(tag_filters.get("blacklist") or [])

    selected_sim_favorites: list[int] = []
    saved_has_record = bool(saved_filters.get("has_record"))
    if g.user:
        selected_sim_favorites = request.args.getlist("sim_favorite")
        selected_sim_favorites = [
            int(fid) for fid in selected_sim_favorites if str(fid).isdigit()
        ]
        if not selected_sim_favorites:
            selected_sim_favorites = saved_filters.get("sim_favorites", [])
        available_ids = [fav["id"] for fav in user_favorites]
        selected_sim_favorites = [
            fid for fid in selected_sim_favorites if fid in available_ids
        ]
        if not selected_sim_favorites and not saved_has_record:
            selected_sim_favorites = available_ids

        _save_filters(
            g.user["id"],
            categories=selected_categories,
            tags=tag_filters,
            sim_favorites=selected_sim_favorites,
        )

    papers = [_format_paper(row) for row in rows]
    papers = _localize_papers(papers, language)
    papers = _strip_images_if_missing(papers, target_date)
    if selected_categories:
        papers = [
            p
            for p in papers
            if set(selected_categories).intersection(set(_split_categories(p["category"])))
        ]

    interest_vectors = []
    if g.user:
        interest_vectors = recommendations.get_favorite_embeddings(
            g.user["id"], selected_sim_favorites or None
        )
    if interest_vectors:
        recommendations.attach_similarity(papers, interest_vectors)
        papers.sort(key=lambda p: p.get("similarity") or 0, reverse=True)

    grouped = {"white": [], "neutral": [], "black": []}

    def _classify_tags(tag_list: list[str]) -> str:
        tags_set = set(tag_list or [])
        if blacklist_tags and tags_set.intersection(blacklist_tags):
            return "black"
        if whitelist_tags and tags_set.intersection(whitelist_tags):
            return "white"
        return "neutral"

    for paper in papers:
        group_key = _classify_tags(paper["tags"])
        paper["filter_group"] = group_key
        grouped[group_key].append(paper)

    def _sort_key(item):
        return (item.get("similarity") or 0) * -1

    for key in grouped:
        grouped[key].sort(key=_sort_key)

    papers = grouped["white"] + grouped["neutral"] + grouped["black"]
    paper_groups = [
        {
            "key": "white",
            "title": copy["group_white_title"],
            "subtitle": copy["group_white_subtitle"],
            "papers": grouped["white"],
        },
        {
            "key": "neutral",
            "title": copy["group_neutral_title"],
            "subtitle": copy["group_neutral_subtitle"],
            "papers": grouped["neutral"],
        },
        {
            "key": "black",
            "title": copy["group_black_title"],
            "subtitle": copy["group_black_subtitle"],
            "papers": grouped["black"],
        },
    ]

    history_row = None
    if g.user:
        history_row = db_conn.execute(
            "SELECT paper_id, position FROM BrowsingHistory WHERE user_id = ? AND date = ?",
            (g.user["id"], target_date.isoformat()),
        ).fetchone()
        if not history_row and saved_filters and saved_filters.get("last_date") == target_date:
            history_row = {
                "paper_id": saved_filters.get("last_paper_id"),
                "position": saved_filters.get("last_position") or 0,
            }
        if not history_row:
            history_row = last_history_row

    favorite_paper_ids = set()
    if g.user:
        rows = db_conn.execute(
            """
            SELECT FavoritePapers.paper_id
            FROM FavoritePapers
            JOIN Favorites ON Favorites.id = FavoritePapers.favorite_id
            WHERE Favorites.user_id = ?
            """,
            (g.user["id"],),
        ).fetchall()
        favorite_paper_ids = {row["paper_id"] for row in rows}

    selected_favorite_names = [
        favorites_lookup[fid]["name"] for fid in selected_sim_favorites if fid in favorites_lookup
    ]

    return render_template(
        "index.html",
        papers=papers,
        target_date=target_date,
        selected_categories=selected_categories,
        tag_filters=tag_filters,
        history=history_row,
        favorite_paper_ids=favorite_paper_ids,
        paper_groups=paper_groups,
        selected_favorite_names=selected_favorite_names,
        current_language=language,
        lang_copy=copy,
    )


@bp.route("/data/images/<path:path>")
@login_required
def data_image(path: str):
    """Serve images stored under PAPERS_DATA_DIR/images/."""
    data_dir = _data_dir() / "images"
    safe_path = Path(path)
    if safe_path.parts and safe_path.parts[0] == "images":
        try:
            safe_path = safe_path.relative_to(Path("images"))
        except ValueError:
            abort(404)
    full_path = (data_dir / safe_path).resolve()
    try:
        data_root = data_dir.resolve()
    except FileNotFoundError:
        abort(404)
    if not str(full_path).startswith(str(data_root)):
        abort(404)
    if not full_path.exists():
        abort(404)
    return send_from_directory(str(data_dir), str(safe_path))


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    current_language = _current_language()
    filters = _load_filters(g.user["id"])
    category_options = list(DEFAULT_CATEGORIES)
    tag_options = set(_collect_tag_pool())
    tag_options.update(filters.get("tags", {}).get("whitelist", []))
    tag_options.update(filters.get("tags", {}).get("blacklist", []))
    tag_options = sorted(tag_options)
    user_favorites = favorites_service.list_favorites(g.user["id"])

    if request.method == "POST":
        selected_categories = [
            c for c in request.form.getlist("category") if c in category_options
        ]
        selected_whitelist = [
            t for t in request.form.getlist("tag_whitelist") if t in tag_options
        ]
        selected_blacklist = [
            t for t in request.form.getlist("tag_blacklist") if t in tag_options
        ]
        selected_sim_favorites = [
            int(fid) for fid in request.form.getlist("sim_favorite") if str(fid).isdigit()
        ]
        available_ids = [fav["id"] for fav in user_favorites]
        selected_sim_favorites = [
            fid for fid in selected_sim_favorites if fid in available_ids
        ]
        language_pref = request.form.get("language_preference", current_language)
        saved_language = _update_language_preference(g.user["id"], language_pref)
        g.language_preference = saved_language
        if isinstance(g.user, dict):
            g.user["language_preference"] = saved_language
        _save_filters(
            g.user["id"],
            categories=selected_categories,
            tags={"whitelist": selected_whitelist, "blacklist": selected_blacklist},
            sim_favorites=selected_sim_favorites,
        )
        flash("Settings saved.", "success")
        return redirect(url_for("feed.settings"))

    return render_template(
        "settings.html",
        category_options=category_options,
        tag_options=tag_options,
        filters=filters,
        user_favorites=user_favorites,
        current_language=current_language,
    )


@bp.route("/paper/<paper_id>")
@login_required
def paper_detail(paper_id: str):
    row, paper_date = paper_store.find_by_id(paper_id)
    if row is None:
        flash("Paper not found.", "warning")
        return redirect(url_for("feed.index"))
    language = _current_language()
    copy = _copy_for_language(language)
    paper = _format_paper(row)
    paper = _apply_language_to_paper(paper, language)
    if not paper.get("pub_date") and paper_date:
        paper["pub_date"] = paper_date.isoformat()
    pdf_link = paper["pdf_path"] or f"https://arxiv.org/abs/{paper_id}"
    user_favorites = []
    last_created_fav = session.pop("last_created_fav", None)
    if g.user:
        user_favorites = favorites_service.favorites_with_similarity(
            g.user["id"], paper_id
        )
        if last_created_fav:
            for fav in user_favorites:
                if fav["id"] == last_created_fav:
                    fav["auto_checked"] = True
    return render_template(
        "paper_detail.html",
        paper=paper,
        pdf_link=pdf_link,
        favorites=user_favorites,
        current_language=language,
        lang_copy=copy,
    )


@bp.route("/favorites")
@login_required
def favorites():
    db_conn = get_db()
    language = _current_language()
    copy = _copy_for_language(language)
    user_favorites = favorites_service.list_favorites(g.user["id"])
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"favorites": [dict(fav) for fav in user_favorites]})
    if not user_favorites:
        return render_template(
            "favorites.html",
            favorites=[],
            selected=None,
            papers=[],
            target=None,
            current_language=language,
            lang_copy=copy,
        )

    favorite_id = request.args.get("favorite_id", type=int)
    selected = None
    if favorite_id:
        selected = favorites_service.get_favorite(db_conn, favorite_id)
        if selected is None:
            flash("Favorite not found.", "warning")
    if selected is None:
        selected = user_favorites[0]
        favorite_id = selected["id"]

    paper_rows = db_conn.execute(
        "SELECT paper_id FROM FavoritePapers WHERE favorite_id = ?",
        (favorite_id,),
    ).fetchall()
    paper_ids = [row["paper_id"] for row in paper_rows]
    papers = []
    if paper_ids:
        for pid in paper_ids:
            paper_row, _ = paper_store.find_by_id(pid)
            if paper_row:
                papers.append(_format_paper(paper_row))
        def _sort_paper(item):
            date_val = _parse_date_value(item.get("pub_date"))
            return date_val or dt.date.min
        papers.sort(key=_sort_paper, reverse=True)
    papers = _localize_papers(papers, language)
    return render_template(
        "favorites.html",
        favorites=user_favorites,
        selected=selected,
        papers=papers,
        target=favorite_id,
        current_language=language,
        lang_copy=copy,
    )


@bp.route("/api/favorites", methods=["GET"])
@login_required
def favorites_api():
    """Return favorites list, marking whether a given paper is already in each favorite."""
    paper_id = request.args.get("paper_id")
    favorites = favorites_service.favorites_with_similarity(g.user["id"], paper_id)
    return jsonify({"favorites": favorites})


@bp.route("/favorites/create", methods=["POST"])
@login_required
def create_favorite():
    name = request.form.get("name", "").strip() or request.form.get("new_favorite_name", "").strip()
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )
    return_to = request.form.get("return_to") or request.referrer
    if not name:
        if wants_json:
            return jsonify({"error": "Please provide a folder name."}), 400
        flash("Please provide a folder name.", "warning")
        return redirect(return_to or url_for("feed.favorites"))
    fav_id = favorites_service.ensure_favorite(g.user["id"], name)
    _append_sim_favorite(g.user["id"], fav_id)
    session["last_created_fav"] = fav_id
    if wants_json:
        return jsonify({"id": fav_id, "name": name, "status": "ok"})
    flash("Favorite created.", "success")
    return redirect(return_to or url_for("feed.favorites"))


@bp.route("/favorites/add", methods=["POST"])
@login_required
def add_to_favorites():
    paper_id = request.form.get("paper_id")
    selected_ids = request.form.getlist("favorite_ids")
    new_folder = request.form.get("new_favorite_name", "").strip()
    if not paper_id:
        flash("Missing paper id.", "warning")
        return redirect(url_for("feed.index"))

    if new_folder:
        fav_id = favorites_service.ensure_favorite(g.user["id"], new_folder)
        _append_sim_favorite(g.user["id"], fav_id)
        selected_ids.append(str(fav_id))

    db_conn = get_db()
    added = 0
    for fav_id_str in selected_ids:
        try:
            fav_id = int(fav_id_str)
        except ValueError:
            continue
        if (
            db_conn.execute(
                "SELECT id FROM Favorites WHERE id = ? AND user_id = ?",
                (fav_id, g.user["id"]),
            ).fetchone()
            is None
        ):
            continue
        if favorites_service.add_paper_to_favorite(fav_id, paper_id):
            favorites_service.recompute_favorite_embedding(fav_id)
            added += 1
    if added:
        flash(f"Added to {added} favorite(s).", "success")
    else:
        flash("No favorites selected.", "info")
    return redirect(url_for("feed.paper_detail", paper_id=paper_id))


@bp.route("/favorites/<int:favorite_id>/remove", methods=["POST"])
@login_required
def remove_from_favorite(favorite_id: int):
    paper_id = request.form.get("paper_id")
    db_conn = get_db()
    favorite = db_conn.execute(
        "SELECT id FROM Favorites WHERE id = ? AND user_id = ?", (favorite_id, g.user["id"])
    ).fetchone()
    if favorite is None:
        flash("Favorite not found.", "warning")
        return redirect(url_for("feed.favorites"))
    if paper_id:
        favorites_service.remove_paper_from_favorite(favorite_id, paper_id)
        favorites_service.recompute_favorite_embedding(favorite_id)
        flash("Removed from favorite.", "success")
    return redirect(url_for("feed.favorites", favorite_id=favorite_id))


@bp.route("/favorites/<int:favorite_id>/delete", methods=["POST"])
@login_required
def delete_favorite(favorite_id: int):
    db_conn = get_db()
    favorite = db_conn.execute(
        "SELECT id, name FROM Favorites WHERE id = ? AND user_id = ?",
        (favorite_id, g.user["id"]),
    ).fetchone()
    if favorite is None:
        flash("Favorite not found.", "warning")
        return redirect(url_for("feed.favorites"))
    db_conn.execute(
        "DELETE FROM Favorites WHERE id = ? AND user_id = ?", (favorite_id, g.user["id"])
    )
    db_conn.commit()
    flash(f"Deleted favorite \"{favorite['name']}\".", "success")
    return redirect(url_for("feed.favorites"))


@bp.route("/favorites/<int:favorite_id>/rename", methods=["POST"])
@login_required
def rename_favorite(favorite_id: int):
    new_name = request.form.get("name", "").strip()
    if not new_name:
        flash("Folder name cannot be empty.", "warning")
        return redirect(url_for("feed.favorites", favorite_id=favorite_id))
    db_conn = get_db()
    favorite = db_conn.execute(
        "SELECT id FROM Favorites WHERE id = ? AND user_id = ?",
        (favorite_id, g.user["id"]),
    ).fetchone()
    if favorite is None:
        flash("Favorite not found.", "warning")
        return redirect(url_for("feed.favorites"))
    conflict = db_conn.execute(
        "SELECT id FROM Favorites WHERE user_id = ? AND name = ? AND id != ?",
        (g.user["id"], new_name, favorite_id),
    ).fetchone()
    if conflict:
        flash("A folder with this name already exists.", "warning")
        return redirect(url_for("feed.favorites", favorite_id=favorite_id))
    db_conn.execute(
        "UPDATE Favorites SET name = ? WHERE id = ? AND user_id = ?",
        (new_name, favorite_id, g.user["id"]),
    )
    db_conn.commit()
    flash("Folder renamed.", "success")
    return redirect(url_for("feed.favorites", favorite_id=favorite_id))


@bp.route("/history", methods=["POST"])
@login_required
def save_history():
    payload = request.get_json(silent=True) or {}
    paper_id = payload.get("paper_id")
    position = int(payload.get("position", 0))
    date_str = payload.get("date") or dt.date.today().isoformat()
    if not paper_id:
        return {"status": "ignored"}, 400
    db_conn = get_db()
    # Keep only the latest browsing record per user
    db_conn.execute("DELETE FROM BrowsingHistory WHERE user_id = ?", (g.user["id"],))
    db_conn.execute(
        """
        INSERT INTO BrowsingHistory (user_id, paper_id, date, position)
        VALUES (?, ?, ?, ?)
        """,
        (g.user["id"], paper_id, date_str, position),
    )
    db_conn.commit()
    _save_filters(
        g.user["id"],
        last_date=date_str,
        last_paper_id=paper_id,
        last_position=position,
    )
    return {"status": "ok"}
