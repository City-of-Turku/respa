from django.urls import re_path

from qualitytool.api.views import (
    QualityToolFormView, QualityToolFeedbackView,
    QualityToolTargetListView,  QualityToolCheckResourceView
)

app_name = 'qualitytool'

urlpatterns = [
    re_path(r'qualitytool/form/$', QualityToolFormView.as_view(), name='qualitytool-api-form-view'),
    re_path(r'qualitytool/targets/$', QualityToolTargetListView.as_view(), name='qualitytool-api-target-list'),
    
    re_path(r'qualitytool/feedback/$', QualityToolFeedbackView.as_view(), name='qualitytool-api-feedback-view'),
    re_path(r'qualitytool/check/$', QualityToolCheckResourceView.as_view(), name='qualitytool-api-check')
]
