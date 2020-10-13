from django.contrib.admin import ModelAdmin, site
from django.utils.translation import gettext_lazy as _
from respa_o365.models import OutlookCalendarLink

class OutlookCalendarLinkAdmin(ModelAdmin):
    list_display = ('resource', 'user')
    search_fields = ('resource', 'user')
    fields = ('resource', 'user', 'reservation_calendar_id', 'availability_calendar_id')
    readonly_fields = ('resource', 'reservation_calendar_id', 'availability_calendar_id')

    def get_form(self, request, obj=None, **kwargs):  # pragma: no cover
        form = super(OutlookCalendarLinkAdmin, self).get_form(request, obj, **kwargs)
        return form
        
    class Meta:
        verbose_name = _("O365 Calendar Link")
        verbose_name_plural = _("O365 Calendar Links")

site.register(OutlookCalendarLink, OutlookCalendarLinkAdmin)
