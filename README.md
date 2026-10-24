# Library Management System

A beginner-friendly Python web app built with Streamlit and SQLite.

## Features
- Add, search, view, and safely delete books
- Register students and teachers
- Issue and return books
- 14-day loan period (configurable)
- Rs. 20 fine per overdue day (configurable)
- Borrow limits: students 3, teachers 5
- Overdue list and transaction history
- Persistent local SQLite database (`library.db`)

## Run on Windows (VS Code)

1. Install Python 3 if you do not already have it.
2. Open this folder in VS Code.
3. Open Terminal > New Terminal.
4. (Recommended) Create a virtual environment:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

5. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

6. Run the app:

   ```bash
   python -m streamlit run app.py
   ```

Streamlit will show a local URL, usually http://localhost:8501.

## Important settings
At the top of `app.py`:
- `LOAN_DAYS = 14`
- `FINE_PER_DAY = 20`
- `BORROW_LIMITS = {"Student": 3, "Teacher": 5}`

Change these values to match your library's policy.

## Database
The app automatically creates `library.db` beside `app.py` on first run. Keep this file to preserve records. Do not delete it unless you intend to reset the database.

## Notes
- This is a local learning project, not a hardened multi-user production system.
- Book deletion is blocked when transaction history exists, to preserve records.
- Fines for issued books are estimates until the return is recorded.
