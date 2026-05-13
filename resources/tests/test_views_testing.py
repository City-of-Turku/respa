import datetime

import pytest
import pytz
from django.test import RequestFactory

from resources.views import testing


def test_testing_view_returns_html_and_uses_default_duration(monkeypatch):
    called = {}

    def fake_get_availability(begin, end, resources=None, duration=None):
        called["begin"] = begin
        called["end"] = end
        called["duration"] = duration
        return {"r1": "openings"}, {"r1": "availability"}

    monkeypatch.setattr(testing.resources.timetools, "get_availability", fake_get_availability)

    request = RequestFactory().get("/test/availability", {"start_date": "2015-03-02", "end_date": "2015-03-07"})
    response = testing.testing_view(request)

    assert response.status_code == 200
    assert b"opens" in response.content
    assert b"avail" in response.content
    assert called["begin"] == datetime.datetime(2015, 3, 2)
    assert called["end"] == datetime.datetime(2015, 3, 7)
    assert called["duration"] == datetime.timedelta(hours=2)


def test_tester_uses_timewarp_and_returns_availability(monkeypatch):
    class FakeTimeWarp:
        def __init__(self, dt):
            self.dt = dt

        def astimezone(self, tz):
            assert tz == "UTC"
            return pytz.utc.localize(self.dt)

    monkeypatch.setattr(testing.resources.timetools, "TimeWarp", FakeTimeWarp)

    def fake_get_availability(begin, end, resources=None, duration=None):
        assert begin.tzinfo is not None
        assert end.tzinfo is not None
        assert duration == datetime.timedelta(hours=2)
        return "openings", "availability"

    monkeypatch.setattr(testing.resources.timetools, "get_availability", fake_get_availability)

    openings, availability = testing.tester()
    assert openings == "openings"
    assert availability == "availability"
