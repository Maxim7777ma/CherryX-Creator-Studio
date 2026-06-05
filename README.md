# CherryX Creator Studio

CherryX Creator Studio is a creator workspace for conversion, YouTube/TikTok clips, covers, subtitles, publication packages, PDF resumes, design projects, video editing, billing-aware storage, and project sharing.

## What It Includes

- Django Creator Studio with accounts, billing, jobs, projects, designer, video editor, and sharing.
- Image formats: PNG, JPG, WEBP, PDF, BMP, TIFF, GIF.
- Video formats: MP4, WEBM, GIF through FFmpeg from `imageio-ffmpeg`.
- YouTube links to vertical Shorts-style MP4 clips.
- Face-focus crop for interview and talking-head video.
- Interface language support for English, Russian, Ukrainian, French, German, Spanish, Georgian, Armenian, and Italian.
- SQLite-backed users, subscriptions, projects, shares, jobs, and output history.

## Run Locally

Install dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the main Django Creator Studio:

```powershell
.\run_web.ps1
```

Creator Studio URL: `http://127.0.0.1:8000`

`run_django.ps1` starts the same Django site:

```powershell
.\run_django.ps1
```

## Environment

Copy `.env.example` to `.env` and fill in the secrets you need:

```powershell
Copy-Item .env.example .env
```

Useful settings:

- `DJANGO_SECRET_KEY`: Django secret key for non-local use.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hosts for Django, for example `127.0.0.1,localhost,my-tunnel.ngrok-free.app`.
- `MAX_IMAGE_MB`, `MAX_VIDEO_MB`: upload limits.
- `YOUTUBE_MAX_SHORTS`, `YOUTUBE_SHORT_SECONDS`: Shorts generation limits.

## How To Share Or Demo

For a local demo, run the Django Studio:

```powershell
.\run_django.ps1
```

Open `http://127.0.0.1:8000`.

For an external demo, expose the Django port with ngrok or cloudflared:

```powershell
ngrok http 8000
```

Then add the tunnel host to `.env`:

```env
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,your-tunnel.ngrok-free.app
```

Restart `run_web.ps1` or `run_django.ps1`.

## Smoke Checks

Run these before sharing the project:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test studio.tests.WorkspaceSharingTests
```

## Native Helpers

Optional C++ helpers speed up CPU-heavy media analysis: audio RMS, visual moment scoring, and cover frame picking. Build them when a C++ compiler is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\native\build_native.ps1
```

The app falls back to Python automatically when native binaries are not built.

Manual smoke paths:

- Django landing: `http://127.0.0.1:8000/`
- Django workspace: `http://127.0.0.1:8000/app/`
- Designer: `http://127.0.0.1:8000/app/designer/`
- Video editor: `http://127.0.0.1:8000/app/video-editor/`
- Design projects: `http://127.0.0.1:8000/app/design-projects/`

## YouTube Shorts

Use the Creator Studio YouTube tools with links such as `https://youtu.be/...` or `https://www.youtube.com/watch?v=...`.

The project downloads the video with `yt-dlp`, checks duration limits, and creates vertical MP4 clips. Only process videos you own or have permission to use.
