from __future__ import annotations

from django.urls import path

from . import views


app_name = "studio"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("app/", views.index, name="index"),
    path("app/stats/<str:section>/", views.dashboard_detail, name="dashboard_detail"),
    path("app/video-projects/", views.video_project_list, name="video_project_list"),
    path("app/video-editor/", views.video_editor, name="video_editor"),
    path("api/video-projects/", views.video_projects, name="video_projects"),
    path("api/video-projects/create/", views.create_video_project, name="create_video_project"),
    path("api/video-projects/<int:project_id>/", views.video_project_detail, name="video_project_detail"),
    path("api/video-projects/<int:project_id>/save/", views.save_video_project, name="save_video_project"),
    path("api/video-projects/<int:project_id>/delete/", views.delete_video_project, name="delete_video_project"),
    path("api/video-projects/<int:project_id>/assets/", views.upload_video_project_asset, name="upload_video_project_asset"),
    path("api/video-projects/<int:project_id>/assets/<int:asset_id>/preview/", views.preview_video_project_asset, name="video_project_asset_preview"),
    path("api/video-projects/<int:project_id>/assets/<int:asset_id>/thumbnail/", views.thumbnail_video_project_asset, name="video_project_asset_thumbnail"),
    path("api/video-projects/<int:project_id>/assets/<int:asset_id>/delete/", views.delete_video_project_asset, name="delete_video_project_asset"),
    path("app/designer/", views.designer_mode, name="designer"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/settings/", views.account_settings, name="account_settings"),
    path("accounts/avatar/", views.account_avatar, name="account_avatar"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("language/", views.set_interface_language, name="set_language"),
    path("jobs/<str:job_id>/", views.job_detail, name="job_detail"),
    path("api/convert/", views.start_convert, name="start_convert"),
    path("api/youtube/", views.start_youtube, name="start_youtube"),
    path("api/cover/", views.start_cover, name="start_cover"),
    path("api/subtitles/", views.start_subtitles, name="start_subtitles"),
    path("api/package/", views.start_package, name="start_package"),
    path("api/resume/", views.start_resume, name="start_resume"),
    path("api/jobs/<str:job_id>/", views.job_status, name="job_status"),
    path("api/jobs/<str:job_id>/repeat/", views.repeat_job, name="repeat_job"),
    path("api/jobs/<str:job_id>/delete/", views.delete_job, name="delete_job"),
    path("preview/<str:job_id>/<int:index>/", views.preview_output, name="preview_output"),
    path("download/<str:job_id>/<int:index>/", views.download_output, name="download_output"),
    path("download/<str:job_id>/all/", views.download_all_outputs, name="download_all_outputs"),
    path("health/", views.health, name="health"),
]
