from resources.enums import UnitAuthorizationLevel


def test_unit_authorization_level_comparisons():
    assert UnitAuthorizationLevel.admin > UnitAuthorizationLevel.manager
    assert UnitAuthorizationLevel.manager > UnitAuthorizationLevel.viewer
    assert UnitAuthorizationLevel.viewer < UnitAuthorizationLevel.admin
    assert UnitAuthorizationLevel.admin >= UnitAuthorizationLevel.admin
    assert UnitAuthorizationLevel.viewer <= UnitAuthorizationLevel.manager


def test_unit_authorization_level_below_and_above():
    assert UnitAuthorizationLevel.manager.below() == ["viewer"]
    assert UnitAuthorizationLevel.manager.above() == ["admin"]
    assert UnitAuthorizationLevel.viewer.above() == ["manager", "admin"]
