from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, File, UploadFile

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = PROJECT_ROOT / "uploads"


@router.post("/upload/video")
async def upload_video(video: UploadFile = File(...)):
	session_id = str(uuid4())
	original_filename = Path(video.filename).name
	saved_filename = f"{session_id}_{original_filename}"
	saved_path = UPLOAD_DIR / saved_filename

	UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

	async with aiofiles.open(saved_path, "wb") as output_file:
		while True:
			chunk = await video.read(1024 * 1024)
			if not chunk:
				break
			await output_file.write(chunk)

	await video.close()

	return {
		"session_id": session_id,
		"video_path": str(saved_path),
	}
