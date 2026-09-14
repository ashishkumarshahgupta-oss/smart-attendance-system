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
