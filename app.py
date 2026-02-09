import os

from flask import Flask

from models import db, User

# Config e ambiente
from config import APP_ENV, get_database_url

# Extensions
from extensions import migrate, login_manager

# Blueprints (rotas separadas)
from routes import register_blueprints


def create_app() -> Flask:
    """
    Fábrica do app.

    Estrutura:
    - config.py      → APP_ENV e get_database_url()
    - extensions.py  → migrate, login_manager
    - routes/        → auth, dashboard, transactions, categories, accounts etc.
    """

    # instance_relative_config=True faz o SQLite ir para /instance por padrão
    app = Flask(__name__, instance_relative_config=True)

    # ============================================================
    # SECRET KEY (sessão, flash, login)
    # ============================================================
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ============================================================
    # DATABASE
    # ============================================================
    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ============================================================
    # EXTENSIONS
    # ============================================================
    db.init_app(app)
    migrate.init_app(app, db)

    # ============================================================
    # LOGIN
    # ============================================================
    login_manager.login_view = "auth.login"  # endpoint correto (blueprint auth)
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # ============================================================
    # BLUEPRINTS
    # ============================================================
    register_blueprints(app)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=(APP_ENV != "prod"))
