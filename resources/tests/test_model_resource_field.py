import pytest

from resources.models import UniversalFormFieldType


@pytest.mark.django_db
def test_universal_form_field_type_str_and_generated_id():
    field_type = UniversalFormFieldType.objects.create(type="Select")
    assert str(field_type) == "Select"
    assert field_type.id
