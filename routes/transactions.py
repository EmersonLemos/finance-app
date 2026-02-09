from datetime import datetime, timedelta
import csv
from io import StringIO

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select

from models import db, Transaction, Category, Account

bp = Blueprint("transactions", __name__)


# ----------------------------
# Helpers
# ----------------------------
def safe_float_br(value: str) -> float:
    if value is None:
        raise ValueError("empty")

    s = str(value).strip()
    if not s:
        raise ValueError("empty")

    s = s.replace(" ", "")

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")

    return float(s)


def get_owned_or_404(model, obj_id: int):
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()


def _owned_or_none(model, obj_id: int):
    if not obj_id:
        return None
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first()


def _parse_date_ymd(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def _valid_type(tx_type: str | None) -> bool:
    return tx_type in ("entrada", "saida")


# ----------------------------
# LIST + FILTER + PAGINATION
# ----------------------------
@bp.route("/transactions")
@login_required
def list_transactions():
    uid = current_user.id

    tx_type = request.args.get("type")
    category_id = request.args.get("category_id", type=int)
    account_id = request.args.get("account_id", type=int)

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    min_amount_str = request.args.get("min_amount")
    max_amount_str = request.args.get("max_amount")

    page = request.args.get("page", 1, type=int)
    per_page = 10

    stmt = select(Transaction).where(Transaction.user_id == uid)

    if _valid_type(tx_type):
        stmt = stmt.where(Transaction.type == tx_type)

    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)

    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)

    start_dt = _parse_date_ymd(start_date_str)
    end_dt = _parse_date_ymd(end_date_str)

    if start_dt:
        stmt = stmt.where(Transaction.date >= start_dt)

    if end_dt:
        stmt = stmt.where(Transaction.date < end_dt + timedelta(days=1))

    if min_amount_str:
        try:
            stmt = stmt.where(Transaction.amount >= safe_float_br(min_amount_str))
        except:
            pass

    if max_amount_str:
        try:
            stmt = stmt.where(Transaction.amount <= safe_float_br(max_amount_str))
        except:
            pass

    stmt = stmt.order_by(Transaction.date.desc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    transactions = pagination.items

    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()

    filters = {
        "type": tx_type,
        "category_id": category_id,
        "account_id": account_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "min_amount": min_amount_str,
        "max_amount": max_amount_str,
    }

    return render_template(
        "transactions/list.html",
        current_page="transactions",
        transactions=transactions,
        categories=categories,
        accounts=accounts,
        tx_type=tx_type,
        category_id=category_id,
        account_id=account_id,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
        min_amount=min_amount_str,
        max_amount=max_amount_str,
        pagination=pagination,
        filters=filters,
    )


# ----------------------------
# NEW
# ----------------------------
@bp.route("/transactions/new", methods=["GET", "POST"])
@login_required
def new_transaction():
    uid = current_user.id

    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        amount_str = request.form.get("amount", "").strip()
        tx_type = request.form.get("type", "").strip()
        date_str = request.form.get("date", "").strip()
        category_id = request.form.get("category_id", type=int)
        account_id = request.form.get("account_id", type=int)

        if not description:
            flash("Descrição obrigatória.", "error")
            return render_template("transactions/form.html", categories=categories, accounts=accounts)

        try:
            amount = safe_float_br(amount_str)
        except:
            flash("Valor inválido.", "error")
            return render_template("transactions/form.html", categories=categories, accounts=accounts)

        tx = Transaction(
            user_id=uid,
            description=description,
            amount=amount,
            type=tx_type,
            date=_parse_date_ymd(date_str),
            category_id=category_id,
            account_id=account_id,
        )

        db.session.add(tx)
        db.session.commit()

        flash("Transação criada!", "success")
        return redirect(url_for("transactions.list_transactions"))

    return render_template("transactions/form.html",
                           categories=categories,
                           accounts=accounts,
                           current_page="transactions")


# ----------------------------
# EDIT
# ----------------------------
@bp.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(tx_id):
    tx = get_owned_or_404(Transaction, tx_id)
    uid = current_user.id

    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()

    if request.method == "POST":
        tx.description = request.form.get("description")
        tx.amount = safe_float_br(request.form.get("amount"))
        tx.type = request.form.get("type")
        tx.date = _parse_date_ymd(request.form.get("date"))
        tx.category_id = request.form.get("category_id", type=int)
        tx.account_id = request.form.get("account_id", type=int)

        db.session.commit()
        flash("Transação atualizada.", "success")
        return redirect(url_for("transactions.list_transactions"))

    return render_template("transactions/form.html",
                           transaction=tx,
                           categories=categories,
                           accounts=accounts,
                           current_page="transactions")


# ----------------------------
# DELETE
# ----------------------------
@bp.route("/transactions/<int:tx_id>/delete", methods=["POST"])
@login_required
def delete_transaction(tx_id):
    tx = get_owned_or_404(Transaction, tx_id)

    db.session.delete(tx)
    db.session.commit()

    flash("Transação excluída.", "success")
    return redirect(url_for("transactions.list_transactions"))


# ----------------------------
# IMPORT CSV (GET página + POST importa)
# ----------------------------
@bp.route("/transactions/import", methods=["GET", "POST"])
@login_required
def import_transactions():

    # abre tela
    if request.method == "GET":
        return render_template("transactions/import.html", current_page="import_csv")

    file = request.files.get("file")

    if not file or file.filename == "":
        flash("Selecione um arquivo CSV.", "error")
        return redirect(url_for("transactions.import_transactions"))

    raw = file.read()

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    csv_reader = csv.DictReader(StringIO(content))

    uid = current_user.id
    total = 0
    skipped = 0

    for row in csv_reader:
        try:
            tx = Transaction(
                user_id=uid,
                description=(row.get("descricao") or row.get("description") or "").strip(),
                amount=safe_float_br(row.get("valor") or row.get("amount")),
                type=(row.get("tipo") or row.get("type") or "").strip().lower(),
                date=_parse_date_ymd(row.get("data") or row.get("date")),
            )

            if not tx.description or not _valid_type(tx.type) or tx.amount is None:
                skipped += 1
                continue

            db.session.add(tx)
            total += 1
        except:
            skipped += 1
            continue

    db.session.commit()

    flash(f"{total} transações importadas! ({skipped} ignoradas)", "success")
    return redirect(url_for("transactions.list_transactions"))
