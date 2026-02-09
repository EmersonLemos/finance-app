# routes/dashboard.py
from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import db, Transaction, Category, Goal
from utils import month_range_from_str

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    now = datetime.utcnow()
    month_year = f"{now.year:04d}-{now.month:02d}"
    start_month, next_month = month_range_from_str(month_year)

    uid = current_user.id

    total_entradas = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == uid, Transaction.type == "entrada")
        .scalar()
    )
    total_saidas = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))
        .filter(Transaction.user_id == uid, Transaction.type == "saida")
        .scalar()
    )
    saldo = float(total_entradas or 0.0) - float(total_saidas or 0.0)

    total_entradas_mes = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.user_id == uid,
            Transaction.type == "entrada",
            Transaction.date >= start_month,
            Transaction.date < next_month,
        )
        .scalar()
    )
    total_saidas_mes = (
        db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))
        .filter(
            Transaction.user_id == uid,
            Transaction.type == "saida",
            Transaction.date >= start_month,
            Transaction.date < next_month,
        )
        .scalar()
    )

    pie_results = (
        db.session.query(
            Category.name,
            db.func.coalesce(db.func.sum(Transaction.amount), 0.0),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == uid,
            Category.user_id == uid,
            Transaction.type == "saida",
            Transaction.date >= start_month,
            Transaction.date < next_month,
        )
        .group_by(Category.id)
        .all()
    )

    pie_chart_data = [
        {"label": name, "value": float(total or 0.0)}
        for name, total in pie_results
        if (total or 0.0) > 0
    ]

    tx_month = (
        Transaction.query.filter(
            Transaction.user_id == uid,
            Transaction.date >= start_month,
            Transaction.date < next_month,
        )
        .order_by(Transaction.date.asc())
        .all()
    )

    daily_delta = {}
    for tx in tx_month:
        day_str = tx.date.strftime("%Y-%m-%d")
        sign = 1 if tx.type == "entrada" else -1
        daily_delta[day_str] = daily_delta.get(day_str, 0.0) + sign * float(tx.amount)

    line_chart_data = []
    running = 0.0
    day = start_month
    while day < next_month:
        day_str = day.strftime("%Y-%m-%d")
        running += daily_delta.get(day_str, 0.0)
        line_chart_data.append({"date": day_str, "saldo": running})
        day += timedelta(days=1)

    bar_chart_data = {
        "entrada": float(total_entradas_mes or 0.0),
        "saida": float(total_saidas_mes or 0.0),
    }

    goals = (
        Goal.query.filter(
            Goal.user_id == uid,
            (Goal.month_year == month_year) | (Goal.month_year.is_(None)),
        )
        .all()
    )

    goals_progress = []
    for g in goals:
        current_value = 0.0

        if g.type == "gasto_mensal":
            current_value = float(total_saidas_mes or 0.0)
        elif g.type == "economia":
            current_value = float((total_entradas_mes or 0.0) - (total_saidas_mes or 0.0))
        elif g.type == "categoria" and g.category_id:
            cat_total = (
                db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))
                .filter(
                    Transaction.user_id == uid,
                    Transaction.type == "saida",
                    Transaction.category_id == g.category_id,
                    Transaction.date >= start_month,
                    Transaction.date < next_month,
                )
                .scalar()
            )
            current_value = float(cat_total or 0.0)

        target = float(g.target_amount or 0.0)
        percent = min(100.0, (current_value / target) * 100.0) if target > 0 else 0.0

        goals_progress.append(
            {
                "name": g.name,
                "type": g.type,
                "target": target,
                "current": current_value,
                "percent": round(percent, 1),
                "category_name": g.category.name if getattr(g, "category", None) else None,
            }
        )

    return render_template(
        "index.html",
        current_page="dashboard",
        month_year=month_year,
        total_entradas=float(total_entradas or 0.0),
        total_saidas=float(total_saidas or 0.0),
        saldo=float(saldo or 0.0),
        pie_chart_data=pie_chart_data or [],
        line_chart_data=line_chart_data or [],
        bar_chart_data=bar_chart_data or {"entrada": 0.0, "saida": 0.0},
        goals_progress=goals_progress or [],
    )
