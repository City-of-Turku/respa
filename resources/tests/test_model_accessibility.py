import pytest

from resources.models import (
    AccessibilityValue,
    AccessibilityViewpoint,
    ResourceAccessibility,
    UnitAccessibility,
)


@pytest.mark.django_db
def test_accessibility_viewpoint_and_value_str():
    viewpoint = AccessibilityViewpoint.objects.create(name="Wheelchair user")
    value = AccessibilityValue.objects.create(value="green", order=10)
    assert str(viewpoint) == "Wheelchair user"
    assert str(value) == "green"


@pytest.mark.django_db
def test_resource_accessibility_save_sets_order_from_value(resource_in_unit):
    viewpoint = AccessibilityViewpoint.objects.create(name="Wheelchair user")
    value = AccessibilityValue.objects.create(value="green", order=20)
    summary = ResourceAccessibility.objects.create(
        viewpoint=viewpoint,
        resource=resource_in_unit,
        value=value,
        order=-1,
    )
    summary.refresh_from_db()
    assert summary.order == 20
    assert str(summary) == f"{resource_in_unit} / {viewpoint}: {value}"


@pytest.mark.django_db
def test_unit_accessibility_save_sets_order_from_value(test_unit):
    viewpoint = AccessibilityViewpoint.objects.create(name="Hearing impaired")
    value = AccessibilityValue.objects.create(value="red", order=-5)
    summary = UnitAccessibility.objects.create(
        viewpoint=viewpoint,
        unit=test_unit,
        value=value,
        order=999,
    )
    summary.refresh_from_db()
    assert summary.order == -5
    assert str(summary) == f"{test_unit} / {viewpoint}: {value}"


@pytest.mark.django_db
def test_accessibility_value_save_updates_cached_resource_accessibility_order(resource_in_unit):
    viewpoint = AccessibilityViewpoint.objects.create(name="Wheelchair user")
    value = AccessibilityValue.objects.create(value="yellow", order=1)
    summary = ResourceAccessibility.objects.create(
        viewpoint=viewpoint,
        resource=resource_in_unit,
        value=value,
        order=0,
    )
    value.order = 42
    value.save()
    summary.refresh_from_db()
    assert summary.order == 42
