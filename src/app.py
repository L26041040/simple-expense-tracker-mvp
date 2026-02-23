#!/usr/bin/env python3
from flask import Flask, request

app = Flask(__name__)

@app.get("/")
def home():
    # Minimal HTML form (no templates yet)
    return """
    <h2>Simple Expense Tracker (MVP)</h2>

    <form action="/record" method="POST">
      <label>Category:</label><br>
      <input name="category" placeholder="Food" required><br><br>

      <label>Type:</label><br>
      <select name="txn_type" required>
        <option value="expense" selected>Expense</option>
        <option value="income">Income</option>
      </select><br><br>

      <label>Amount (USD):</label><br>
      <input name="amount" type="number" step="0.01" placeholder="12.50" required><br><br>

      <button type="submit">Submit</button>
    </form>
    """

@app.post("/record")
def record():
    category = (request.form.get("category") or "").strip()
    txn_type = (request.form.get("txn_type") or "").strip().lower()
    amount_raw = (request.form.get("amount") or "").strip()

    # Basic validation (student-level)
    if not category:
        return "Category is required.", 400
    if txn_type not in ("expense", "income"):
        return "Type must be expense or income.", 400
    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        return "Amount must be a positive number.", 400

    # Echo back (this is enough for the assignment)
    return f"Recorded: {category} {txn_type} ${amount:.2f} (USD)"