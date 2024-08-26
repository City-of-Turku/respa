from django.db import models
from helusers.models import AbstractUser
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from resources.models import Resource
import datetime

class LoginMethod(models.Model):
    id = models.CharField(verbose_name=_('Id'), unique=True, primary_key=True)
    name = models.CharField(verbose_name=_('Name'), blank=False, null=False)
    icon = models.FileField(upload_to='loginmethod_icons', validators=[FileExtensionValidator(['svg'])],
                            null=True, blank=True)
    
    @property
    def is_strong_auth(self):
        return self.id in settings.STRONG_AUTH_CLAIMS

    def __str__(self):
        return f'{self.name} ({self.id})' if self.name else self.id
    
    class Meta:
        verbose_name = _('Login method')
        verbose_name_plural = _('Login methods')

class User(AbstractUser):
    first_name = models.CharField(verbose_name=_('First name'), max_length=100, null=True, blank=True)
    last_name = models.CharField(verbose_name=_('Last name'), max_length=100, null=True, blank=True)
    email = models.CharField(verbose_name=_('Email'), null=True, max_length=100)
    birthdate = models.DateField(null=True, blank=True, verbose_name=_('Birthdate'))
    oid = models.CharField(verbose_name=_('Oid'), max_length=255, null=True, blank=True)
    amr = models.ForeignKey(LoginMethod,
                            on_delete=models.SET_NULL,
                            verbose_name=_('Login method'), null=True, blank=True)

    ical_token = models.SlugField(
        max_length=16, null=True, blank=True, unique=True, db_index=True, verbose_name="iCal token"
    )
    preferred_language = models.CharField(max_length=8, null=True, blank=True,
                                          verbose_name="Preferred UI language",
                                          choices=settings.LANGUAGES)
    favorite_resources = models.ManyToManyField(Resource, blank=True, verbose_name=_('Favorite resources'),
                                                related_name='favorited_by')

    # Duplicate the is staff field from the abstract base class to here
    # so that we can override the verbose name and help text.
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_(
            "Designates whether the user can log into "
            "Django Admin or Respa Admin sites."))

    is_general_admin = models.BooleanField(
        default=False, verbose_name=_("general administrator status"),
        help_text=_(
            "Designates whether the user is a General Administrator "
            "with special permissions to many objects within Respa. "
            "This is almost as powerful as superuser."))

    @property
    def is_strong_auth(self):
        return self.amr and self.amr.is_strong_auth

    def __str__(self):
        display_name = str('%s %s' % (self.first_name or '', self.last_name or '')).strip()
        if display_name:
            return f'{display_name} ({self.email})'
        return str('%s %s' % (self.username, f'({self.email})' if self.email else '')).strip()



    class Meta:
        ordering = ('id',)
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def get_display_name(self):
        return '{0} {1}'.format(self.first_name, self.last_name).strip()

    def get_or_create_ical_token(self, recreate=False):
        if not self.ical_token or recreate:
            self.ical_token = get_random_string(length=16)
            self.save()
        return self.ical_token

    def get_preferred_language(self):
        if self.preferred_language:
            return self.preferred_language
        return settings.LANGUAGES[0][0]

    def get_user_age(self):
        return int((datetime.date.today() - datetime.datetime.strptime(str(self.birthdate), '%Y-%m-%d').date()).days / 365.25)

    def has_outlook_link(self):
        return getattr(self, 'outlookcalendarlink', False)


class ResourceOrder(models.TextField):
    description = "A custom field to store a comma-separated list of resource IDs"

    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        return value.split(',')

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self.to_python(value)

    def get_prep_value(self, value):
        if not value:
            return ''
        if isinstance(value, list):
            return ','.join(map(str, value))
        raise ValidationError("Value must be a list")

    def validate(self, value, model_instance):
        if not isinstance(value, list):
            raise ValidationError("Value must be a list")
        super().validate(value, model_instance)


class ExtraPrefs(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    admin_resource_order = ResourceOrder()

    def __str__(self):
        return f"{_('Extra preferences')} ({self.id})"
