# Supabase Integration Requirements for backend_api

## Authentication

- Uses Supabase Auth REST API for sign-up, login, and token validation.
- Clients must provide the access token (JWT) as "Bearer" in the `Authorization` header for protected endpoints.
- Endpoints:
  - `/auth/v1/signup` for registration
  - `/auth/v1/token?grant_type=password` for login
  - `/auth/v1/user` to check/validate JWT

## Storage

- Requires a storage bucket, recommended name: `pdf-uploads` (configurable).
- PDF files are uploaded with path format: `<user_id>/<filename>`.
- Each file is made public in the bucket after upload for preview and Q&A.
- Endpoints:
  - `/storage/v1/object/<bucket>/<object_path>` for upload and download
  - `/storage/v1/object/list/<bucket>?prefix=<user_id>/` to list user files

## Notes

- JWT tokens are required for file and Q&A endpoints (for authorization and per-user file separation).
- For extra security, consider server-side database for logging file metadata/Q&A if desired.
