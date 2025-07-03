"""
Main FastAPI application for the backend_api container.

Features:
- Supabase authentication (sign up, login, token validation)
- PDF/book file upload to Supabase storage
- Preview PDF/book content endpoint (first few pages as text)
- Q&A endpoint for uploaded files
"""

import os
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    status,
    Body,
    Query,
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
import requests
from io import BytesIO
import fitz  # PyMuPDF
import tempfile

# --- ENVIRONMENT VARIABLES (from .env or runtime env) ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = "pdf-uploads"  # Customize if needed

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set.")

# --- FastAPI APP CONFIG ---
app = FastAPI(
    title="Document Q&A Backend API",
    description="API service for PDF/book upload, content preview, and Q&A using Supabase.",
    version="1.0",
    openapi_tags=[
        {"name": "auth", "description": "Supabase authentication (signup/login/validate)"},
        {"name": "files", "description": "PDF upload, listing, and preview"},
        {"name": "qa", "description": "Ask questions about uploaded files"},
    ],
)

# Set CORS for frontend/react
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You should restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# --- MODELS ---

class UserSignupRequest(BaseModel):
    """Request body for user signup."""
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=6, description="User password (min 6 chars)")


class UserLoginRequest(BaseModel):
    """Request body for user login."""
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class FileMeta(BaseModel):
    """File metadata returned on upload/list."""
    name: str = Field(..., description="File name")
    url: str = Field(..., description="URL to access the file in Supabase storage")


class QAModelRequest(BaseModel):
    """Request body for Q&A."""
    file_url: str = Field(..., description="Public URL to the uploaded file")
    question: str = Field(..., description="The user's natural language question")


class QAResponse(BaseModel):
    """Response to user's question."""
    answer: str = Field(..., description="Generated answer")
    status: str = Field(..., description="success or error")


# --- HELPER FUNCTIONS ---

def supabase_rpc(endpoint: str, *, json: dict, method="POST"):
    """Generic call to Supabase Auth REST endpoints."""
    url = f"{SUPABASE_URL}/auth/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.request(method, url, json=json, headers=headers)
    try:
        out = resp.json()
    except Exception:
        out = None
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=out)
    return out

def supabase_storage_upload(file_bytes: bytes, filename: str, access_token: str) -> str:
    """Upload a file to Supabase storage. Returns the public URL."""
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{filename}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {access_token}",
        "x-upsert": "true",
        "Content-Type": "application/pdf",
    }
    result = requests.post(upload_url, headers=headers, data=file_bytes)
    if not result.ok:
        raise HTTPException(status_code=result.status_code, detail=f"Upload failed: {result.text}")

    # Make file public
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
    return public_url

def supabase_storage_list(user_id: str, access_token: str):
    """List files in the user's folder."""
    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}?prefix={user_id}/"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

def get_pdf_preview(file_bytes: bytes, max_pages: int = 3) -> List[str]:
    """Extracts preview text (up to max_pages) from a PDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for i in range(min(len(doc), max_pages)):
        text = doc[i].get_text()
        pages.append(text)
    return pages

def supabase_get_user(token: str):
    """Validates the JWT and returns user info (calls /auth/v1/user)."""
    url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {token}",
    }
    resp = requests.get(url, headers=headers)
    if not resp.ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return resp.json()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """PUBLIC_INTERFACE
    Dependency to extract current user from JWT token via Supabase.
    """
    user = supabase_get_user(token)
    return user

# Dummy Q&A: Replace with real LLM/integration as needed
def answer_question_with_pdf(pdf_bytes: bytes, question: str) -> str:
    """Fake answer generator: returns the first paragraph containing any keyword of the question."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    q_words = set(question.lower().split())
    for page in doc:
        for paragraph in page.get_text("blocks"):
            for w in q_words:
                if w in paragraph[4].lower():
                    return paragraph[4][:350]  # first match, truncated
    return "I'm sorry, I could not find an answer in the document."


# --- API ENDPOINTS ---

# PUBLIC_INTERFACE
@app.post("/auth/signup", summary="Sign up", tags=["auth"])
def signup(req: UserSignupRequest):
    """
    Registers a new user in Supabase Auth.
    """
    out = supabase_rpc("signup", json={
        "email": req.email,
        "password": req.password
    })
    return {"msg": "User registered", "data": out}


# PUBLIC_INTERFACE
@app.post("/auth/login", summary="Login", tags=["auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Logs in a user using Supabase Auth, returns access token.
    """
    out = supabase_rpc("token?grant_type=password", method="POST", json={
        "email": form_data.username,
        "password": form_data.password,
    })
    return {
        "access_token": out["access_token"],
        "refresh_token": out["refresh_token"],
        "token_type": "bearer",
        "user": out.get("user"),
    }

# PUBLIC_INTERFACE
@app.get("/auth/user", summary="Check user validity", tags=["auth"])
async def auth_user_me(current_user: dict = Depends(get_current_user)):
    """
    Checks the validity of a Supabase JWT token and returns user details.
    """
    return {"user": current_user}


# PUBLIC_INTERFACE
@app.post("/files/upload", summary="Upload a PDF/book file", tags=["files"], response_model=FileMeta)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """
    Upload a PDF/book file to Supabase storage.
    - Only accepts files with content-type application/pdf.
    - Files are uploaded under a user-specific folder.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files supported.")

    user_id = current_user["id"]
    filename = f"{user_id}/{file.filename}"

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Empty file is not allowed.")

    # Upload to Supabase Storage
    public_url = supabase_storage_upload(file_bytes, filename, token)
    return FileMeta(name=file.filename, url=public_url)


# PUBLIC_INTERFACE
@app.get("/files/list", summary="List uploaded files", tags=["files"], response_model=List[FileMeta])
async def list_user_files(
    current_user: dict = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """
    Returns a list of files uploaded by the user.
    """
    user_id = current_user["id"]
    result = supabase_storage_list(user_id, token)
    files = []
    for obj in result:
        name = obj.get("name")
        if not name or name.endswith("/"):
            continue
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{name}"
        files.append(FileMeta(name=os.path.basename(name), url=public_url))
    return files

# PUBLIC_INTERFACE
@app.get("/files/preview", summary="Preview a PDF/book file", tags=["files"])
async def preview_file(
    file_url: str = Query(..., description="Public URL to the file"),
    pages: int = Query(3, description="Number of pages to preview"),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns the text of the first N pages of the given PDF file.
    """
    resp = requests.get(file_url)
    if not resp.ok:
        raise HTTPException(400, f"Failed to fetch file from {file_url}")
    preview_pages = get_pdf_preview(resp.content, max_pages=pages)
    return {"preview": preview_pages}


# PUBLIC_INTERFACE
@app.post("/qa/ask", response_model=QAResponse, summary="Ask a question about a file", tags=["qa"])
async def ask_question(
    req: QAModelRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Accepts a public file URL and a question; answers the question using file context.
    The answer is generated by extracting relevant text from the uploaded file.
    """
    resp = requests.get(req.file_url)
    if not resp.ok:
        raise HTTPException(400, f"Could not fetch file at {req.file_url}")
    answer = answer_question_with_pdf(resp.content, req.question)
    return QAResponse(answer=answer, status="success")

# PUBLIC_INTERFACE
@app.get("/", summary="API status/info", tags=["misc"])
def root():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "Backend API for Document Q&A"}


# PUBLIC_INTERFACE
@app.get("/docs/websocket", tags=["misc"])
def websocket_usage():
    """No websocket support in this backend. All endpoints are REST over HTTP."""
    return {"info": "This API uses only HTTP REST endpoints. No WebSocket required."}

