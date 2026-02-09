from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import db, Category, Transaction

bp = Blueprint("categories", __name__)


def get_owned_or_404(model, obj_id: int):
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()


@bp.route("/categories")
@login_required
def list_categories():
    uid = current_user.id
    categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
    return render_template(
        "categories/list.html",
        categories=categories,
        current_page="categories",
    )


@bp.route("/categories/new", methods=["GET", "POST"])
@login_required
def new_category():
    uid = current_user.id

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Nome é obrigatório.", "error")
            return render_template(
                "categories/form.html",
                category=None,
                error="Nome é obrigatório.",
                current_page="categories",
            )

        if Category.query.filter_by(user_id=uid, name=name).first():
            flash("Categoria já existe.", "error")
            return render_template(
                "categories/form.html",
                category=None,
                error="Categoria já existe.",
                current_page="categories",
            )

        try:
            db.session.add(Category(user_id=uid, name=name))
            db.session.commit()
            flash("Categoria criada com sucesso.", "success")
            return redirect(url_for("categories.list_categories"))
        except IntegrityError:
            db.session.rollback()
            flash("Categoria já existe (integridade).", "error")
        except Exception:
            db.session.rollback()
            flash("Erro ao criar categoria.", "error")

    return render_template(
        "categories/form.html",
        category=None,
        error=None,
        current_page="categories",
    )


@bp.route("/categories/<int:cat_id>/edit", methods=["GET", "POST"])
@login_required
def edit_category(cat_id):
    uid = current_user.id
    category = get_owned_or_404(Category, cat_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Nome é obrigatório.", "error")
            return render_template(
                "categories/form.html",
                category=category,
                error="Nome é obrigatório.",
                current_page="categories",
            )

        exists = Category.query.filter(
            Category.user_id == uid,
            Category.name == name,
            Category.id != cat_id,
        ).first()
        if exists:
            flash("Já existe outra categoria com esse nome.", "error")
            return render_template(
                "categories/form.html",
                category=category,
                error="Já existe outra categoria com esse nome.",
                current_page="categories",
            )

        try:
            category.name = name
            db.session.commit()
            flash("Categoria atualizada com sucesso.", "success")
            return redirect(url_for("categories.list_categories"))
        except IntegrityError:
            db.session.rollback()
            flash("Já existe outra categoria com esse nome (integridade).", "error")
        except Exception:
            db.session.rollback()
            flash("Erro ao atualizar categoria.", "error")

    return render_template(
        "categories/form.html",
        category=category,
        error=None,
        current_page="categories",
    )


@bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_category(cat_id):
    category = get_owned_or_404(Category, cat_id)

    has_tx = (
        Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.category_id == cat_id,
        ).first()
        is not None
    )

    if has_tx:
        flash("Não é possível excluir: existem transações vinculadas a esta categoria.", "error")
        return redirect(url_for("categories.list_categories"))

    try:
        db.session.delete(category)
        db.session.commit()
        flash("Categoria excluída com sucesso.", "success")
    except Exception:
        db.session.rollback()
        flash("Erro ao excluir categoria.", "error")

    return redirect(url_for("categories.list_categories"))
