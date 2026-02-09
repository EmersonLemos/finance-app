from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import db, Account, Transaction

accounts_bp = Blueprint("accounts", __name__)


def get_owned_or_404(model, obj_id: int):
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()


@accounts_bp.route("/accounts")
@login_required
def list_accounts():
    uid = current_user.id
    accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()
    return render_template("accounts/list.html", accounts=accounts, current_page="accounts")


@accounts_bp.route("/accounts/new", methods=["GET", "POST"])
@login_required
def new_account():
    uid = current_user.id

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        acc_type = request.form.get("type", "").strip()

        if not name:
            flash("Nome é obrigatório.", "error")
            return render_template("accounts/form.html", account=None, error="Nome é obrigatório.", current_page="accounts")

        if not acc_type:
            flash("Tipo é obrigatório.", "error")
            return render_template("accounts/form.html", account=None, error="Tipo é obrigatório.", current_page="accounts")

        if Account.query.filter_by(user_id=uid, name=name).first():
            flash("Conta já existe.", "error")
            return render_template("accounts/form.html", account=None, error="Conta já existe.", current_page="accounts")

        try:
            db.session.add(Account(user_id=uid, name=name, type=acc_type))
            db.session.commit()
            flash("Conta criada com sucesso.", "success")
            return redirect(url_for("accounts.list_accounts"))
        except IntegrityError:
            db.session.rollback()
            flash("Conta já existe (integridade).", "error")
        except Exception:
            db.session.rollback()
            flash("Erro ao criar conta.", "error")

    return render_template("accounts/form.html", account=None, error=None, current_page="accounts")


@accounts_bp.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
def edit_account(account_id):
    uid = current_user.id
    account = get_owned_or_404(Account, account_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        acc_type = request.form.get("type", "").strip()

        if not name:
            flash("Nome é obrigatório.", "error")
            return render_template("accounts/form.html", account=account, error="Nome é obrigatório.", current_page="accounts")

        if not acc_type:
            flash("Tipo é obrigatório.", "error")
            return render_template("accounts/form.html", account=account, error="Tipo é obrigatório.", current_page="accounts")

        exists = Account.query.filter(
            Account.user_id == uid,
            Account.name == name,
            Account.id != account_id,
        ).first()
        if exists:
            flash("Já existe outra conta com esse nome.", "error")
            return render_template("accounts/form.html", account=account, error="Já existe outra conta com esse nome.", current_page="accounts")

        try:
            account.name = name
            account.type = acc_type
            db.session.commit()
            flash("Conta atualizada com sucesso.", "success")
            return redirect(url_for("accounts.list_accounts"))
        except IntegrityError:
            db.session.rollback()
            flash("Já existe outra conta com esse nome (integridade).", "error")
        except Exception:
            db.session.rollback()
            flash("Erro ao atualizar conta.", "error")

    return render_template("accounts/form.html", account=account, error=None, current_page="accounts")


@accounts_bp.route("/accounts/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_account(account_id):
    account = get_owned_or_404(Account, account_id)

    has_tx = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.account_id == account_id,
    ).first() is not None

    if has_tx:
        flash("Não é possível excluir: existem transações vinculadas a esta conta.", "error")
        return redirect(url_for("accounts.list_accounts"))

    try:
        db.session.delete(account)
        db.session.commit()
        flash("Conta excluída com sucesso.", "success")
    except Exception:
        db.session.rollback()
        flash("Erro ao excluir conta.", "error")

    return redirect(url_for("accounts.list_accounts"))
