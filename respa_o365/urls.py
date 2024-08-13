from django.urls import path
from django.conf.urls import include
from rest_framework import routers
from respa_o365 import views
from respa_o365.calendar_login import LoginCallBackView, LoginStartView
from respa_o365.outlook_notification_handler import NotificationCallback

router = routers.DefaultRouter()
router.register(r'calendar_links', views.OutlookCalendarLinkViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('start_connect_resource_to_calendar/', LoginStartView.as_view()),
    path('finalise_connection/', LoginCallBackView.as_view()),
    path("notification_callback", NotificationCallback.as_view()),
]
