"""Transactional POS simulator. No fiscal, payment or real-POS integration."""

import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class CheckoutError(ValueError):
    """Invalid, stale or conflicting checkout command."""


class CheckoutStore:
    def __init__(self, path: Path, catalog: list[dict]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog = {}
        for item in catalog:
            sku = item["sku"]
            if not isinstance(sku, str) or not sku or sku in self.catalog:
                raise CheckoutError("SKU inválido/duplicado no catálogo de demonstração.")
            if type(item["price_cents"]) is not int or item["price_cents"] <= 0:
                raise CheckoutError("Preço fictício deve ser um inteiro positivo de centavos.")
            self.catalog[sku] = dict(item)
        self.catalog_version = hashlib.sha256(
            json.dumps(self.catalog, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, closed INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                    image_hash TEXT NOT NULL, sku TEXT, decision TEXT NOT NULL,
                    expires REAL NOT NULL, catalog_version TEXT NOT NULL, ack TEXT);
                CREATE TABLE IF NOT EXISTS lines(
                    event_id TEXT PRIMARY KEY REFERENCES events(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    sku TEXT NOT NULL, name TEXT NOT NULL, price_cents INTEGER NOT NULL);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _open(self, db, session):
        found = db.execute("SELECT closed FROM sessions WHERE id=?", (session,)).fetchone()
        if found is None or found["closed"]:
            raise CheckoutError("Sessão inexistente ou encerrada.")

    def create_session(self):
        session = uuid.uuid4().hex
        with self._db() as db:
            db.execute("INSERT INTO sessions VALUES(?,0)", (session,))
        return session

    def close_session(self, session):
        with self._db() as db:
            self._open(db, session)
            db.execute("UPDATE sessions SET closed=1 WHERE id=?", (session,))

    def observe(self, session, event, image_hash, sku, decision, *, now=None, ttl=30):
        now = time.time() if now is None else now
        if decision not in {"accepted", "review", "rejected"}:
            raise CheckoutError("Decisão inválida.")
        if sku is not None and sku not in self.catalog:
            raise CheckoutError("SKU não pertence ao catálogo da demonstração.")
        if decision == "accepted" and sku is None:
            raise CheckoutError("Aceitação sem SKU.")
        if not isinstance(event, str) or not 1 <= len(event) <= 128:
            raise CheckoutError("Identificador de evento inválido.")
        if not math.isfinite(now) or not math.isfinite(ttl) or not 0 < ttl <= 3600:
            raise CheckoutError("Prazo inválido.")
        with self._db() as db:
            self._open(db, session)
            existing = db.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
            if existing:
                if (
                    existing["session_id"],
                    existing["image_hash"],
                    existing["sku"],
                    existing["decision"],
                ) != (session, image_hash, sku, decision):
                    raise CheckoutError("Evento já usado com conteúdo ou sessão diferente.")
                return dict(existing)
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?,NULL)",
                (event, session, image_hash, sku, decision, now + ttl, self.catalog_version),
            )
            return dict(db.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone())

    def commit(self, event, *, sku=None, operator_confirmed=False, now=None, session_id=None):
        now = time.time() if now is None else now
        with self._db() as db:
            found = db.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
            if found is None:
                raise CheckoutError("Evento inexistente.")
            if session_id is not None and found["session_id"] != session_id:
                raise CheckoutError("Evento pertence a outra sessão.")
            if found["ack"]:
                ack = json.loads(found["ack"])
                if sku is not None and sku != ack["sku"]:
                    raise CheckoutError("Evento já confirmado com outro SKU.")
                return ack
            self._open(db, found["session_id"])
            if not math.isfinite(now) or now > found["expires"]:
                raise CheckoutError("Evento expirado: apresente o item novamente.")
            if found["catalog_version"] != self.catalog_version:
                raise CheckoutError("Catálogo alterado: apresente o item novamente.")
            selected = sku if operator_confirmed and sku is not None else found["sku"]
            if not operator_confirmed and (
                found["decision"] != "accepted" or (sku is not None and sku != found["sku"])
            ):
                raise CheckoutError("Evento exige confirmação explícita do operador.")
            if selected not in self.catalog:
                raise CheckoutError("SKU não pertence ao catálogo da demonstração.")
            product = self.catalog[selected]
            db.execute(
                "INSERT INTO lines VALUES(?,?,?,?,?)",
                (event, found["session_id"], selected, product["name"], product["price_cents"]),
            )
            ack = {
                "status": "acknowledged",
                "event_id": event,
                "session_id": found["session_id"],
                "sku": selected,
                "quantity_delta": 1,
                "price_cents": product["price_cents"],
                "operator_confirmed": bool(operator_confirmed),
                "simulated": True,
            }
            db.execute("UPDATE events SET ack=? WHERE id=?", (json.dumps(ack), event))
            return ack

    def receipt(self, session):
        with self._db() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (session,)).fetchone():
                raise CheckoutError("Sessão inexistente.")
            lines = [
                dict(row)
                for row in db.execute(
                    "SELECT event_id,sku,name,price_cents FROM lines "
                    "WHERE session_id=? ORDER BY rowid",
                    (session,),
                )
            ]
        return {
            "session_id": session,
            "items": lines,
            "total_cents": sum(line["price_cents"] for line in lines),
            "simulated": True,
        }
