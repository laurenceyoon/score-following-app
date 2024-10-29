import asyncio
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from .position_manager import position_manager
from .utils import get_audio_devices, preprocess_score, run_score_following


@asynccontextmanager
async def lifespan(app: FastAPI):
    upload_dir = Path("./uploads")
    # Clean up at the start
    if upload_dir.exists() and upload_dir.is_dir():
        for file in upload_dir.iterdir():
            if file.is_file():
                file.unlink()
    yield
    # Clean up at the end
    if upload_dir.exists() and upload_dir.is_dir():
        for file in upload_dir.iterdir():
            if file.is_file():
                file.unlink()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:50003", "http://127.0.0.1:50003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
executor = ThreadPoolExecutor(max_workers=1)


# ================== API ==================
@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/audio-devices")
async def audio_devices():
    devices = get_audio_devices()
    return {"devices": devices}


@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())[:8]
    upload_dir = Path("./uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{file_id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    preprocess_score(file_path)
    return {"file_id": file_id}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    data = await websocket.receive_json()  # data: {"onset_beats": [0.5, 1, 1.5, ...]}
    file_id = data["file_id"]
    print(f"Received data: {data}, file_id: {file_id}")

    # Run score following in a separate thread (as a background task)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, run_score_following, file_id)

    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            current_position = position_manager.get_position(file_id)
            print(
                f"[{datetime.now().strftime('%H:%M:%S.%f')}] Current position: {current_position}"
            )

            await websocket.send_json({"beat_position": current_position})
            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"Websocket send data error: {e}, {type(e)}")
        position_manager.reset()
        return
