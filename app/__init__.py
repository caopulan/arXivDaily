import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

from . import auth
from . import cli as cli_commands
from . import db
from . import feed


def create_app(test_config=None):
    """Application factory for the frontend-only paper viewer."""
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)

    default_db_path = Path(app.instance_path) / "app.db"
    default_data_dir = Path(app.root_path).parent / "arXivDaily-data"
    data_dir_env = Path(os.getenv("PAPERS_DATA_DIR", str(default_data_dir))).expanduser()
    no_auth_env = os.getenv("NO_AUTH_MODE", "false").lower()
    no_auth_mode = no_auth_env in ("1", "true", "yes", "on")
    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev-secret-key"),
        DATABASE=os.getenv("DATABASE_PATH", str(default_db_path)),
        PAPERS_DATA_DIR=str(data_dir_env),
        NO_AUTH_MODE=no_auth_mode,
        DEFAULT_USER_USERNAME=os.getenv("DEFAULT_USER_USERNAME", "guest"),
        DEFAULT_USER_PASSWORD=os.getenv("DEFAULT_USER_PASSWORD", "guest"),
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    cli_commands.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(feed.bp)

    # Apply lightweight migrations (adds optional columns if missing)
    with app.app_context():
        db.apply_light_migrations()

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app
