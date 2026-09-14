from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

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


def configure_styles() -> None:
	style = ttk.Style()
	style.theme_use("clam")
	style.configure("App.TFrame", background=BG)
	style.configure("Card.TFrame", background=SURFACE)
	style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 22, "bold"))
	style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
	style.configure("CardTitle.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 12, "bold"))
	style.configure("Field.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9, "bold"))
	style.configure("Accent.TButton", background=ACCENT, foreground=BG, borderwidth=0, padding=(14, 9), font=("Segoe UI", 9, "bold"))
	style.map("Accent.TButton", background=[("active", "#5eead4")])
	style.configure("Secondary.TButton", background=SURFACE_LIGHT, foreground=TEXT, borderwidth=0, padding=(12, 8))
	style.map("Secondary.TButton", background=[("active", "#334155")])
	style.configure("Dark.TEntry", fieldbackground=SURFACE_LIGHT, foreground=TEXT, insertcolor=TEXT, borderwidth=0, padding=7)
	style.configure("Dark.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=28, borderwidth=0)
	style.configure("Dark.Treeview.Heading", background=SURFACE_LIGHT, foreground=MUTED, relief="flat", font=("Segoe UI", 9, "bold"))
	style.map("Dark.Treeview", background=[("selected", ACCENT_DARK)], foreground=[("selected", "white")])


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
		self.bind("<Return>", lambda _event: self.login())

	def _build_ui(self) -> None:
		container = ttk.Frame(self, padding=30, style="Card.TFrame")
		container.pack(fill="both", expand=True)
		tk.Label(container, text="SMART ATTENDANCE", background=SURFACE, foreground=TEXT, font=("Segoe UI", 18, "bold")).pack(pady=(8, 5))
		tk.Label(container, text="Secure access to your classroom records", background=SURFACE, foreground=MUTED).pack(pady=(0, 22))
		form = ttk.Frame(container, style="Card.TFrame")
		form.pack(fill="x")
		ttk.Label(form, text="USERNAME", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=7)
		ttk.Entry(form, textvariable=self.username, width=30, style="Dark.TEntry").grid(row=0, column=1, padx=(15, 0), pady=7)
		ttk.Label(form, text="PASSWORD", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=7)
		ttk.Entry(form, textvariable=self.password, show="*", width=30, style="Dark.TEntry").grid(row=1, column=1, padx=(15, 0), pady=7)
		tk.Button(container, text="Sign in", command=self.login, style="Accent.TButton").pack(pady=(18, 5), ipadx=35)
		tk.Label(container, textvariable=self.status, background=SURFACE, foreground=ERROR).pack()

	def login(self) -> None:
		expected_username = os.getenv("SMART_ATTENDANCE_USERNAME", "admin")
		expected_password = os.getenv("SMART_ATTENDANCE_PASSWORD", "admin123")
		if self.username.get() == expected_username and self.password.get() == expected_password:
			self.destroy()
			self.on_success()
		else:
			self.status.set("Invalid username or password")
			self.password.set("")


class AttendanceApp(tk.Tk):
	def __init__(self) -> None:
		super().__init__()
		configure_styles()
		self.title("Smart Attendance System")
		self.geometry("1120x700")
		self.resizable(False, False)
		self.configure(bg=BG)
		self._build_ui()
		self.refresh()

	def _build_ui(self) -> None:
		header = ttk.Frame(self, style="App.TFrame")
		header.pack(fill="x", padx=24, pady=(22, 8))
		ttk.Label(header, text="Attendance command center", style="Title.TLabel").pack(anchor="w")
		ttk.Label(header, text="Register faces, verify presence, and monitor participation.", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
		form = ttk.LabelFrame(self, text="  REGISTER STUDENT  ")
		form.pack(fill="x", padx=20, pady=8)
		self.name = tk.StringVar()
		self.email = tk.StringVar()
		self.department = tk.StringVar()
		self.year = tk.StringVar()
		ttk.Label(form, text="Name", style="Field.TLabel").grid(row=0, column=0, padx=8, pady=10)
		ttk.Entry(form, textvariable=self.name, width=28, style="Dark.TEntry").grid(row=0, column=1, padx=8)
		ttk.Label(form, text="Email", style="Field.TLabel").grid(row=0, column=2, padx=8)
		ttk.Entry(form, textvariable=self.email, width=28, style="Dark.TEntry").grid(row=0, column=3, padx=8)
		ttk.Label(form, text="Department", style="Field.TLabel").grid(row=1, column=0, padx=8, pady=10)
		ttk.Entry(form, textvariable=self.department, width=28, style="Dark.TEntry").grid(row=1, column=1, padx=8)
		ttk.Label(form, text="Year", style="Field.TLabel").grid(row=1, column=2, padx=8)
		ttk.Entry(form, textvariable=self.year, width=28, style="Dark.TEntry").grid(row=1, column=3, padx=8)
		ttk.Button(form, text="Capture face", command=self.register, style="Accent.TButton").grid(row=1, column=4, padx=12)
		actions = ttk.Frame(self, style="App.TFrame")
		actions.pack(fill="x", padx=20, pady=8)
		ttk.Button(actions, text="Start live attendance", command=self.start_attendance, style="Accent.TButton").pack(side="left")
		ttk.Button(actions, text="Refresh data", command=self.refresh, style="Secondary.TButton").pack(side="right")
		ttk.Label(self, text="Attendance records", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(8, 2))
		columns = ("student_id", "name", "department", "year", "email", "date", "time", "period")
		self.table = ttk.Treeview(self, columns=columns, show="headings", height=10, style="Dark.Treeview")
		for column, heading, width in zip(columns, ("Student ID", "Name", "Department", "Year", "Email", "Date", "Time", "Hours period"), (75, 140, 120, 60, 190, 95, 85, 110)):
			self.table.heading(column, text=heading)
			self.table.column(column, width=width)
		self.table.pack(fill="both", expand=True, padx=20, pady=(0, 20))
		ttk.Label(self, text="Attendance health", style="CardTitle.TLabel").pack(anchor="w", padx=20, pady=(0, 2))
		report_columns = ("student_id", "student", "department", "year", "present", "absent", "total", "percentage")
		self.report = ttk.Treeview(self, columns=report_columns, show="headings", height=5, style="Dark.Treeview")
		for column, heading, width in zip(report_columns, ("ID", "Student", "Department", "Year", "Present days", "Absent days", "Recorded days", "Percentage"), (55, 150, 120, 60, 95, 95, 105, 100)):
			self.report.heading(column, text=heading)
			self.report.column(column, width=width)
		self.report.pack(fill="x", padx=20, pady=(0, 20))

	def register(self) -> None:
		try:
			capture_student(self.name.get(), self.email.get(), self.department.get(), self.year.get())
			self.name.set("")
			self.email.set("")
			self.department.set("")
			self.year.set("")
			messagebox.showinfo("Registered", "Face captured and model trained.")
			self.refresh()
		except Exception as error:
			messagebox.showerror("Registration failed", str(error))

	def start_attendance(self) -> None:
		try:
			run_attendance()
			self.refresh()
		except Exception as error:
			messagebox.showerror("Attendance failed", str(error))

	def refresh(self) -> None:
		for item in self.table.get_children():
			self.table.delete(item)
		for item in self.report.get_children():
			self.report.delete(item)
		for row in get_attendance():
			self.table.insert("", "end", values=(row["student_id"], row["name"], row["department"], row["year"], row["email"], row["attended_on"], row["attended_at"].split("T")[-1], row["period"]))
		for row in get_attendance_report():
			self.report.insert("", "end", values=(row["id"], row["name"], row["department"], row["year"], row["present_days"], row["absent_days"], row["total_days"], f'{row["percentage"]:.2f}%'))


def launch() -> None:
	def open_dashboard() -> None:
		AttendanceApp().mainloop()

	LoginApp(open_dashboard).mainloop()
