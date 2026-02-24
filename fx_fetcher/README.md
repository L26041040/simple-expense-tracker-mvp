# FX Fetcher (API -> DB)

This small program fetches exchange rates from an external REST API (Frankfurter)
and stores the result into a local SQLite database.

## What it does
- Fetch latest FX rates using base=USD and symbols=TWD,JPY,EUR
- Create a SQLite DB + table if not exists
- Insert one snapshot row per run

## How to run (Windows PowerShell)

cd fx_fetcher
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

python fetch_fx_and_store.py

## Verify DB
A file `fx_rates.sqlite3` will be created/updated.
You should also see a "Fetch + Store succeeded" message in the terminal.