from django.urls import path

from qualitytool.api.views import (
    QualityToolFormView, QualityToolFeedbackView,
    QualityToolTargetListView,  QualityToolCheckResourceView
)

app_name = 'qualitytool'

urlpatterns = [
    path('qualitytool/form', QualityToolFormView.as_view(), name='qualitytool-api-form-view'),
    path('qualitytool/targets', QualityToolTargetListView.as_view(), name='qualitytool-api-target-list'),
    
    path('qualitytool/feedback/', QualityToolFeedbackView.as_view(), name='qualitytool-api-feedback-view'),
    path('qualitytool/check/', QualityToolCheckResourceView.as_view(), name='qualitytool-api-check')
]
