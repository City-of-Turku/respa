import datetime

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from resources.models import Reservation
from resources.views.ical import ICalFeedView, ICalRenderer


def test_ical_renderer_decodes_bytes():
    renderer = ICalRenderer()
    payload = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
    assert renderer.render(payload) == "BEGIN:VCALENDAR\nEND:VCALENDAR"


@pytest.mark.django_db
def test_ical_feed_denies_unknown_token():
    request = APIRequestFactory().get("/v1/reservation/ical/not-existing-token.ics")
    view = ICalFeedView()
    with pytest.raises(PermissionDenied):
        view.get(request, "not-existing-token")


@pytest.mark.django_db
def test_ical_feed_returns_calendar_for_valid_token(client, user, resource_with_opening_hours):
    user.ical_token = "validicaltoken12"
    user.save(update_fields=["ical_token"])

    begin = timezone.now() + datetime.timedelta(hours=1)
    end = begin + datetime.timedelta(hours=2)
    reservation = Reservation.objects.create(
        resource=resource_with_opening_hours,
        user=user,
        reserver_name="ical user",
        begin=begin,
        end=end,
    )

    url = reverse("ical-feed", kwargs={"ical_token": user.ical_token})
    response = client.get(url)

    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "BEGIN:VCALENDAR" in text
    assert f"respa_reservation_{reservation.id}" in text
