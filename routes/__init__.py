from .auth import bp as auth_bp
from .dashboard import bp as dashboard_bp
from .transactions import bp as transactions_bp
from .categories import bp as categories_bp
from .accounts import accounts_bp
from routes.score import bp as score_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(score_bp)
