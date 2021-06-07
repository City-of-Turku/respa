from django.urls import path, re_path
from django.conf.urls import include

from accessibility.api import ServiceRequirementCreateView


urlpatterns = [
    path('accessibility/service-requirement', ServiceRequirementCreateView.as_view()),
]