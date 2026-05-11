import pytest
from types import SimpleNamespace
from django.test import RequestFactory
from rest_framework import exceptions
from rest_framework.request import Request
from resources.models import Reservation
from resources.tests.conftest import *
from reports.api.reservation_details import ReservationDetailsDocxRenderer, ReservationDetailsReport


list_url = '/reports/reservation_details/'


@pytest.fixture
def reservation(resource_in_unit, user):
    return Reservation.objects.create(
        resource=resource_in_unit,
        begin='2015-04-04T09:00:00+02:00',
        end='2015-04-04T10:00:00+02:00',
        user=user,
        reserver_name='John Smith',
        event_subject="John's welcome party",
    )


@pytest.fixture
def reservation2(resource_in_unit2, user):
    return Reservation.objects.create(
        resource=resource_in_unit2,
        begin='2015-04-04T15:00:00+02:00',
        end='2015-04-04T16:00:00+02:00',
        user=user,
        reserver_name='Mike Smith',
        event_subject="John's farewell party",
    )


def check_valid_response(response):
    headers = response.headers
    assert headers['Content-Type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert headers['Content-Disposition'].endswith('.docx')
    assert len(response.content) > 0


@pytest.mark.django_db
def test_get_reservation_details_report(api_client, reservation):
    response = api_client.get(list_url + '?reservation=%s' % reservation.id)
    assert response.status_code == 200

    check_valid_response(response)


@pytest.mark.django_db
def test_daily_reservations_filter_errors(api_client, test_unit, reservation, resource_in_unit):
    response = api_client.get(list_url + '?reservation=592843752987', HTTP_ACCEPT_LANGUAGE='en')
    assert response.status_code == 404
    assert 'does not exist' in str(response.data)

    response = api_client.get(list_url + '?start=abc', HTTP_ACCEPT_LANGUAGE='en')
    assert response.status_code == 400
    assert 'must be a timestamp in ISO' in str(response.data)


@pytest.mark.django_db
def test_reservation_details_filter_queryset_too_many_raises_not_acceptable():
    fake_queryset = SimpleNamespace(count=lambda: 1001)
    report = ReservationDetailsReport()
    report.request = Request(RequestFactory().get(list_url))
    report.filter_backends = ()
    report.format_kwarg = None
    report.kwargs = {}

    with pytest.raises(exceptions.NotAcceptable):
        report.filter_queryset(fake_queryset)


@pytest.mark.django_db
def test_reservation_details_serializer_context_uses_cache_when_page_set(reservation, monkeypatch):
    report = ReservationDetailsReport()
    report.request = Request(RequestFactory().get(list_url))
    report.format_kwarg = None
    report.kwargs = {}
    report._page = [reservation]
    monkeypatch.setattr(
        report,
        "_get_cache_context",
        lambda: {"reservation_metadata_set_cache": {"dummy": "value"}},
    )

    context = report.get_serializer_context()
    assert "request" in context
    assert context["reservation_metadata_set_cache"] == {"dummy": "value"}


@pytest.mark.django_db
def test_reservation_details_docx_renderer_render_one_without_attrs(reservation):
    renderer = ReservationDetailsDocxRenderer()
    renderer.resources = {
        reservation.resource.id: SimpleNamespace(
            name=reservation.resource.name,
            unit=SimpleNamespace(name=reservation.resource.unit.name),
        )
    }
    renderer.catering_orders = {}
    document = renderer.create_document()
    initial_table_count = len(document.tables)
    initial_paragraph_count = len(document.paragraphs)
    reservation_data = {
        "id": reservation.id,
        "resource": reservation.resource.id,
        "begin": reservation.begin.isoformat(),
        "end": reservation.end.isoformat(),
    }

    renderer.render_one(document, reservation_data, renderer_context={})

    # No attrs -> no new detail/catering tables expected.
    assert len(document.tables) == initial_table_count
    # "No information available" paragraph should be added.
    assert len(document.paragraphs) > initial_paragraph_count


@pytest.mark.django_db
def test_reservation_details_docx_renderer_render_one_with_attrs_and_catering(reservation):
    renderer = ReservationDetailsDocxRenderer()
    renderer.resources = {
        reservation.resource.id: SimpleNamespace(
            name=reservation.resource.name,
            unit=SimpleNamespace(name=reservation.resource.unit.name),
        )
    }

    order_line = SimpleNamespace(product=SimpleNamespace(name='Coffee'), quantity=3)
    catering_order = SimpleNamespace(
        order_lines=SimpleNamespace(all=lambda: [order_line]),
        message='Leave at door',
        invoicing_data='Invoice details',
    )
    renderer.catering_orders = {reservation.id: catering_order}
    document = renderer.create_document()
    initial_table_count = len(document.tables)
    reservation_data = {
        "id": reservation.id,
        "resource": reservation.resource.id,
        "begin": reservation.begin.isoformat(),
        "end": reservation.end.isoformat(),
        "event_subject": "Event title",
        "reserver_name": "John Smith",
        "has_catering_order": True,
    }

    renderer.render_one(document, reservation_data, renderer_context={})

    # one new table for reservation attrs and one for catering details
    assert len(document.tables) >= initial_table_count + 2
