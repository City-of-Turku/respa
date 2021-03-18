from datetime import datetime, timezone


class ReservationSyncItem:
    """Class represents data transferred between Respa and Outlook (or another remote system)."""

    def __init__(self):
        self.begin = datetime.now(tz=timezone.utc)
        self.end = datetime.now(tz=timezone.utc)
        self.reserver_name = ""
        self.reserver_email_address = ""
        self.reserver_phone_number = ""
        self.comments = ""

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
    if reservation_model.reserver_name == '' and reservation_model.user:
            item.reserver_name = f"{reservation_model.user.first_name} {reservation_model.user.last_name}"
    else:
        item.reserver_name = reservation_model.reserver_name

    if reservation_model.reserver_email_address == '' and reservation_model.user:
        item.reserver_email_address = reservation_model.user.email
    else:
        item.reserver_email_address = reservation_model.reserver_email_address

    item.reserver_phone_number = reservation_model.reserver_phone_number
    item.comments = reservation_model.comments
    
    return item
