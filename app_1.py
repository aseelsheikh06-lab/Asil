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
from html import escape
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

# =============================================================================
# CAMPUSOS UI: theme, screens and main app
# =============================================================================

CAMPUS_CSS = """
<style>
/* ---------- base ---------- */
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #f8faff !important;
    font-family: "Inter", "Segoe UI", "DejaVu Sans", system-ui, sans-serif;
    color: #1e293b;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display: none !important; }

/* hide the invisible helper elements (this css, cookie script) so they leave no gap */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style),
.element-container:has(> [data-testid="stMarkdown"] style) { display: none !important; }
[data-testid="stElementContainer"]:has(iframe[height="0"]),
.element-container:has(iframe[height="0"]) { position: absolute; width: 0; height: 0; overflow: hidden; }

/* ---------- main area ---------- */
[data-testid="stMainBlockContainer"], .block-container {
    max-width: 960px;
    padding: 3.6rem 2rem 3rem 2.75rem !important;
    margin-left: 0;
}
.page-title { font-size: 2.1rem; font-weight: 800; color: #1e2a3b; line-height: 1.2; margin: 0; }
.page-sub   { color: #64748b; font-size: 1rem; margin: .45rem 0 1.4rem; }
.page-gap   { height: 1.6rem; }

/* ---------- inputs ---------- */
[data-testid="stWidgetLabel"] p, label p { font-weight: 700; color: #1e293b; font-size: .95rem; }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="base-input"] {
    background: #fff !important; border-radius: 10px !important;
}
[data-baseweb="input"], [data-baseweb="textarea"] { border: 1px solid #e2e8f0 !important; min-height: 52px; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
    background: #fff !important; color: #1e293b !important; padding: 0 1rem; font-size: 1rem;
}
[data-baseweb="textarea"] textarea { padding: .9rem 1rem; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
    border-color: #2563eb !important; box-shadow: none !important;
}

/* ---------- forms (no box around them) ---------- */
[data-testid="stForm"] { border: none !important; padding: 0 !important; background: transparent !important; }

/* ---------- buttons ---------- */
.stButton > button, [data-testid="stFormSubmitButton"] > button {
    background: #2563eb; color: #fff; border: none; border-radius: 10px;
    font-weight: 700; height: 48px; padding: 0 2rem; min-width: 150px;
}
.stButton > button p, [data-testid="stFormSubmitButton"] > button p { color: #fff; font-weight: 700; }
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover { background: #1d4ed8; color: #fff; border: none; }
.stButton > button:focus, [data-testid="stFormSubmitButton"] > button:focus { color: #fff; box-shadow: none; }

/* ---------- alerts ---------- */
[data-testid="stAlert"] { border-radius: 10px; }

/* ---------- cards, metrics, tables ---------- */
.metric-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.35rem 1.4rem; }
.metric-card .m-label { color: #64748b; font-size: .95rem; }
.metric-card .m-value { color: #1e293b; font-size: 2.1rem; font-weight: 800; margin-top: .35rem; }
.info-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.4rem 1.5rem; margin-top: .6rem; }
.info-card h3 { margin: 0 0 .6rem; font-size: 1.25rem; font-weight: 800; color: #1e293b; padding: 0; }
.info-card p  { margin: 0; color: #64748b; }
.note-box { background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 12px; padding: 1.5rem 1.4rem; }
.tbl-wrap { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; overflow-x: auto; }
.tbl { width: 100%; border-collapse: collapse; font-size: .95rem; }
.tbl th { background: #f1f5f9; text-align: left; font-weight: 700; padding: 1rem .9rem; color: #1e293b; }
.tbl td { padding: 1rem .9rem; border-top: 1px solid #e2e8f0; color: #1e293b; }

/* ---------- sidebar (fixed width, works in portrait AND landscape) ---------- */
:root { --sbw: 250px; }
@media (max-width: 991px) { :root { --sbw: 200px; } }

[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stExpandSidebarButton"], [data-testid="stSidebarHeader"] { display: none !important; }

[data-testid="stSidebar"], [data-testid="stSidebar"][aria-expanded="false"] {
    position: fixed !important; top: 0; left: 0; z-index: 99;
    height: 100vh !important; height: 100dvh !important;
    width: var(--sbw) !important; min-width: var(--sbw) !important; max-width: var(--sbw) !important;
    transform: none !important; margin-left: 0 !important; visibility: visible !important;
    background: #f0f4f9 !important; border-right: none !important;
}
[data-testid="stSidebar"] > div { width: 100% !important; }
[data-testid="stAppViewContainer"]:has(.who) [data-testid="stMain"], [data-testid="stAppViewContainer"]:has(.who) section.main {
    margin-left: var(--sbw) !important; width: calc(100% - var(--sbw)) !important;
}
[data-testid="stSidebarUserContent"] { padding: 1.5rem 1rem 1.5rem !important; }
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { min-height: calc(100vh - 3rem); min-height: calc(100dvh - 3rem); gap: .35rem; }

.side-title { font-size: 1.5rem; font-weight: 800; color: #17304f; white-space: nowrap; }
.side-rule  { border-top: 1px solid #e2e8f0; margin: .9rem 0 1rem; }
.who { color: #1e293b; font-size: .95rem; line-height: 1.7; }
.who span { color: #64748b; }
.menu-label { font-size: .8rem; letter-spacing: .06em; color: #64748b; font-weight: 700; margin: 1rem 0 .2rem; }

/* menu items = plain text buttons (no dots) */
[class*="st-key-nav"], [class*="st-key-nav"] .stButton { width: 100% !important; }
[class*="st-key-nav"] button {
    width: 100%; min-width: 0; height: auto; padding: .7rem .8rem; border: none; border-radius: 10px;
    background: transparent; box-shadow: none; justify-content: flex-start; text-align: left;
}
[class*="st-key-nav"] button > div { width: 100%; justify-content: flex-start; }
[class*="st-key-nav"] button p { color: #1e293b; font-weight: 500; font-size: 1.02rem; text-align: left; white-space: nowrap; }
[class*="st-key-nav"] button:hover { background: #e8eef7; border: none; }
[class*="st-key-navsel"] button { background: #e3ebf7; }
[class*="st-key-navsel"] button p { color: #2563eb; font-weight: 700; }

/* logout at the bottom */
.st-key-logout { margin-top: auto; width: 100% !important; }
.st-key-logout .stButton { width: 100% !important; }
.st-key-logout button {
    width: 100%; background: #fff; color: #1e293b; border: 1px solid #e2e8f0;
    justify-content: flex-start; padding: 0 1.2rem;
}
.st-key-logout button p { color: #1e293b; font-weight: 700; }
.st-key-logout button:hover { background: #f8fafc; border: 1px solid #cbd5e1; color: #1e293b; }

[class*="st-key-nav"] button:focus, .st-key-logout button:focus, .st-key-sbtoggle button:focus,
[class*="st-key-nav"] button:active, .st-key-logout button:active, .st-key-sbtoggle button:active {
    color: #1e293b; box-shadow: none; outline: none;
}

/* the show/hide sidebar button */
.st-key-sbtoggle { position: fixed; top: .7rem; left: calc(var(--sbw) + 10px); z-index: 1000; width: auto !important; }
.st-key-sbtoggle button {
    min-width: 0; width: 42px; height: 42px; padding: 0; background: #fff; color: #1e293b;
    border: 1px solid #e2e8f0; border-radius: 10px; box-shadow: 0 1px 3px rgba(15,23,42,.1);
}
.st-key-sbtoggle button p { color: #1e293b; font-size: 1.2rem; }
.st-key-sbtoggle button:hover { background: #f1f5f9; color: #1e293b; border: 1px solid #cbd5e1; }

@media (max-width: 991px) {
    [data-testid="stMainBlockContainer"], .block-container { padding: 3.6rem 1rem 3rem 1.2rem !important; }
    .side-title { font-size: 1.25rem; }
    .who { font-size: .85rem; }
    [class*="st-key-nav"] button p { font-size: .92rem; }
    .page-title { font-size: 1.6rem; }
    .metric-card .m-value { font-size: 1.7rem; }
}

/* ---------- login card ---------- */
[data-testid="stMainBlockContainer"]:has(.login-marker) {
    max-width: 585px; margin: 100px auto 0; background: #fff;
    border: 1.5px solid #dbe3ef; border-radius: 18px; padding: 3rem 4.4rem 1.6rem !important;
}
.login-title { text-align: center; font-size: 2.1rem; font-weight: 800; color: #17304f; }
.login-sub   { text-align: center; font-size: 1.5rem; font-weight: 800; color: #1e293b; margin: .6rem 0 1.4rem; }
.login-hint  { text-align: center; color: #64748b; font-size: .9rem; margin-top: .2rem; }
[data-testid="stMainBlockContainer"] [data-testid="stRadio"] [role="radiogroup"] {
    background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: .75rem 1.3rem; gap: 3rem;
}
[data-testid="stMainBlockContainer"] [data-baseweb="radio"]:has(input:checked) p { color: #2563eb; font-weight: 700; }
[data-testid="stMainBlockContainer"] [data-baseweb="radio"]:has(input:checked) > div:first-of-type {
    background-color: #2563eb !important; border-color: #2563eb !important;
}
[data-testid="stMainBlockContainer"]:has(.login-marker) .stButton > button { width: 100%; }
</style>
"""


CLOSED_CSS = """
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stAppViewContainer"]:has(.who) [data-testid="stMain"],
[data-testid="stAppViewContainer"]:has(.who) section.main { margin-left: 0 !important; width: 100% !important; }
.st-key-sbtoggle { left: 10px !important; }
</style>
"""


def _set_page(name):
    st.session_state.page = name


def _toggle_sidebar():
    st.session_state.sidebar_open = not st.session_state.get("sidebar_open", True)


# ---------------------------------------------------------------------------
# SMALL UI HELPERS
# ---------------------------------------------------------------------------

def page_header(title, sub=None):
    html = f'<div class="page-title">{title}</div>'
    html += f'<div class="page-sub">{sub}</div>' if sub else '<div class="page-gap"></div>'
    st.markdown(html, unsafe_allow_html=True)


def metric_card(label, value):
    return (f'<div class="metric-card"><div class="m-label">{label}</div>'
            f'<div class="m-value">{value}</div></div>')


def note(text):
    st.markdown(f'<div class="note-box">{escape(text)}</div>', unsafe_allow_html=True)


def html_table(df):
    """Show a DataFrame as a clean HTML table (all text is escaped = safe)."""
    def cell(v):
        return escape(str(v)).replace("\n", " ").replace("$", "&#36;")
    head = "".join(f"<th>{cell(c)}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{cell(v)}</td>" for v in r) + "</tr>"
        for r in df.itertuples(index=False)
    )
    st.markdown(
        f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# LOGIN PAGE (new look)
# ---------------------------------------------------------------------------

def login_page():
    st.markdown(
        '<div class="login-marker"></div>'
        '<div class="login-title">🎓 CampusOS</div>'
        '<div class="login-sub">Login</div>',
        unsafe_allow_html=True,
    )
    role = st.radio("Login as", ["Student", "Admin"], horizontal=True)
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = run_query(
            "SELECT * FROM users WHERE username=? AND password=? AND role=?",
            (username, password, role.lower()),
            fetch=True,
        )
        if user.empty:
            st.error("Wrong username, password or role.")
        else:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = role.lower()
            if "create_session" in globals():  # keeps you logged in after closing Chrome
                st.session_state.token = create_session(username, role.lower())
                st.session_state.set_cookie = True
            st.rerun()

    st.markdown(
        '<div class="login-hint">Demo: student / student123 &nbsp;&nbsp;|&nbsp;&nbsp; admin / admin123</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# STUDENT PAGES (new look)
# ---------------------------------------------------------------------------

def student_home():
    page_header("🏠 Student Home", f"Welcome, {escape(st.session_state.username)}!")
    n_classes = len(run_query("SELECT id FROM timetable", fetch=True))
    n_assign = len(run_query("SELECT id FROM assignments", fetch=True))
    c1, c2 = st.columns(2)
    c1.markdown(metric_card("Classes", n_classes), unsafe_allow_html=True)
    c2.markdown(metric_card("Assignments", n_assign), unsafe_allow_html=True)
    st.markdown(
        '<div class="info-card"><h3>Welcome to CampusOS</h3>'
        "<p>Use the sidebar to view your timetable, check assignments, or report an issue.</p></div>",
        unsafe_allow_html=True,
    )


def view_timetable():
    page_header("📅 Timetable")
    data = run_query(
        "SELECT subject AS Subject, time AS Time, room AS Room, faculty AS Faculty "
        "FROM timetable", fetch=True)
    if data.empty:
        note("No timetable added yet.")
    else:
        html_table(data)


def view_assignments():
    page_header("📝 Assignments")
    data = run_query(
        "SELECT title AS Title, subject AS Subject, due_date AS 'Due Date' "
        "FROM assignments", fetch=True)
    if data.empty:
        note("No assignments yet.")
    else:
        html_table(data)


def report_issue():
    page_header("⚠️ Report an Issue", "Tell the administration what needs attention.")
    with st.form("issue_form", clear_on_submit=True):
        issue = st.text_area("Describe the issue", height=110)
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
# ADMIN PAGES (new look)
# ---------------------------------------------------------------------------

def admin_dashboard():
    page_header("📊 Admin Dashboard")
    n_students = len(run_query("SELECT * FROM users WHERE role='student'", fetch=True))
    n_classes = len(run_query("SELECT id FROM timetable", fetch=True))
    n_assign = len(run_query("SELECT id FROM assignments", fetch=True))
    n_issues = len(run_query("SELECT id FROM issues", fetch=True))

    c1, c2 = st.columns(2)
    c1.markdown(metric_card("Students", n_students), unsafe_allow_html=True)
    c2.markdown(metric_card("Classes", n_classes), unsafe_allow_html=True)
    st.write("")
    c3, c4 = st.columns(2)
    c3.markdown(metric_card("Assignments", n_assign), unsafe_allow_html=True)
    c4.markdown(metric_card("Issues", n_issues), unsafe_allow_html=True)


def add_timetable():
    page_header("➕ Add Timetable", "Add a class entry for students.")
    with st.form("timetable_form", clear_on_submit=True):
        subject = st.text_input("Subject")
        time = st.text_input("Time (e.g. Mon 10:00-11:00)")
        c1, c2 = st.columns(2)
        room = c1.text_input("Room")
        faculty = c2.text_input("Faculty")
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
    page_header("➕ Add Assignment", "Create an assignment and set its due date.")
    with st.form("assignment_form", clear_on_submit=True):
        title = st.text_input("Title")
        subject = st.text_input("Subject")
        c1, _ = st.columns(2)
        due_date = c1.date_input("Due date", format="YYYY-MM-DD")
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
    page_header("📋 Reported Issues")
    data = run_query(
        "SELECT student_name AS Student, issue AS Issue, "
        "location AS Location, status AS Status FROM issues", fetch=True)
    if data.empty:
        note("No issues reported.")
    else:
        html_table(data)


def add_student():
    page_header("➕ Add Student", "Create a student login account.")
    with st.form("student_form", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Add Student")

    if submitted:
        if not (username and password):
            st.warning("Please fill in both fields.")
        else:
            existing = run_query("SELECT * FROM users WHERE username=?",
                                 (username,), fetch=True)
            if not existing.empty:
                st.error("That username already exists.")
            else:
                run_query("INSERT INTO users VALUES (?, ?, 'student')",
                          (username, password))
                st.success(f"Student '{username}' added.")


# ---------------------------------------------------------------------------
# MAIN APP (new layout)
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="CampusOS", page_icon="🎓",
                       initial_sidebar_state="expanded")
    st.markdown(CAMPUS_CSS, unsafe_allow_html=True)
    init_db()

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Browser was closed and reopened? log back in from the cookie
    if not st.session_state.logged_in and "restore_session" in globals():
        restore_session()

    if not st.session_state.logged_in:
        if "browser_cookie" in globals() and st.session_state.pop("clear_cookie", False):
            browser_cookie("", 0)
        login_page()
        return

    if "browser_cookie" in globals() and st.session_state.pop("set_cookie", False):
        browser_cookie(st.session_state.token, SESSION_DAYS)

    role = st.session_state.role
    if role == "student":
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

    if st.session_state.get("page") not in pages:
        st.session_state.page = list(pages)[0]
    if "sidebar_open" not in st.session_state:
        st.session_state.sidebar_open = True
    sidebar_open = st.session_state.sidebar_open

    # one button that shows / hides the sidebar
    st.button("✕" if sidebar_open else "☰", key="sbtoggle", on_click=_toggle_sidebar)
    if not sidebar_open:
        st.markdown(CLOSED_CSS, unsafe_allow_html=True)

    sb = st.sidebar
    sb.markdown(
        '<div class="side-title">🎓 CampusOS</div><div class="side-rule"></div>'
        f'<div class="who">Logged in as {escape(st.session_state.username)}'
        f'<br><span>({escape(role)})</span></div>'
        '<div class="menu-label">MENU</div>',
        unsafe_allow_html=True,
    )
    for i, name in enumerate(pages):
        selected = name == st.session_state.page
        sb.button(name, key=f"{'navsel' if selected else 'nav'}_{i}",
                  on_click=_set_page, args=(name,))

    if sb.button("Logout", key="logout"):
        if "delete_session" in globals():
            delete_session(st.session_state.get("token"))
        st.session_state.clear_cookie = True
        st.session_state.token = ""
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()

    pages[st.session_state.page]()


main()
