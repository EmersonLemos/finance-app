import os
import csv
from datetime import datetime, timedelta
from io import BytesIO, StringIO

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    Response,
    flash,
)
from flask_migrate import Migrate
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Transaction, Category, Account, Goal, User


# ============================================================
# HELPERS
# ============================================================
def month_range_from_str(month_str: str | None):
    """Converte 'YYYY-MM' em (start_date, next_month_date). Se None, usa mês atual."""
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
    """Cria contas padrão para um usuário, se ele ainda não tiver."""
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
    """Converte '10,50' ou '10.50' ou '1.234,56' para float."""
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
    """Busca um registro garantindo que pertence ao usuário logado."""
    return model.query.filter_by(id=obj_id, user_id=current_user.id).first_or_404()


# ============================================================
# APP FACTORY
# ============================================================
def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # SECRET_KEY (para flash e sessão do login)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # ============================================================
    # DATABASE (Somente PostgreSQL)
    # ============================================================
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL não definido. Ex:\n"
            "postgresql+psycopg2://usuario:senha@localhost:5432/finance_app"
        )

    # Railway/Heroku às vezes usam postgres://, mas o SQLAlchemy prefere postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    Migrate(app, db)

    # ----------------------------
    # LOGIN MANAGER
    # ----------------------------
    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # preferível usar session.get no SQLAlchemy 2.0,
        # mas isso aqui funciona bem também
        return db.session.get(User, int(user_id))

    # ============================================================
    # AUTH
    # ============================================================
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

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
                return redirect(url_for("login"))

            try:
                u = User(
                    name=name,
                    email=email,
                    password_hash=generate_password_hash(password),
                )
                db.session.add(u)
                db.session.commit()

                # cria contas padrão do usuário
                seed_defaults_for_user(u.id)

                flash("Conta criada! Faça login.", "success")
                return redirect(url_for("login"))
            except IntegrityError:
                db.session.rollback()
                flash("E-mail já existe (integridade).", "error")
            except Exception:
                db.session.rollback()
                flash("Erro ao criar usuário.", "error")

        return render_template("auth/register.html", current_page="auth")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()

            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password_hash, password):
                flash("E-mail ou senha inválidos.", "error")
                return render_template("auth/login.html", current_page="auth")

            login_user(user)

            # garante contas padrão para quem já existia antes dessa feature
            try:
                seed_defaults_for_user(user.id)
            except Exception:
                db.session.rollback()

            flash("Bem-vindo!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("index"))

        return render_template("auth/login.html", current_page="auth")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("Você saiu da conta.", "success")
        return redirect(url_for("login"))

    # ============================================================
    # DASHBOARD
    # ============================================================
    @app.route("/")
    @login_required
    def index():
        now = datetime.utcnow()
        month_year = f"{now.year:04d}-{now.month:02d}"
        start_month, next_month = month_range_from_str(month_year)

        uid = current_user.id

        # totais gerais (do usuário)
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

        # totais do mês atual (do usuário)
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

        # pizza: gastos por categoria no mês (do usuário)
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

        # linha: evolução diária do saldo no mês (do usuário)
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

        # barras: entradas x saídas (mês)
        bar_chart_data = {
            "entrada": float(total_entradas_mes or 0.0),
            "saida": float(total_saidas_mes or 0.0),
        }

        # metas (do usuário)
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

    # ============================================================
    # TRANSAÇÕES
    # ============================================================
    @app.route("/transactions")
    @login_required
    def list_transactions():
        uid = current_user.id

        tx_type = request.args.get("type")
        category_id = request.args.get("category_id", type=int)
        account_id = request.args.get("account_id", type=int)
        start_date_str = request.args.get("start_date")
        end_date_str = request.args.get("end_date")
        min_amount = request.args.get("min_amount", type=float)
        max_amount = request.args.get("max_amount", type=float)

        page = request.args.get("page", 1, type=int)
        per_page = 10

        stmt = select(Transaction).where(Transaction.user_id == uid)

        if tx_type in ("entrada", "saida"):
            stmt = stmt.where(Transaction.type == tx_type)

        if category_id:
            stmt = stmt.where(Transaction.category_id == category_id)

        if account_id:
            stmt = stmt.where(Transaction.account_id == account_id)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                stmt = stmt.where(Transaction.date >= start_date)
            except ValueError:
                flash("Data inicial inválida (use YYYY-MM-DD).", "error")
                start_date_str = None

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)
                stmt = stmt.where(Transaction.date < end_date)
            except ValueError:
                flash("Data final inválida (use YYYY-MM-DD).", "error")
                end_date_str = None

        if min_amount is not None:
            stmt = stmt.where(Transaction.amount >= min_amount)

        if max_amount is not None:
            stmt = stmt.where(Transaction.amount <= max_amount)

        stmt = stmt.order_by(Transaction.date.desc())

        pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
        transactions = pagination.items

        categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
        accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()

        filters = {}
        if tx_type in ("entrada", "saida"):
            filters["type"] = tx_type
        if category_id:
            filters["category_id"] = category_id
        if account_id:
            filters["account_id"] = account_id
        if start_date_str:
            filters["start_date"] = start_date_str
        if end_date_str:
            filters["end_date"] = end_date_str
        if min_amount is not None:
            filters["min_amount"] = min_amount
        if max_amount is not None:
            filters["max_amount"] = max_amount

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
            min_amount=min_amount,
            max_amount=max_amount,
            pagination=pagination,
            filters=filters,
        )

    @app.route("/transactions/new", methods=["GET", "POST"])
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
            category_id_str = request.form.get("category_id", "").strip()
            account_id_str = request.form.get("account_id", "").strip()

            if not description:
                flash("Descrição é obrigatória.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=None,
                    categories=categories,
                    accounts=accounts,
                    error="Descrição é obrigatória.",
                    current_page="transactions",
                )

            try:
                amount = safe_float_br(amount_str)
            except Exception:
                flash("Valor inválido.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=None,
                    categories=categories,
                    accounts=accounts,
                    error="Valor inválido.",
                    current_page="transactions",
                )

            if tx_type not in ("entrada", "saida"):
                flash("Tipo inválido.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=None,
                    categories=categories,
                    accounts=accounts,
                    error="Tipo inválido.",
                    current_page="transactions",
                )

            if date_str:
                try:
                    tx_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    tx_date = datetime.utcnow()
                    flash("Data inválida, use YYYY-MM-DD. Usei a data de hoje.", "warning")
            else:
                tx_date = datetime.utcnow()

            category_id = int(category_id_str) if category_id_str else None
            account_id = int(account_id_str) if account_id_str else None

            tx = Transaction(
                user_id=uid,
                description=description,
                amount=float(amount),
                type=tx_type,
                date=tx_date,
                category_id=category_id,
                account_id=account_id,
            )

            try:
                db.session.add(tx)
                db.session.commit()
                flash("Transação criada com sucesso.", "success")
                return redirect(url_for("list_transactions"))
            except Exception:
                db.session.rollback()
                flash("Erro ao salvar transação.", "error")

        return render_template(
            "transactions/form.html",
            transaction=None,
            categories=categories,
            accounts=accounts,
            error=None,
            current_page="transactions",
        )

    @app.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_transaction(tx_id):
        tx = get_owned_or_404(Transaction, tx_id)
        uid = current_user.id

        categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
        accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()

        if request.method == "POST":
            description = request.form.get("description", "").strip()
            amount_str = request.form.get("amount", "").strip()
            tx_type = request.form.get("type", "").strip()
            date_str = request.form.get("date", "").strip()
            category_id_str = request.form.get("category_id", "").strip()
            account_id_str = request.form.get("account_id", "").strip()

            if not description:
                flash("Descrição é obrigatória.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=tx,
                    categories=categories,
                    accounts=accounts,
                    error="Descrição é obrigatória.",
                    current_page="transactions",
                )

            try:
                amount = safe_float_br(amount_str)
            except Exception:
                flash("Valor inválido.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=tx,
                    categories=categories,
                    accounts=accounts,
                    error="Valor inválido.",
                    current_page="transactions",
                )

            if tx_type not in ("entrada", "saida"):
                flash("Tipo inválido.", "error")
                return render_template(
                    "transactions/form.html",
                    transaction=tx,
                    categories=categories,
                    accounts=accounts,
                    error="Tipo inválido.",
                    current_page="transactions",
                )

            if date_str:
                try:
                    tx_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    tx_date = tx.date
                    flash("Data inválida (YYYY-MM-DD). Mantive a data anterior.", "warning")
            else:
                tx_date = tx.date

            tx.description = description
            tx.amount = float(amount)
            tx.type = tx_type
            tx.date = tx_date
            tx.category_id = int(category_id_str) if category_id_str else None
            tx.account_id = int(account_id_str) if account_id_str else None

            try:
                db.session.commit()
                flash("Transação atualizada com sucesso.", "success")
                return redirect(url_for("list_transactions"))
            except Exception:
                db.session.rollback()
                flash("Erro ao atualizar transação.", "error")

        return render_template(
            "transactions/form.html",
            transaction=tx,
            categories=categories,
            accounts=accounts,
            error=None,
            current_page="transactions",
        )

    @app.route("/transactions/<int:tx_id>/delete", methods=["POST"])
    @login_required
    def delete_transaction(tx_id):
        tx = get_owned_or_404(Transaction, tx_id)
        try:
            db.session.delete(tx)
            db.session.commit()
            flash("Transação excluída com sucesso.", "success")
        except Exception:
            db.session.rollback()
            flash("Erro ao excluir transação.", "error")
        return redirect(url_for("list_transactions"))

    @app.route("/transactions/import", methods=["GET", "POST"])
    @login_required
    def import_transactions():
        uid = current_user.id

        if request.method == "POST":
            file = request.files.get("file")
            if not file:
                flash("Selecione um arquivo CSV.", "error")
                return redirect(url_for("import_transactions"))

            raw = file.read().decode("utf-8-sig", errors="ignore")

            first_line = raw.splitlines()[0] if raw else ""
            delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","

            reader = csv.DictReader(StringIO(raw), delimiter=delimiter)

            if not reader.fieldnames:
                flash("CSV inválido: sem cabeçalho.", "error")
                return redirect(url_for("import_transactions"))

            headers = [h.strip() for h in reader.fieldnames]
            headers_lower = [h.lower() for h in headers]

            def get(row, key):
                if key in row:
                    return row.get(key)
                for i, h in enumerate(headers_lower):
                    if h == key.lower():
                        return row.get(headers[i])
                return None

            required = ["data", "descricao", "tipo", "valor"]
            if not all(any(h == r for h in headers_lower) for r in required):
                flash(
                    "CSV inválido: precisa de colunas Data/Descricao/Tipo/Valor. (Categoria e Conta são opcionais).",
                    "error",
                )
                return redirect(url_for("import_transactions"))

            imported = 0
            skipped = 0
            errors = []

            for idx, row in enumerate(reader, start=2):
                try:
                    data = (get(row, "data") or "").strip()
                    descricao = (get(row, "descricao") or "").strip()
                    tipo = (get(row, "tipo") or "").strip().lower()
                    valor = (get(row, "valor") or "").strip()

                    cat_name = (get(row, "categoria") or "").strip()
                    acc_name = (get(row, "conta") or "").strip()

                    if not descricao:
                        raise ValueError("descricao vazia")
                    if tipo not in ("entrada", "saida"):
                        raise ValueError("tipo inválido")
                    amount = safe_float_br(valor)
                    tx_date = datetime.strptime(data, "%Y-%m-%d")

                    cat_id = None
                    if cat_name:
                        cat = Category.query.filter_by(user_id=uid, name=cat_name).first()
                        if not cat:
                            cat = Category(user_id=uid, name=cat_name)
                            db.session.add(cat)
                            db.session.flush()
                        cat_id = cat.id

                    acc_id = None
                    if acc_name:
                        acc = Account.query.filter_by(user_id=uid, name=acc_name).first()
                        if not acc:
                            acc = Account(user_id=uid, name=acc_name, type="banco")
                            db.session.add(acc)
                            db.session.flush()
                        acc_id = acc.id

                    tx = Transaction(
                        user_id=uid,
                        description=descricao,
                        amount=float(amount),
                        type=tipo,
                        date=tx_date,
                        category_id=cat_id,
                        account_id=acc_id,
                    )
                    db.session.add(tx)
                    imported += 1

                except Exception as e:
                    skipped += 1
                    if len(errors) < 10:
                        errors.append(f"Linha {idx}: {e}")

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("Erro ao salvar importação (rollback). Verifique o CSV.", "error")
                return redirect(url_for("import_transactions"))

            flash(f"Importação concluída. Importadas: {imported} | Ignoradas: {skipped}", "success")
            if errors:
                flash("Erros (primeiros 10): " + " | ".join(errors), "warning")

            return redirect(url_for("list_transactions"))

        return render_template("transactions/import.html", current_page="transactions")

    # ============================================================
    # EXPORTAÇÕES
    # ============================================================
    @app.route("/export/csv")
    @login_required
    def export_csv():
        uid = current_user.id
        month_str = request.args.get("month")
        start, end = month_range_from_str(month_str)

        txs = (
            Transaction.query.filter(
                Transaction.user_id == uid,
                Transaction.date >= start,
                Transaction.date < end,
            )
            .order_by(Transaction.date.asc())
            .all()
        )

        output = StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["Data", "Descrição", "Tipo", "Categoria", "Conta", "Valor"])

        for tx in txs:
            writer.writerow(
                [
                    tx.date.strftime("%Y-%m-%d"),
                    tx.description,
                    tx.type,
                    tx.category.name if tx.category else "",
                    tx.account.name if tx.account else "",
                    f"{tx.amount:.2f}",
                ]
            )

        output.seek(0)
        filename = f"transacoes_{start.strftime('%Y-%m')}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/export/excel")
    @login_required
    def export_excel():
        resp = export_csv()
        resp.headers["Content-Type"] = "application/vnd.ms-excel"
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd and not cd.endswith(".xls"):
            resp.headers["Content-Disposition"] = cd.replace(".csv", ".xls")
        return resp

    @app.route("/export/pdf")
    @login_required
    def export_pdf():
        uid = current_user.id
        month_str = request.args.get("month")
        start, end = month_range_from_str(month_str)

        txs = (
            Transaction.query.filter(
                Transaction.user_id == uid,
                Transaction.date >= start,
                Transaction.date < end,
            )
            .order_by(Transaction.date.asc())
            .all()
        )

        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            return ("Instale reportlab: pip install reportlab", 500)

        buffer = BytesIO()
        c = canvas.Canvas(buffer)
        c.setTitle(f"Relatório {start.strftime('%Y-%m')}")

        y = 800
        c.drawString(50, y, f"Relatório de transações - {start.strftime('%Y-%m')}")
        y -= 30

        for tx in txs:
            line = (
                f"{tx.date.strftime('%d/%m/%Y')} | {tx.description} | {tx.type} | "
                f"{tx.category.name if tx.category else ''} | "
                f"{tx.account.name if tx.account else ''} | R$ {tx.amount:.2f}"
            )
            c.drawString(50, y, line)
            y -= 15
            if y < 50:
                c.showPage()
                y = 800

        c.showPage()
        c.save()
        buffer.seek(0)

        filename = f"relatorio_{start.strftime('%Y-%m')}.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )

    # ============================================================
    # CATEGORIAS (CRUD + BLOQUEIO)
    # ============================================================
    @app.route("/categories")
    @login_required
    def list_categories():
        uid = current_user.id
        categories = Category.query.filter_by(user_id=uid).order_by(Category.name).all()
        return render_template("categories/list.html", categories=categories, current_page="categories")

    @app.route("/categories/new", methods=["GET", "POST"])
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
                return redirect(url_for("list_categories"))
            except IntegrityError:
                db.session.rollback()
                flash("Categoria já existe (integridade).", "error")
            except Exception:
                db.session.rollback()
                flash("Erro ao criar categoria.", "error")

        return render_template("categories/form.html", category=None, error=None, current_page="categories")

    @app.route("/categories/<int:cat_id>/edit", methods=["GET", "POST"])
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
                return redirect(url_for("list_categories"))
            except IntegrityError:
                db.session.rollback()
                flash("Já existe outra categoria com esse nome (integridade).", "error")
            except Exception:
                db.session.rollback()
                flash("Erro ao atualizar categoria.", "error")

        return render_template("categories/form.html", category=category, error=None, current_page="categories")

    @app.route("/categories/<int:cat_id>/delete", methods=["POST"])
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
            return redirect(url_for("list_categories"))

        try:
            db.session.delete(category)
            db.session.commit()
            flash("Categoria excluída com sucesso.", "success")
        except Exception:
            db.session.rollback()
            flash("Erro ao excluir categoria.", "error")

        return redirect(url_for("list_categories"))

    # ============================================================
    # CONTAS (CRUD + BLOQUEIO)
    # ============================================================
    @app.route("/accounts")
    @login_required
    def list_accounts():
        uid = current_user.id
        accounts = Account.query.filter_by(user_id=uid).order_by(Account.name).all()
        return render_template("accounts/list.html", accounts=accounts, current_page="accounts")

    @app.route("/accounts/new", methods=["GET", "POST"])
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
                return redirect(url_for("list_accounts"))
            except IntegrityError:
                db.session.rollback()
                flash("Conta já existe (integridade).", "error")
            except Exception:
                db.session.rollback()
                flash("Erro ao criar conta.", "error")

        return render_template("accounts/form.html", account=None, error=None, current_page="accounts")

    @app.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
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
                Account.id != account_id
            ).first()
            if exists:
                flash("Já existe outra conta com esse nome.", "error")
                return render_template("accounts/form.html", account=account, error="Já existe outra conta com esse nome.", current_page="accounts")

            try:
                account.name = name
                account.type = acc_type
                db.session.commit()
                flash("Conta atualizada com sucesso.", "success")
                return redirect(url_for("list_accounts"))
            except IntegrityError:
                db.session.rollback()
                flash("Já existe outra conta com esse nome (integridade).", "error")
            except Exception:
                db.session.rollback()
                flash("Erro ao atualizar conta.", "error")

        return render_template("accounts/form.html", account=account, error=None, current_page="accounts")

    @app.route("/accounts/<int:account_id>/delete", methods=["POST"])
    @login_required
    def delete_account(account_id):
        account = get_owned_or_404(Account, account_id)

        has_tx = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.account_id == account_id
        ).first() is not None

        if has_tx:
            flash("Não é possível excluir: existem transações vinculadas a esta conta.", "error")
            return redirect(url_for("list_accounts"))

        try:
            db.session.delete(account)
            db.session.commit()
            flash("Conta excluída com sucesso.", "success")
        except Exception:
            db.session.rollback()
            flash("Erro ao excluir conta.", "error")

        return redirect(url_for("list_accounts"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)

