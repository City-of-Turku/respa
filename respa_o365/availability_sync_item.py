from datetime import date, time, datetime, timezone
from resources.models import Day

class AvailabilitySyncItem:
    """Class represents data transferred between Respa and Outlook (or another remote system)."""

    def __init__(self):
        self.begin = datetime.now(tz=timezone.utc)
        self.end = datetime.now(tz=timezone.utc)

    def __eq__(self, other):
        """Action is equal when internal fields are equal"""
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __str__(self):
        """Creates string representation that looks like this:
             {'field1': 'value2', 'field2': 'value2'}
        """
        return str({k: v for k, v in self.__dict__.items()})


def period_to_item(period):
    if not period:
        return None
    days = Day.objects.filter(period=period)
    if not days or len(days) != 1:
        return None
    day = days[0]
    date = period.start
    item = AvailabilitySyncItem()
    item.begin = datetime.combine(date, day.opens)
    item.end = datetime.combine(date, day.closes)

    return item
