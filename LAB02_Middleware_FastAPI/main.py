import os
import json
import threading
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- plik bazy danych ---
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
LOCK = threading.Lock()

def _ensure_db():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"users": [], "next_id": 1}, f, ensure_ascii=False, indent=2)

def load_db():
    _ensure_db()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

# --- konfiguracja ustawień i API_KEY ---
class Settings(BaseSettings):
    API_KEY: str = "secret"
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
API_KEY = settings.API_KEY

# --- modele Pydantic dla użytkowników ---
class UserIn(BaseModel):
    username: str
    email: str
    age: int

class UserOut(UserIn):
    id: int

# --- inicjalizacja FastAPI ---
app = FastAPI(
    title="LAB02 - FastAPI CRUD /users",
    description="CORS + X-Process-Time + CRUD /users w data.json. Admin endpoint z X-API-Key.",
    version="0.1.0",
)

# --- middleware CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- middleware X-Process-Time ---
@app.middleware("http")
async def timing_header(request: Request, call_next):
    import time
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
    return response

# --- middleware admin guard ---
@app.middleware("http")
async def admin_guard(request: Request, call_next):
    if request.url.path.startswith("/admin/"):
        provided = request.headers.get("X-API-Key")
        if provided != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized (missing/invalid X-API-Key)"})
    return await call_next(request)

# --- endpointy zdrowia i admin ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/admin/secret")
def admin_secret():
    return {"ok": True, "msg": "Welcome, admin."}

# --- CRUD /users ---
@app.get("/users", response_model=List[UserOut])
def list_users():
    db = load_db()
    return db["users"]

@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int):
    db = load_db()
    for u in db["users"]:
        if u["id"] == user_id:
            return u
    raise HTTPException(status_code=404, detail="User not found")

@app.post("/users", response_model=UserOut, status_code=201)
def create_user(user: UserIn):
    with LOCK:
        db = load_db()
        new_id = db.get("next_id", 1)
        rec = {"id": new_id, **user.dict()}
        db["users"].append(rec)
        db["next_id"] = new_id + 1
        save_db(db)
        return rec

@app.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user: UserIn):
    with LOCK:
        db = load_db()
        for i, u in enumerate(db["users"]):
            if u["id"] == user_id:
                updated = {"id": user_id, **user.dict()}
                db["users"][i] = updated
                save_db(db)
                return updated
    raise HTTPException(status_code=404, detail="User not found")

@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    with LOCK:
        db = load_db()
        for i, u in enumerate(db["users"]):
            if u["id"] == user_id:
                db["users"].pop(i)
                save_db(db)
                return
    raise HTTPException(status_code=404, detail="User not found")
