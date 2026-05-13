import pytest
from django.db import models as django_models

from resources.models.timmi import TimmiPayload
from resources.timmi.exceptions import MissingSapCodeError, MissingSapUnitError


def test_timmi_payload_encode_and_decode_roundtrip():
    payload = TimmiPayload()
    source = {"cashProduct": [{"accountingCode": 123, "accountingUnit": 45}], "ok": True}
    payload.encode(source)
    assert payload.payload == source


def test_timmi_payload_sap_code_and_sap_unit_zero_padded():
    payload = TimmiPayload()
    payload.encode({"cashProduct": [{"accountingCode": 98765, "accountingUnit": 4321}]})
    assert payload.sap_code == "000000000000098765"
    assert payload.sap_unit == "0000004321"


def test_timmi_payload_sap_code_and_sap_unit_missing_raise():
    payload = TimmiPayload()
    payload.encode({"cashProduct": [{}]})

    with pytest.raises(MissingSapCodeError):
        _ = payload.sap_code

    with pytest.raises(MissingSapUnitError):
        _ = payload.sap_unit


def test_timmi_payload_save_encodes_payload_and_removes_kwarg(monkeypatch):
    payload = TimmiPayload()
    captured = {"encoded": None, "save_kwargs": None}

    def fake_encode(data):
        captured["encoded"] = data

    def fake_model_save(self, *args, **kwargs):
        captured["save_kwargs"] = kwargs
        return None

    monkeypatch.setattr(payload, "encode", fake_encode)
    monkeypatch.setattr(django_models.Model, "save", fake_model_save)

    payload.save(payload={"x": 1}, force_insert=False)
    assert captured["encoded"] == {"x": 1}
    assert "payload" not in captured["save_kwargs"]
