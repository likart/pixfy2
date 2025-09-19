from django.urls import path
from . import views

app_name = 'gallery'

urlpatterns = [
    path('', views.home, name='home'),
    path('photo/<int:photo_id>/', views.photo_detail, name='photo_detail'),
    path('upload/', views.upload_photo, name='upload'),
    path('upload/handle/', views.handle_photo_upload, name='handle_upload'),
    path('upload/temp/', views.upload_to_temp, name='upload_to_temp'),
    path('download/<int:photo_id>/', views.download_photo, name='download'),
    path('my-photos/', views.user_photos, name='user_photos'),
    path('my-photos/manage/', views.manage_user_photos, name='manage_user_photos'),
    path('api/search/', views.search_api, name='search_api'),
    path('api/extract-metadata/', views.extract_metadata_api, name='extract_metadata_api'),
]
