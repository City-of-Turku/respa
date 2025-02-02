import random
import uuid
from .models import LoginMethod
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib import admin
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from resources.models import Reservation
from resources.models.utils import generate_id
from respa_admin.forms import RespaSVGField
from respa_admin.templatetags import templatetags
from allauth.socialaccount.models import SocialAccount, EmailAddress


User = get_user_model()

first_names_list = [
    'Patrick',
    'Julia',
    'Andrew',
    'Paige',
    'Ewan',
    'Elsie',
    'Toby',
    'Holly',
    'Dominic',
    'Isla',
    'Edison',
    'Luna',
    'Ronald',
    'Bryanna',
    'Augustus',
    'Laurel',
    'Miles',
    'Patricia',
    'Beckett',
    'Elle'
]

last_names_list = [
    'Ward',
    'Robertson',
    'Nicholson',
    'Armstrong',
    'White',
    'Trevino',
    'James',
    'Hines',
    'Clark',
    'Castro',
    'Read',
    'Brown',
    'Griffiths',
    'Taylor',
    'Cole',
    'Leach',
    'Chavez',
    'Stout',
    'Mccullough',
    'Richards'
]


def _add_general_admin_to_fieldsets(fieldsets):
    def modify_field_data(field_data):
        if 'is_superuser' in (field_data or {}).get('fields', ()):
            fields = list(field_data['fields'])
            fields.insert(fields.index('is_superuser'), 'is_general_admin')
            return dict(field_data, fields=tuple(fields))
        return field_data

    return tuple(
        (label, modify_field_data(field_data))
        for (label, field_data) in fieldsets)


def anonymize_user_data(modeladmin, request, queryset):
    for user in queryset:
        user.first_name = random.choice(first_names_list)
        user.last_name = random.choice(last_names_list)
        user.username = f'anonymized-{uuid.uuid4()}'
        user.email = f'{user.first_name}.{user.last_name}@anonymized.net'.lower()
        user.uuid = uuid.uuid4()
        user.save()

        SocialAccount.objects.filter(user=user).update(uid=user.uuid, extra_data='{}')
        EmailAddress.objects.filter(user=user).update(email=user.email)

        user_reservations = Reservation.objects.filter(user=user)
        user_reservations.update(
            state=Reservation.CANCELLED,
            event_subject='Removed',
            event_description='Sensitive data of this reservation has been anonymized by a script.',
            host_name='Removed',
            reservation_extra_questions='Removed',
            reserver_name='Removed',
            reserver_id='Removed',
            reserver_email_address='Removed',
            reserver_phone_number='Removed',
            reserver_address_street='Removed',
            reserver_address_zip='Removed',
            reserver_address_city='Removed',
            company='Removed',
            billing_first_name='Removed',
            billing_last_name='Removed',
            billing_email_address='Removed',
            billing_phone_number='Removed',
            billing_address_street='Removed',
            billing_address_zip='Removed',
            billing_address_city='Removed',
            participants='Removed'
        )
    anonymize_user_data.short_description = 'Anonymize user\'s personal information'


class UserAdmin(DjangoUserAdmin):
    fieldsets = _add_general_admin_to_fieldsets(DjangoUserAdmin.fieldsets) + (
        (None, {'fields': ('amr', 'department_name', 'uuid', 'favorite_resources')}),
    )
    list_display = [
        'uuid', 'username', 'email',
        'first_name', 'last_name',
        'is_staff', 'is_general_admin', 'is_superuser',
        'login_method'
    ]
    list_filter = [
        'is_staff', 'is_general_admin', 'is_superuser',
        'is_active',
        'groups',
    ]
    actions = [anonymize_user_data]

    def login_method(self, obj):
        return templatetags.get_login_method(obj)
    login_method.short_description = _('Login method')
    login_method.admin_order_field = 'amr__id'

class LoginMethodAdminForm(forms.ModelForm):
    icon = RespaSVGField(label=_('Icon'), required=False)

    class Meta:
        model = LoginMethod
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        icon = cleaned_data.get('icon')
        id = cleaned_data.get('id')
        if icon and isinstance(icon, str):
            cleaned_data['icon'] = ContentFile(icon, name=f'{id}_{generate_id()}.svg')
        return cleaned_data

class LoginMethodAdmin(admin.ModelAdmin):
    form = LoginMethodAdminForm
    list_display = ('__str__', 'is_strong_auth', )
    readonly_fields = ('is_strong_auth', )
    fieldsets = (
        (_('General'), {
            'fields': (
                'id', 'name', 'icon',
            )
        }),
    )

    def is_strong_auth(self, obj):
        return obj.is_strong_auth
    is_strong_auth.short_description = _('Strong authentication')
    is_strong_auth.boolean = True
           

admin.site.register(LoginMethod, LoginMethodAdmin)
admin.site.register(User, UserAdmin)
