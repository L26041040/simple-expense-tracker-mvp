#!/usr/bin/env python3
from flask import Flask, request

app = Flask(__name__)

@app.get("/")
def home():
    return """
    <h2>Simple Expense Tracker (MVP)</h2>

    <form action="/record" method="POST">
      <label><b>Category:</b></label><br>

      <style>
        .cat { display:inline-block; margin:6px 8px 6px 0; }
        .cat input { display:none; }
        .cat span {
          display:inline-block;
          padding:8px 12px;
          border:1px solid #333;
          border-radius:6px;
          cursor:pointer;
          user-select:none;
        }
        .cat input:checked + span {
          font-weight:bold;
          text-decoration:underline;
        }
      </style>

      <label class="cat">
        <input type="radio" name="category" value="Food" required>
        <span>Food</span>
      </label>

      <label class="cat">
        <input type="radio" name="category" value="Transport">
        <span>Transport</span>
      </label>

      <label class="cat">
        <input type="radio" name="category" value="Housing">
        <span>Housing</span>
      </label>

      <label class="cat">
        <input type="radio" name="category" value="Entertainment">
        <span>Entertainment</span>
      </label>

      <label class="cat">
        <input type="radio" name="category" value="Other">
        <span>Other</span>
      </label>

      <br><br>

      <label><b>Type:</b></label><br>
      <select name="txn_type">
        <option value="expense" selected>Expense</option>
        <option value="income">Income</option>
      </select>

      <br><br>

      <label><b>Amount (USD):</b></label><br>
      <input name="amount" type="number" step="0.01" placeholder="Key in here" required>

      <br><br>

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