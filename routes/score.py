import calendar
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func

from models import db, ScoreRule, Category, Transaction

bp = Blueprint("score", __name__)


def month_range_dt(year: int, month: int):
    """
    Retorna (start_dt, next_dt) para filtrar DateTime:
      - start_dt: primeiro dia do mês 00:00:00
      - next_dt: primeiro dia do mês seguinte 00:00:00
    Usamos: date >= start_dt AND date < next_dt
    """
    start_dt = datetime(year, month, 1, 0, 0, 0)

    if month == 12:
        next_dt = datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        next_dt = datetime(year, month + 1, 1, 0, 0, 0)

    return start_dt, next_dt


@bp.route("/score")
@login_required
def list_score():
    uid = current_user.id

    # filtro opcional (?year=2025&m=1). Se não vier, usa mês atual.
    now = datetime.utcnow()
    year = request.args.get("year", type=int) or now.year
    month = request.args.get("m", type=int) or now.month

    # evita valores inválidos
    if month < 1:
        month = 1
    if month > 12:
        month = 12

    start_dt, next_dt = month_range_dt(year, month)

    # Para exibir no template como "período" (start até último dia do mês)
    last_day = calendar.monthrange(year, month)[1]
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    # regras ativas
    rules = db.session.execute(
        select(ScoreRule, Category)
        .join(Category, Category.id == ScoreRule.category_id)
        .where(ScoreRule.user_id == uid, ScoreRule.active == True)
        .order_by(Category.name.asc())
    ).all()

    # gasto do mês por categoria (somente SAÍDAS)
    spent_rows = db.session.execute(
        select(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("spent"),
        )
        .where(
            Transaction.user_id == uid,
            Transaction.type == "saida",
            Transaction.date >= start_dt,
            Transaction.date < next_dt,
        )
        .group_by(Transaction.category_id)
    ).all()

    spent_map = {cid: float(spent) for cid, spent in spent_rows}

    items = []
    for rule, cat in rules:
        limit = float(rule.monthly_limit)
        warn_pct = float(rule.warning_pct)
        spent = float(spent_map.get(cat.id, 0.0))

        pct = (spent / limit) if limit > 0 else 0.0

        if pct > 1:
            status = "red"
        elif pct >= warn_pct:
            status = "yellow"
        else:
            status = "green"

        remaining = limit - spent

        items.append(
            {
                "rule": rule,
                "category": cat,
                "limit": limit,
                "spent": spent,
                "pct": pct,
                "status": status,
                "remaining": remaining,
            }
        )

    # links mês anterior / próximo (UX)
    prev_year, prev_month = year, month - 1
    next_year, next_month = year, month + 1
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    if next_month == 13:
        next_month = 1
        next_year += 1

    return render_template(
        "score/list.html",
        items=items,
        start=start_dt,
        end=end_dt,
        year=year,
        month=month,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        current_page="score",
    )


@bp.route("/score/new", methods=["GET", "POST"])
@login_required
def new_rule():
    uid = current_user.id

    categories = db.session.execute(
        select(Category).where(Category.user_id == uid).order_by(Category.name.asc())
    ).scalars().all()

    if request.method == "POST":
        category_id = int(request.form.get("category_id"))
        monthly_limit = request.form.get("monthly_limit", "").replace(",", ".")
        warning_pct = request.form.get("warning_pct", "0.80").replace(",", ".")

        try:
            monthly_limit = float(monthly_limit)
            warning_pct = float(warning_pct)
        except ValueError:
            flash("Valores inválidos.", "danger")
            return render_template(
                "score/form.html",
                categories=categories,
                rule=None,
                current_page="score",
            )

        if monthly_limit <= 0:
            flash("O limite mensal deve ser maior que zero.", "danger")
            return render_template(
                "score/form.html",
                categories=categories,
                rule=None,
                current_page="score",
            )

        if warning_pct <= 0 or warning_pct >= 1.5:
            flash("Percentual de aviso inválido. Use algo como 0.80.", "danger")
            return render_template(
                "score/form.html",
                categories=categories,
                rule=None,
                current_page="score",
            )

        # upsert simples: se já existir, atualiza
        existing = db.session.execute(
            select(ScoreRule).where(
                ScoreRule.user_id == uid,
                ScoreRule.category_id == category_id,
            )
        ).scalar_one_or_none()

        if existing:
            existing.monthly_limit = monthly_limit
            existing.warning_pct = warning_pct
            existing.active = True
        else:
            db.session.add(
                ScoreRule(
                    user_id=uid,
                    category_id=category_id,
                    monthly_limit=monthly_limit,
                    warning_pct=warning_pct,
                    active=True,
                )
            )

        db.session.commit()
        flash("Regra de score salva!", "success")
        return redirect(url_for("score.list_score"))

    return render_template(
        "score/form.html",
        categories=categories,
        rule=None,
        current_page="score",
    )


@bp.route("/score/<int:rule_id>/edit", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id: int):
    uid = current_user.id

    rule = db.session.execute(
        select(ScoreRule).where(ScoreRule.id == rule_id, ScoreRule.user_id == uid)
    ).scalar_one_or_none()

    if not rule:
        flash("Regra não encontrada.", "danger")
        return redirect(url_for("score.list_score"))

    categories = db.session.execute(
        select(Category).where(Category.user_id == uid).order_by(Category.name.asc())
    ).scalars().all()

    category_name = db.session.execute(
        select(Category.name).where(
            Category.id == rule.category_id,
            Category.user_id == uid
        )
    ).scalar_one_or_none()

    if request.method == "POST":
        monthly_limit = request.form.get("monthly_limit", "").replace(",", ".")
        warning_pct = request.form.get("warning_pct", "0.80").replace(",", ".")

        try:
            monthly_limit = float(monthly_limit)
            warning_pct = float(warning_pct)
        except ValueError:
            flash("Valores inválidos.", "danger")
            return render_template(
                "score/form.html",
                categories=categories,
                rule=rule,
                category_name=category_name,
                current_page="score",
            )

        if monthly_limit <= 0:
            flash("O limite mensal deve ser maior que zero.", "danger")
            return render_template(
                "score/form.html",
                categories=categories,
                rule=rule,
                category_name=category_name,
                current_page="score",
            )

        rule.monthly_limit = monthly_limit
        rule.warning_pct = warning_pct
        rule.active = True

        db.session.commit()
        flash("Regra atualizada!", "success")
        return redirect(url_for("score.list_score"))

    return render_template(
        "score/form.html",
        categories=categories,
        rule=rule,
        category_name=category_name,
        current_page="score",
    )


@bp.route("/score/<int:rule_id>/delete", methods=["POST"])
@login_required
def delete_rule(rule_id: int):
    uid = current_user.id

    rule = db.session.execute(
        select(ScoreRule).where(ScoreRule.id == rule_id, ScoreRule.user_id == uid)
    ).scalar_one_or_none()

    if not rule:
        flash("Regra não encontrada.", "danger")
        return redirect(url_for("score.list_score"))

    db.session.delete(rule)
    db.session.commit()
    flash("Regra removida!", "success")
    return redirect(url_for("score.list_score"))
