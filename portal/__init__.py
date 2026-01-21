import os

from flask import Flask
from dotenv import load_dotenv

from .extensions import db, login_manager
from .routes import bp as main_bp
from .migrations import run_simple_migrations


def create_app():
    load_dotenv()

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # SQLite-файл по умолчанию (в корне проекта)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///enterra.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Ограничиваем размер всех загружаемых файлов (200 МБ)
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    app.register_blueprint(main_bp)

    with app.app_context():
        from . import models  # noqa: F401

        db.create_all()

        # Простые миграции для существующих SQLite-баз
        run_simple_migrations()

        from .seed import ensure_seed_data

        ensure_seed_data()

    return app


