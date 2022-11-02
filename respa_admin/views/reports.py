from django.utils.translation import override as translation_override, ugettext as _
from django.views.generic.base import TemplateView
from resources.models import Unit, UnitAuthorization, Resource, Day
from resources.auth import is_general_admin
from resources.models.utils import generate_id
from respa_admin.views.base import ExtraContextMixin


class ReportView(ExtraContextMixin, TemplateView):
    context_object_name = 'reports'
    template_name = 'respa_admin/page_reports.html'


    def get_context_data(self, **kwargs):
        user = self.request.user
        context = super().get_context_data(**kwargs)
        if is_general_admin(user):
            units = Unit.objects.all()
        else:
            units = Unit.objects.filter(
                id__in=UnitAuthorization.objects.for_user(user).values_list(
                'subject', flat=True).distinct())
        context['units'] = units
        
        if self.query_params:
            resources = Resource.objects.filter(unit__id__in=self.query_params)
            context['resources'] = resources
            for unit in context['units']:
                if unit.id in self.query_params:
                    setattr(unit, 'checked', True)
        context['random_id_str'] = generate_id()
        with translation_override('en'):
            context['WEEKDAYS'] = [dict(value=value, day=day, short=day[:3]) for value, day in Day.DAYS_OF_WEEK]
        return context


    def get(self, request, *args, **kwargs):
        self.query_params = request.GET.getlist('unit', [])
        return super().get(request, *args, **kwargs)
