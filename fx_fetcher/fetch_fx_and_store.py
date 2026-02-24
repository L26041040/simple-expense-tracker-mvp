#!/usr/bin/env python3
import json
from datetime import datetime, timezone

import requests
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry




FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
BASE_CURRENCY = "USD"
SYMBOLS = "TWD,JPY,EUR"

DB_FILENAME = "fx_rates.sqlite3"
engine = create_engine(f"sqlite:///{DB_FILENAME}", echo=False)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class FxRateSnapshot(Base):
    __tablename__ = "fx_rate_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fetched_at_utc = Column(DateTime, nullable=False)
    base = Column(String(8), nullable=False)
    date = Column(String(16), nullable=False)         # Frankfurter's "date" field (string)
    symbols = Column(String(64), nullable=False)      # e.g., "TWD,JPY,EUR"
    rates_json = Column(Text, nullable=False)         # store full rates dict as JSON text




URLS = [
    "https://api.frankfurter.app/latest",      # Normal portal
    "https://api.frankfurter.dev/v1/latest",   # Official route
]

def _session():
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": "fx-fetcher-toy/1.0"})
    return s

def fetch_latest_rates(base="USD", symbols="TWD,JPY,EUR,GBP"):
    params = {"base": base, "symbols": symbols}
    s = _session()

    last_err = None
    for url in URLS:
        try:
            r = s.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e

    raise RuntimeError(f"All FX endpoints failed. Last error: {last_err}")







def main():
    # 1) Create tables (DB setup)
    Base.metadata.create_all(engine)

    # 2) Fetch from external API
    data = fetch_latest_rates()

    # 3) Store into DB
    now_utc = datetime.now(timezone.utc)
    snapshot = FxRateSnapshot(
        fetched_at_utc=now_utc,
        base=data.get("base", BASE_CURRENCY),
        date=str(data.get("date", "")),
        symbols=SYMBOLS,
        rates_json=json.dumps(data.get("rates", {}), ensure_ascii=False),
    )

    db = SessionLocal()
    try:
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    finally:
        db.close()

    # 4) Print confirmation (useful for screenshot)
    rates = data.get("rates", {})
    print("✅ Fetch + Store succeeded")
    print(f"Inserted row id: {snapshot.id}")
    print(f"Fetched at (UTC): {now_utc.isoformat()}")
    print(f"Base: {snapshot.base}, Date: {snapshot.date}, Symbols: {SYMBOLS}")
    print(f"Rates: {rates}")


if __name__ == "__main__":
    main()