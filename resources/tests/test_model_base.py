import pytest
from django.core.exceptions import ValidationError

from resources.models import AccessibilityValue, AccessibilityViewpoint, Purpose
from resources.models.base import ValidatedIdentifier


@pytest.mark.django_db
def test_auto_identified_model_generates_pk_for_charfield(monkeypatch):
    monkeypatch.setattr("resources.models.base.generate_id", lambda: "generated_id_123")
    viewpoint = AccessibilityViewpoint(name="Wheelchair user")
    viewpoint.save()
    assert viewpoint.pk == "generated_id_123"


@pytest.mark.django_db
def test_auto_identified_model_autofield_path_does_not_use_generate_id(monkeypatch):
    def fail_generate():
        raise AssertionError("generate_id should not be called for AutoField PK")

    monkeypatch.setattr("resources.models.base.generate_id", fail_generate)
    value = AccessibilityValue(value="base-autofield-test")
    value.save()
    assert value.pk is not None


@pytest.mark.django_db
def test_auto_identified_model_raises_for_unsupported_pk_type(monkeypatch):
    viewpoint = AccessibilityViewpoint(id="existing", name="Name")
    monkeypatch.setattr(viewpoint._meta.pk, "get_internal_type", lambda: "UUIDField")
    with pytest.raises(Exception, match="Unsupported primary key field"):
        viewpoint.save()


@pytest.mark.django_db
def test_name_identified_model_slugifies_from_english_then_finnish():
    purpose_en = Purpose(name_en="My English Name", name_fi="Suomenkielinen")
    purpose_en.save()
    assert purpose_en.pk == "my-english-name"

    purpose_fi = Purpose(name_en="", name_fi="Tama on nimi")
    purpose_fi.save()
    assert purpose_fi.pk == "tama-on-nimi"


@pytest.mark.django_db
def test_name_identified_model_raises_for_unsupported_pk_type(monkeypatch):
    purpose = Purpose(id="existing-purpose", name="Existing purpose")
    monkeypatch.setattr(purpose._meta.pk, "get_internal_type", lambda: "UUIDField")
    with pytest.raises(Exception, match="Unsupported primary key field"):
        purpose.save()


def test_validated_identifier_validate_id_error_paths():
    too_short = type("Obj", (), {"id": "abc"})()
    with pytest.raises(ValidationError, match="longer than 5 letters"):
        ValidatedIdentifier.validate_id(too_short)

    invalid_char = type("Obj", (), {"id": "abcdef!"})()
    with pytest.raises(ValidationError, match="Invalid characters in id"):
        ValidatedIdentifier.validate_id(invalid_char)

    starts_number = type("Obj", (), {"id": "1abcdef"})()
    with pytest.raises(ValidationError, match="cannot start with a number"):
        ValidatedIdentifier.validate_id(starts_number)

    starts_underscore = type("Obj", (), {"id": "_abcdef"})()
    with pytest.raises(ValidationError, match="cannot start with an underscore"):
        ValidatedIdentifier.validate_id(starts_underscore)

    consecutive_underscores = type("Obj", (), {"id": "abc__def"})()
    with pytest.raises(ValidationError, match="Consecutive underscore"):
        ValidatedIdentifier.validate_id(consecutive_underscores)


def test_validated_identifier_validate_id_accepts_valid_value():
    valid = type("Obj", (), {"id": "abc_def"})()
    ValidatedIdentifier.validate_id(valid)


def test_validated_identifier_clean_calls_validate_only_for_charfield_with_pk():
    class Pk:
        def __init__(self, internal_type):
            self._internal_type = internal_type

        def get_internal_type(self):
            return self._internal_type

    class Meta:
        def __init__(self, internal_type):
            self.pk = Pk(internal_type)

    called = []

    class Obj:
        def __init__(self, internal_type, pk):
            self._meta = Meta(internal_type)
            self.pk = pk

        def validate_id(self):
            called.append(True)

    ValidatedIdentifier.clean(Obj("AutoField", "foo"))
    assert called == []

    ValidatedIdentifier.clean(Obj("CharField", None))
    assert called == []

    ValidatedIdentifier.clean(Obj("CharField", "identifier"))
    assert called == [True]
