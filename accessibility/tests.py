import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from accessibility.api.accessibility import ServicePointViewSet, ServiceRequirementCreateView
from accessibility.models import (
    Sentence,
    SentenceGroup,
    ServiceEntrance,
    ServicePoint,
    ServiceRequirement,
    ServiceSentence,
    ServiceShortage,
)
from accessibility.serializers.accessibility import (
    ServiceEntranceSerializer,
    ServicePointSerializer,
    ServicePointUpdateSerializer,
    ServiceShortagesSerializer,
    build_url,
)


def _name_translations(prefix):
    return {"fi": f"{prefix} fi", "en": f"{prefix} en", "sv": f"{prefix} sv"}


def _make_request(method, path):
    factory = APIRequestFactory()
    req = getattr(factory, method.lower())(path)
    return req


def test_build_url_removes_query_and_appends_pk():
    request = _make_request("GET", "/v1/accessibility/?include=service_shortages")
    url = build_url(request, 42)
    assert url.endswith("/v1/accessibility/42/")


def test_build_url_keeps_existing_pk():
    request = _make_request("GET", "/v1/accessibility/42/?include=service_entrances")
    url = build_url(request, 42)
    assert url.endswith("/v1/accessibility/42/")


@pytest.mark.django_db
def test_service_entrance_serializer_validate_location_invalid_json():
    serializer = ServiceEntranceSerializer()
    with pytest.raises(ValidationError):
        serializer.validate_location("not-json")


@pytest.mark.django_db
def test_service_shortages_serializer_includes_requirement_when_requested():
    requirement = ServiceRequirement.objects.create(
        text_fi="req fi",
        text_en="req en",
        text_sv="req sv",
        is_indoor_requirement=True,
        evaluation_zone="A",
    )
    service_point = ServicePoint.objects.create(code=10, name_fi="point fi")
    shortage = ServiceShortage.objects.create(
        service_point=service_point,
        service_requirement=requirement,
        viewpoint=1,
        shortage_fi="short fi",
        shortage_en="short en",
        shortage_sv="short sv",
    )

    serializer = ServiceShortagesSerializer(instance=shortage, context={"includes": ["service_requirement"]})
    data = serializer.data

    assert isinstance(data["service_requirement"], dict)
    assert data["service_requirement"]["id"] == requirement.id


@pytest.mark.django_db
def test_service_point_serializer_representation_counts_when_not_included():
    point = ServicePoint.objects.create(code=11, name_fi="point fi")
    ServiceShortage.objects.create(
        service_point=point,
        viewpoint=1,
        shortage_fi="short fi",
        shortage_en="short en",
        shortage_sv="short sv",
    )
    ServiceEntrance.objects.create(service_point=point, name_fi="entrance fi")

    request = _make_request("GET", "/v1/accessibility/")
    serializer = ServicePointSerializer(instance=point, context={"request": request})
    data = serializer.data

    assert data["url"].endswith(f"/v1/accessibility/{point.id}/")
    assert data["service_shortages"]["count"] == 1
    assert data["service_entrances"]["count"] == 1


@pytest.mark.django_db
def test_service_point_serializer_create_with_nested_data():
    payload = {
        "code": 100,
        "name": _name_translations("point"),
        "service_shortages": [
            {
                "viewpoint": 1,
                "shortage": _name_translations("shortage"),
            }
        ],
        "service_entrances": [
            {
                "id": 700,
                "name": _name_translations("entrance"),
                "is_main_entrance": True,
                "service_sentences": [
                    {
                        "sentence_order_text": {"fi": "order fi"},
                        "sentence_group": {
                            "name": _name_translations("group"),
                            "sentences": [{"sentence": _name_translations("sentence")}],
                        },
                    }
                ],
            }
        ],
    }
    request = _make_request("POST", "/v1/accessibility/")
    serializer = ServicePointSerializer(data=payload, context={"request": request})
    assert serializer.is_valid(), serializer.errors

    point = serializer.save()

    assert ServicePoint.objects.filter(pk=point.id).exists()
    assert point.service_shortages.count() == 1
    assert point.service_entrances.count() == 1
    assert ServiceSentence.objects.filter(service_point=point).count() == 1
    assert SentenceGroup.objects.count() == 1
    assert Sentence.objects.count() == 1


@pytest.mark.django_db
def test_service_point_update_serializer_patch_requires_nested_ids():
    point = ServicePoint.objects.create(code=101, name_fi="point fi")
    request = _make_request("PATCH", f"/v1/accessibility/{point.id}/")

    serializer = ServicePointUpdateSerializer(
        instance=point,
        data={"service_shortages": [{"viewpoint": 1, "shortage": _name_translations("short")}]} ,
        context={"request": request},
        partial=True,
    )
    assert serializer.is_valid() is False
    assert "message" in serializer.errors

    serializer = ServicePointUpdateSerializer(
        instance=point,
        data={"service_entrances": [{"name": _name_translations("entrance")}]} ,
        context={"request": request},
        partial=True,
    )
    assert serializer.is_valid() is False
    assert "message" in serializer.errors


@pytest.mark.django_db
def test_service_point_update_serializer_updates_existing_nested_data():
    point = ServicePoint.objects.create(code=102, name_fi="point fi")
    requirement = ServiceRequirement.objects.create(
        text_fi="req fi",
        text_en="req en",
        text_sv="req sv",
        evaluation_zone="A",
    )
    shortage = ServiceShortage.objects.create(
        service_point=point,
        service_requirement=requirement,
        viewpoint=1,
        shortage_fi="old fi",
        shortage_en="old en",
        shortage_sv="old sv",
    )
    entrance = ServiceEntrance.objects.create(service_point=point, name_fi="old entrance fi")

    request = _make_request("PATCH", f"/v1/accessibility/{point.id}/")
    payload = {
        "name": _name_translations("updated point"),
        "service_shortages": [
            {
                "id": shortage.id,
                "viewpoint": 2,
                "shortage": _name_translations("updated shortage"),
                "service_requirement": requirement.id,
            }
        ],
        "service_entrances": [
            {
                "id": entrance.id,
                "name": _name_translations("updated entrance"),
                "service_sentences": [
                    {
                        "sentence_order_text": {"fi": "updated sentence order"},
                        "sentence_group": {
                            "name": _name_translations("updated group"),
                            "sentences": [{"sentence": _name_translations("updated sentence")}],
                        },
                    }
                ],
            }
        ],
    }
    serializer = ServicePointUpdateSerializer(
        instance=point,
        data=payload,
        context={"request": request},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()

    shortage.refresh_from_db()
    entrance.refresh_from_db()
    point.refresh_from_db()
    assert shortage.viewpoint == 2
    assert entrance.name_fi == "updated entrance fi"
    assert point.name_fi == "updated point fi"
    assert ServiceSentence.objects.filter(service_point=point).count() == 1


def test_service_point_viewset_and_requirement_view_choose_many_and_partial():
    req = _make_request("PATCH", "/v1/accessibility/?include=service_shortages")
    view = ServicePointViewSet()
    view.request = view.initialize_request(req)
    view.format_kwarg = None
    view.kwargs = {}
    serializer = view.get_serializer(data=[])
    context = view.get_serializer_context()
    assert serializer.many is True
    assert serializer.partial is True
    assert "service_shortages" in context["includes"]
    assert view.get_serializer_class() is ServicePointUpdateSerializer

    req_view = ServiceRequirementCreateView()
    req_view.request = req_view.initialize_request(_make_request("POST", "/v1/accessibility/service-requirement"))
    req_view.format_kwarg = None
    req_view.kwargs = {}
    serializer = req_view.get_serializer(data=[])
    assert serializer.many is True
