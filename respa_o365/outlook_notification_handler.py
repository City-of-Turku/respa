import json
import logging
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from respa_o365.calendar_sync import perform_sync_to_exchange
from respa_o365.models import OutlookCalendarLink, OutlookCalendarReservation
from respa_o365.reservation_sync_operations import ChangeType

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class NotificationCallback(View):
    """
    Endpoint to receive notifications from Microsoft Graph API.
    https://docs.microsoft.com/en-us/graph/webhooks
    """
    # TODO Call synchronisation with received changes.

    def post(self, request):
        if self.is_validation_request(request):
            return self.handle_validation_request(request)
        if self.is_notification(request):
            return self.handle_notification(request)
        return self.http_method_not_allowed(request)
    pass

    def is_validation_request(self, request):
        validation_token = request.GET.get('validationToken')
        return validation_token is not None and len(request.GET) == 1

    def handle_validation_request(self, request):
        validation_token = request.GET.get('validationToken')
        return HttpResponse(content=validation_token, content_type='text/plain', status=200)

    def is_notification(self, request):
        if request.content_type != 'application/json':
            return False
        return request.body.startswith(b'{')

    def handle_notification(self, request):
        # notifications = json.loads(request.body).get("value")
        # for notification in notifications:
        #     print(notification)
        #     change_type = notification.get("changeType")
        #     sub_id = notification.get("subscriptionId")
        #     ct = ChangeType.UPDATED
        #     if change_type == "created":
        #         ct = ChangeType.CREATED
        #     if change_type == "deleted":
        #         ct = ChangeType.DELETED
        #
        #     item_id = notification.get("resourceData").get("id")
        #     link = OutlookCalendarLink.objects.filter(exchange_subscription_id=sub_id).first()
        #     if link:
        #         logger.info("Notification from {}. Syncing resource {} for user {}",
        #                     sub_id, link.resource_id, link.user_id)
        #         perform_sync_to_exchange(link, lambda s: s.sync({}, {item_id: ct}))
        #     else:
        #         logger.warning("Received notification from subscription {} not connected to any calendar link.", sub_id)

        return HttpResponse(status=202)





