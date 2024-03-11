import logging
from io import StringIO
from contextlib import redirect_stdout
from django.conf import settings
from django.conf.urls import re_path
from django.contrib import admin
from django.contrib.admin import site as admin_site
from django.contrib.admin.utils import unquote
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.gis.admin import OSMGeoAdmin
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http.request import HttpRequest
from django.utils.translation import gettext_lazy as _
from django import forms
from django.template.response import TemplateResponse
from guardian import admin as guardian_admin
from image_cropping import ImageCroppingMixin
from modeltranslation.admin import TranslationAdmin, TranslationStackedInline

from resources.models import RESERVATION_EXTRA_FIELDS
from .base import ExtraReadonlyFieldsOnUpdateMixin, CommonExcludeMixin, PopulateCreatedAndModifiedMixin
from resources.admin.period_inline import PeriodInline

from ..models import (
    AccessibilityValue, AccessibilityViewpoint, Day, Equipment, EquipmentAlias, EquipmentCategory, Purpose,
    Reservation, ReservationBulk, ReservationReminder, ReservationMetadataField, ReservationMetadataSet,
    ReservationHomeMunicipalityField, ReservationHomeMunicipalitySet, Resource, ResourceTag, ResourceAccessibility,
    ResourceEquipment, ResourceGroup, ResourceImage, ResourceType, TermsOfUse,
    Unit, UnitAuthorization, UnitIdentifier, UnitGroup, UnitGroupAuthorization,
    UniversalFormFieldType, ResourceUniversalField, ResourceUniversalFormOption, ResourcePublishDate
)
from ..models.utils import generate_id
from munigeo.models import Municipality
from rest_framework.authtoken.admin import Token

logger = logging.getLogger(__name__)


class _CommonMixin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin):
    pass


class EmailAndUsernameChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '%s | %s' % (obj.email, obj.username) if obj.email else obj.username


class CustomUserManage(forms.Form):
    """
    Show only apikey and staff users in a dropdown on object permission manage page
    """
    user = EmailAndUsernameChoiceField(
        queryset=get_user_model().objects.filter(
            Q(auth_token__isnull=False) | Q(is_staff=True)
        ).distinct().order_by('email', 'username')
    )
    def validate(self, user):
        super().validate(user)


class CustomGroupManage(forms.Form):
    group = forms.ModelChoiceField(Group.objects.all())


class FixedGuardedModelAdminMixin(guardian_admin.GuardedModelAdminMixin):
    def get_obj_perms_user_select_form(self, request):
        return CustomUserManage

    def get_obj_perms_group_select_form(self, request):
        return CustomGroupManage

    # fix editing an object with quoted chars in pk
    def obj_perms_manage_user_view(self, request, object_pk, user_id):
        return super().obj_perms_manage_user_view(request, unquote(object_pk), user_id)


class HttpsFriendlyGeoAdmin(OSMGeoAdmin):
    openlayers_url = 'https://cdnjs.cloudflare.com/ajax/libs/openlayers/2.13.1/OpenLayers.js'


class DayInline(admin.TabularInline):
    model = Day


class ResourceEquipmentInline(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationStackedInline):
    model = ResourceEquipment
    fields = ('equipment', 'description', 'data')
    extra = 0


class ResourceUniversalInline(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationStackedInline):
    model = ResourceUniversalField
    list_display = ('options', )
    extra = 0

class ResourceUniversalFormOptionInline(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationStackedInline):
    model = ResourceUniversalFormOption
    extra = 0

class ResourceGroupInline(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.TabularInline):
    model = ResourceGroup.resources.through
    fields = ('resourcegroup',)
    verbose_name = _('Resource group')
    verbose_name_plural = _('Resource groups')
    extra = 0


class UnitIdentifierInline(admin.StackedInline):
    model = UnitIdentifier
    fields = ('namespace', 'value')
    extra = 0

class ResourceTagInline(admin.TabularInline):
    model = ResourceTag
    fields = ('label',)
    verbose_name = _('Keyword')
    verbose_name_plural = _('Keywords')
    extra = 0


class ResourcePublishDateInline(admin.TabularInline):
    model = ResourcePublishDate
    fields = ('begin', 'end', 'reservable')
    verbose_name = _('Publish date')
    verbose_name_plural = _('Publish dates')
    extra = 0
    max_num = 1

def restore_resources(modeladmin, request, queryset):
    queryset.restore()
restore_resources.short_description = _('Restore selected resources')

def delete_resources(modeladmin, request, queryset):
    queryset.delete()
delete_resources.short_description = _('Delete selected resources')

if settings.DEBUG:
    def hard_delete_resources(modeladmin, request, queryset):
        queryset.delete(hard_delete=True)
    hard_delete_resources.short_description = _('Hard delete selected resources')


class ResourceAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, 
                    TranslationAdmin, HttpsFriendlyGeoAdmin):
    default_lon = 2478871  # Central Railway Station in EPSG:3857
    default_lat = 8501259
    default_zoom = 12

    list_display = ('name', 'unit', '_public', 'reservable', 'soft_deleted')
    list_filter = ('unit', '_public', 'reservable', 'soft_deleted')
    list_select_related = ('unit',)
    ordering = ('unit', 'name',)
    actions = [delete_resources, restore_resources]
    if settings.DEBUG:
        actions.append(hard_delete_resources)

    fieldsets = (
        (None, {
            'fields': (
                'unit', 'type',
                'purposes',
            ),
        }),
        (_('Resource Information'), {
            'fields': (
                'is_external',
                '_public', 'reservable',
                'reservable_by_all_staff',
                'name', 'description',
                'authentication',
                'min_age', 'max_age',
                'people_capacity', 'area',
                'location', 'generic_terms',
                'payment_terms', 'specific_terms',
                'access_code_type',
            ),
        }),
        (_('Timmi Information'), {
            'fields': (
                'timmi_resource', 'timmi_room_id',
            ),
        }),
        (_('Reservation Information'), {
            'fields': (
                'need_manual_confirmation',
                'send_sms_notification',
                'reservation_metadata_set',
                'reservation_home_municipality_set',
                'reservable_min_days_in_advance',
                'reservable_max_days_in_advance',
                'cooldown', 'slot_size',
                'min_period', 'max_period',
                'max_reservations_per_user',
                'reservation_feedback_url',
                'resource_staff_emails',
                'reservation_info',
                'reservation_additional_information',
                'responsible_contact_info',
                'reservation_requested_notification_extra',
                'reservation_confirmed_notification_extra',
            ),
        }),
        (_('Price Information'), {
            'fields': (
                'min_price', 'max_price',
                'price_type', 'payment_requested_waiting_time',
                'cash_payments_allowed'
            ),
        }),
        (_('Extra Information'), {
            'fields': (
                'tags',
                'external_reservation_url',
                'id',
            ),
        }),
    )

    readonly_fields = ('tags', )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.update_opening_hours()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        if 'id' in form.base_fields:
            form.base_fields['id'].initial = generate_id()
        self.inlines = self._get_inlines(obj)
        return form

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_external:
            return [field.name for field in self.model._meta.fields if field.name != 'is_external'] + [ 'tags', 'purposes' ]
        if obj and obj.publish_date:
            return ['_public', 'reservable']
        return super().get_readonly_fields(request, obj)

    def _get_inlines(self, obj):
        return [] if obj and obj.is_external else [
            ResourcePublishDateInline,
            PeriodInline,
            ResourceEquipmentInline,
            ResourceGroupInline,
            ResourceTagInline,
            ResourceUniversalInline,
            ResourceUniversalFormOptionInline,
        ]

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj and not obj.soft_deleted)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = self.model._default_manager.with_soft_deleted.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset


class UnitAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, FixedGuardedModelAdminMixin,
                TranslationAdmin, HttpsFriendlyGeoAdmin):
    inlines = [
        UnitIdentifierInline,
        PeriodInline,
    ]
    change_list_template = 'admin/units/import_buttons.html'
    import_template = 'admin/units/import_template.html'

    default_lon = 2478871  # Central Railway Station in EPSG:3857
    default_lat = 8501259
    default_zoom = 12

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.update_opening_hours()

    def get_urls(self):
        urls = super(UnitAdmin, self).get_urls()
        extra_urls = [
            re_path(r'^tprek_import/$', self.admin_site.admin_view(self.tprek_import),
                name='tprek_import'),
            re_path(r'^libraries_import/$', self.admin_site.admin_view(self.libraries_import),
                name='libraries_import'),
        ]
        return extra_urls + urls

    def tprek_import(self, request):
        context = dict(
            self.admin_site.each_context(request),
        )
        out = StringIO()
        with redirect_stdout(out):
            try:
                call_command('resources_import', '--all', 'tprek', stdout=out)
                context['command_output'] = out.getvalue()
            except Exception as e:
                context['command_output'] = 'Running import script caused the following exception: {0}'.format(str(e))
                logger.exception('Running import script caused an exception')
        context['title'] = _('Import Service Map')
        context['opts'] = self.model._meta
        return TemplateResponse(request, self.import_template, context)

    def libraries_import(self, request):
        context = dict(
            self.admin_site.each_context(request),
        )
        out = StringIO()
        with redirect_stdout(out):
            try:
                call_command('resources_import', '--all', 'kirjastot', stdout=out)
                context['command_output'] = out.getvalue()
            except Exception as e:
                context['command_output'] = 'Running import script caused the following exception: {0}'.format(str(e))
                logger.exception('Running import script caused an exception')
        context['title'] = _('Import Kirkanta')
        context['opts'] = self.model._meta
        return TemplateResponse(request, self.import_template, context)


class LimitAuthorizedToStaff(admin.ModelAdmin):
    def get_field_queryset(self, db, db_field, request):
        qs = super().get_field_queryset(db, db_field, request)
        if db_field.name == 'authorized':
            return qs.filter(is_staff=True).order_by(
                'last_name', 'first_name', 'email')
        return qs


@admin.register(UnitAuthorization)
class UnitAuthorizationAdmin(_CommonMixin, LimitAuthorizedToStaff, admin.ModelAdmin):
    list_display = ['id', 'subject', 'level', 'authorized']


@admin.register(UnitGroup)
class UnitGroupAdmin(_CommonMixin, TranslationAdmin):
    pass


@admin.register(UnitGroupAuthorization)
class UnitGroupAuthorizationAdmin(_CommonMixin, LimitAuthorizedToStaff, admin.ModelAdmin):
    list_display = ['id', 'subject', 'level', 'authorized']


class ResourceImageAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, ImageCroppingMixin, TranslationAdmin):
    exclude = ('sort_order', 'image_format')


class EquipmentAliasInline(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.TabularInline):
    model = EquipmentAlias
    readonly_fields = ()
    exclude = CommonExcludeMixin.exclude + ('id',)
    extra = 1


class EquipmentAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    inlines = (
        EquipmentAliasInline,
    )


class ResourceEquipmentAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    fields = ('resource', 'equipment', 'description', 'data')


class ReservationAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, ExtraReadonlyFieldsOnUpdateMixin,
                       admin.ModelAdmin):
    list_display = ('__str__', 'type')
    list_filter = ('type',)
    extra_readonly_fields_on_update = ('access_code',)
    search_fields = ('user__first_name', 'user__last_name', 'user__username', 'user__email')
    raw_id_fields = ('user', 'resource')


class ResourceTypeAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    pass


class EquipmentCategoryAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    pass


class PurposeAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    pass

class UniversalFieldAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass

class ResourceUniversalFormOptionAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    pass

class TermsOfUseAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, TranslationAdmin):
    list_display = ['name', 'terms_type']
    pass


class ReservationMetadataSetForm(forms.ModelForm):
    supported_fields = forms.ModelMultipleChoiceField(
        ReservationMetadataField.objects.all(),
        widget=FilteredSelectMultiple(_('Supported fields'), False),
        required=False)
    required_fields = forms.ModelMultipleChoiceField(
        ReservationMetadataField.objects.all(),
        widget=FilteredSelectMultiple(_('Required fields'), False),
        required=False)

    class Meta:
        model = ReservationMetadataSet
        exclude = CommonExcludeMixin.exclude + ('id',)

    def clean(self):
        supported = set(self.cleaned_data.get('supported_fields', []))
        required = set(self.cleaned_data.get('required_fields', []))
        if not required.issubset(supported):
            raise ValidationError(_('Required fields must be a subset of supported fields'))
        return self.cleaned_data


class ReservationMetadataSetAdmin(PopulateCreatedAndModifiedMixin, admin.ModelAdmin):
    exclude = CommonExcludeMixin.exclude + ('id',)
    form = ReservationMetadataSetForm

class ReservationHomeMunicipalityFieldAdmin(CommonExcludeMixin, TranslationAdmin):
    pass

class ReservationHomeMunicipalitySetForm(forms.ModelForm):
    class Meta:
        model = ReservationHomeMunicipalitySet
        exclude = CommonExcludeMixin.exclude + ('id',)

class ReservationHomeMunicipalitySetAdmin(PopulateCreatedAndModifiedMixin, admin.ModelAdmin):
    exclude = CommonExcludeMixin.exclude + ('id',)
    form = ReservationHomeMunicipalitySetForm

class ResourceGroupAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, FixedGuardedModelAdminMixin,
                         admin.ModelAdmin):
    pass


class MunicipalityAdmin(PopulateCreatedAndModifiedMixin, CommonExcludeMixin, admin.ModelAdmin):
    change_list_template = 'admin/municipalities/import_buttons.html'
    import_template = 'admin/municipalities/import_template.html'

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_urls(self):
        urls = super(MunicipalityAdmin, self).get_urls()
        extra_urls = [
            re_path(r'^municipalities_import/$', self.admin_site.admin_view(self.municipalities_import),
                name='municipalities_import'),
            re_path(r'^divisions_helsinki_import/$', self.admin_site.admin_view(self.divisions_helsinki_import),
                name='divisions_helsinki_import'),
        ]
        return extra_urls + urls

    def municipalities_import(self, request):
        context = dict(
            self.admin_site.each_context(request),
        )
        out = StringIO()
        with redirect_stdout(out):
            try:
                call_command('geo_import', '--municipalities', 'finland', stdout=out)
                context['command_output'] = out.getvalue()
            except Exception as e:
                context['command_output'] = 'Running import script caused the following exception: {0}'.format(str(e))
                logger.exception('Running import script caused an exception')
        context['title'] = _('Import municipalities')
        context['opts'] = self.model._meta
        return TemplateResponse(request, self.import_template, context)

    def divisions_helsinki_import(self, request):
        context = dict(
            self.admin_site.each_context(request),
        )
        out = StringIO()
        with redirect_stdout(out):
            try:
                call_command('geo_import', '--divisions', 'helsinki', stdout=out)
                context['command_output'] = out.getvalue()
            except Exception as e:
                context['command_output'] = 'Running import script caused the following exception: {0}'.format(str(e))
                logger.exception('Running import script caused an exception')
        context['title'] = _('Import divisions')
        context['opts'] = self.model._meta
        return TemplateResponse(request, self.import_template, context)


class AccessibilityViewpointAdmin(TranslationAdmin):
    pass


class ResourceAccessibilityAdmin(admin.ModelAdmin):
    list_display = ('resource', 'viewpoint', 'value')
    list_filter = ('value',)
    raw_id_fields = ('resource',)
    search_fields = ('resource__name', 'viewpoint__name')


class ReservationMetadataFieldForm(forms.ModelForm):
    class Meta:
        model = ReservationMetadataField
        fields = ('field_name',)
        widgets = {
            'field_name': forms.Select()
        }


class ReservationMetadataFieldAdmin(admin.ModelAdmin):
    form = ReservationMetadataFieldForm
    ordering = ('field_name',)

    def get_label(self, obj):
        return str(obj.field_name)

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'field_name':
            # limit choices to valid field names that are not yet in use
            all_choices = [(f, str(f)) for f in sorted(RESERVATION_EXTRA_FIELDS)]
            kwargs['widget'].choices = [
                c for c in all_choices
                if c[0] not in ReservationMetadataField.objects.values_list('field_name', flat=True)
            ]
        return super().formfield_for_dbfield(db_field, **kwargs)


class ReservationInline(admin.StackedInline):
    model = Reservation
    fields = ('resource', 'begin', 'end', )
    readonly_fields = ('resource', 'begin', 'end', )
    show_change_link = True
    extra = 0

    def __init__(self, *args, **kwargs):
        super(ReservationInline, self).__init__(*args, **kwargs)
        for perm in ('change', 'add'):
            setattr(self, 'has_%s_permission' % perm, lambda *args, **kwargs: False)

class ReservationBulkAdmin(admin.ModelAdmin):
    inlines = [
        ReservationInline
    ]
    readonly_fields = (
        'created_by', 'created_at',
        'modified_by', 'modified_at',
    )

class ReservationReminderAdmin(admin.ModelAdmin):
    extra_readonly_fields_on_update = ('reservation_type',)

# Override TokenAdmin of django rest framework
# to use raw_id_field on user
class RespaTokenAdmin(admin.ModelAdmin):
    list_display = ('key', 'user', 'created')
    fields = ('user',)
    ordering = ('-created',)
    raw_id_fields = ('user',)



admin_site.register(ResourceImage, ResourceImageAdmin)
admin_site.register(Resource, ResourceAdmin)
admin_site.register(Reservation, ReservationAdmin)
admin_site.register(ResourceType, ResourceTypeAdmin)
admin_site.register(Purpose, PurposeAdmin)
admin_site.register(Day)
admin_site.register(Unit, UnitAdmin)
admin_site.register(Equipment, EquipmentAdmin)
admin_site.register(ResourceEquipment, ResourceEquipmentAdmin)
admin_site.register(EquipmentCategory, EquipmentCategoryAdmin)
admin_site.register(TermsOfUse, TermsOfUseAdmin)
admin_site.register(ReservationMetadataField, ReservationMetadataFieldAdmin)
admin.site.register(ReservationBulk, ReservationBulkAdmin)
admin.site.register(ReservationReminder, ReservationReminderAdmin)
admin_site.register(ReservationMetadataSet, ReservationMetadataSetAdmin)
admin_site.register(ReservationHomeMunicipalityField, ReservationHomeMunicipalityFieldAdmin)
admin_site.register(ReservationHomeMunicipalitySet, ReservationHomeMunicipalitySetAdmin)
admin.site.register(ResourceGroup, ResourceGroupAdmin)
if admin.site.is_registered(Municipality):
    admin.site.unregister(Municipality)
admin.site.register(Municipality, MunicipalityAdmin)
admin.site.register(AccessibilityViewpoint, AccessibilityViewpointAdmin)
admin.site.register(AccessibilityValue)
admin.site.register(ResourceAccessibility, ResourceAccessibilityAdmin)

if admin.site.is_registered(Token):
    admin.site.unregister(Token)
admin_site.register(Token, RespaTokenAdmin)
admin_site.register(UniversalFormFieldType, UniversalFieldAdmin)
admin_site.register(ResourceUniversalFormOption, ResourceUniversalFormOptionAdmin)
