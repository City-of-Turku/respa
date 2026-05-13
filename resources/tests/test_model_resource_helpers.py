import datetime

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from resources.models import Purpose, ResourceTag, TermsOfUse
from resources.models.resource import (
    Resource,
    determine_hours_time_range,
    generate_access_code,
    validate_access_code,
)


def test_generate_access_code_for_supported_and_unknown_types():
    assert generate_access_code(Resource.ACCESS_CODE_TYPE_NONE) == ""

    pin4 = generate_access_code(Resource.ACCESS_CODE_TYPE_PIN4)
    assert len(pin4) == 4
    assert pin4.isdigit()

    pin6 = generate_access_code(Resource.ACCESS_CODE_TYPE_PIN6)
    assert len(pin6) == 6
    assert pin6.isdigit()

    with pytest.raises(NotImplementedError):
        generate_access_code("unknown-type")


def test_validate_access_code_for_pin_types_and_errors():
    assert validate_access_code("1234", Resource.ACCESS_CODE_TYPE_PIN4) == "1234"
    assert validate_access_code("123456", Resource.ACCESS_CODE_TYPE_PIN6) == "123456"
    assert validate_access_code("", Resource.ACCESS_CODE_TYPE_NONE) is None

    with pytest.raises(ValidationError):
        validate_access_code("12a4", Resource.ACCESS_CODE_TYPE_PIN4)
    with pytest.raises(ValidationError):
        validate_access_code("12345", Resource.ACCESS_CODE_TYPE_PIN6)
    with pytest.raises(NotImplementedError):
        validate_access_code("1234", "invalid")


def test_determine_hours_time_range_handles_defaults_and_boundaries():
    tz = timezone.get_current_timezone()
    begin_date = datetime.date(2115, 1, 10)
    end_date = datetime.date(2115, 1, 11)
    begin_dt, end_dt = determine_hours_time_range(begin_date, end_date, tz)
    assert begin_dt.date() == begin_date
    assert begin_dt.time() == datetime.time(0, 0)
    assert end_dt.date() == end_date + datetime.timedelta(days=1)
    assert end_dt.time() == datetime.time(0, 0)

    default_begin, default_end = determine_hours_time_range(None, None, tz)
    assert default_begin.time() == datetime.time(0, 0)
    assert default_end.time() == datetime.time(0, 0)
    assert default_end - default_begin == datetime.timedelta(days=1)


@pytest.mark.django_db
def test_resource_related_small_model_str_methods(resource_in_unit, space_resource_type, purpose, generic_terms):
    tag = ResourceTag.objects.create(resource=resource_in_unit, label="hot")
    assert str(tag) == f"<{resource_in_unit.name}: hot>"

    resource_type_text = str(space_resource_type)
    assert space_resource_type.id in resource_type_text

    purpose_obj = Purpose.objects.get(pk=purpose.pk)
    assert purpose_obj.id in str(purpose_obj)

    terms_obj = TermsOfUse.objects.get(pk=generic_terms.pk)
    assert str(terms_obj)
