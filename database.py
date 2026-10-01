from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash


DATABASE_PATH = Path(__file__).with_name("attendance.db")


def _connect() -> sqlite3.Connection:
	connection = sqlite3.connect(DATABASE_PATH)
	connection.row_factory = sqlite3.Row
	return connection


def initialize_database() -> None:
	with _connect() as connection:
		connection.executescript(
			"""
			CREATE TABLE IF NOT EXISTS students (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				name TEXT NOT NULL,
				email TEXT NOT NULL UNIQUE,
				created_at TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS users (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				username TEXT NOT NULL UNIQUE,
				password_hash TEXT NOT NULL,
				role TEXT NOT NULL CHECK(role IN ('teacher', 'student')),
				created_at TEXT NOT NULL
			);
			CREATE TABLE IF NOT EXISTS attendance (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				student_id INTEGER NOT NULL,
				attended_on TEXT NOT NULL,
				attended_at TEXT NOT NULL,
				UNIQUE(student_id, attended_on),
				FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
			);
			"""
		)
		columns = {row[1] for row in connection.execute("PRAGMA table_info(students)")}
		if "department" not in columns:
			connection.execute("ALTER TABLE students ADD COLUMN department TEXT NOT NULL DEFAULT ''")
		if "year" not in columns:
			connection.execute("ALTER TABLE students ADD COLUMN year TEXT NOT NULL DEFAULT ''")
		attendance_columns = {row[1] for row in connection.execute("PRAGMA table_info(attendance)")}
		if "period" not in attendance_columns:
			connection.execute("ALTER TABLE attendance ADD COLUMN period TEXT NOT NULL DEFAULT ''")
		if "status" not in attendance_columns:
			connection.execute("ALTER TABLE attendance ADD COLUMN status TEXT NOT NULL DEFAULT 'Present'")
		user_columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
		if "student_id" not in user_columns:
			connection.execute("ALTER TABLE users ADD COLUMN student_id INTEGER")
		connection.execute(
			"INSERT OR IGNORE INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
			("admin", generate_password_hash("admin123"), "teacher", datetime.now().isoformat(timespec="seconds")),
		)
		connection.execute(
			"INSERT OR IGNORE INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
			("student", generate_password_hash("student123"), "student", datetime.now().isoformat(timespec="seconds")),
		)


def create_user(username: str, password: str, role: str, name: str = "", email: str = "", department: str = "", year: str = "") -> int:
	username, password = username.strip(), password.strip()
	if not username or len(password) < 6 or role not in {"teacher", "student"}:
		raise ValueError("Username, a 6-character password, and a valid role are required.")
	if role == "student" and not all(value.strip() for value in (name, email, department, year)):
		raise ValueError("Student name, email, department, and year are required.")
	with _connect() as connection:
		student_id = None
		if role == "student":
			student_cursor = connection.execute(
				"INSERT INTO students(name, email, department, year, created_at) VALUES (?, ?, ?, ?, ?)",
				(name.strip(), email.strip().lower(), department.strip(), year.strip(), datetime.now().isoformat(timespec="seconds")),
			)
			student_id = int(student_cursor.lastrowid)
		cursor = connection.execute(
			"INSERT INTO users(username, password_hash, role, created_at, student_id) VALUES (?, ?, ?, ?, ?)",
			(username, generate_password_hash(password), role, datetime.now().isoformat(timespec="seconds"), student_id),
		)
		return int(cursor.lastrowid)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
	with _connect() as connection:
		row = connection.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username.strip(),)).fetchone()
	if row and check_password_hash(row["password_hash"], password):
		return {"id": row["id"], "username": row["username"], "role": row["role"]}
	return None


def change_password(username: str, current_password: str, new_password: str) -> None:
	if len(new_password.strip()) < 6:
		raise ValueError("New password must contain at least 6 characters.")
	with _connect() as connection:
		row = connection.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
		if not row or not check_password_hash(row["password_hash"], current_password):
			raise ValueError("Current password is incorrect.")
		connection.execute(
			"UPDATE users SET password_hash = ? WHERE username = ?",
			(generate_password_hash(new_password.strip()), username),
		)


def get_users() -> list[dict[str, Any]]:
	with _connect() as connection:
		rows = connection.execute(
			"""
			SELECT users.id, users.username, users.role, users.created_at,
			       students.id AS student_id, students.name, students.email, students.department, students.year
			FROM users LEFT JOIN students ON students.id = users.student_id
			ORDER BY users.username
			"""
		).fetchall()
	return [dict(row) for row in rows]


def add_student(name: str, email: str, department: str = "", year: str = "") -> int:
	name, email = name.strip(), email.strip().lower()
	department, year = department.strip(), year.strip()
	if not name or not email or not department or not year:
		raise ValueError("Name, email, department, and year are required.")
	with _connect() as connection:
		cursor = connection.execute(
			"INSERT INTO students(name, email, department, year, created_at) VALUES (?, ?, ?, ?, ?)",
			(name, email, department, year, datetime.now().isoformat(timespec="seconds")),
		)
		return int(cursor.lastrowid)


def get_students() -> list[dict[str, Any]]:
	with _connect() as connection:
		rows = connection.execute("SELECT * FROM students ORDER BY name").fetchall()
	return [dict(row) for row in rows]


def current_period() -> str:
	now = datetime.now()
	return f"{now.hour:02d}:00-{(now.hour + 1) % 24:02d}:00"


def mark_attendance(student_id: int, period: str | None = None) -> bool:
	today = date.today().isoformat()
	with _connect() as connection:
		cursor = connection.execute(
			"INSERT OR IGNORE INTO attendance(student_id, attended_on, attended_at, period, status) VALUES (?, ?, ?, ?, 'Present')",
			(student_id, today, datetime.now().isoformat(timespec="seconds"), period or current_period()),
		)
	return cursor.rowcount == 1


def set_attendance(student_id: int, attended_on: str, attended_time: str, period: str, status: str) -> None:
	if status not in {"Present", "Absent"}:
		raise ValueError("Status must be Present or Absent.")
	try:
		datetime.fromisoformat(f"{attended_on}T{attended_time}")
	except ValueError as error:
		raise ValueError("Enter a valid date and time.") from error
	with _connect() as connection:
		connection.execute(
			"""
			INSERT INTO attendance(student_id, attended_on, attended_at, period, status)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(student_id, attended_on) DO UPDATE SET
			attended_at=excluded.attended_at, period=excluded.period, status=excluded.status
			""",
			(student_id, attended_on, f"{attended_on}T{attended_time}", period.strip(), status),
		)


def get_attendance(attended_on: str | None = None) -> list[dict[str, Any]]:
	attended_on = attended_on or date.today().isoformat()
	with _connect() as connection:
		rows = connection.execute(
			"""
			SELECT students.id AS student_id, students.name, students.department, students.year,
			       students.email, attendance.attended_on, attendance.attended_at, attendance.period, attendance.status
			FROM attendance JOIN students ON students.id = attendance.student_id
			WHERE attendance.attended_on = ? ORDER BY attendance.attended_at
			""",
			(attended_on,),
		).fetchall()
	return [dict(row) for row in rows]


def get_attendance_summary(attended_on: str | None = None) -> dict[str, Any]:
	attended_on = attended_on or date.today().isoformat()
	with _connect() as connection:
		total_students = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
		present = connection.execute(
			"SELECT COUNT(*) FROM attendance WHERE attended_on = ? AND status = 'Present'", (attended_on,)
		).fetchone()[0]
		absent = connection.execute(
			"SELECT COUNT(*) FROM attendance WHERE attended_on = ? AND status = 'Absent'", (attended_on,)
		).fetchone()[0]
	return {
		"date": attended_on,
		"total_students": total_students,
		"present": present,
		"absent": absent,
		"unmarked": max(total_students - present - absent, 0),
		"attendance_rate": round((present / total_students) * 100, 2) if total_students else 0.0,
	}


def get_attendance_report() -> list[dict[str, Any]]:
	with _connect() as connection:
		total_days = connection.execute("SELECT COUNT(DISTINCT attended_on) FROM attendance").fetchone()[0]
		rows = connection.execute(
			"""
			SELECT students.id, students.name, students.department, students.year,
			       COUNT(CASE WHEN attendance.status = 'Present' THEN 1 END) AS present_days
			FROM students LEFT JOIN attendance ON students.id = attendance.student_id
			GROUP BY students.id ORDER BY students.name
			"""
		).fetchall()
	return [
		{
			**dict(row),
			"total_days": total_days,
			"absent_days": max(total_days - row["present_days"], 0),
			"percentage": round((row["present_days"] / total_days) * 100, 2) if total_days else 0.0,
		}
		for row in rows
	]


initialize_database()
from __future__ import annotations

import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from attendance import run_attendance
from database import get_attendance, get_attendance_report
from register import capture_student


BG = "#0f172a"
SURFACE = "#172033"
SURFACE_LIGHT = "#26344d"
TEXT = "#e5edf8"
MUTED = "#93a4bd"
ACCENT = "#2dd4bf"
ACCENT_DARK = "#0f766e"
ERROR = "#fb7185"
WARNING = "#fbbf24"


def configure_styles() -> None:
    style = ttk.Style()
    style.theme_use("clam")

    style.configure(
        "App.TFrame",
        background=BG
    )

    style.configure(
        "Card.TFrame",
        background=SURFACE
    )

    style.configure(
        "Title.TLabel",
        background=BG,
        foreground=TEXT,
        font=("Segoe UI", 22, "bold")
    )

    style.configure(
        "Subtitle.TLabel",
        background=BG,
        foreground=MUTED,
        font=("Segoe UI", 10)
    )

    style.configure(
        "CardTitle.TLabel",
        background=BG,
        foreground=TEXT,
        font=("Segoe UI", 12, "bold")
    )

    style.configure(
        "Field.TLabel",
        background=SURFACE,
        foreground=MUTED,
        font=("Segoe UI", 9, "bold")
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=BG,
        borderwidth=0,
        padding=(14, 9),
        font=("Segoe UI", 9, "bold")
    )

    style.map(
        "Accent.TButton",
        background=[("active", "#5eead4")]
    )

    style.configure(
        "Secondary.TButton",
        background=SURFACE_LIGHT,
        foreground=TEXT,
        borderwidth=0,
        padding=(12, 8)
    )

    style.map(
        "Secondary.TButton",
        background=[("active", "#334155")]
    )

    style.configure(
        "Dark.TEntry",
        fieldbackground=SURFACE_LIGHT,
        foreground=TEXT,
        insertcolor=TEXT,
        borderwidth=0,
        padding=7
    )

    style.configure(
        "Dark.Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        rowheight=28,
        borderwidth=0
    )

    style.configure(
        "Dark.Treeview.Heading",
        background=SURFACE_LIGHT,
        foreground=MUTED,
        relief="flat",
        font=("Segoe UI", 9, "bold")
    )

    style.map(
        "Dark.Treeview",
        background=[("selected", ACCENT_DARK)],
        foreground=[("selected", "white")]
    )


class LoginApp(tk.Tk):

    def __init__(self, on_success) -> None:
        super().__init__()

        configure_styles()

        self.on_success = on_success

        self.title("Login - Smart Attendance System")
        self.geometry("420x300")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.status = tk.StringVar()

        self._build_ui()

        self.bind(
            "<Return>",
            lambda _event: self.login()
        )

    def _build_ui(self) -> None:

        container = ttk.Frame(
            self,
            padding=30,
            style="Card.TFrame"
        )

        container.pack(
            fill="both",
            expand=True
        )

        tk.Label(
            container,
            text="SMART ATTENDANCE",
            background=SURFACE,
            foreground=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(8, 5))

        tk.Label(
            container,
            text="Secure access to your classroom records",
            background=SURFACE,
            foreground=MUTED
        ).pack(pady=(0, 22))

        form = ttk.Frame(
            container,
            style="Card.TFrame"
        )

        form.pack(fill="x")

        ttk.Label(
            form,
            text="USERNAME",
            style="Field.TLabel"
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=7
        )

        ttk.Entry(
            form,
            textvariable=self.username,
            width=30,
            style="Dark.TEntry"
        ).grid(
            row=0,
            column=1,
            padx=(15, 0),
            pady=7
        )

        ttk.Label(
            form,
            text="PASSWORD",
            style="Field.TLabel"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=7
        )

        ttk.Entry(
            form,
            textvariable=self.password,
            show="*",
            width=30,
            style="Dark.TEntry"
        ).grid(
            row=1,
            column=1,
            padx=(15, 0),
            pady=7
        )

        tk.Button(
            container,
            text="Sign in",
            command=self.login,
            background=ACCENT,
            foreground=BG,
            border=0,
            font=("Segoe UI", 9, "bold")
        ).pack(
            pady=(18, 5),
            ipadx=35
        )

        tk.Label(
            container,
            textvariable=self.status,
            background=SURFACE,
            foreground=ERROR
        ).pack()

    def login(self) -> None:

        expected_username = os.getenv(
            "SMART_ATTENDANCE_USERNAME",
            "admin"
        )

        expected_password = os.getenv(
            "SMART_ATTENDANCE_PASSWORD",
            "admin123"
        )

        if (
            self.username.get() == expected_username
            and
            self.password.get() == expected_password
        ):

            self.destroy()
            self.on_success()

        else:

            self.status.set(
                "Invalid username or password"
            )

            self.password.set("")


class AttendanceApp(tk.Tk):

    def __init__(self) -> None:

        super().__init__()

        configure_styles()

        self.title(
            "Smart Attendance System"
        )

        self.geometry(
            "1200x780"
        )

        self.resizable(
            False,
            False
        )

        self.configure(
            bg=BG
        )

        self.all_attendance = []
        self.all_reports = []

        self.search_text = tk.StringVar()
        self.search_date = tk.StringVar()

        self._build_ui()

        self.refresh()

    def _build_ui(self) -> None:

        header = ttk.Frame(
            self,
            style="App.TFrame"
        )

        header.pack(
            fill="x",
            padx=24,
            pady=(22, 8)
        )

        ttk.Label(
            header,
            text="Attendance Command Center",
            style="Title.TLabel"
        ).pack(
            anchor="w"
        )

        ttk.Label(
            header,
            text="Register faces, verify presence, and monitor participation.",
            style="Subtitle.TLabel"
        ).pack(
            anchor="w",
            pady=(3, 0)
        )

        self.create_dashboard_cards()

        self.create_registration()

        self.create_actions()

        self.create_search()

        self.create_attendance_table()

        self.create_report_table()

    def create_dashboard_cards(self):

        cards = ttk.Frame(
            self,
            style="App.TFrame"
        )

        cards.pack(
            fill="x",
            padx=20,
            pady=8
        )

        self.total_label = self.create_card(
            cards,
            "TOTAL STUDENTS",
            "0"
        )

        self.present_label = self.create_card(
            cards,
            "ATTENDANCE RECORDS",
            "0"
        )

        self.absent_label = self.create_card(
            cards,
            "ABSENT RECORDS",
            "0"
        )

        self.average_label = self.create_card(
            cards,
            "AVERAGE ATTENDANCE",
            "0%"
        )

    def create_card(
        self,
        parent,
        title,
        value
    ):

        card = tk.Frame(
            parent,
            bg=SURFACE,
            width=260,
            height=80
        )

        card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=5
        )

        card.pack_propagate(False)

        tk.Label(
            card,
            text=title,
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(10, 0)
        )

        label = tk.Label(
            card,
            text=value,
            bg=SURFACE,
            fg=ACCENT,
            font=("Segoe UI", 18, "bold")
        )

        label.pack(
            anchor="w",
            padx=15
        )

        return label

    def create_registration(self):

        form = ttk.LabelFrame(
            self,
            text="  REGISTER STUDENT  "
        )

        form.pack(
            fill="x",
            padx=20,
            pady=8
        )

        self.name = tk.StringVar()
        self.email = tk.StringVar()
        self.department = tk.StringVar()
        self.year = tk.StringVar()

        ttk.Label(
            form,
            text="Name",
            style="Field.TLabel"
        ).grid(
            row=0,
            column=0,
            padx=8,
            pady=10
        )

        ttk.Entry(
            form,
            textvariable=self.name,
            width=24,
            style="Dark.TEntry"
        ).grid(
            row=0,
            column=1,
            padx=8
        )

        ttk.Label(
            form,
            text="Email",
            style="Field.TLabel"
        ).grid(
            row=0,
            column=2,
            padx=8
        )

        ttk.Entry(
            form,
            textvariable=self.email,
            width=24,
            style="Dark.TEntry"
        ).grid(
            row=0,
            column=3,
            padx=8
        )

        ttk.Label(
            form,
            text="Department",
            style="Field.TLabel"
        ).grid(
            row=1,
            column=0,
            padx=8,
            pady=10
        )

        ttk.Entry(
            form,
            textvariable=self.department,
            width=24,
            style="Dark.TEntry"
        ).grid(
            row=1,
            column=1,
            padx=8
        )

        ttk.Label(
            form,
            text="Year",
            style="Field.TLabel"
        ).grid(
            row=1,
            column=2,
            padx=8
        )

        ttk.Entry(
            form,
            textvariable=self.year,
            width=24,
            style="Dark.TEntry"
        ).grid(
            row=1,
            column=3,
            padx=8
        )

        ttk.Button(
            form,
            text="Capture Face",
            command=self.register,
            style="Accent.TButton"
        ).grid(
            row=1,
            column=4,
            padx=12
        )

    def create_actions(self):

        actions = ttk.Frame(
            self,
            style="App.TFrame"
        )

        actions.pack(
            fill="x",
            padx=20,
            pady=8
        )

        ttk.Button(
            actions,
            text="Start Live Attendance",
            command=self.start_attendance,
            style="Accent.TButton"
        ).pack(
            side="left"
        )

        ttk.Button(
            actions,
            text="Refresh Data",
            command=self.refresh,
            style="Secondary.TButton"
        ).pack(
            side="left",
            padx=8
        )

        ttk.Button(
            actions,
            text="Export CSV",
            command=self.export_csv,
            style="Secondary.TButton"
        ).pack(
            side="right"
        )

    def create_search(self):

        search_frame = ttk.Frame(
            self,
            style="App.TFrame"
        )

        search_frame.pack(
            fill="x",
            padx=20,
            pady=(5, 8)
        )

        ttk.Label(
            search_frame,
            text="Search:",
            style="CardTitle.TLabel"
        ).pack(
            side="left"
        )

        ttk.Entry(
            search_frame,
            textvariable=self.search_text,
            width=30,
            style="Dark.TEntry"
        ).pack(
            side="left",
            padx=8
        )

        ttk.Button(
            search_frame,
            text="Search",
            command=self.search_records,
            style="Secondary.TButton"
        ).pack(
            side="left"
        )

        ttk.Button(
            search_frame,
            text="Clear",
            command=self.clear_search,
            style="Secondary.TButton"
        ).pack(
            side="left",
            padx=5
        )

    def create_attendance_table(self):

        ttk.Label(
            self,
            text="Attendance Records",
            style="CardTitle.TLabel"
        ).pack(
            anchor="w",
            padx=20,
            pady=(4, 2)
        )

        columns = (
            "student_id",
            "name",
            "department",
            "year",
            "email",
            "date",
            "time",
            "period"
        )

        self.table = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=8,
            style="Dark.Treeview"
        )

        headings = (
            "Student ID",
            "Name",
            "Department",
            "Year",
            "Email",
            "Date",
            "Time",
            "Period"
        )

        widths = (
            75,
            140,
            120,
            60,
            180,
            95,
            85,
            100
        )

        for column, heading, width in zip(
            columns,
            headings,
            widths
        ):

            self.table.heading(
                column,
                text=heading
            )

            self.table.column(
                column,
                width=width
            )

        self.table.pack(
            fill="x",
            padx=20
        )

    def create_report_table(self):

        ttk.Label(
            self,
            text="Attendance Health",
            style="CardTitle.TLabel"
        ).pack(
            anchor="w",
            padx=20,
            pady=(8, 2)
        )

        columns = (
            "student_id",
            "student",
            "department",
            "year",
            "present",
            "absent",
            "total",
            "percentage"
        )

        self.report = ttk.Treeview(
            self,
            columns=columns,
            show="headings",
            height=4,
            style="Dark.Treeview"
        )

        headings = (
            "ID",
            "Student",
            "Department",
            "Year",
            "Present Days",
            "Absent Days",
            "Recorded Days",
            "Percentage"
        )

        widths = (
            55,
            150,
            120,
            60,
            95,
            95,
            105,
            100
        )

        for column, heading, width in zip(
            columns,
            headings,
            widths
        ):

            self.report.heading(
                column,
                text=heading
            )

            self.report.column(
                column,
                width=width
            )

        self.report.pack(
            fill="x",
            padx=20,
            pady=(0, 15)
        )

    def register(self):

        try:

            if not self.name.get().strip():
                messagebox.showwarning(
                    "Input Required",
                    "Please enter student name."
                )
                return

            capture_student(
                self.name.get(),
                self.email.get(),
                self.department.get(),
                self.year.get()
            )

            self.name.set("")
            self.email.set("")
            self.department.set("")
            self.year.set("")

            messagebox.showinfo(
                "Registered",
                "Face captured and model trained successfully."
            )

            self.refresh()

        except Exception as error:

            messagebox.showerror(
                "Registration Failed",
                str(error)
            )

    def start_attendance(self):

        try:

            run_attendance()

            self.refresh()

            messagebox.showinfo(
                "Attendance",
                "Attendance session completed."
            )

        except Exception as error:

            messagebox.showerror(
                "Attendance Failed",
                str(error)
            )

    def refresh(self):

        try:

            self.all_attendance = list(
                get_attendance()
            )

            self.all_reports = list(
                get_attendance_report()
            )

            self.display_attendance(
                self.all_attendance
            )

            self.display_reports(
                self.all_reports
            )

            self.update_statistics()

        except Exception as error:

            messagebox.showerror(
                "Database Error",
                str(error)
            )

    def display_attendance(self, records):

        for item in self.table.get_children():

            self.table.delete(item)

        for row in records:

            attended_at = row["attended_at"]

            if "T" in attended_at:

                attended_time = attended_at.split("T")[-1]

            else:

                attended_time = attended_at

            self.table.insert(
                "",
                "end",
                values=(
                    row["student_id"],
                    row["name"],
                    row["department"],
                    row["year"],
                    row["email"],
                    row["attended_on"],
                    attended_time,
                    row["period"]
                )
            )

    def display_reports(self, reports):

        for item in self.report.get_children():

            self.report.delete(item)

        for row in reports:

            self.report.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["name"],
                    row["department"],
                    row["year"],
                    row["present_days"],
                    row["absent_days"],
                    row["total_days"],
                    f'{row["percentage"]:.2f}%'
                )
            )

    def update_statistics(self):

        total_students = len(
            self.all_reports
        )

        total_records = len(
            self.all_attendance
        )

        total_present = 0
        total_absent = 0

        for row in self.all_reports:

            total_present += int(
                row["present_days"]
            )

            total_absent += int(
                row["absent_days"]
            )

        total_days = (
            total_present +
            total_absent
        )

        if total_days > 0:

            average = (
                total_present /
                total_days
            ) * 100

        else:

            average = 0

        self.total_label.config(
            text=str(total_students)
        )

        self.present_label.config(
            text=str(total_records)
        )

        self.absent_label.config(
            text=str(total_absent)
        )

        self.average_label.config(
            text=f"{average:.2f}%"
        )

    def search_records(self):

        search = (
            self.search_text
            .get()
            .strip()
            .lower()
        )

        if not search:

            self.display_attendance(
                self.all_attendance
            )

            return

        filtered = []

        for row in self.all_attendance:

            values = [
                str(row["student_id"]),
                str(row["name"]),
                str(row["department"]),
                str(row["year"]),
                str(row["email"]),
                str(row["attended_on"]),
                str(row["period"])
            ]

            text = " ".join(values).lower()

            if search in text:

                filtered.append(row)

        self.display_attendance(
            filtered
        )

    def clear_search(self):

        self.search_text.set("")

        self.display_attendance(
            self.all_attendance
        )

    def export_csv(self):

        if not self.all_attendance:

            messagebox.showwarning(
                "No Data",
                "There is no attendance data to export."
            )

            return

        file_path = filedialog.asksaveasfilename(
            title="Save Attendance Report",
            defaultextension=".csv",
            filetypes=[
                ("CSV Files", "*.csv")
            ]
        )

        if not file_path:

            return

        try:

            with open(
                file_path,
                "w",
                newline="",
                encoding="utf-8"
            ) as file:

                writer = csv.writer(file)

                writer.writerow([
                    "Student ID",
                    "Name",
                    "Department",
                    "Year",
                    "Email",
                    "Date",
                    "Time",
                    "Period"
                ])

                for row in self.all_attendance:

                    attended_at = row["attended_at"]

                    if "T" in attended_at:

                        attended_time = (
                            attended_at.split("T")[-1]
                        )

                    else:

                        attended_time = attended_at

                    writer.writerow([
                        row["student_id"],
                        row["name"],
                        row["department"],
                        row["year"],
                        row["email"],
                        row["attended_on"],
                        attended_time,
                        row["period"]
                    ])

            messagebox.showinfo(
                "Export Complete",
                "Attendance report exported successfully."
            )

        except Exception as error:

            messagebox.showerror(
                "Export Failed",
                str(error)
            )


def launch():

    def open_dashboard():

        AttendanceApp().mainloop()

    LoginApp(
        open_dashboard
    ).mainloop()


if __name__ == "__main__":

    launch()
    