from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

from models import db, User
from utils import seed_defaults_for_user

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()

        if not name or not email or not password:
            flash("Preencha nome, e-mail e senha.", "error")
            return render_template("auth/register.html", current_page="auth")

        if password != confirm:
            flash("As senhas não conferem.", "error")
            return render_template("auth/register.html", current_page="auth")

        if User.query.filter_by(email=email).first():
            flash("E-mail já cadastrado. Faça login.", "error")
            return redirect(url_for("auth.login"))

        try:
            u = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
            )
            db.session.add(u)
            db.session.commit()

            seed_defaults_for_user(u.id)

            flash("Conta criada! Faça login.", "success")
            return redirect(url_for("auth.login"))
        except IntegrityError:
            db.session.rollback()
            flash("E-mail já existe (integridade).", "error")
        except Exception:
            db.session.rollback()
            flash("Erro ao criar usuário.", "error")

    return render_template("auth/register.html", current_page="auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("E-mail ou senha inválidos.", "error")
            return render_template("auth/login.html", current_page="auth")

        login_user(user)

        try:
            seed_defaults_for_user(user.id)
        except Exception:
            db.session.rollback()

        flash("Bem-vindo!", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("auth/login.html", current_page="auth")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Você saiu da conta.", "success")
    return redirect(url_for("auth.login"))
