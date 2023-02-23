import itertools
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import FieldDoesNotExist
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.forms import ValidationError
from django.template.response import TemplateResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect
from django.views.generic import CreateView, ListView, UpdateView, TemplateView
from django.views.generic.base import View
from django.contrib.admin.utils import construct_change_message
from guardian.shortcuts import assign_perm, remove_perm
from respa_admin.views.base import ExtraContextMixin
from resources.enums import UnitGroupAuthorizationLevel, UnitAuthorizationLevel
from resources.auth import is_any_admin

from users.models import User

from resources.models import (
    Resource,
    ResourceTag,
    Period,
    Day,
    ResourceImage,
    ResourceType,
    Unit,
    UnitGroup,
    UnitAuthorization
)
from respa_admin import accessibility_api, forms
from respa_admin.forms import (
    ResourceForm,
    UserForm,
    get_period_formset,
    get_resource_image_formset,
    get_unit_authorization_formset,
    get_resource_universal_formset,
    get_universal_options_formset,
)
from respa_admin.views.base import PeriodMixin
from resources.models.utils import log_entry, generate_id

import json


class ResourceListView(ExtraContextMixin, ListView):
    model = Resource
    paginate_by = 10
    context_object_name = 'resources'
    template_name = 'respa_admin/page_resources.html'

    def get(self, request, *args, **kwargs):
        get_params = request.GET
        self.search_query = get_params.get('search_query')
        self.resource_type = get_params.get('resource_type')
        self.resource_unit = get_params.get('resource_unit')
        self.resource_integration = get_params.get('resource_integration')
        self.order_by = get_params.get('order_by')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ResourceListView, self).get_context_data()
        resources = self.get_unfiltered_queryset()
        context['types'] = ResourceType.objects.filter(
            pk__in=resources.values('type'))
        context['units'] = Unit.objects.filter(
            pk__in=resources.values('unit'))
        context['search_query'] = self.search_query or ''
        context['selected_resource_type'] = self.resource_type or ''
        context['selected_resource_unit'] = self.resource_unit or ''
        context['selected_resource_integration'] = self.resource_integration or ''
        context['order_by'] = self.order_by or ''
        context['CAN_RESTORE_RESOURCES'] = self.model._default_manager \
            .with_soft_deleted \
            .modifiable_by(self.request.user) \
            .filter(soft_deleted=True).count() > 0
        return context

    def get_unfiltered_queryset(self):
        qs = super(ResourceListView, self).get_queryset()
        qs = qs.modifiable_by(self.request.user)
        return qs

    def get_queryset(self):
        qs = self.get_unfiltered_queryset()

        if self.search_query:
            qs = qs.filter(name__icontains=self.search_query)
        if self.resource_type:
            qs = qs.filter(type=self.resource_type)
        if self.resource_unit:
            qs = qs.filter(unit=self.resource_unit)
        if self.resource_integration:
            qs = qs.exclude(is_external=self.resource_integration == 'ra')
        if self.order_by:
            order_by_param = self.order_by.strip('-')
            try:
                if Resource._meta.get_field(order_by_param):
                    qs = qs.order_by(self.order_by)
            except FieldDoesNotExist:
                qs = self.get_unfiltered_queryset()

        qs = qs.prefetch_related('images', 'unit')

        return qs


class ManageUserPermissionsView(ExtraContextMixin, UpdateView):
    model = User
    context_object_name = 'user_object'
    pk_url_kwarg = 'user_id'
    form_class = UserForm
    template_name = 'respa_admin/resources/edit_user.html'

    def get_success_url(self, **kwargs):
        return reverse_lazy('respa_admin:edit-user', kwargs={'user_id': self.object.pk})

    def _validate_forms(self, form, unit_authorization_formset):
        valid_form = form.is_valid()
        valid_unit_authorization_formset = unit_authorization_formset.is_valid()

        if valid_unit_authorization_formset:
            perms_are_empty_or_marked_for_deletion = all(
                {"DELETE": True}.items() <= dict.items() or len(dict) == 0
                for dict in unit_authorization_formset.cleaned_data
            )

        if not form.cleaned_data['is_staff'] and not perms_are_empty_or_marked_for_deletion:
            form.add_error(None, _('You can\'t remove staff status from user with existing permissions'))
            return False

        return valid_form and valid_unit_authorization_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unit_authorization_formset'] = get_unit_authorization_formset(
            request=self.request,
            instance=self.object,
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()

        unit_authorization_formset = get_unit_authorization_formset(request=request, instance=self.get_object())

        if self._validate_forms(form, unit_authorization_formset):
            return self.forms_valid(form, unit_authorization_formset)
        else:
            return self.forms_invalid(form, unit_authorization_formset)

    def forms_valid(self, form, unit_authorization_formset):
        user = self.request.user
        is_edit = self.object is not None

        self.object = form.save()
        unit_authorization_formset.instance = self.object
        for form in unit_authorization_formset.cleaned_data:
            level = form.get('level',  None)
            subject = form.get('subject', None)
            if subject and level:
                if form['can_approve_reservation']:
                    assign_perm('unit:can_approve_reservation', self.object, subject)
                else:
                    remove_perm('unit:can_approve_reservation', self.object, subject)
                if form['DELETE']:
                    log_entry(self.object, user, is_edit=is_edit, message="Unit '%s' authorization removed: %s" % (subject.name, level))
                else:
                    if not UnitAuthorization.objects \
                        .for_user(self.object).to_unit(subject) \
                                .filter(level=level).exists():
                        log_entry(self.object, user, is_edit=is_edit, message="Unit '%s' authorization added: %s" % (subject.name, level))


        unit_auths = unit_authorization_formset.save()
        if not unit_auths:
            unit_auths = UnitAuthorization.objects.filter(authorized=self.object)
        for _, unit_auths in itertools.groupby(unit_auths, lambda unit_auth: unit_auth.subject):
            max(unit_auths)._ensure_lower_auth()


        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, form, unit_authorization_formset):
        messages.error(self.request, _('Failed to save. Please check the form for errors.'))

        return self.render_to_response(
            self.get_context_data(
                form=form,
                unit_authorization_formset=unit_authorization_formset,
            )
        )


class ManageUserPermissionsListView(ExtraContextMixin, ListView):
    model = Unit
    context_object_name = 'units'
    template_name = 'respa_admin/user_management.html'
    user_list_template_name = 'respa_admin/resources/_unit_user_list.html'
    paginate_by = 10

    def get(self, request, *args, **kwargs):
        get_params = request.GET
        self.selected_unit = get_params.get('selected_unit')
        return super().get(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if not is_any_admin(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_all_available_units(self):
        if self.request.user.is_superuser:
            all_units = self.model.objects.all().prefetch_related('authorizations').exclude(authorizations__authorized__isnull=True)
            return all_units

        unit_filters = Q(authorizations__authorized=self.request.user,
                         authorizations__level__in={
                             UnitAuthorizationLevel.admin,
                         })
        unit_group_filters = Q(unit_groups__authorizations__authorized=self.request.user,
                               unit_groups__authorizations__level__in={
                                   UnitGroupAuthorizationLevel.admin,
                               })
        all_available_units = self.model.objects.filter(unit_filters | unit_group_filters).prefetch_related('authorizations')
        return all_available_units.exclude(authorizations__authorized__isnull=True).distinct('name')

    def get_queryset(self):
        qs = self.get_all_available_units()
        if self.selected_unit:
            qs = qs.filter(id=self.selected_unit)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['selected_unit'] = self.selected_unit or ''
        context['all_available_units'] = self.get_all_available_units()
        context['user_list_template_name'] = self.user_list_template_name
        return context


class ManageUserPermissionsSearchView(ExtraContextMixin, ListView):
    model = User
    context_object_name = 'users'
    template_name = 'respa_admin/user_management.html'
    user_list_template_name = 'respa_admin/resources/_user_list.html'

    def get(self, request, *args, **kwargs):
        get_params = request.GET
        self.search_query = get_params.get('search_query')
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if self.search_query and '@' in self.search_query:
            return self.model.objects.filter(email__iexact=self.search_query)
        elif self.search_query:
            filters = Q()
            for name in self.search_query.split():
                filters &= Q(first_name__icontains=name) | Q(last_name__icontains=name)
            return self.model.objects.filter(filters)
        return self.model.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['user_list_template_name'] = self.user_list_template_name
        context['search_query'] = self.search_query or None

        return context


class RespaAdminIndex(ResourceListView):
    paginate_by = 7
    template_name = 'respa_admin/index.html'


def admin_office(request):
    return TemplateResponse(request, 'respa_admin/page_office.html')

class SoftDeleteRestoreResourceView(ExtraContextMixin, TemplateView):
    template_name = 'respa_admin/resources/_restore_resources_list.html'
    model = Resource
    

    def get_queryset(self):
        queryset = self.model.objects.with_soft_deleted.filter(soft_deleted=True)
        return queryset

    
    def restore_resources(self, payload):
        resources = payload['resources']
        return self.get_queryset().filter(pk__in=resources).restore()

        

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['random_id_str'] = generate_id()
        context['resources'] = self.get_queryset()
        return context
    
    def post(self, request, *args, **kwargs):
        payload = json.loads(request.body)
        self.restore_resources(payload)
        return JsonResponse({
            'redirect_url': reverse_lazy('respa_admin:resources')
        })

class SoftDeleteResourceView(ExtraContextMixin, View):
    context_object_name = 'resource'
    model = Resource
    pk_url_kwarg = 'resource_id'

    def process_request(self, request, *args, **kwargs):
        resource_id = kwargs.pop('resource_id', None)
        if not resource_id:
            raise ValidationError(_('Something went wrong'), 500)
        try:
            self.object = self.model.objects.get(pk=resource_id)
        except self.model.DoesNotExist:
            raise ValidationError(_('Something went wrong'), 400)


    def post(self, request, *args, **kwargs):
        try:
            self.process_request(request, *args, **kwargs)
        except ValidationError as exc:
            return JsonResponse(
                {'message': exc.message, 'type': 'error'},
                status=exc.code
            )
        self.object.delete()
        return redirect('respa_admin:resources')


class SaveResourceView(ExtraContextMixin, PeriodMixin, CreateView):
    """
    View for saving new resources and updating existing resources.
    """
    http_method_names = ['get', 'post']
    model = Resource
    pk_url_kwarg = 'resource_id'
    form_class = ResourceForm
    template_name = 'respa_admin/resources/create_resource.html'

    def get_context_data(self, **kwargs):
        context = super(SaveResourceView, self).get_context_data(**kwargs)
        if settings.RESPA_ADMIN_VIEW_RESOURCE_URL and self.object:
            context['RESPA_ADMIN_VIEW_RESOURCE_URL'] = settings.RESPA_ADMIN_VIEW_RESOURCE_URL + self.object.id
        else:
            context['RESPA_ADMIN_VIEW_RESOURCE_URL'] = ''
        return context

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.modifiable_by(self.request.user)

    def get_success_url(self, **kwargs):
        messages.success(self.request, 'Resurssi tallennettu')
        return reverse_lazy('respa_admin:edit-resource', kwargs={
            self.pk_url_kwarg: self.object.id,
        })

    def get(self, request, *args, **kwargs):
        if self.pk_url_kwarg in kwargs:
            self.object = self.get_object()
            page_headline = _('Edit resource')
        else:
            page_headline = _('Create new resource')
            self.object = None

        form = self.get_form()

        resource_image_formset = get_resource_image_formset(
            self.request,
            instance=self.object,
        )

        resource_universal_formset = get_resource_universal_formset(
            self.request,
            instance=self.object,
        )

        resource_options_formset = get_universal_options_formset(
            self.request,
            instance=self.object,
        )

        trans_fields = forms.get_translated_field_count(resource_image_formset)
        trans_fields.update(forms.get_translated_field_count(resource_universal_formset))
        trans_fields.update(forms.get_translated_field_count(resource_options_formset))

        accessibility_data_link = self._get_accessibility_data_link(request)

        extra = {}
        
        if self.object:
            disabled_fields_set = self.object.get_disabled_fields()
            extra.update({
                'images_is_disabled': 'images' in disabled_fields_set,
                'free_of_charge_is_disabled': 'free_of_charge' in disabled_fields_set,
                'periods_field_is_disabled': 'periods' in disabled_fields_set,
                'public_is_disabled': 'public' in disabled_fields_set,
                'reservable_is_disabled': 'reservable' in disabled_fields_set,
                'all_fields_disabled': len(disabled_fields_set) == len(ResourceForm.Meta.fields + ['groups', 'periods', 'images', 'free_of_charge'])
            })

        return self.render_to_response(
            self.get_context_data(
                accessibility_data_link=accessibility_data_link,
                form=form,
                resource_image_formset=resource_image_formset,
                resource_universal_formset=resource_universal_formset,
                resource_options_formset=resource_options_formset,
                trans_fields=trans_fields,
                page_headline=page_headline,
                **extra
            )
        )

    def _get_accessibility_data_link(self, request):
        if self.object is None or self.object.unit is None or not self.object.unit.is_admin(request.user):
            return None
        if self.object.type.id not in getattr(settings, 'RESPA_ADMIN_ACCESSIBILITY_VISIBILITY', []):
            return None
        if not getattr(settings, 'RESPA_ADMIN_ACCESSIBILITY_API_SECRET', None):
            return None
        api_url = getattr(settings, 'RESPA_ADMIN_ACCESSIBILITY_API_BASE_URL', '')
        system_id = getattr(settings, 'RESPA_ADMIN_ACCESSIBILITY_API_SYSTEM_ID', '')
        secret = getattr(settings, 'RESPA_ADMIN_ACCESSIBILITY_API_SECRET', '')
        target_id = self.object.pk
        target_name = self.object.name
        location_id = str(self.object.unit.id).lstrip('tprek:')  # remove prefix, use bare tprek id
        user = request.user.email or request.user.username
        return accessibility_api.generate_url(
            api_url,
            system_id,
            target_id,
            target_name,
            user,
            secret,
            location_id=location_id
        )

    def post(self, request, *args, **kwargs):
        if self.pk_url_kwarg in kwargs:
            self.object = self.get_object()
        else:
            self.object = None


        form = self.get_form()

        period_formset_with_days = self.get_period_formset()
        resource_image_formset = get_resource_image_formset(request=request, instance=self.object)

        resource_universal_formset = get_resource_universal_formset(request=request, instance=self.object)
        resource_options_formset = get_universal_options_formset(request=request, instance=self.object)


        if self._validate_forms(form, period_formset_with_days, resource_image_formset, resource_universal_formset, resource_options_formset):
            try:
                return self.forms_valid(form, period_formset_with_days, resource_image_formset, resource_universal_formset, resource_options_formset)
            except:
                return self.forms_invalid(form, period_formset_with_days, resource_image_formset, resource_universal_formset, resource_options_formset)
        else:
            return self.forms_invalid(form, period_formset_with_days, resource_image_formset, resource_universal_formset, resource_options_formset)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        unit_field = form.fields['unit']
        unit_field.queryset = unit_field.queryset.managed_by(self.request.user)
        unit_field.required = True
        if self.object and self.object.pk:
            unit_field.disabled = True
        return form

    def forms_valid(self, form, period_formset_with_days, resource_image_formset, universal_formset, options_formset):
        user = self.request.user
        is_edit = self.object is not None
        self.object = form.save()
        df_set = self.object.get_disabled_fields()

        log_entry(self.object, user, is_edit=is_edit, message=construct_change_message(
            form, None, not is_edit
        ))

        if not df_set or \
            (df_set and 'universal' not in df_set) or \
            (df_set and 'universal' in df_set and not is_edit):
                self._save_resource_universal(universal_formset)
        if not df_set or \
            (df_set and 'options' not in df_set) or \
            (df_set and 'options' in df_set and not is_edit):
                self._save_universal_options(options_formset)
        if not df_set or \
            (df_set and 'purposes' not in df_set) or \
            (df_set and 'purposes' in df_set and not is_edit):
                self._save_resource_purposes()
        if not df_set or \
            (df_set and 'images' not in df_set) or \
            (df_set and 'images' in df_set and not is_edit):
                self._delete_extra_images(resource_image_formset)
                self._save_resource_images(resource_image_formset)
        if not df_set or \
            (df_set and 'periods' not in df_set) or \
            (df_set and 'periods' in df_set and not is_edit):
            self.save_period_formset(period_formset_with_days)
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, form, period_formset_with_days, resource_image_formset, resource_universal_formset, resource_options_formset):
        messages.error(self.request, _('Failed to save. Please check the form for errors.'))

        # Extra forms are not added upon post so they
        # need to be added manually below. This is because
        # the front-end uses the empty 'extra' forms for cloning.
        temp_image_formset = get_resource_image_formset()
        resource_image_formset.forms.append(temp_image_formset.forms[0])
        period_formset_with_days = self.add_empty_forms(period_formset_with_days)
        trans_fields = forms.get_translated_field_count(resource_image_formset)
        opt_fields = forms.get_translated_field_count(resource_options_formset)
        trans_fields.update(opt_fields)

        # resource_staff_emails and resource_tags are treated as single string,
        # re-fill resource_staff_emails from initial data, return as list,
        # re-fetch tags, return as list.
        original = form.data.copy()
        original.update({
                'resource_staff_emails': form.initial.get('resource_staff_emails', []),
                'resource_tags': form.get_resource_tags()
            })

        form.data = original
        return self.render_to_response(
            self.get_context_data(
                form=form,
                period_formset_with_days=period_formset_with_days,
                resource_image_formset=resource_image_formset,
                resource_universal_formset=resource_universal_formset,
                resource_options_formset=resource_options_formset,
                trans_fields=trans_fields,
                page_headline=_('Edit resource'),
            )
        )

    def _validate_forms(self, form, period_formset, image_formset, universal_formset, options_formset):
        df_set = []
        is_valid = []
    
        if self.object:
            df_set = self.object.get_disabled_fields()

        is_valid.append(form.is_valid())
        if not df_set or (df_set and 'periods' not in df_set):
            is_valid.append(period_formset.is_valid())
        if not df_set or (df_set and 'images' not in df_set):
            is_valid.append(image_formset.is_valid())
        if not df_set or (df_set and 'universal' not in df_set):
            is_valid.append(universal_formset.is_valid())
        if not df_set or (df_set and 'options' not in df_set):
            is_valid.append(options_formset.is_valid())

        return all(is_valid)

    def _save_resource_purposes(self):
        checked_purposes = self.request.POST.getlist('purposes')

        for purpose in checked_purposes:
            self.object.purposes.add(purpose)

    def _save_resource_images(self, resource_image_formset):
        count = len(resource_image_formset)

        for i in range(count):
            resource_image = resource_image_formset.forms[i].save(commit=False)
            resource_image.resource = self.object
            image_key = 'images-' + str(i) + '-image'

            if image_key in self.request.FILES:
                resource_image.image = self.request.FILES[image_key]
            resource_image.save()

    def _save_resource_universal(self, resource_universal_formset):
        resource_universal_formset.save()

    def _save_universal_options(self, resource_options_formset):
        resource_options_formset.save()

    def _delete_extra_images(self, resource_images_formset):
        data = resource_images_formset.data
        image_ids = get_formset_ids('images', data)

        if image_ids is None:
            return

        ResourceImage.objects.filter(resource=self.object).exclude(pk__in=image_ids).delete()


def get_formset_ids(formset_name, data):
    count = to_int(data.get('{}-TOTAL_FORMS'.format(formset_name)))
    if count is None:
        return None

    ids_or_nones = (
        to_int(data.get('{}-{}-{}'.format(formset_name, i, 'id')))
        for i in range(count)
    )

    return {x for x in ids_or_nones if x is not None}


def to_int(string):
    if not string or not string.isdigit():
        return None
    return int(string)
