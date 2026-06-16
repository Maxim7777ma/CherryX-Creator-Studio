# CherryX Creator Studio Upgrade Screen Map

This map anchors the productivity, UX/UI, mobile, and feature-upgrade work so each pass has a clear surface to verify.

## Core Workspace

- Main workspace: `/app/`, `studio/templates/studio/index.html`, `studio/static/studio/app.js`
- Dashboard detail and files: `/app/stats/<section>/`, `dashboard_detail`, `dashboard_files_section.html`, `stats_files.js`
- Job detail and outputs: `/jobs/<job_id>/`, `job_detail.html`, output edit handoff endpoints

## Editors

- Design projects: `/app/design-projects/`, `/api/design-projects/`, `design_projects.html`
- Design editor: `/app/designer/`, `designer.html`, designer code inside `app.js`
- Video projects: `/app/video-projects/`, `/api/video-projects/`, `video_projects.html`
- Video editor: `/app/video-editor/`, `video_editor.html`, export and asset APIs in `studio/views.py`
- Music projects/editor: `/app/music-projects/`, `/app/music-editor/`, `music_projects.js`, `music_editor.js`

## Account, Sharing, Billing

- Auth: `/accounts/login/`, `/accounts/register/`, `auth.html`
- Account settings: `/accounts/settings/`, `account_settings.html`
- Sharing: `/api/shares/`, `_share_modal.html`, `sharing.js`
- Billing: `/pricing/`, `/checkout/`, `billing/templates/billing`

## Upgrade Verification Matrix

- Viewports: `390x844`, `768x1024`, `1440x900`
- States: guest, authenticated, paid, unpaid
- Roles: owner, viewer, editor
- Workflows: upload -> job output -> edit in Design Mode -> register/login transfer -> share project -> export/download
- Quality checks: no mojibake in localized output, stable project-list pagination metadata, AI metadata shows used/fallback state
