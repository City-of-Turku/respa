from datetime import datetime


class ReservationSyncItem:
    """Class represents data transferred between Respa and Outlook (or another remote system)."""
    begin = datetime.now()
    end = datetime.now()
    reserver_name = ""
    reserver_email_address = ""
    reserver_phone_number = ""


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
