import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


def get_app_env() -> str:
    env = os.getenv("APP_ENV", "dev").strip().lower()
    return "prod" if env == "prod" else "dev"


def load_env_files() -> str:
    env = get_app_env()

    if env == "prod" or not load_dotenv:
        return env

    dotenv_path = f".env.{env}"
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path, override=False)
    else:
        load_dotenv(override=False)

    return env


APP_ENV = load_env_files()


def get_database_url() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL não definido.\n"
            "Ex (DEV): sqlite:///dev.db\n"
            "Ex (PROD): postgresql+psycopg2://usuario:senha@host:5432/finance_prod"
        )

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return db_url
