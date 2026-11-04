"""
CampusOS - a simple campus app built with Streamlit + SQLite.

Run with:
    pip install streamlit
    streamlit run app.py

Default logins:
    Admin   -> admin   / admin123
    Student -> student / student123
"""

import secrets
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DB_NAME = "campusos.db"  # SQLite file is created automatically next to app.py
COOKIE_NAME = "campusos_token"
SESSION_DAYS = 7  # how long a login is remembered after closing the browser


# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------

def run_query(sql, params=(), fetch=False):
    """Run one SQL command.
    - fetch=True  -> returns a pandas DataFrame (for SELECT)
    - fetch=False -> saves changes (for INSERT / CREATE)
    """
    conn = sqlite3.connect(DB_NAME)
    try:
        if fetch:
            return pd.read_sql_query(sql, conn, params=params)
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables (if missing) and add the default users."""
    run_query("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role     TEXT NOT NULL
        )""")
    run_query("""
        CREATE TABLE IF NOT EXISTS timetable (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            time    TEXT,
            room    TEXT,
            faculty TEXT
        )""")
    run_query("""
        CREATE TABLE IF NOT EXISTS assignments (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT,
            subject  TEXT,
            due_date TEXT
        )""")
    run_query("""
        CREATE TABLE IF NOT EXISTS issues (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            issue        TEXT,
            location     TEXT,
            status       TEXT DEFAULT 'Open'
        )""")

    run_query("""
        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            username   TEXT NOT NULL,
            role       TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )""")

    # INSERT OR IGNORE = do nothing if the user already exists
    run_query("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
              ("admin", "admin123", "admin"))
    run_query("INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
              ("student", "student123", "student"))



# ---------------------------------------------------------------------------
# REMEMBER-ME SESSIONS (keeps you logged in after closing the browser)
# ---------------------------------------------------------------------------

def create_session(username, role):
    """Store a random token in the DB and return it."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat()
    run_query("INSERT INTO sessions VALUES (?, ?, ?, ?)",
              (token, username, role, expires))
    return token


def restore_session():
    """If the browser has a valid token cookie, log the user back in."""
    token = st.context.cookies.get(COOKIE_NAME)
    if not token:
        return False
    row = run_query("SELECT * FROM sessions WHERE token=?", (token,), fetch=True)
    if row.empty:
        return False
    if datetime.fromisoformat(row.iloc[0]["expires_at"]) < datetime.now():
        run_query("DELETE FROM sessions WHERE token=?", (token,))
        return False
    st.session_state.logged_in = True
    st.session_state.username = row.iloc[0]["username"]
    st.session_state.role = row.iloc[0]["role"]
    st.session_state.token = token
    return True


def delete_session(token):
    if token:
        run_query("DELETE FROM sessions WHERE token=?", (token,))


def browser_cookie(value, days):
    """Set (days > 0) or clear (days = 0) the cookie in the browser."""
    seconds = days * 86400
    components.html(
        f"<script>window.parent.document.cookie = "
        f"'{COOKIE_NAME}={value}; max-age={seconds}; path=/; SameSite=Lax';</script>",
        height=0,
    )

# ---------------------------------------------------------------------------
# LOGIN PAGE
# ---------------------------------------------------------------------------

def login_page():
    st.title("🎓 CampusOS")
    st.subheader("Login")

    role = st.radio("Login as", ["Student", "Admin"], horizontal=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        # Look for a user matching username + password + role
        user = run_query(
            "SELECT * FROM users WHERE username=? AND password=? AND role=?",
            (username, password, role.lower()),
            fetch=True,
        )
        if user.empty:
            st.error("Wrong username, password or role.")
        else:
            # Save login info in session_state so it survives page reruns
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = role.lower()
            st.session_state.token = create_session(username, role.lower())
            st.session_state.set_cookie = True  # cookie is written after the rerun
            st.rerun()


# ---------------------------------------------------------------------------
# STUDENT PAGES
# ---------------------------------------------------------------------------

def student_home():
    st.title("🏠 Student Home")
    st.write(f"Welcome, **{st.session_state.username}**!")

    # Quick numbers
    n_classes = len(run_query("SELECT id FROM timetable", fetch=True))
    n_assign = len(run_query("SELECT id FROM assignments", fetch=True))
    col1, col2 = st.columns(2)
    col1.metric("Classes", n_classes)
    col2.metric("Assignments", n_assign)


def view_timetable():
    st.title("📅 Timetable")
    data = run_query(
        "SELECT subject AS Subject, time AS Time, room AS Room, faculty AS Faculty "
        "FROM timetable", fetch=True)
    if data.empty:
        st.info("No timetable added yet.")
    else:
        st.dataframe(data, use_container_width=True, hide_index=True)


def view_assignments():
    st.title("📝 Assignments")
    data = run_query(
        "SELECT title AS Title, subject AS Subject, due_date AS 'Due Date' "
        "FROM assignments", fetch=True)
    if data.empty:
        st.info("No assignments yet.")
    else:
        st.dataframe(data, use_container_width=True, hide_index=True)


def report_issue():
    st.title("⚠️ Report an Issue")
    # clear_on_submit empties the form after sending
    with st.form("issue_form", clear_on_submit=True):
        issue = st.text_area("Describe the issue")
        location = st.text_input("Location (e.g. Library, Room 204)")
        submitted = st.form_submit_button("Submit")

    if submitted:
        if issue.strip() == "" or location.strip() == "":
            st.warning("Please fill in both fields.")
        else:
            run_query(
                "INSERT INTO issues (student_name, issue, location, status) "
                "VALUES (?, ?, ?, 'Open')",
                (st.session_state.username, issue, location),
            )
            st.success("Issue reported. Thank you!")


# ---------------------------------------------------------------------------
# ADMIN PAGES
# ---------------------------------------------------------------------------

def admin_dashboard():
    st.title("📊 Admin Dashboard")

    n_students = len(run_query("SELECT * FROM users WHERE role='student'", fetch=True))
    n_classes = len(run_query("SELECT id FROM timetable", fetch=True))
    n_assign = len(run_query("SELECT id FROM assignments", fetch=True))
    n_issues = len(run_query("SELECT id FROM issues", fetch=True))

    col1, col2 = st.columns(2)
    col1.metric("Students", n_students)
    col2.metric("Classes", n_classes)
    col3, col4 = st.columns(2)
    col3.metric("Assignments", n_assign)
    col4.metric("Issues", n_issues)


def add_timetable():
    st.title("➕ Add Timetable")
    with st.form("timetable_form", clear_on_submit=True):
        subject = st.text_input("Subject")
        time = st.text_input("Time (e.g. Mon 10:00-11:00)")
        room = st.text_input("Room")
        faculty = st.text_input("Faculty")
        submitted = st.form_submit_button("Add")

    if submitted:
        if not (subject and time and room and faculty):
            st.warning("Please fill in all fields.")
        else:
            run_query(
                "INSERT INTO timetable (subject, time, room, faculty) VALUES (?, ?, ?, ?)",
                (subject, time, room, faculty),
            )
            st.success("Timetable entry added.")


def add_assignment():
    st.title("➕ Add Assignment")
    with st.form("assignment_form", clear_on_submit=True):
        title = st.text_input("Title")
        subject = st.text_input("Subject")
        due_date = st.date_input("Due date")
        submitted = st.form_submit_button("Add")

    if submitted:
        if not (title and subject):
            st.warning("Please fill in title and subject.")
        else:
            run_query(
                "INSERT INTO assignments (title, subject, due_date) VALUES (?, ?, ?)",
                (title, subject, str(due_date)),
            )
            st.success("Assignment added.")


def view_issues():
    st.title("📋 Reported Issues")
    data = run_query(
        "SELECT student_name AS Student, issue AS Issue, "
        "location AS Location, status AS Status FROM issues", fetch=True)
    if data.empty:
        st.info("No issues reported.")
    else:
        st.dataframe(data, use_container_width=True, hide_index=True)


def add_student():
    st.title("➕ Add Student")
    with st.form("student_form", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password")
        submitted = st.form_submit_button("Add Student")

    if submitted:
        if not (username and password):
            st.warning("Please fill in both fields.")
        else:
            # Check if the username is already taken
            existing = run_query("SELECT * FROM users WHERE username=?",
                                 (username,), fetch=True)
            if not existing.empty:
                st.error("That username already exists.")
            else:
                run_query("INSERT INTO users VALUES (?, ?, 'student')",
                          (username, password))
                st.success(f"Student '{username}' added.")


# ---------------------------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="CampusOS", page_icon="🎓")
    init_db()

    # Set default session values the first time the app runs
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Browser was closed and reopened? Try to log back in from the cookie
    if not st.session_state.logged_in:
        restore_session()

    # Not logged in -> show login page only
    if not st.session_state.logged_in:
        if st.session_state.pop("clear_cookie", False):
            browser_cookie("", 0)
        login_page()
        return

    # Just logged in -> save the token cookie in the browser
    if st.session_state.pop("set_cookie", False):
        browser_cookie(st.session_state.token, SESSION_DAYS)

    # Sidebar: menu depends on role
    st.sidebar.title("🎓 CampusOS")
    st.sidebar.write(f"Logged in as **{st.session_state.username}** "
                     f"({st.session_state.role})")

    if st.session_state.role == "student":
        pages = {
            "Home": student_home,
            "View Timetable": view_timetable,
            "View Assignments": view_assignments,
            "Report Issue": report_issue,
        }
    else:
        pages = {
            "Dashboard": admin_dashboard,
            "Add Timetable": add_timetable,
            "Add Assignments": add_assignment,
            "View Issues": view_issues,
            "Add Students": add_student,
        }

    choice = st.sidebar.radio("Menu", list(pages.keys()))

    if st.sidebar.button("Logout"):
        delete_session(st.session_state.get("token"))
        st.session_state.clear_cookie = True
        st.session_state.token = ""
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()

    # Call the function for the selected page
    pages[choice]()


main()
