# backend_api

Backend REST API service for Document Q&A project.

## Features

- User sign-up and login (Supabase authentication)
- PDF/book file upload to Supabase Storage
- List and preview uploaded files (first pages as text)
- Ask natural language questions about uploaded PDFs/books

## Endpoints

### Authentication

- `POST /auth/signup` &mdash; Sign up with email/password
- `POST /auth/login` &mdash; Login and obtain JWT
- `GET /auth/user` &mdash; Check JWT and get user info

### File Handling

- `POST /files/upload` &mdash; Upload PDF (requires JWT)
- `GET /files/list` &mdash; List user files (requires JWT)
- `GET /files/preview?file_url=...` &mdash; Get preview text (requires JWT)

### Q&A

- `POST /qa/ask` — Submit a file URL and question, get response (requires JWT)

## Setup

1. `cp .env.example .env` and fill in with your Supabase project settings.
2. `pip install -r requirements.txt`
3. `uvicorn main:app --reload`

## Notes

- Requires a Supabase project with "pdf-uploads" storage bucket.
- Q&A answers are simple text extraction—replace with LLM for production.
