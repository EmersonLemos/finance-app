from datetime import datetime
from flask_login import current_user
from models import db, Account


def month_range_from_str(month_str: str | None):
    now = datetime.utcnow()
    if month_str:
        try:
            year, month = map(int, month_str.split("-"))
            start = datetime(year, month, 1)
        except Exception:
            start = datetime(now.year, now.month, 1)
    else:
        start = datetime(now.year, now.month, 1)

    if start.month == 12:
        next_month = datetime(start.year + 1, 1, 1)
    else:
        next_month = datetime(start.year, start.month + 1, 1)

    return start, next_month


def seed_defaults_for_user(user_id: int):
    if Account.query.filter_by(user_id=user_id).count() == 0:
        default_accounts = [
            ("Carteira", "carteira"),
            ("Banco", "banco"),
            ("Cartão", "cartao"),
            ("Reserva", "reserva"),
        ]
        for name, acc_type in default_accounts:
            db.session.add(Account(user_id=user_id, name=name, type=acc_type))
        db.session.commit()


def safe_float_br(value: str) -> float:
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
