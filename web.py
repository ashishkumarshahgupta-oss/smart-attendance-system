from __future__ import annotations

import base64
import os
from functools import wraps
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from database import authenticate_user, change_password, create_user, current_period, get_attendance, get_attendance_report, get_students, get_users, mark_attendance, set_attendance
from database import add_student
from register import DATASET_DIR, FACE_CASCADE, MODEL_PATH, train_model


app = Flask(__name__)
app.secret_key = os.getenv("SMART_ATTENDANCE_SECRET", "change-this-local-secret")


def login_required(function):
	@wraps(function)
	def wrapped(*args, **kwargs):
		if not session.get("logged_in"):
			return redirect(url_for("login"))
		return function(*args, **kwargs)
	return wrapped


def role_required(role: str):
	def decorator(function):
		@wraps(function)
		def wrapped(*args, **kwargs):
			if not session.get("logged_in"):
				return redirect(url_for("login"))
			if session.get("role") != role:
				abort(403)
			return function(*args, **kwargs)
		return wrapped
	return decorator


def decode_image(payload: str) -> np.ndarray:
	encoded = payload.split(",", 1)[-1]
	image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_GRAYSCALE)
	if image is None:
		raise ValueError("Invalid camera image.")
	return image


def largest_face(image: np.ndarray) -> np.ndarray | None:
	cascade = cv2.CascadeClassifier(str(FACE_CASCADE))
	faces = cascade.detectMultiScale(image, 1.2, 5, minSize=(100, 100))
	if len(faces) == 0:
		return None
	x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
	return image[y : y + height, x : x + width]


@app.route("/login", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		role = request.form.get("role")
		user = authenticate_user(request.form.get("username", ""), request.form.get("password", ""))
		if user and user["role"] == role:
			session["logged_in"] = True
			session["role"] = role
			session["username"] = user["username"]
			return redirect(url_for("admin_page" if role == "teacher" else "student_page"))
		return render_template("login.html", error="Invalid username or password")
	return render_template("login.html")


@app.get("/logout")
def logout():
	session.clear()
	return redirect(url_for("login"))


@app.get("/")
def dashboard():
	if not session.get("logged_in"):
		return redirect(url_for("login"))
	return redirect(url_for("admin_page" if session.get("role") == "teacher" else "student_page"))


@app.get("/student")
@role_required("student")
def student_page():
	return render_template("index.html", records=get_attendance(), report=get_attendance_report())


@app.get("/admin")
@role_required("teacher")
def admin_page():
	return render_template("admin.html", students=get_students(), records=get_attendance(), users=get_users())


@app.post("/api/register")
@role_required("student")
def register():
	data = request.get_json(silent=True) or {}
	try:
		student_id = add_student(data.get("name", ""), data.get("email", ""), data.get("department", ""), data.get("year", ""))
		return jsonify({"student_id": student_id})
	except Exception as error:
		return jsonify({"error": str(error)}), 400


@app.post("/api/capture/<int:student_id>")
@role_required("student")
def capture(student_id: int):
	data = request.get_json(silent=True) or {}
	try:
		image = largest_face(decode_image(data.get("image", "")))
		if image is None:
			return jsonify({"captured": False, "message": "No face detected."})
		DATASET_DIR.mkdir(exist_ok=True)
		files = list(DATASET_DIR.glob(f"{student_id}_*.jpg"))
		path = DATASET_DIR / f"{student_id}_{len(files)}.jpg"
		cv2.imwrite(str(path), image)
		count = len(files) + 1
		if count >= 5:
			train_model()
		return jsonify({"captured": True, "count": count, "ready": count >= 5})
	except Exception as error:
		return jsonify({"error": str(error)}), 400


@app.post("/api/recognize")
@role_required("student")
def recognize():
	if not MODEL_PATH.exists() or not hasattr(cv2, "face"):
		return jsonify({"error": "Capture and train at least one student first."}), 400
	try:
		image = largest_face(decode_image((request.get_json(silent=True) or {}).get("image", "")))
		if image is None:
			return jsonify({"recognized": False, "message": "No face detected."})
		recognizer = cv2.face.LBPHFaceRecognizer_create()
		recognizer.read(str(MODEL_PATH))
		student_id, confidence = recognizer.predict(image)
		students = {student["id"]: student for student in get_students()}
		student = students.get(student_id)
		if not student or confidence > 75:
			return jsonify({"recognized": False, "message": "Face not recognized."})
		marked = mark_attendance(student_id, current_period())
		return jsonify({"recognized": True, "name": student["name"], "marked": marked, "period": current_period()})
	except Exception as error:
		return jsonify({"error": str(error)}), 400


@app.get("/api/data")
@role_required("student")
def data():
	return jsonify({"records": get_attendance(), "report": get_attendance_report()})


@app.post("/api/admin/attendance")
@role_required("teacher")
def admin_attendance():
	data = request.get_json(silent=True) or {}
	try:
		set_attendance(int(data["student_id"]), data["date"], data["time"], data["period"], data["status"])
		return jsonify({"message": f"Attendance updated as {data['status']}."})
	except (KeyError, TypeError, ValueError) as error:
		return jsonify({"error": str(error)}), 400


@app.post("/api/admin/users")
@role_required("teacher")
def admin_users():
	data = request.get_json(silent=True) or {}
	try:
		user_id = create_user(
			data["username"], data["password"], data["role"], data.get("name", ""),
			data.get("email", ""), data.get("department", ""), data.get("year", ""),
		)
		return jsonify({"user_id": user_id, "message": "User account created."})
	except (KeyError, TypeError, ValueError) as error:
		return jsonify({"error": str(error)}), 400
	except Exception:
		return jsonify({"error": "Username already exists."}), 409


@app.post("/api/admin/change-password")
@role_required("teacher")
def admin_change_password():
	data = request.get_json(silent=True) or {}
	try:
		change_password(session["username"], data["current_password"], data["new_password"])
		return jsonify({"message": "Password changed successfully."})
	except (KeyError, TypeError, ValueError) as error:
		return jsonify({"error": str(error)}), 400


@app.post("/api/change-password")
@role_required("student")
def student_change_password():
	data = request.get_json(silent=True) or {}
	try:
		change_password(session["username"], data["current_password"], data["new_password"])
		return jsonify({"message": "Password changed successfully."})
	except (KeyError, TypeError, ValueError) as error:
		return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
	app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
