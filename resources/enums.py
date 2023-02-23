from django.utils.translation import gettext_lazy as _
from enumfields import Enum

UNIT_AUTH_MAP = {
    'viewer': 1,
    'manager': 2,
    'admin': 3,
}

class UnitGroupAuthorizationLevel(Enum):
    admin = 'admin'

    class Labels:
        admin = _("unit group administrator")


class UnitAuthorizationLevel(Enum):
    admin = 'admin'
    manager = 'manager'
    viewer = 'viewer'

    class Labels:
        admin = _("unit administrator")
        manager = _("unit manager")
        viewer = _("unit viewer")



    def __gt__(self, other):
        return UNIT_AUTH_MAP.get(self._value_, None) > UNIT_AUTH_MAP.get(other._value_, None)

    def __lt__(self, other):
        return UNIT_AUTH_MAP.get(self._value_, None) < UNIT_AUTH_MAP.get(other._value_, None)

    def __ge__(self, other):
        return UNIT_AUTH_MAP.get(self._value_, None) >= UNIT_AUTH_MAP.get(other._value_, None)

    def __le__(self, other):
        return UNIT_AUTH_MAP.get(self._value_, None) <= UNIT_AUTH_MAP.get(other._value_, None)
        
    def below(self):
        return [label for label, level in UNIT_AUTH_MAP.items() if level < UNIT_AUTH_MAP[self._value_]]
    
    def above(self):
        return [label for label, level in UNIT_AUTH_MAP.items() if level > UNIT_AUTH_MAP[self._value_]]
