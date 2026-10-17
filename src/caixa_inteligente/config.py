import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def database_engine() -> Engine:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("Defina DATABASE_URL no .env (veja .env.example).")
    if not url.startswith("mysql+pymysql://"):
        raise ValueError("O protótipo utiliza MySQL: DATABASE_URL deve usar mysql+pymysql://.")
    return create_engine(url, pool_pre_ping=True)
