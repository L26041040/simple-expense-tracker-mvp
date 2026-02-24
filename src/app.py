#!/usr/bin/env python3
"""
Simple Expense Tracker (Final Project MVP)

This app demonstrates:
- Web UI (Flask) that accepts user input
- SQL database (SQLite) for persistence
- Fetching data from a public REST API (FX rates)
- Storing fetched FX data into DB (so the web app uses DB, not live API)
- A simple analysis page (monthly summary)

Student note:
- On free hosting (Render), disk can be ephemeral, so SQLite may reset.
"""

import os
import ast
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import requests

# Make template path explicit so Flask never gets confused
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(__name__, template_folder=TEMPLATES_DIR)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

db_path = os.path.join(os.getcwd(), "app.sqlite3")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

DEFAULT_CATEGORIES = ["Food", "Transport", "Housing", "Entertainment", "Other"]
SUPPORTED_CURRENCIES = ["USD", "TWD", "JPY", "EUR", "GBP"]

# Default rates (demo-safe)
# Meaning: 1 USD = rate_to_usd * currency
DEFAULT_FX_RATES = {
    "USD": 1.0,
    "TWD": 31.5,
    "JPY": 155.0,
    "EUR": 0.85,
    "GBP": 0.74,
}


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expense_date = db.Column(db.Date, nullable=False, default=date.today)

    category = db.Column(db.String(32), nullable=False)

    # What user typed (original)
    amount_original = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")

    # What we store for analysis (normalized)
    amount_usd = db.Column(db.Float, nullable=False)


class FxRate(db.Model):
    """
    Stores the latest known FX rates in a simple table.
    rate_to_usd means: 1 USD = rate_to_usd * <currency>
    Example: 1 USD = 31.5 TWD  => rate_to_usd = 31.5
    """
    currency = db.Column(db.String(8), primary_key=True)
    rate_to_usd = db.Column(db.Float, nullable=False)
    updated_at_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class FxSnapshot(db.Model):
    """
    Optional: keep a snapshot history row (for showing "we stored API response in DB").
    """
    id = db.Column(db.Integer, primary_key=True)
    fetched_at_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    base = db.Column(db.String(8), nullable=False)
    date_str = db.Column(db.String(16), nullable=False)
    symbols = db.Column(db.String(128), nullable=False)
    rates_json = db.Column(db.Text, nullable=False)


def init_db_if_needed():
    with app.app_context():
        db.create_all()
        seed_default_fx_if_needed()


def seed_default_fx_if_needed():
    """
    Seed a safe default FX table so the app never breaks.
    Users can still click Fetch FX to update values.
    """
    existing = FxRate.query.count()
    if existing > 0:
        return

    now = datetime.utcnow()
    for cur, rate in DEFAULT_FX_RATES.items():
        db.session.add(FxRate(currency=cur, rate_to_usd=float(rate), updated_at_utc=now))
    db.session.commit()


def fetch_fx_latest(base="USD", symbols=None):
    """
    Fetch latest FX rates from a public API.
    We use Frankfurter because it is free and simple.
    """
    if symbols is None:
        symbols = ["TWD", "JPY", "EUR", "GBP"]

    url = "https://api.frankfurter.app/latest"
    params = {"base": base, "symbols": ",".join(symbols)}

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def upsert_fx_rates_from_api(data):
    """
    Update fx_rates table based on API response.
    Always keep USD=1.
    """
    now = datetime.utcnow()

    # Ensure USD is present
    usd_row = FxRate.query.filter_by(currency="USD").first()
    if usd_row:
        usd_row.rate_to_usd = 1.0
        usd_row.updated_at_utc = now
    else:
        db.session.add(FxRate(currency="USD", rate_to_usd=1.0, updated_at_utc=now))

    rates = data.get("rates", {})
    for cur, rate in rates.items():
        row = FxRate.query.filter_by(currency=cur).first()
        if row:
            row.rate_to_usd = float(rate)
            row.updated_at_utc = now
        else:
            db.session.add(FxRate(currency=cur, rate_to_usd=float(rate), updated_at_utc=now))

    db.session.commit()


def save_fx_snapshot(data, symbols):
    snapshot = FxSnapshot(
        base=data.get("base", "USD"),
        date_str=data.get("date", ""),
        symbols=",".join(symbols),
        rates_json=str(data.get("rates", {})),
    )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


def get_fx_table():
    """
    Returns a list of FxRate rows sorted by currency for display.
    """
    rows = FxRate.query.order_by(FxRate.currency.asc()).all()
    return rows


def get_fx_timestamp():
    """
    Use the newest updated_at_utc in fx_rates as the "current FX timestamp".
    """
    row = FxRate.query.order_by(FxRate.updated_at_utc.desc()).first()
    return row.updated_at_utc if row else None


def get_rate_to_usd(currency: str):
    row = FxRate.query.filter_by(currency=currency).first()
    return float(row.rate_to_usd) if row else None


def convert_to_usd(amount_original: float, currency: str):
    """
    Convert user input to USD using fx_rates table.
    - If currency is USD, return amount_original
    - Otherwise: USD amount = amount_original / rate_to_usd
      because rate_to_usd means 1 USD = rate_to_usd * currency
    """
    if currency == "USD":
        return amount_original

    rate = get_rate_to_usd(currency)
    if not rate or rate <= 0:
        return None

    return amount_original / rate


def monthly_report(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    rows = Expense.query.filter(Expense.expense_date >= start, Expense.expense_date < end).all()

    total = sum(r.amount_usd for r in rows)
    totals_by_cat = {}
    for r in rows:
        totals_by_cat[r.category] = totals_by_cat.get(r.category, 0.0) + r.amount_usd

    percent_by_cat = {}
    for cat, amt in totals_by_cat.items():
        percent_by_cat[cat] = (amt / total * 100.0) if total > 0 else 0.0

    top_item = max(rows, key=lambda x: x.amount_usd) if rows else None

    return {
        "year": year,
        "month": month,
        "count": len(rows),
        "total": round(total, 2),
        "totals_by_cat": {k: round(v, 2) for k, v in totals_by_cat.items()},
        "percent_by_cat": {k: round(v, 2) for k, v in percent_by_cat.items()},
        "top_item": top_item,
        "rows": rows,
    }


@app.route("/", methods=["GET"])
def index():
    init_db_if_needed()

    recent = Expense.query.order_by(Expense.id.desc()).limit(10).all()

    fx_rows = get_fx_table()
    fx_ts = get_fx_timestamp()

    # Prepare a simple dict for display "to USD"
    # We display currency -> rate_to_usd
    fx_map = {r.currency: r.rate_to_usd for r in fx_rows}

    return render_template(
        "index.html",
        categories=DEFAULT_CATEGORIES,
        currencies=SUPPORTED_CURRENCIES,
        recent=recent,
        fx_timestamp=fx_ts,
        fx_map=fx_map,
    )


@app.route("/add_expense", methods=["POST"])
def add_expense():
    init_db_if_needed()

    category = request.form.get("category", "").strip()
    amount = request.form.get("amount", "").strip()
    currency = request.form.get("currency", "USD").strip()
    expense_date_str = request.form.get("expense_date", "").strip()

    if not category:
        flash("Please pick a category.")
        return redirect(url_for("index"))

    if currency not in SUPPORTED_CURRENCIES:
        flash("Unsupported currency.")
        return redirect(url_for("index"))

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError()
    except ValueError:
        flash("Amount should be a positive number.")
        return redirect(url_for("index"))

    if expense_date_str:
        try:
            d = datetime.strptime(expense_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Date format should be YYYY-MM-DD.")
            return redirect(url_for("index"))
    else:
        d = date.today()

    usd_val = convert_to_usd(amount_val, currency)
    if usd_val is None:
        flash("FX rate is missing. Please click Fetch FX and try again.")
        return redirect(url_for("index"))

    e = Expense(
        category=category,
        amount_original=amount_val,
        currency=currency,
        amount_usd=float(usd_val),
        expense_date=d,
    )
    db.session.add(e)
    db.session.commit()

    flash(
        f"Recorded: {category} {amount_val:.2f} {currency} (stored as ${usd_val:.2f} USD) on {d.isoformat()}"
    )
    return redirect(url_for("index"))


@app.route("/report", methods=["GET"])
def report():
    init_db_if_needed()
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    r = monthly_report(year, month)
    return render_template("report.html", r=r)


@app.route("/fx/update", methods=["POST"])
def fx_update():
    init_db_if_needed()
    symbols = ["TWD", "JPY", "EUR", "GBP"]

    try:
        data = fetch_fx_latest(base="USD", symbols=symbols)

        # Update main FX table (used by web conversion)
        upsert_fx_rates_from_api(data)

        # Also store one snapshot row (so we can show "API data stored in DB")
        snapshot = save_fx_snapshot(data, symbols)

        flash(f"✅ FX updated from API (snapshot id={snapshot.id}, date={snapshot.date_str})")
    except Exception as ex:
        flash(f"FX update failed: {str(ex)}")

    return redirect(url_for("index"))


@app.route("/fx", methods=["GET"])
def fx_page():
    init_db_if_needed()
    latest = FxSnapshot.query.order_by(FxSnapshot.id.desc()).first()
    fx_rows = get_fx_table()
    fx_ts = get_fx_timestamp()
    return render_template("fx.html", latest=latest, fx_rows=fx_rows, fx_timestamp=fx_ts)


if __name__ == "__main__":
    init_db_if_needed()
    app.run(host="127.0.0.1", port=5000, debug=False)