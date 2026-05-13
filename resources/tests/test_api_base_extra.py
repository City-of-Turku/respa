import datetime
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers

from resources.api.base import (
    CancelReservationPermission,
    CancelReservationsSerializer,
    CancelReservationsView,
    DRFFilterBooleanWidget,
    LocationField,
    NullableDateTimeField,
    NullableTimeField,
    TranslatedModelSerializer,
    all_views,
    get_translated_field_help_text,
    register_view,
)
from resources.models import Reservation, ResourceEquipment


def test_get_translated_field_help_text_contains_all_languages():
    help_text = get_translated_field_help_text("name")
    assert '"name"' in help_text
    assert '"fi"' in help_text
    assert '"en"' in help_text
    assert '"sv"' in help_text


def test_register_view_adds_entries_with_and_without_base_name():
    original_len = len(all_views)
    try:
        register_view(object, "dummy")
        register_view(object, "dummy2", base_name="dummy-base")
        assert len(all_views) == original_len + 2
        assert all_views[-2]["name"] == "dummy"
        assert "base_name" not in all_views[-2]
        assert all_views[-1]["base_name"] == "dummy-base"
    finally:
        del all_views[original_len:]


def test_drffilter_boolean_widget_render_returns_none():
    widget = DRFFilterBooleanWidget()
    assert widget.render() is None


def test_nullable_fields_return_none_for_empty_value():
    assert NullableDateTimeField().to_representation(None) is None
    assert NullableTimeField().to_representation(None) is None


def test_location_field_to_internal_value_point_and_validation():
    field = LocationField()
    point = field.to_internal_value({"type": "Point", "coordinates": [24.94, 60.17]})
    assert round(point.x, 2) == 24.94
    assert round(point.y, 2) == 60.17

    empty_state, normalized = field.validate_empty_values({"type": "Point", "coordinates": [24, 60]})
    assert empty_state is False
    assert normalized["coordinates"] == [24.0, 60.0]


def test_location_field_to_representation_for_point():
    field = LocationField()
    point = field.to_internal_value({"type": "Point", "coordinates": [24.94, 60.17]})
    represented = field.to_representation(point)
    assert represented["type"] == "Point"
    assert represented["coordinates"] == [24.94, 60.17]


def test_location_field_validate_empty_values_errors():
    field = LocationField()

    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({})
    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({"coordinates": [24.0, 60.0]})
    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({"type": 123, "coordinates": [24.0, 60.0]})
    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({"type": "Point", "coordinates": "24,60"})
    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({"type": "Point", "coordinates": [24.0]})
    with pytest.raises(serializers.ValidationError):
        field.validate_empty_values({"type": "Point", "coordinates": ["24.0", object()]})


def test_cancel_reservation_permission_checks_instance_admin():
    instance = SimpleNamespace(is_admin=lambda user: user == "allowed")
    permission = CancelReservationPermission(instance)
    request = SimpleNamespace(user="allowed")
    denied_request = SimpleNamespace(user="denied")
    view = SimpleNamespace()
    assert permission.has_permission(request, view) is True
    assert permission.has_permission(denied_request, view) is False


def test_translated_model_serializer_required_translation_validation():
    class TestSerializer(TranslatedModelSerializer):
        description = serializers.DictField(required=False)

        class Meta:
            model = ResourceEquipment
            fields = ("description",)
            required_translations = ("description_fi",)

    serializer = TestSerializer()
    with pytest.raises(DjangoValidationError) as exc:
        serializer.validate_translation({"description": {"en": "Only english"}})
    assert "description" in exc.value.message_dict


def test_translated_model_serializer_allow_null_populates_language_keys():
    class TestSerializer(TranslatedModelSerializer):
        description = serializers.DictField(required=False, allow_null=True)

        class Meta:
            model = ResourceEquipment
            fields = ("description",)
            required_translations = ()

    serializer = TestSerializer()
    data = {"description": None}
    serializer.validate_translation(data)
    assert "description_fi" in data
    assert "description_en" in data
    assert "description_sv" in data
    assert data["description_fi"] is None


def test_cancel_reservations_serializer_validation():
    serializer = CancelReservationsSerializer(
        data={"begin": "2026-01-10T12:00:00Z", "end": "2026-01-10T11:00:00Z"}
    )
    assert serializer.is_valid() is False
    assert "begin" in serializer.errors

    valid = CancelReservationsSerializer(
        data={"begin": "2026-01-10T11:00:00Z", "end": "2026-01-10T12:00:00Z"}
    )
    assert valid.is_valid(), valid.errors


@pytest.mark.django_db
def test_cancel_reservations_view_get_object_not_found():
    class TestView(CancelReservationsView):
        class Meta:
            model = Reservation

    view = TestView()
    view.kwargs = {"pk": -1}
    with pytest.raises(exceptions.NotFound):
        view.get_object()


def test_cancel_reservations_view_delete_calls_cancel_when_exists():
    class FakeQuerySet:
        def __init__(self, exists_value):
            self._exists_value = exists_value
            self.cancel_called = False
            self.exclude_kwargs = {}

        def exclude(self, **kwargs):
            self.exclude_kwargs = kwargs
            return self

        def exists(self):
            return self._exists_value

        def cancel(self, _user):
            self.cancel_called = True

    class TestView(CancelReservationsView):
        def __init__(self, queryset):
            super().__init__()
            self._queryset = queryset

        def get_reservation_queryset(self, begin, end):
            assert isinstance(begin, datetime.datetime)
            assert isinstance(end, datetime.datetime)
            return self._queryset

    request = SimpleNamespace(
        user=SimpleNamespace(id=1),
        data={"begin": "2026-01-10T11:00:00Z", "end": "2026-01-10T12:00:00Z"},
    )

    qs = FakeQuerySet(exists_value=True)
    view = TestView(qs)
    response = view.delete(request)
    assert response.status_code == 204
    assert qs.cancel_called is True
    assert qs.exclude_kwargs.get("state") == Reservation.CANCELLED

    qs_noop = FakeQuerySet(exists_value=False)
    view_noop = TestView(qs_noop)
    response = view_noop.delete(request)
    assert response.status_code == 204
    assert qs_noop.cancel_called is False
    assert qs_noop.exclude_kwargs.get("state") == Reservation.CANCELLED
