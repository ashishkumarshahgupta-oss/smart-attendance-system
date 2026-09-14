from __future__ import annotations

import csv
from pathlib import Path

import cv2

from database import add_student


DATASET_DIR = Path(__file__).with_name("dataset")
MODEL_PATH = DATASET_DIR / "face_model.yml"
LABELS_PATH = DATASET_DIR / "labels.csv"
FACE_CASCADE = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"


def capture_student(name: str, email: str, department: str, year: str, samples: int = 25) -> int:
	student_id = add_student(name, email, department, year)
	DATASET_DIR.mkdir(exist_ok=True)
	cascade = cv2.CascadeClassifier(str(FACE_CASCADE))
	camera = cv2.VideoCapture(0)
	if not camera.isOpened():
		raise RuntimeError("Could not open the camera.")

	captured = 0
	try:
		while captured < samples:
			success, frame = camera.read()
			if not success:
				continue
			gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
			faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(100, 100))
			for x, y, width, height in faces:
				image = gray[y : y + height, x : x + width]
				cv2.imwrite(str(DATASET_DIR / f"{student_id}_{captured}.jpg"), image)
				captured += 1
				cv2.rectangle(frame, (x, y), (x + width, y + height), (0, 220, 0), 2)
				break
			cv2.putText(frame, f"Samples: {captured}/{samples} | Q to stop", (10, 30),
						cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 0), 2)
			cv2.imshow("Register student", frame)
			if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
				break
	finally:
		camera.release()
		cv2.destroyAllWindows()

	if captured == 0:
		raise RuntimeError("No face samples were captured.")
	train_model()
	return student_id


def train_model() -> None:
	if not hasattr(cv2, "face"):
		raise RuntimeError("Install opencv-contrib-python to enable face recognition.")
	images, labels = [], []
	for image_path in DATASET_DIR.glob("*.jpg"):
		try:
			label = int(image_path.stem.split("_")[0])
		except ValueError:
			continue
		image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
		if image is not None:
			images.append(image)
			labels.append(label)
	if not images:
		raise RuntimeError("Capture at least one face before training.")
	recognizer = cv2.face.LBPHFaceRecognizer_create()
	recognizer.train(images, labels)
	recognizer.write(str(MODEL_PATH))
	with LABELS_PATH.open("w", newline="", encoding="utf-8") as file:
		writer = csv.writer(file)
		writer.writerow(["id", "name"])
		from database import get_students
		writer.writerows((student["id"], student["name"]) for student in get_students())
