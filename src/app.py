#!/usr/bin/env python3
"""
Simple Expense Tracker (Final Project)

This is a small class project.
- User can input an expense (category, currency, amount).
- App stores data into SQLite (expenses + FX snapshots).
- App can fetch FX rates from a public API and update the FX table.

Note: This is a toy project for learning, not production.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Tuple

import requests
from flask import Flask, redirect, render_template, request, url_for, flash
from flask_sqlalchemy import SQLAlchemy


# -----------------------
# App + DB setup
# -----------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../simple_expense_web
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH = os.path.join(BASE_DIR, "app.sqlite3")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

app.secret_key = "dev-secret-key"  # ok for class project

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -----------------------
# Constants
# -----------------------

DEFAULT_CATEGORIES = ["Food", "Transport", "Housing", "Entertainment", "Other"]
SUPPORTED_CURRENCIES = ["USD", "TWD", "JPY", "EUR"]

# Default FX values so the app never crashes even if user never fetches FX.
# These are "to USD" rates (1 USD -> X currency). We convert currency->USD by dividing.
DEFAULT_FX_TABLE = {
    "timestamp_utc": "Tue, 24 Feb 2026 00:02:31 +0000",
    "base": "USD",
    "rates": {
        "USD": 1.0,
        "TWD": 31.449566,
        "JPY": 154.590916,
        "EUR": 0.848046,
    },
}


# -----------------------
# DB models
# -----------------------

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at_utc = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    category = db.Column(db.String(32), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    amount_usd = db.Column(db.Float, nullable=False)


class FxSnapshot(db.Model):
    """
    Store the latest FX snapshot we fetched.
    We store JSON to keep this project simple.
    """
    id = db.Column(db.Integer, primary_key=True)
    fetched_at_utc = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    provider = db.Column(db.String(64), nullable=False, default="open.er-api.com")
    base = db.Column(db.String(8), nullable=False, default="USD")
    timestamp_text = db.Column(db.String(128), nullable=False)
    rates_json = db.Column(db.Text, nullable=False)


# -----------------------
# Helpers
# -----------------------

def safe_float(s: str) -> float:
    try:
        return float(s)
    except Exception:
        return 0.0


def get_latest_fx_table() -> Dict:
    """
    Return the most recent FX table from DB.
    If DB is empty, return DEFAULT_FX_TABLE.
    """
    row = FxSnapshot.query.order_by(FxSnapshot.id.desc()).first()
    if not row:
        return DEFAULT_FX_TABLE

    try:
        rates = json.loads(row.rates_json)
    except Exception:
        rates = DEFAULT_FX_TABLE["rates"]

    return {
        "timestamp_utc": row.timestamp_text,
        "base": row.base,
        "rates": rates,
    }


def fetch_fx_from_open_er_api() -> Tuple[str, Dict[str, float]]:
    """
    Fetch FX rates from a free public API.

    Endpoint:
    https://open.er-api.com/v6/latest/USD

    We only keep the currencies used in this app.
    """
    url = "https://open.er-api.com/v6/latest/USD"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    timestamp_text = data.get("time_last_update_utc") or ""
    rates_block = data.get("rates") or data.get("conversion_rates") or {}

    rates: Dict[str, float] = {"USD": 1.0}
    for ccy in SUPPORTED_CURRENCIES:
        if ccy == "USD":
            continue
        if ccy in rates_block:
            rates[ccy] = float(rates_block[ccy])

    # Ensure all currencies exist (fallback to defaults if missing)
    for ccy in SUPPORTED_CURRENCIES:
        rates.setdefault(ccy, DEFAULT_FX_TABLE["rates"].get(ccy, 1.0))

    if not timestamp_text:
        timestamp_text = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return timestamp_text, rates


def convert_to_usd(amount: float, currency: str, fx_table: Dict) -> float:
    """
    Convert amount in selected currency -> USD using table (1 USD -> rate[currency]).
    Example: If 1 USD = 31.4 TWD, then 1 TWD = 1/31.4 USD.
    """
    currency = currency.upper().strip()
    if currency == "USD":
        return amount

    rates = fx_table.get("rates", {})
    rate = float(rates.get(currency, 0.0))
    if rate <= 0.0:
        # Fallback so the app never crashes
        return amount

    return amount / rate


# -----------------------
# Routes
# -----------------------

@app.route("/", methods=["GET"])
def index():
    fx_table = get_latest_fx_table()
    recent = Expense.query.order_by(Expense.id.desc()).limit(10).all()
    return render_template(
        "index.html",
        categories=DEFAULT_CATEGORIES,
        currencies=SUPPORTED_CURRENCIES,
        fx_table=fx_table,
        recent=recent,
    )


@app.route("/expense/add", methods=["POST"])
def add_expense():
    category = request.form.get("category", "Other").strip()
    amount = safe_float(request.form.get("amount", "0"))
    currency = (request.form.get("currency", "USD") or "USD").upper().strip()

    fx_table = get_latest_fx_table()
    amount_usd = convert_to_usd(amount, currency, fx_table)

    exp = Expense(category=category, amount=amount, currency=currency, amount_usd=amount_usd)
    db.session.add(exp)
    db.session.commit()

    flash(f"Recorded: {category} expense {amount:.2f} {currency} (~{amount_usd:.2f} USD)")
    return redirect(url_for("index"))


@app.route("/fx/update", methods=["POST"])
def fx_update():
    """
    Fetch FX rates and store them into DB.
    This route is POST only.
    """
    try:
        timestamp_text, rates = fetch_fx_from_open_er_api()
        snapshot = FxSnapshot(
            timestamp_text=timestamp_text,
            rates_json=json.dumps(rates),
            base="USD",
            provider="open.er-api.com",
        )
        db.session.add(snapshot)
        db.session.commit()
        flash("FX updated successfully.")
    except Exception as e:
        flash(f"FX update failed. Please try again later (we will keep the current FX values). ({type(e).__name__})")

    return redirect(url_for("index"))


def init_db_if_needed() -> None:
    """
    Create DB tables if they do not exist.
    Also seed one FX snapshot so UI always has a table.
    """
    with app.app_context():
        db.create_all()

        if FxSnapshot.query.count() == 0:
            snapshot = FxSnapshot(
                timestamp_text=DEFAULT_FX_TABLE["timestamp_utc"],
                rates_json=json.dumps(DEFAULT_FX_TABLE["rates"]),
                base="USD",
                provider="default-seed",
            )
            db.session.add(snapshot)
            db.session.commit()


if __name__ == "__main__":
    init_db_if_needed()
    app.run(host="127.0.0.1", port=5000, debug=True)