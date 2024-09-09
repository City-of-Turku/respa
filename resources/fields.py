from django.db import models
from django.conf import settings

class EquipmentField(models.ManyToManyField):
    """
    Model field for Equipment M2M in Resource.

    Used for overriding save_form_data so that it allows saving the form
    m2m field even though there is an intermediary model.
    """
    def save_form_data(self, instance, data):
        # data is a queryset of equipment
        # instance is a Resource
        instance_equipment = getattr(instance, self.attname)  # ManyRelatedManager

        # The through model (a.k.a intermediate table)
        through_model = instance_equipment.through

        # Delete the relations that were unchecked from the form
        equipment_to_delete = instance_equipment.exclude(pk__in=data)
        for equipment in equipment_to_delete:
            through_model.objects.filter(resource=instance, equipment=equipment).delete()

        # Add new relations for those that don't exist yet
        for equipment in data:
            if not instance_equipment.filter(pk=equipment).exists():
                through_model.objects.update_or_create(resource=instance, equipment=equipment)


# Since we treat translated CharFields and TextFields as DictFields in API,
# We have to ensure that the field value isn't a stringified dict.
class TranslatedCharField(models.CharField):
    """Ensure CharField value isn't stringified dict"""
    def to_python(self, value) -> str:
        if isinstance(value, dict):
            return super().to_python(value.get(self.get_language(), ''))
        return super().to_python(value)
    
    def get_language(self) -> str:
        """Returns the language set for the field"""
        language = self.name.split('_')[-1].lower()
        if language not in ['fi', 'sv', 'en']:
            return settings.LANGUAGE_CODE # Fallback
        return language

    
class TranslatedTextField(models.TextField):
    """Ensure TextField value isn't stringified dict"""
    def to_python(self, value) -> str:
        if isinstance(value, dict):
            return super().to_python(value.get(self.get_language(), ''))
        return super().to_python(value)

    def get_language(self) -> str:
        """Returns the language set for the field"""
        language = self.name.split('_')[-1].lower()
        if language not in ['fi', 'sv', 'en']:
            return settings.LANGUAGE_CODE # Fallback
        return language

class MultiEmailField(models.TextField):
    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        return [val.strip() for val in value.splitlines() if val]
    
    def get_db_prep_value(self, value, connection, prepared):
        if isinstance(value, list):
            return '\n'.join(value)
        return value

    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)
