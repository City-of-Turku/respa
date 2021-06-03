import json
from datetime import datetime, timedelta
from respa_o365.o365_calendar import MicrosoftApiError


class O365Notifications:
    def __init__(self, microsoft_api):
        self._api = microsoft_api

    def list(self):
        try: 
            result = self._api.get("subscriptions")
        except MicrosoftApiError:
            return []
        return result.get("value")

    def create(self, resource, events, notification_url, client_state):
        expirationDatetime = datetime.utcnow()+timedelta(hours=48)
        date = expirationDatetime.isoformat()+"Z"
        result = self._api.post("subscriptions",
                                {
                                    "changeType": ",".join(events),
                                    "notificationUrl": notification_url,
                                    "resource": resource,
                                    "expirationDateTime": date,
                                    "clientState": client_state,
                                    "latestSupportedTlsVersion": "v1_2",
                                })
        if result.status_code != 201:
            raise SubscriptionError("Failed to crate notification ({}) {}".format(result.status_code, result.content))
        return result.json().get("id")

    def get(self, id):
        try:
            result = self._api.get("subscriptions/{}".format(id))
        except MicrosoftApiError:
            result = None
        return result

    def delete(self, id):
        result = self._api.delete("subscriptions/{}".format(id))

    def renew(self, id):
        expirationDatetime = datetime.utcnow()+timedelta(hours=48)
        date = expirationDatetime.isoformat()+"Z"
        result = self._api.patch("subscriptions/{}".format(id),
                        {
                            "expirationDateTime": date,
                        })
        if result == 201:
            raise SubscriptionError(result)

    def ensureNotifications(self, notification_url, resource, events, client_state, subscription_id):
        subscriptions = self.list()
        key = None
        for s in subscriptions:
            if s.get("resource") == resource and s.get("notificationUrl"):
                id = s.get("id")
                if not key and id == subscription_id:
                    key = id
                    self.renew(key)
                else:
                    self.delete(s.get("id"))
        if key:
            return key, False
        else:
            return self.create(notification_url=notification_url, resource=resource, events=events, client_state=client_state), True


class SubscriptionError(Exception):

    def __init__(self, result):
        self._result = result
