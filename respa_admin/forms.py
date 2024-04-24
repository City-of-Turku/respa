from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.forms.formsets import DELETION_FIELD_NAME
from guardian.core import ObjectPermissionChecker

from .widgets import (
    RespaCheckboxSelect,
    RespaCheckboxInput,
    RespaGenericCheckboxInput,
    RespaRadioSelect,
)

from resources.models import (
    Day,
    Equipment,
    Period,
    Purpose,
    Resource,
    ResourceImage,
    ResourceTag,
    Unit,
    UnitAuthorization,
    TermsOfUse,
    ResourceUniversalField,
    ResourceUniversalFormOption,
    ResourcePublishDate
)

from users.models import User

from respa.settings import LANGUAGES

from multi_email_field.forms import MultiEmailField

hour_increment_choices = (
    ('00:00:00', '0 h'),
    ('01:00:00', '1 h'),
    ('02:00:00', '2 h'),
    ('03:00:00', '3 h'),
    ('04:00:00', '4 h'),
    ('05:00:00', '5 h'),
    ('06:00:00', '6 h'),
    ('07:00:00', '7 h'),
    ('08:00:00', '8 h'),
    ('09:00:00', '9 h'),
    ('10:00:00', '10 h'),
)

thirty_minute_increment_choices = (
    ('00:30:00', '0,5 h'),
    ('01:00:00', '1 h'),
    ('01:30:00', '1,5 h'),
    ('02:00:00', '2 h'),
    ('02:30:00', '2,5 h'),
    ('03:00:00', '3 h'),
    ('03:30:00', '3,5 h'),
    ('04:00:00', '4 h'),
    ('04:30:00', '4,5 h'),
    ('05:00:00', '5 h'),
    ('05:30:00', '5,5 h'),
    ('06:00:00', '6 h'),
    ('06:30:00', '6,5 h'),
    ('07:00:00', '7 h'),
    ('07:30:00', '7,5 h'),
    ('08:00:00', '8 h'),
    ('08:30:00', '8,5 h'),
    ('09:00:00', '9 h'),
    ('09:30:00', '9,5 h'),
    ('10:00:00', '10 h'),
    ('10:30:00', '10,5 h'),
    ('11:00:00', '11 h'),
    ('11:30:00', '11,5 h'),
    ('12:00:00', '12 h'),
    ('12:30:00', '12,5 h'),
    ('13:00:00', '13 h'),
    ('13:30:00', '13,5 h'),
    ('14:00:00', '14 h'),
    ('14:30:00', '14,5 h'),
    ('15:00:00', '15 h'),
    ('15:30:00', '15,5 h'),
    ('16:00:00', '16 h'),
    ('16:30:00', '16,5 h'),
    ('17:00:00', '17 h'),
    ('17:30:00', '17,5 h'),
    ('18:00:00', '18 h'),
    ('18:30:00', '18,5 h'),
    ('19:00:00', '19 h'),
    ('19:30:00', '19,5 h'),
    ('20:00:00', '20 h'),
    ('20:30:00', '20,5 h'),
    ('21:00:00', '21 h'),
    ('21:30:00', '21,5 h'),
    ('22:00:00', '22 h'),
    ('22:30:00', '22,5 h'),
    ('23:00:00', '23 h'),
    ('23:30:00', '23,5 h'),
)


class DaysForm(forms.ModelForm):
    opens = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            format='%H:%M',
            attrs={'class': 'text-input form-control',
                   'placeholder': 'hh:mm'}
        )
    )

    closes = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            format='%H:%M',
            attrs={'class': 'text-input form-control',
                   'placeholder': 'hh:mm'}
        )
    )

    closed = forms.NullBooleanField(
        widget=RespaCheckboxInput,
    )

    class Meta:
        model = Day
        fields = ['weekday', 'opens', 'closes', 'closed']

    def clean(self):
        cleaned_data = super().clean()
        opens = cleaned_data.get('opens', None)
        closes = cleaned_data.get('closes', None)
        is_closed = cleaned_data.get('closed', False)
        if (not opens or not closes):
            if not is_closed and (not self.has_error('opens') and not self.has_error('closes')):
                self.add_error('period', _('Missing opening or closing time'))
        else:
            if opens > closes:
                self.add_error('period', _('Opening time cannot be greater than closing time'))

        return cleaned_data


class PeriodForm(forms.ModelForm):
    name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'text-input form-control'})
    )

    start = forms.DateField(
        required=True,
        widget=forms.DateInput(
            attrs={
                'class': 'text-input form-control datepicker',
                'data-provide': 'datepicker',
                'data-date-format': _("yyyy-mm-dd"),
                'data-date-language': 'fi',
            }
        )
    )

    end = forms.DateField(
        required=True,
        widget=forms.DateInput(
            attrs={
                'class': 'text-input form-control datepicker',
                'data-provide': 'datepicker',
                'data-date-format': _("yyyy-mm-dd"),
                'data-date-language': 'fi',
            }
        )
    )

    class Meta:
        model = Period
        fields = ['name', 'start', 'end']


class ImageForm(forms.ModelForm):
    class Meta:
        model = ResourceImage
        translated_fields = ['caption_fi', 'caption_en', 'caption_sv']
        fields = ['image', 'type'] + translated_fields


class ResourceTagField(forms.CharField):
    def to_python(self, value):
        if not value:
            return []
        if not isinstance(value, list):
            value = value.splitlines()
        data = {
            'remove': [],
            'create': []
        }

        for val in value:
            if val.startswith('remove_'):
                tag = val.split('remove_')[1].strip()
                if tag in data['remove']:
                    continue
                data['remove'].append(tag)
            elif val.startswith('create_'):
                tag = val.split('create_')[1].strip()
                if tag in data['create']:
                    continue
                data['create'].append(tag)
        return data


class RespaMultiEmailField(MultiEmailField):
    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        return [val.strip() for val in value.splitlines() if val]


class ResourceForm(forms.ModelForm):
    purposes = forms.ModelMultipleChoiceField(
        widget=RespaCheckboxSelect,
        queryset=Purpose.objects.all(),
        required=True,
    )

    equipment = forms.ModelMultipleChoiceField(
        required=False,
        widget=RespaCheckboxSelect,
        queryset=Equipment.objects.all(),
    )

    name_fi = forms.CharField(
        required=True,
        label='Nimi [fi]',
    )

    resource_tags = ResourceTagField(
        required=False,
        label=_('Keywords')
    )

    resource_staff_emails = RespaMultiEmailField(
        required=False,
        label=_('E-mail addresses for client correspondence')
    )

    public = forms.BooleanField(
        widget=forms.Select(
            choices=((False, _('Hidden')), (True, _('Published')))
        ),
        label=_('Public'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(ResourceForm, self).__init__(*args, **kwargs)
        self.fields['generic_terms'].queryset = TermsOfUse.objects.filter(terms_type=TermsOfUse.TERMS_TYPE_GENERIC)
        self.fields['payment_terms'].queryset = TermsOfUse.objects.filter(terms_type=TermsOfUse.TERMS_TYPE_PAYMENT)
        if self.instance:
            if self.instance.publish_date:
                self.fields['public'].widget.choices = (((None), _('Scheduled publish')), )

            df_set = self.instance.get_disabled_fields()
            if df_set:
                for field in set(df_set) - set(['groups', 'periods', 'images', 'free_of_charge']):
                    self.fields[field].disabled = True

    class Meta:
        model = Resource

        translated_fields = [
            'name_fi',
            'name_en',
            'name_sv',
            'description_fi',
            'description_en',
            'description_sv',
            'reservation_info_fi',
            'reservation_info_en',
            'reservation_info_sv',
            'specific_terms_fi',
            'specific_terms_en',
            'specific_terms_sv',
            'reservation_requested_notification_extra_fi',
            'reservation_requested_notification_extra_en',
            'reservation_requested_notification_extra_sv',
            'reservation_confirmed_notification_extra_fi',
            'reservation_confirmed_notification_extra_en',
            'reservation_confirmed_notification_extra_sv',
            'responsible_contact_info_fi',
            'responsible_contact_info_en',
            'responsible_contact_info_sv',
            'reservation_additional_information_fi',
            'reservation_additional_information_en',
            'reservation_additional_information_sv',
        ]

        fields = [
            'unit',
            'type',
            'purposes',
            'equipment',
            'external_reservation_url',
            'people_capacity',
            'min_age',
            'max_age',
            'area',
            'min_period',
            'max_period',
            'slot_size',
            'cooldown',
            'reservable_max_days_in_advance',
            'reservable_min_days_in_advance',
            'max_reservations_per_user',
            'reservation_feedback_url',
            'reservable',
            'need_manual_confirmation',
            'authentication',
            'resource_staff_emails',
            'access_code_type',
            'max_price',
            'min_price',
            'price_type',
            'generic_terms',
            'payment_terms',
            'public',
            'reservation_metadata_set',
            'reservation_home_municipality_set',
            'resource_tags',
            'payment_requested_waiting_time',
            'cash_payments_allowed',
            'reservable_by_all_staff'
        ] + translated_fields

        widgets = {
            'min_period': forms.Select(
                choices=(thirty_minute_increment_choices)
            ),
            'max_period': forms.Select(
                choices=(thirty_minute_increment_choices)
            ),
            'slot_size': forms.Select(
                choices=(thirty_minute_increment_choices)
            ),
            'cooldown': forms.Select(
                choices=(
                    (('00:00:00', '0 h'), ) + thirty_minute_increment_choices
                )
            ),
            'need_manual_confirmation': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
            'reservable': forms.Select(
                choices=((False, _('Can not be reserved')), (True, _('Bookable')))
            ),
            'cash_payments_allowed': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
            'reservable_by_all_staff': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
        }

    def get_resource_tags(self):
        tags = list(ResourceTag.objects.filter(resource=self.instance).values_list('label', flat=True))
        tags.extend(tag for tag in self.instance.tags.names() if tag not in tags)
        return tags

    def get_initial_for_field(self, field, field_name):
        if field_name == 'resource_tags' and self.instance.pk:
            self.initial['resource_tags'] = self.get_resource_tags()
        elif field_name == 'public':
            self.initial['public'] = self.instance.public
        return super().get_initial_for_field(field, field_name)

    def save(self, commit=True):
        resource_tags = self.cleaned_data.pop('resource_tags', [])
        super().save(commit=commit)

        if isinstance(resource_tags, dict):
            ResourceTag.objects.filter(resource=self.instance, label__in=resource_tags['remove']).delete()
            old_tags = list(ResourceTag.objects.filter(resource=self.instance).values_list('label', flat=True))
            old_tags.extend([tag for tag in self.instance.tags.names() if tag not in old_tags])
            cleaned_tags = [
                ResourceTag(label=tag, resource=self.instance)
                for tag in resource_tags['create'] if tag not in old_tags
            ]

            # Swap from old tag system to new
            for tag in self.instance.tags.all():
                cleaned_tags.append(
                    ResourceTag(label=str(tag), resource=self.instance)
                )
                tag.delete()
            for tag in cleaned_tags:
                tag.save()

        return self.instance


class UnitForm(forms.ModelForm):
    name_fi = forms.CharField(
        required=True,
        label='Nimi [fi]',
    )

    street_address_fi = forms.CharField(
        required=True,
        label=f"{_('Street address')} [fi]"
    )

    class Meta:
        model = Unit

        translated_fields = [
            'description_en',
            'description_fi',
            'description_sv',
            'name_en',
            'name_fi',
            'name_sv',
            'street_address_en',
            'street_address_fi',
            'street_address_sv',
            'www_url_en',
            'www_url_fi',
            'www_url_sv',
        ]

        fields = [
            'address_zip',
            'municipality',
            'phone',
            'disallow_overlapping_reservations',
            'disallow_overlapping_reservations_per_user',
            'payment_requested_waiting_time'
        ] + translated_fields

        widgets = {
            'disallow_overlapping_reservations': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
            'disallow_overlapping_reservations_per_user': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
        }


class PeriodFormset(forms.BaseInlineFormSet):

    def _get_days_formset(self, form, extra_days=1):
        days_formset = inlineformset_factory(
            Period,
            Day,
            form=DaysForm,
            extra=extra_days,
            validate_max=True
        )

        if self.instance and self.instance.pk:
            df_set = self.instance.get_disabled_fields()
            for _, field in days_formset.form.base_fields.items():
                field.disabled = 'periods' in df_set
                if field.disabled:
                    field.required = False

        return days_formset(
            instance=form.instance,
            data=form.data if form.is_bound else None,
            prefix='days-%s' % (
                form.prefix,
            ),
        )

    def add_fields(self, form, index):
        super(PeriodFormset, self).add_fields(form, index)
        form.days = self._get_days_formset(form=form)

    def is_valid(self):
        valid_form = super(PeriodFormset, self).is_valid()
        if not valid_form:
            return valid_form

        # Do additional checks on top of the built in checks to
        # validate that nested days are also valid
        valid_days = []
        for form in self.forms:
            valid_days.append(form.days.is_valid())
            if not form.days.is_valid():
                if hasattr(form, 'cleaned_data'):
                    form.add_error(None, form.days.errors)

        return valid_form and all(valid_days)

    def save(self, commit=True):
        saved_form = super(PeriodFormset, self).save(commit=commit)

        if saved_form or self.forms:
            for form in self.forms:
                form.save(commit=commit)
                if hasattr(form, 'days'):
                    form.days.save(commit=commit)

        return saved_form


def get_period_formset(request=None, extra=1, instance=None, parent_class=Resource):
    period_formset_with_days = inlineformset_factory(
        parent_class,
        Period,
        fk_name=parent_class._meta.model_name,
        form=PeriodForm,
        formset=PeriodFormset,
        extra=extra,
    )

    if instance:
        df_set = instance.get_disabled_fields()
        for _, field in period_formset_with_days.form.base_fields.items():
            field.disabled = 'periods' in df_set
            if field.disabled:
                field.required = False
    else:  # fields are getting cached?
        for _, field in period_formset_with_days.form.base_fields.items():
            field.disabled = False

    if not request:
        return period_formset_with_days(instance=instance)
    if request.method == 'GET':
        return period_formset_with_days(instance=instance)
    else:
        return period_formset_with_days(data=request.POST, instance=instance)


class ResourcePublishDateForm(forms.ModelForm):
    class Meta:
        model = ResourcePublishDate
        fields = ('begin', 'end', 'reservable')

        widgets = {
            'begin':  forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local'
                }),
            'end':  forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local'
                }),
            'reservable': RespaRadioSelect(
                choices=((True, _('Yes')), (False, _('No')))
            ),
        }
    

def get_resource_publish_date_formset(request=None, instance=None, **kwargs):
    publish_date_formset = inlineformset_factory(
        Resource,
        ResourcePublishDate,
        fk_name=Resource._meta.model_name,
        form=ResourcePublishDateForm,
        extra=1,
        can_delete=True,
        can_delete_extra=True,
        max_num=1
    )

    if not request:
        return publish_date_formset(instance=instance)
    if request.method == 'GET':
        return publish_date_formset(instance=instance)
    else:
        return publish_date_formset(data=request.POST, instance=instance)

class UniversalFieldForm(forms.ModelForm):
    class Meta:
        model = ResourceUniversalField
        translated_fields = ['description_fi', 'description_en', 'description_sv', 'label_fi', 'label_en', 'label_sv']
        fields = ['field_type', 'name', 'data'] + translated_fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['label_fi'].help_text = _('Universal value inherit info')
        self.fields['description_fi'].help_text = _('Universal value inherit info')

    def clean(self):
        cleaned_data = super().clean()
        label_val = cleaned_data.get('label_fi')
        desc_val = cleaned_data.get('description_fi')
        # set missing language values to same value as the required finnish value.
        for x in ['label_en', 'label_sv', 'description_en', 'description_sv']:
            if not cleaned_data[x]:
                if 'label' in x and label_val:
                    cleaned_data[x] = label_val
                elif 'description' in x and desc_val:
                    cleaned_data[x] = desc_val
                else:
                    raise ValidationError("Missing values for 'label_fi' and 'description_fi'.")

        return cleaned_data


def get_resource_universal_formset(request=None, extra=1, instance=None):
    parent = Resource
    resource_universal_formset = inlineformset_factory(
        parent,
        ResourceUniversalField,
        fk_name=parent._meta.model_name,
        form=UniversalFieldForm,
        extra=extra,
        can_delete=True,
        max_num=1,
    )

    for _, field in resource_universal_formset.form.base_fields.items():
        if _ in ['name', 'description_fi', 'label_fi', 'field_type']:
            # field_type,name, description_fi and label_fi set to required.
            field.required = True
        else:
            field.required = False

    if not request:
        return resource_universal_formset(instance=instance)
    if request.method == 'GET':
        return resource_universal_formset(instance=instance)
    else:
        return resource_universal_formset(data=request.POST, instance=instance)


class OptionsForm(forms.ModelForm):
    class Meta:
        model = ResourceUniversalFormOption
        translated_fields = ['text_fi', 'text_sv', 'text_en']
        fields = ['resource_universal_field', 'name', 'sort_order'] + translated_fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text_fi'].help_text = _('Universal value inherit info')

    def clean(self):
        cleaned_data = super().clean()
        text_fi_value = cleaned_data.get('text_fi')
        if text_fi_value:
            # set missing language texts to same value as 'text_fi'
            for x in ['text_sv', 'text_en']:
                if not cleaned_data[x]:
                    cleaned_data[x] = text_fi_value

        return cleaned_data


def get_universal_options_formset(request=None, extra=1, instance=None):
    parent = Resource
    universal_options_formset = inlineformset_factory(
        parent,
        ResourceUniversalFormOption,
        fk_name=parent._meta.model_name,
        form=OptionsForm,
        can_delete=True,
        can_order=True,
        extra=extra,
    )
    # option forms is enabled if the resource has a saved universal field.
    if instance and ResourceUniversalField.objects.filter(resource=instance).count():
        for _, field in universal_options_formset.form.base_fields.items():
            # the following fields are set as required fields.
            if _ in ['name', 'resource_universal_field', 'sort_order', 'text_fi']:
                field.required = True
                if _ == 'sort_order':
                    # set initial order to current options count + 1
                    current_options_count = ResourceUniversalFormOption.objects.filter(resource=instance).count()
                    field.initial = current_options_count + 1
                if _ == 'resource_universal_field':
                    # Select options should only include ResourceUniversalField objects that have this resource.
                    field.queryset = ResourceUniversalField.objects.filter(resource=instance)
            else:
                field.required = False
    else:
        for _, field in universal_options_formset.form.base_fields.items():
            field.disabled = True
            field.required = False

    if not request:
        return universal_options_formset(instance=instance)

    if request.method == 'GET':
        return universal_options_formset(instance=instance)
    else:
        return universal_options_formset(data=request.POST, instance=instance)


def get_resource_image_formset(request=None, extra=1, instance=None):
    resource_image_formset = inlineformset_factory(
        Resource,
        ResourceImage,
        form=ImageForm,
        extra=extra,
    )

    if instance:
        df_set = instance.get_disabled_fields()
        for _, field in resource_image_formset.form.base_fields.items():
            field.disabled = 'images' in df_set
            if field.disabled:
                field.required = False
    else:  # fields are getting cached?
        for _, field in resource_image_formset.form.base_fields.items():
            field.disabled = False

    if not request:
        return resource_image_formset(instance=instance)

    if request.method == 'GET':
        return resource_image_formset(instance=instance)
    return resource_image_formset(data=request.POST, files=request.FILES, instance=instance)


def get_translated_field_count(image_formset=None):
    """
    Serve a count of how many fields are possible to translate with the translate
    buttons in the UI. The image formset is passed as a parameter since it can hold
    a number of forms with fields which can be translated.

    :param image_formset: formset holding images
    :return: dictionary of all languages as keys and the count of translated fields
    in corresponding language.
    """
    resource_form_data = ResourceForm.Meta.translated_fields
    translated_fields = resource_form_data
    lang_num = {}

    if translated_fields:
        for key, value in LANGUAGES:
            postfix = '_' + key
            images_fields_count = _get_images_formset_translated_fields(image_formset, postfix)
            lang_num[key] = sum(x.endswith(postfix) for x in translated_fields) + images_fields_count

    return lang_num


def _get_images_formset_translated_fields(images_formset, lang_postfix):
    if images_formset is None:
        return 0
    image_forms = images_formset.forms
    images_translation_count = 0

    for form in image_forms:
        if form.initial:
            images_translation_count += len([x for x in form.initial if x.endswith(lang_postfix)])

    return images_translation_count


class UserForm(forms.ModelForm):

    class Meta:
        model = User

        fields = [
            'is_staff',
        ]

        widgets = {
            'is_staff': RespaGenericCheckboxInput(attrs={
                'label': _('Staff account'),
                'help_text': _('Allows user to grant permissions to units')
            })
        }


class UnitAuthorizationForm(forms.ModelForm):
    can_approve_reservation = forms.BooleanField(widget=RespaGenericCheckboxInput, required=False)

    def __init__(self, *args, **kwargs):
        permission_checker = kwargs.pop('permission_checker')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        can_approve_initial_value = False
        if self.instance.pk:
            unit = self.instance.subject
            user_has_unit_auth = self.request.user.unit_authorizations.to_unit(unit).admin_level().exists() \
                or self.request.user.is_superuser
            user_has_unit_group_auth = self.request.user.unit_group_authorizations.to_unit(unit).admin_level().exists()
            can_approve_initial_value = permission_checker.has_perm(
                "unit:can_approve_reservation", self.instance.subject
            )
            if not user_has_unit_auth and not user_has_unit_group_auth:
                self.fields['subject'].disabled = True
                self.fields['level'].disabled = True
                self.fields['can_approve_reservation'].disabled = True
                self.is_disabled = True
            self.fields['can_approve_reservation'].widget.attrs['data-unit-id'] = f'{unit.id}'
        self.fields['can_approve_reservation'].initial = can_approve_initial_value

    def clean(self):
        cleaned_data = super().clean()
        unit = cleaned_data.get('subject')
        user_has_unit_auth = self.request.user.unit_authorizations.to_unit(unit).admin_level().exists() \
            or self.request.user.is_superuser
        user_has_unit_group_auth = self.request.user.unit_group_authorizations.to_unit(unit).admin_level().exists()
        if self.has_changed():
            if not user_has_unit_auth and not user_has_unit_group_auth:
                self.add_error('subject', _('You can\'t add, change or delete permissions to unit you are not admin of'))
                self.cleaned_data[DELETION_FIELD_NAME] = False
            if self.cleaned_data[DELETION_FIELD_NAME]:
                self.cleaned_data['can_approve_reservation'] = False
        return cleaned_data

    class Meta:
        model = UnitAuthorization

        fields = [
            'subject',
            'level',
            'authorized',
        ]


class UnitAuthorizationFormSet(forms.BaseInlineFormSet):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.permission_checker = ObjectPermissionChecker(kwargs['instance'])
        self.permission_checker.prefetch_perms(Unit.objects.filter(authorizations__authorized=kwargs['instance']))

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['permission_checker'] = self.permission_checker
        kwargs['request'] = self.request
        return kwargs


def get_unit_authorization_formset(request=None, extra=1, instance=None):
    unit_authorization_formset = inlineformset_factory(
        User,
        UnitAuthorization,
        form=UnitAuthorizationForm,
        formset=UnitAuthorizationFormSet,
        extra=extra,
    )

    if not request:
        return unit_authorization_formset(instance=instance)
    if request.method == 'GET':
        return unit_authorization_formset(request=request, instance=instance)
    else:
        return unit_authorization_formset(request=request, data=request.POST, instance=instance)
