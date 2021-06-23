from django.urls import path, re_path
from django.conf.urls import include

from resources.api import ResourceCreateView, ResourceUpdateView, ResourceCreateProductView


urlpatterns = [
    path('resource/new/', ResourceCreateView.as_view()),
    path('resource/<str:pk>/update/', ResourceUpdateView.as_view()),
    path('resource/<str:pk>/product/', ResourceCreateProductView.as_view())
]