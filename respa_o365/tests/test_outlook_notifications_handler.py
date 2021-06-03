import pytest
from django.http import HttpRequest
from django.test import RequestFactory
from respa_o365.outlook_notification_handler import NotificationCallback

r_factory = RequestFactory()
notification_callback = NotificationCallback()

def post(*args, **kwargs):
    return r_factory.post(*args, **kwargs)

def test_microsoft_notification_endpoint_validation_request_is_handled_correctly():
    """
    https://docs.microsoft.com/en-us/graph/webhooks#notification-endpoint-validation

    The client must provide a response with the following characteristics within 10 seconds of step 1:
     - A status code of HTTP 200 OK.
     - A content type of text/plain.
     - A body that includes the URL decoded validation token.
       Simply reflect back the same string that was sent in the validationToken query parameter.
    """
    # Arrange
    req = post('/ihansama?validationToken=randomToken', '', 'plain/text')
    # Act
    resp = notification_callback.dispatch(req)
    # Assert
    assert resp.status_code == 200
    assert resp.content == b'randomToken'
    assert resp.get('content-type') == 'text/plain'


def test_validation_request_with_unnecessary_parameters_is_ignored():
    # Arrange
    req = r_factory.post('/ihansama?validationToken=randomToken&other=1', '', 'plain/text')
    # Act
    resp = notification_callback.dispatch(req)
    # Assert
    assert resp.status_code == 405



@pytest.mark.skip("Not implemented properly yet")
def test_validation_request_with_unnecessary_parameters_is_ignored():
    """
    https://docs.microsoft.com/en-us/graph/webhooks#processing-the-change-notification

    1. Send a 202 - Accepted status code in your response to Microsoft
    Graph. If Microsoft Graph doesn't receive a 2xx class code, it
    will try to publishing the change notification a number of times,
    for a period of about 4 hours; after that, the change notification
    will be dropped and won't be delivered.

      Note: Send a 202 - Accepted status code as soon as you receive
      the change notification, even before validating its
      authenticity. You are simply acknowledging the receipt of the
      change notification and preventing unnecessary retries. The
      current timeout is 30 seconds, but it might be reduced in the
      future to optimize service performance. If the notification URL
      doesn't reply within 30 seconds for more than 10% of the
      requests from Microsoft Graph over a 10 minute period, all
      following notifications will be delayed and retried for a period
      of 4 hours. If a notification URL doesn't reply within 30
      seconds for more than 20% of the requests from Microsoft Graph
      over a 10 minute period, all following notifications will be
      dropped.

    2. Validate the clientState property. It must match the value
    originally submitted with the subscription creation request.

      Note: If this isn't true, you should not consider this a valid
      change notification. It is possible that the change notification
      has not originated from Microsoft Graph and may have been sent
      by a rogue actor. You should also investigate where the change
      notification comes from and take appropriate action.

    3. Update your application based on your business logic.

    """
    # Arrange
    req = post('',
                         """{
    "value": [
    {
      "id": "lsgTZMr9KwAAA",
      "subscriptionId":"{subscription_guid}",
      "subscriptionExpirationDateTime":"2016-03-19T22:11:09.952Z",
      "clientState":"secretClientValue",
      "changeType":"created",
      "resource":"users/{user_guid}@{tenant_guid}/messages/{long_id_string}",
      "tenantId": "84bd8158-6d4d-4958-8b9f-9d6445542f95",
      "resourceData":
      {
        "@odata.type":"#Microsoft.Graph.Message",
        "@odata.id":"Users/{user_guid}@{tenant_guid}/Messages/{long_id_string}",
        "@odata.etag":"W/\\"CQAAABYAAADkrWGo7bouTKlsgTZMr9KwAAAUWRHf\\"",
        "id":"{long_id_string}"
      }
    }
  ]
}
    """, 'application/json')
    # Act
    # TODO There needs to be solution that works without database to test this
    resp = notification_callback.dispatch(req)
    # Assert
    assert resp.status_code == 202
