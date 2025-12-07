import functools

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _normalize_user_row(row):
    if row is None:
        return None
    data = dict(row)
    if not data.get("language_preference"):
        data["language_preference"] = "en"
    return data


def _ensure_default_user():
    """Create and return the default user for no-auth mode."""
    db_conn = get_db()
    username = current_app.config.get("DEFAULT_USER_USERNAME", "default_user")
    password = current_app.config.get("DEFAULT_USER_PASSWORD", "")
    user = (
        db_conn.execute(
            "SELECT id, username, language_preference FROM Users WHERE username = ?",
            (username,),
        )
        .fetchone()
    )
    if user is None:
        db_conn.execute(
            "INSERT OR IGNORE INTO Users (username, password, language_preference) VALUES (?, ?, ?)",
            (username, password, "en"),
        )
        db_conn.commit()
        user = (
            db_conn.execute(
                "SELECT id, username, language_preference FROM Users WHERE username = ?",
                (username,),
            )
            .fetchone()
        )
    return _normalize_user_row(user)


@bp.before_app_request
def load_logged_in_user():
    if current_app.config.get("NO_AUTH_MODE"):
        user = _ensure_default_user()
        session["user_id"] = user["id"]
        g.user = user
        g.language_preference = user.get("language_preference", "en")
        return
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        row = (
            get_db()
            .execute(
                "SELECT id, username, language_preference FROM Users WHERE id = ?",
                (user_id,),
            )
            .fetchone()
        )
        g.user = _normalize_user_row(row)
    g.language_preference = (g.user or {}).get("language_preference", "en") if isinstance(g.user, dict) else "en"


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if current_app.config.get("NO_AUTH_MODE"):
            if g.get("user") is None:
                user = _ensure_default_user()
                session["user_id"] = user["id"]
                g.user = user
            return view(**kwargs)
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped_view


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        error = None

        if not username or not password:
            error = "Username and password are required."
        elif (
            get_db()
            .execute("SELECT id FROM Users WHERE username = ?", (username,))
            .fetchone()
            is not None
        ):
            error = "User already exists."

        if error is None:
            db_conn = get_db()
            cursor = db_conn.execute(
                "INSERT INTO Users (username, password, language_preference) VALUES (?, ?, ?)",
                (username, password, "en"),
            )
            db_conn.commit()
            session.clear()
            session["user_id"] = cursor.lastrowid
            flash("Signup successful.", "success")
            return redirect(url_for("feed.index"))

        flash(error, "danger")
    return render_template("signup.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if current_app.config.get("NO_AUTH_MODE"):
        return redirect(url_for("feed.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        error = None

        user = (
            get_db()
            .execute(
                "SELECT id, username, password FROM Users WHERE username = ?",
                (username,),
            )
            .fetchone()
        )

        if user is None or user["password"] != password:
            error = "Invalid username or password."

        if error is None:
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("feed.index"))

        flash(error, "danger")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    if current_app.config.get("NO_AUTH_MODE"):
        # In no-auth mode, keep user logged in to avoid blocking.
        return redirect(url_for("feed.index"))
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
