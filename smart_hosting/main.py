import logging
import os
from io import BytesIO
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.logger import logger as fastapi_logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from werkzeug.utils import secure_filename

fastapi_logger.setLevel(logging.DEBUG)

# Initialize the FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the upload folder and allowed file extensions
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads/")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "mp3", "wav", "ogg", "m4a", "aac"}

def is_image_file(filename: str) -> bool:
    """Check if the file is an image based on its extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "gif"}
# Mount the upload folder for serving static files
app.mount("/files", StaticFiles(directory=UPLOAD_FOLDER), name="files")

class URLUpload(BaseModel):
    url: str
    compress: Optional[bool] = True


# Function to check allowed file extensions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def compress_image(image_path: str) -> None:
    # Open the image file
    with Image.open(image_path) as img:
        # Resize image to 640x640 without changing quality
        img_resized = img.resize((640, 640), Image.LANCZOS)
        # Save the resized image
        img_resized.save(image_path, "JPEG", quality=100, optimize=True)


@app.post("/api/files/index")
async def upload_from_url(data: URLUpload):
    url = data.url
    compress = data.compress

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url)
            if response.status_code == 200:
                filename = secure_filename(f"{url.split('=')[-1]}.jpg")
                filepath = os.path.join(UPLOAD_FOLDER, filename)

                
                image_bytes = await response.aread()
                image = Image.open(BytesIO(image_bytes))

                # Convert RGBA to RGB if needed
                if image.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])  # use alpha mask
                    image = background
                else:
                    image = image.convert("RGB")

                # Save as JPEG
                image.save(filepath, "JPEG")

                # Compress the image if necessary
                if compress:
                    compress_image(filepath)

                return {"message": "File uploaded successfully", "filename": filename}
            else:
                raise HTTPException(
                    status_code=400, detail="Failed to fetch image from URL"
                )
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@app.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...), compress=Query(False)):
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Invalid file type")

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as f:
        f.write(await file.read())

    # Compress the image if necessary
    if compress and is_image_file(filename):
        compress_image(filepath)

    return {"message": "File uploaded successfully", "filename": filename}


@app.get("/api/files/{filename}")
async def get_file(filename: str):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)


@app.get("/api/")
async def get_home():
    return {"message": "Home"}
