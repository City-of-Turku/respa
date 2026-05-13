"""
Additional tests for notifications/models.py covering:
- NotificationTemplate.__str__ branches
- NotificationTemplate.clean branches
- NotificationTemplate.validate_templates (invalid template syntax)
- NotificationTemplateGroup.__str__
- render_notification_template raises when template missing
- reservation_time filter (dict and object paths)
- format_datetime (fi and non-fi)
- format_datetime_tz
"""
import datetime

import pytest
import pytz
from django.core.exceptions import ValidationError
from django.utils import translation

from notifications.models import (
    NotificationTemplate,
    NotificationTemplateGroup,
    NotificationType,
    format_datetime,
    format_datetime_tz,
    render_notification_template,
    reservation_time,
    NotificationTemplateException,
)

VALID_TYPE = NotificationType.RESERVATION_CREATED


@pytest.fixture
def default_template(db):
    template = NotificationTemplate.objects.language('en').create(
        type=VALID_TYPE,
        is_default_template=True,
        short_message="hello",
        subject="subject",
        html_body="<b>body</b>",
        body="plain body",
    )
    return template


# ---------------------------------------------------------------------------
# NotificationTemplate.__str__
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notification_template_str_known_type_with_name(default_template):
    default_template.name = "My template"
    default_template.save()
    text = str(default_template)
    assert "My template" in text


@pytest.mark.django_db
def test_notification_template_str_known_type_without_name(default_template):
    default_template.name = ""
    default_template.save()
    text = str(default_template)
    assert text != "N/A"
    assert len(text) > 0


@pytest.mark.django_db
def test_notification_template_str_unknown_type():
    template = NotificationTemplate(type="nonexistent_type_xyz", is_default_template=False)
    assert str(template) == "N/A"


# ---------------------------------------------------------------------------
# NotificationTemplate.clean
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notification_template_clean_second_default_raises(default_template):
    """Creating a second default template for the same type should raise ValidationError."""
    second = NotificationTemplate.objects.language('en').create(
        type=VALID_TYPE,
        is_default_template=False,
        short_message="x",
        subject="x",
        html_body="x",
        body="x",
    )
    second.is_default_template = True
    with pytest.raises(ValidationError):
        second.clean()


@pytest.mark.django_db
def test_notification_template_clean_modify_existing_default_ok(default_template):
    """Saving changes to an existing default template should not raise."""
    default_template.subject = "updated"
    default_template.save()
    default_template.clean()  # Should not raise


@pytest.mark.django_db
def test_notification_template_clean_new_default_when_non_default_exists():
    """Creating a new default when only non-default templates exist should be OK."""
    NotificationTemplate.objects.language('en').create(
        type=VALID_TYPE,
        is_default_template=False,
        short_message="x",
        subject="x",
        html_body="x",
        body="x",
    )
    new_default = NotificationTemplate.objects.language('en').create(
        type=VALID_TYPE,
        is_default_template=True,
        short_message="y",
        subject="y",
        html_body="y",
        body="y",
    )
    # Should not raise, but note log entry is made
    new_default.clean()


# ---------------------------------------------------------------------------
# NotificationTemplate.validate_templates — invalid Jinja2 syntax
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_validate_templates_invalid_syntax_raises():
    template = NotificationTemplate(
        type=VALID_TYPE,
        is_default_template=False,
        short_message="{{ unclosed",
        subject="ok",
        html_body="ok",
        body="ok",
    )
    with pytest.raises(ValidationError):
        template.validate_templates()


# ---------------------------------------------------------------------------
# NotificationTemplateGroup.__str__
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notification_template_group_str():
    group = NotificationTemplateGroup.objects.create(
        identifier="test_group",
        name="Test Group Name",
    )
    assert str(group) == "Test Group Name"


# ---------------------------------------------------------------------------
# render_notification_template — raises when template missing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_render_notification_template_raises_when_missing():
    with pytest.raises(NotificationTemplateException):
        render_notification_template("type_that_does_not_exist", {})


# ---------------------------------------------------------------------------
# reservation_time filter
# ---------------------------------------------------------------------------

def test_reservation_time_with_dict():
    res = {"time_range": "Mon 1.1.2026 09:00–10:00"}
    assert reservation_time(res) == "Mon 1.1.2026 09:00–10:00"


def test_reservation_time_with_object():
    class FakeReservation:
        def format_time(self):
            return "formatted time"

    assert reservation_time(FakeReservation()) == "formatted time"


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------

def test_format_datetime_finnish():
    tz = pytz.timezone("Europe/Helsinki")
    dt = tz.localize(datetime.datetime(2026, 6, 1, 14, 30))
    with translation.override('fi'):
        result = format_datetime(dt)
    # Finnish format: D j.n.Y \k\l\o G.i
    assert "2026" in result
    assert "14.30" in result


def test_format_datetime_english():
    tz = pytz.timezone("Europe/Helsinki")
    dt = tz.localize(datetime.datetime(2026, 6, 1, 14, 30))
    with translation.override('en'):
        result = format_datetime(dt)
    assert "2026" in result
    assert "14:30" in result


# ---------------------------------------------------------------------------
# format_datetime_tz
# ---------------------------------------------------------------------------

def test_format_datetime_tz_converts_timezone():
    utc_dt = pytz.utc.localize(datetime.datetime(2026, 6, 1, 11, 0))
    helsinki_tz = pytz.timezone("Europe/Helsinki")
    with translation.override('en'):
        result = format_datetime_tz(utc_dt, helsinki_tz)
    # UTC 11:00 → Helsinki 14:00 (+3 in summer)
    assert "14" in result
    assert "2026" in result
