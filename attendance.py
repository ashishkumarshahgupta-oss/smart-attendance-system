from __future__ import annotations

from pathlib import Path

import cv2

from database import current_period, get_students, mark_attendance


DATASET_DIR = Path(__file__).with_name("dataset")
MODEL_PATH = DATASET_DIR / "face_model.yml"
FACE_CASCADE = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"


def run_attendance(confidence_limit: float = 75.0) -> None:
	if not MODEL_PATH.exists() or not hasattr(cv2, "face"):
		raise RuntimeError("Train the face model first and install opencv-contrib-python.")
	students = {student["id"]: student for student in get_students()}
	recognizer = cv2.face.LBPHFaceRecognizer_create()
	recognizer.read(str(MODEL_PATH))
	cascade = cv2.CascadeClassifier(str(FACE_CASCADE))
	camera = cv2.VideoCapture(0)
	if not camera.isOpened():
		raise RuntimeError("Could not open the camera.")
	try:
		while True:
			success, frame = camera.read()
			if not success:
				continue
			gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
			for x, y, width, height in cascade.detectMultiScale(gray, 1.2, 5, minSize=(100, 100)):
				student_id, confidence = recognizer.predict(gray[y : y + height, x : x + width])
				known = students.get(student_id)
				recognized = known and confidence <= confidence_limit
				label = known["name"] if recognized else "Unknown"
				if recognized:
					mark_attendance(student_id, current_period())
				color = (0, 220, 0) if recognized else (0, 0, 220)
				cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
				cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
			cv2.putText(frame, "Q or Esc to close", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
			cv2.imshow("Smart attendance", frame)
			if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
				break
	finally:
		camera.release()
		cv2.destroyAllWindows()
