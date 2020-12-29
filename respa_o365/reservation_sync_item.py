from datetime import datetime, timezone


class ReservationSyncItem:
    """Class represents data transferred between Respa and Outlook (or another remote system)."""

    def __init__(self):
        self.begin = datetime.now(tz=timezone.utc)
        self.end = datetime.now(tz=timezone.utc)
        self.reserver_name = ""
        self.reserver_email_address = ""
        self.reserver_phone_number = ""

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


def model_to_item(reservation_model):
    if not reservation_model:
        return None
    item = ReservationSyncItem()
    item.begin = reservation_model.begin
    item.end = reservation_model.end
    item.reserver_name = reservation_model.reserver_name
    item.reserver_email_address = reservation_model.reserver_email_address
    item.reserver_phone_number = reservation_model.reserver_phone_number
    return item
