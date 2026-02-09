from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)

    # dono
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("accounts", lazy=True))

    name = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(30), nullable=False)  # carteira, banco, cartao, reserva

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
    )

    def __repr__(self):
        return f"<Account {self.name} ({self.type})>"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)

    # dono
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("categories", lazy=True))

    name = db.Column(db.String(80), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
    )

    def __repr__(self):
        return f"<Category {self.name}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)

    # dono
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("transactions", lazy=True))

    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    # mantendo seu padrão atual:
    # - "entrada" ou "saida"
    type = db.Column(db.String(10), nullable=False)

    # DateTime (como você já usa)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))

    category = db.relationship("Category", backref="transactions")
    account = db.relationship("Account", backref="transactions")

    def __repr__(self):
        return f"<Transaction {self.description} - {self.amount}>"


class Goal(db.Model):
    """
    Metas:
      type:
        - "gasto_mensal"  -> meta para total de saídas no mês
        - "economia"      -> meta para (entradas - saídas) no mês
        - "categoria"     -> meta de gasto por categoria no mês
      month_year: "YYYY-MM" (ex: "2025-11")
    """
    __tablename__ = "goals"

    id = db.Column(db.Integer, primary_key=True)

    # dono
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("goals", lazy=True))

    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    month_year = db.Column(db.String(7), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    category = db.relationship("Category", backref="goals", lazy="joined")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Goal {self.name} ({self.type})>"


class ScoreRule(db.Model):
    """
    Regras do Score (controle mensal por categoria)

    - monthly_limit: limite mensal em R$
    - warning_pct: percentual (0.80 = 80%) a partir do qual fica "amarelo"
    - active: permite desativar sem apagar
    """
    __tablename__ = "score_rules"

    id = db.Column(db.Integer, primary_key=True)

    # dono
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    user = db.relationship("User", backref=db.backref("score_rules", lazy=True))

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    category = db.relationship("Category", backref=db.backref("score_rules", lazy=True))

    monthly_limit = db.Column(db.Float, nullable=False)
    warning_pct = db.Column(db.Float, nullable=False, default=0.80)
    active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "category_id", name="uq_score_rules_user_category"),
    )

    def __repr__(self):
        return f"<ScoreRule user={self.user_id} cat={self.category_id} limit={self.monthly_limit}>"
