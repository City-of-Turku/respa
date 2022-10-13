import itertools
import json
from subprocess import call
from django.forms import ValidationError
from django.http import JsonResponse
from django.utils.translation import ugettext as _
from django.views import View
from django.views.generic.base import TemplateView
from django.db.models import Q
from qualitytool.models import ResourceQualityTool
from qualitytool.utils import Struct
from resources.auth import is_authenticated_user, is_general_admin
from resources.models import Unit, UnitAuthorization
from resources.models.resource import Resource
from resources.models.utils import generate_id
from respa_admin.views.base import ExtraContextMixin
from qualitytool.manager import QualityToolManager as qt_manager


class QualityToolManagementView(ExtraContextMixin, TemplateView):
    context_object_name = 'qualitytool'
    template_name = 'respa_admin/page_qualitytool.html'


    def get_context_data(self, **kwargs):
        user = self.request.user
        context = super().get_context_data(**kwargs)
        if is_general_admin(user):
            units = Unit.objects.all()
        else:
            units = Unit.objects.filter(
                id__in=UnitAuthorization.objects.for_user(user).values_list(
                'subject', flat=True).distinct())

        if not self.resource_link or self.resource_link == 'no_link':
            query = ~Q(pk__in=[ResourceQualityTool.objects.all().values_list('resources__pk', flat=True)])
        else:
            query = Q(pk__in=[ResourceQualityTool.objects.all().values_list('resources__pk', flat=True)])
        context['resources'] = itertools.chain.from_iterable(
            unit.resources.filter(query) \
                for unit in units)

        if self.search_target:
            targets = []
            target_list = qt_manager().get_target_list()
            for target in target_list:
                if any(name.lower().find(self.search_target.lower()) > -1 for _, name in target['name'].items()):
                    target['id'] = generate_id()
                    targets.append(target)
            context['qualitytool_targets'] = targets


        context['selected_filter'] = self.resource_link

        context['random_id_str'] = generate_id()
        return context


    def get(self, request, *args, **kwargs):
        self.query_params = request.GET.getlist('unit', [])
        self.search_target = request.GET.get('search_target', '')
        self.resource_link = request.GET.get('resource_link', '')
        return super().get(request, *args, **kwargs)



class QualityToolCreateLinkView(View):
    class Meta:
        fields = ('resources', 'target_id', 'name')

    def validate(self, payload):
        for field in self.Meta.fields:
            if field not in payload:
                raise ValidationError(_('Missing fields'), 400)
        if len(set(self.Meta.fields) - set(payload)) > 0:
            raise ValidationError( _('Invalid set size'), 400)

        if not isinstance(payload['name'], dict):
            raise ValidationError(_('Name must be a dict'), 400)

        if not payload['resources']:
            raise ValidationError(_('Resources must be selected'), 400)
        
        if not isinstance(payload['resources'], list):
            raise ValidationError(_('Resources must be a list'), 400)
        

    def post(self, request, *args, **kwargs):
        user = request.user 
        if not is_authenticated_user(user):
            return JsonResponse({'message': _('You are not authorized to create links')}, status=403)

        payload = json.loads(request.body)

        try:
            self.validate(payload)
        except ValidationError as exc:
            return JsonResponse({'message': exc.message}, status=exc.code)

        name = payload['name']
        target_id = payload['target_id']
        resources = payload['resources']


        try:
            rqt = ResourceQualityTool.objects.get(pk=target_id)
        except ResourceQualityTool.DoesNotExist:
            rqt = ResourceQualityTool(target_id=target_id)
            for lang, text in name.items():
                setattr(rqt, 'name_%s' % lang, text)
            rqt.save()

    

        if rqt.resources.filter(pk__in=resources).exists():
            return JsonResponse({'message': _('Some of these resources are already linked.')}, status=400)
        

        for resource in Resource.objects.filter(pk__in=resources):
            rqt.resources.add(resource)
        rqt.save()


        return JsonResponse({
            'message': _('Resources linked with qualitytool target.')
        })
