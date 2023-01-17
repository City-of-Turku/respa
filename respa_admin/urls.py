from django.conf import settings
from django.conf.urls import url as unauthorized_url
from django.urls import include

from . import views
from .auth import admin_url as url
from .views.resources import (
    ManageUserPermissionsListView, ManageUserPermissionsSearchView, ManageUserPermissionsView, ResourceListView,
    SaveResourceView, SoftDeleteResourceView, SoftDeleteRestoreResourceView
)
from .views.units import UnitEditView, UnitListView
from .views.reports import ReportView



app_name = 'respa_admin'
urlpatterns = [
    url(r'^$', ResourceListView.as_view(), name='index'),
    unauthorized_url(r'^login/$', views.LoginView.as_view(), name='login'),
    unauthorized_url(r'^login/tunnistamo/$',
                     views.tunnistamo_login, name='tunnistamo-login'),
    unauthorized_url(r'^logout/$', views.logout, name='logout'),
    url(r'^resources/$', ResourceListView.as_view(), name='resources'),
    url(r'^resource/new/$', SaveResourceView.as_view(), name='new-resource'),
    url(r'^resource/edit/(?P<resource_id>\w+)/$', SaveResourceView.as_view(), name='edit-resource'),
    url(r'^resource/delete/(?P<resource_id>\w+)/$', SoftDeleteResourceView.as_view(), name='soft-delete-resource'),
    url(r'^resource/restore/$', SoftDeleteRestoreResourceView.as_view(), name='restore-resources'),
    url(r'^units/$', UnitListView.as_view(), name='units'),
    url(r'^units/edit/(?P<unit_id>[\w\d:]+)/$', UnitEditView.as_view(), name='edit-unit'),
    url(r'^i18n/$', include('django.conf.urls.i18n'), name='language'),
    url(r'^user_management/$', ManageUserPermissionsListView.as_view(), name='user-management'),
    url(r'^user_management/search/$', ManageUserPermissionsSearchView.as_view(), name='user-management-search'),
    url(r'^user_management/(?P<user_id>\w+)/$', ManageUserPermissionsView.as_view(), name='edit-user'),
    url(r'^reports/', ReportView.as_view(), name='ra-reports'),
]


if settings.O365_CLIENT_ID:
    from respa_o365.views import (
        RAOutlookLinkListView,
        RAOutlookLinkCreateView,
        RAOutlookLinkDeleteView
    )
    urlpatterns.append(url(r'^outlook/$', RAOutlookLinkListView.as_view(), name='ra-outlook'))
    urlpatterns.append(url(r'^outlook/create/$', RAOutlookLinkCreateView.as_view(), name='ra-outlook-create'))
    urlpatterns.append(url(r'^outlook/delete/$', RAOutlookLinkDeleteView.as_view(), name='ra-outlook-delete'))


if settings.QUALITYTOOL_ENABLED:
    from qualitytool.views import (
        QualityToolManagementView,
        QualityToolLinkView,
        QualityToolRemoveLinkView
    )
    urlpatterns.append(url(r'^qualitytool/$', QualityToolManagementView.as_view(), name='ra-qualitytool'))
    urlpatterns.append(url(r'^qualitytool/create/$', QualityToolLinkView.as_view(), name='ra-qualitytool-create'))
    urlpatterns.append(url(r'^qualitytool/remove/(?P<qualitytool_id>[0-9A-Fa-f-]+)/$', QualityToolRemoveLinkView.as_view(), name='ra-qualitytool-remove'))
    urlpatterns.append(url(r'^qualitytool/edit/(?P<qualitytool_id>[0-9A-Fa-f-]+)/$', QualityToolLinkView.as_view(), name='ra-qualitytool-edit'))