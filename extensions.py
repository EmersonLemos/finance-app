from flask_migrate import Migrate
from flask_login import LoginManager
from models import db

migrate = Migrate()
login_manager = LoginManager()
