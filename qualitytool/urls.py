from django.urls import path

from qualitytool.api.views import (
    QualityToolFormView, QualityToolFeedbackView,
    QualityToolTargetListView, 
)

app_name = 'qualitytool'

urlpatterns = [
    path('qualitytool/form', QualityToolFormView.as_view(), name='qualitytool-api-form-view'),
    path('qualitytool/feedback/', QualityToolFeedbackView.as_view(), name='qualitytool-api-feedback-view'),
    path('qualitytool/targets', QualityToolTargetListView.as_view(), name='qualitytool-api-target-list'),
]
