from django.urls import path

from resources.api import (
    ResourceCreateView, 
    ResourceUpdateView, 
    ResourceCreateProductView,
    ResourceDeleteView,
    ResourceRestoreView
)


urlpatterns = [
    path('resource/new/', ResourceCreateView.as_view()),
    path('resource/restore/', ResourceRestoreView.as_view()),
    path('resource/<str:pk>/update/', ResourceUpdateView.as_view()),
    path('resource/<str:pk>/delete/', ResourceDeleteView.as_view()),
    path('resource/<str:pk>/product/', ResourceCreateProductView.as_view())
]