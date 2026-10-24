import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# -------------------- Configuration --------------------
DB_PATH = Path(__file__).with_name("library.db")
LOAN_DAYS = 14
FINE_PER_DAY = 20  # Rs. 20 per overdue day
BORROW_LIMITS = {"Student": 3, "Teacher": 5}

st.set_page_config(page_title="Library Management System", page_icon="📚", layout="wide")


# -------------------- Database helpers --------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL COLLATE NOCASE,
                author TEXT NOT NULL COLLATE NOCASE,
                quantity INTEGER NOT NULL CHECK (quantity >= 1),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE,
                member_type TEXT NOT NULL CHECK (member_type IN ('Student', 'Teacher')),
                email TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL REFERENCES books(id),
                member_id INTEGER NOT NULL REFERENCES members(id),
                issue_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                return_date TEXT,
                fine REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Issued'
                    CHECK (status IN ('Issued', 'Returned'))
            );
            """
        )


def query_df(sql, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql, params=()):
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def get_book(book_id):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()


def get_member(member_id):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()


def available_copies(book_id):
    with get_connection() as conn:
        book = conn.execute("SELECT quantity FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            return 0
        issued = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE book_id = ? AND status = 'Issued'",
            (book_id,),
        ).fetchone()[0]
        return book["quantity"] - issued


def active_borrow_count(member_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE member_id = ? AND status = 'Issued'",
            (member_id,),
        ).fetchone()[0]


def current_fine(due_date_text, on_date=None):
    due = date.fromisoformat(due_date_text)
    today = on_date or date.today()
    overdue_days = max(0, (today - due).days)
    return overdue_days, overdue_days * FINE_PER_DAY


init_db()

# -------------------- Sidebar navigation --------------------
st.sidebar.title("📚 Library Desk")
st.sidebar.caption("Library Management System")
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Books",
        "Members",
        "Issue a Book",
        "Return a Book",
        "Overdue Books",
        "Transactions",
    ],
)
st.sidebar.divider()
st.sidebar.caption(f"Loan period: {LOAN_DAYS} days")
st.sidebar.caption(f"Late fine: Rs. {FINE_PER_DAY} per day")

# -------------------- Dashboard --------------------
if page == "Dashboard":
    st.title("📚 Library Management System")
    st.write("Welcome! Manage books, members, borrowing, returns, and late fines from one place.")

    total_titles = int(query_df("SELECT COUNT(*) AS n FROM books").iloc[0]["n"])
    total_copies = int(query_df("SELECT COALESCE(SUM(quantity), 0) AS n FROM books").iloc[0]["n"])
    total_members = int(query_df("SELECT COUNT(*) AS n FROM members").iloc[0]["n"])
    issued_count = int(query_df("SELECT COUNT(*) AS n FROM transactions WHERE status='Issued'").iloc[0]["n"])
    overdue_count = int(
        query_df(
            "SELECT COUNT(*) AS n FROM transactions WHERE status='Issued' AND due_date < ?",
            (date.today().isoformat(),),
        ).iloc[0]["n"]
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Book titles", total_titles)
    c2.metric("Total copies", total_copies)
    c3.metric("Members", total_members)
    c4.metric("Books issued", issued_count)
    c5.metric("Overdue", overdue_count)

    st.subheader("Currently issued books")
    issued = query_df(
        """
        SELECT t.id AS 'Transaction ID', b.title AS Book, m.name AS Member,
               m.member_type AS 'Member type', t.issue_date AS 'Issue date',
               t.due_date AS 'Due date'
        FROM transactions t
        JOIN books b ON b.id=t.book_id
        JOIN members m ON m.id=t.member_id
        WHERE t.status='Issued'
        ORDER BY t.due_date
        """
    )
    if issued.empty:
        st.info("No books are currently issued.")
    else:
        st.dataframe(issued, use_container_width=True, hide_index=True)

# -------------------- Books --------------------
elif page == "Books":
    st.title("📖 Book Management")
    tab_add, tab_search, tab_delete = st.tabs(["Add book", "Search / view books", "Delete book"])

    with tab_add:
        st.subheader("Add a new book")
        with st.form("add_book_form", clear_on_submit=True):
            title = st.text_input("Book title")
            author = st.text_input("Author")
            quantity = st.number_input("Number of copies", min_value=1, max_value=10000, value=1, step=1)
            submitted = st.form_submit_button("Add book", type="primary")
        if submitted:
            if not title.strip() or not author.strip():
                st.error("Please enter both a title and an author.")
            else:
                execute(
                    "INSERT INTO books(title, author, quantity, created_at) VALUES (?, ?, ?, ?)",
                    (title.strip(), author.strip(), int(quantity), date.today().isoformat()),
                )
                st.success(f"Added '{title.strip()}' to the library.")
                st.rerun()

    with tab_search:
        search = st.text_input("Search by title or author", placeholder="e.g. Python or Ahmed")
        sql = """
            SELECT b.id AS ID, b.title AS Title, b.author AS Author, b.quantity AS 'Total copies',
                   (b.quantity - (SELECT COUNT(*) FROM transactions t
                                  WHERE t.book_id=b.id AND t.status='Issued')) AS Available
            FROM books b
        """
        params = ()
        if search.strip():
            sql += " WHERE b.title LIKE ? OR b.author LIKE ?"
            params = (f"%{search.strip()}%", f"%{search.strip()}%")
        sql += " ORDER BY b.title"
        books = query_df(sql, params)
        if books.empty:
            st.info("No books found. Add a book or try another search.")
        else:
            st.dataframe(books, use_container_width=True, hide_index=True)

    with tab_delete:
        st.subheader("Delete a book record")
        books = query_df("SELECT id, title, author FROM books ORDER BY title")
        if books.empty:
            st.info("There are no books to delete.")
        else:
            labels = {
                int(row["id"]): f'{row["title"]} — {row["author"]} (ID {row["id"]})'
                for _, row in books.iterrows()
            }
            chosen_id = st.selectbox("Choose a book", list(labels.keys()), format_func=lambda x: labels[x])
            if st.button("Delete selected book", type="secondary"):
                with get_connection() as conn:
                    active = conn.execute(
                        "SELECT COUNT(*) FROM transactions WHERE book_id=? AND status='Issued'",
                        (chosen_id,),
                    ).fetchone()[0]
                    history = conn.execute(
                        "SELECT COUNT(*) FROM transactions WHERE book_id=?", (chosen_id,)
                    ).fetchone()[0]
                    if active:
                        st.error("This book is currently issued. Return it before deleting.")
                    elif history:
                        st.error("This book has transaction history, so it cannot be deleted safely. Keep the record for history.")
                    else:
                        conn.execute("DELETE FROM books WHERE id=?", (chosen_id,))
                        st.success("Book deleted.")
                        st.rerun()

# -------------------- Members --------------------
elif page == "Members":
    st.title("👥 Member Registration")
    tab_register, tab_view = st.tabs(["Register member", "View members"])

    with tab_register:
        with st.form("register_member_form", clear_on_submit=True):
            name = st.text_input("Full name")
            member_type = st.selectbox("Member type", ["Student", "Teacher"])
            email = st.text_input("Email (optional)")
            submitted = st.form_submit_button("Register member", type="primary")
        if submitted:
            if not name.strip():
                st.error("Please enter the member's name.")
            else:
                execute(
                    "INSERT INTO members(name, member_type, email, created_at) VALUES (?, ?, ?, ?)",
                    (name.strip(), member_type, email.strip(), date.today().isoformat()),
                )
                st.success(f"Registered {name.strip()} as a {member_type.lower()}.")
                st.rerun()

    with tab_view:
        members = query_df(
            """
            SELECT m.id AS 'Member ID', m.name AS Name, m.member_type AS Type,
                   m.email AS Email,
                   (SELECT COUNT(*) FROM transactions t
                    WHERE t.member_id=m.id AND t.status='Issued') AS 'Currently borrowed',
                   CASE m.member_type WHEN 'Student' THEN 3 ELSE 5 END AS 'Borrow limit'
            FROM members m ORDER BY m.name
            """
        )
        if members.empty:
            st.info("No members registered yet.")
        else:
            st.dataframe(members, use_container_width=True, hide_index=True)

# -------------------- Issue book --------------------
elif page == "Issue a Book":
    st.title("📤 Issue a Book")
    books = query_df("SELECT id, title, author FROM books ORDER BY title")
    members = query_df("SELECT id, name, member_type FROM members ORDER BY name")

    if books.empty:
        st.warning("Add at least one book before issuing.")
    elif members.empty:
        st.warning("Register at least one member before issuing.")
    else:
        book_labels = {
            int(row["id"]): f'{row["title"]} — {row["author"]} (Available: {available_copies(int(row["id"]))})'
            for _, row in books.iterrows()
        }
        member_labels = {
            int(row["id"]): f'{row["name"]} — {row["member_type"]} (ID {row["id"]})'
            for _, row in members.iterrows()
        }
        with st.form("issue_book_form"):
            member_id = st.selectbox("Member", list(member_labels.keys()), format_func=lambda x: member_labels[x])
            book_id = st.selectbox("Book", list(book_labels.keys()), format_func=lambda x: book_labels[x])
            issue_date = st.date_input("Issue date", value=date.today())
            submitted = st.form_submit_button("Issue book", type="primary")
        if submitted:
            member = get_member(member_id)
            limit = BORROW_LIMITS[member["member_type"]]
            borrowed = active_borrow_count(member_id)
            available = available_copies(book_id)
            if issue_date > date.today():
                st.error("Issue date cannot be in the future.")
            elif available < 1:
                st.error("No copies of this book are currently available.")
            elif borrowed >= limit:
                st.error(f"This member has reached the {limit}-book limit for {member['member_type'].lower()}s.")
            else:
                due = issue_date + timedelta(days=LOAN_DAYS)
                execute(
                    """INSERT INTO transactions(book_id, member_id, issue_date, due_date, status)
                       VALUES (?, ?, ?, ?, 'Issued')""",
                    (book_id, member_id, issue_date.isoformat(), due.isoformat()),
                )
                st.success(f"Book issued successfully. Due date: {due.isoformat()}.")
                st.rerun()

# -------------------- Return book --------------------
elif page == "Return a Book":
    st.title("📥 Return a Book")
    issued = query_df(
        """
        SELECT t.id, b.title, m.name, t.issue_date, t.due_date
        FROM transactions t
        JOIN books b ON b.id=t.book_id
        JOIN members m ON m.id=t.member_id
        WHERE t.status='Issued'
        ORDER BY t.due_date
        """
    )
    if issued.empty:
        st.info("There are no books waiting to be returned.")
    else:
        labels = {
            int(row["id"]): f'#{row["id"]} — {row["title"]} | {row["name"]} | Due {row["due_date"]}'
            for _, row in issued.iterrows()
        }
        with st.form("return_book_form"):
            transaction_id = st.selectbox("Select issued book", list(labels.keys()), format_func=lambda x: labels[x])
            return_date = st.date_input("Return date", value=date.today())
            submitted = st.form_submit_button("Return book", type="primary")
        if submitted:
            row = issued.loc[issued["id"] == transaction_id].iloc[0]
            due = date.fromisoformat(row["due_date"])
            if return_date < date.fromisoformat(row["issue_date"]):
                st.error("Return date cannot be before the issue date.")
            else:
                overdue_days = max(0, (return_date - due).days)
                fine = overdue_days * FINE_PER_DAY
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE transactions SET return_date=?, fine=?, status='Returned' WHERE id=?",
                        (return_date.isoformat(), fine, transaction_id),
                    )
                st.success(f"Book returned. Overdue days: {overdue_days}. Fine: Rs. {fine}.")
                st.rerun()

# -------------------- Overdue books --------------------
elif page == "Overdue Books":
    st.title("⏰ Overdue Books")
    today = date.today().isoformat()
    overdue = query_df(
        """
        SELECT t.id AS 'Transaction ID', b.title AS Book, b.author AS Author,
               m.name AS Member, m.member_type AS 'Member type',
               t.due_date AS 'Due date'
        FROM transactions t
        JOIN books b ON b.id=t.book_id
        JOIN members m ON m.id=t.member_id
        WHERE t.status='Issued' AND t.due_date < ?
        ORDER BY t.due_date
        """,
        (today,),
    )
    if overdue.empty:
        st.success("No overdue books today.")
    else:
        overdue["Overdue days"] = overdue["Due date"].apply(
            lambda due: max(0, (date.today() - date.fromisoformat(due)).days)
        )
        overdue["Estimated fine (Rs.)"] = overdue["Overdue days"] * FINE_PER_DAY
        st.dataframe(overdue, use_container_width=True, hide_index=True)
        st.caption("Estimated fines increase daily until the book is returned. Final fine is saved when the book is returned.")

# -------------------- Transaction history --------------------
elif page == "Transactions":
    st.title("🧾 Transaction History")
    transactions = query_df(
        """
        SELECT t.id AS 'Transaction ID', b.title AS Book, m.name AS Member,
               m.member_type AS 'Member type', t.issue_date AS 'Issue date',
               t.due_date AS 'Due date', t.return_date AS 'Return date',
               t.status AS Status, t.fine AS 'Fine (Rs.)'
        FROM transactions t
        JOIN books b ON b.id=t.book_id
        JOIN members m ON m.id=t.member_id
        ORDER BY t.id DESC
        """
    )
    if transactions.empty:
        st.info("No transactions recorded yet.")
    else:
        st.dataframe(transactions, use_container_width=True, hide_index=True)
        total_fines = transactions.loc[transactions["Status"] == "Returned", "Fine (Rs.)"].sum()
        st.metric("Total recorded fines", f"Rs. {total_fines:.0f}")

st.sidebar.divider()
st.sidebar.caption("Data is stored locally in library.db")
