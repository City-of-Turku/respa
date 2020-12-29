import pytest

from respa_o365.o365_calendar import MicrosoftApi
from respa_o365.o365_notifications import O365Notifications


def create_api():
    # These are some token to some test environment.
    # There needs to be some kind of opt out mechanism to choose if these are run as
    # test environment might not be available.
    # TODO Improve documentation on how to obtain these
    # TODO Create mechanism to skip tests if these are not available
    token = """{"token_type": "Bearer", "scope": ["Calendars.ReadWrite", "User.Read", "profile", "openid", "email"], "expires_in": 3599, "ext_expires_in": 3599, "access_token": "eyJ0eXAiOiJKV1QiLCJub25jZSI6Ik03OVo0UmstYmhjak5JZV9MXy1nRlEzemx0QVU1NzNnX0YxZXpiTVhiSlEiLCJhbGciOiJSUzI1NiIsIng1dCI6ImtnMkxZczJUMENUaklmajRydDZKSXluZW4zOCIsImtpZCI6ImtnMkxZczJUMENUaklmajRydDZKSXluZW4zOCJ9.eyJhdWQiOiIwMDAwMDAwMy0wMDAwLTAwMDAtYzAwMC0wMDAwMDAwMDAwMDAiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC8wNDFiOWRkZi00N2Y3LTRmZTAtOTkzMS04OWQ5ZTA2YTIyOGIvIiwiaWF0IjoxNjA4MDE0NDM3LCJuYmYiOjE2MDgwMTQ0MzcsImV4cCI6MTYwODAxODMzNywiYWNjdCI6MCwiYWNyIjoiMSIsImFjcnMiOlsidXJuOnVzZXI6cmVnaXN0ZXJzZWN1cml0eWluZm8iLCJ1cm46bWljcm9zb2Z0OnJlcTEiLCJ1cm46bWljcm9zb2Z0OnJlcTIiLCJ1cm46bWljcm9zb2Z0OnJlcTMiLCJjMSIsImMyIiwiYzMiLCJjNCIsImM1IiwiYzYiLCJjNyIsImM4IiwiYzkiLCJjMTAiLCJjMTEiLCJjMTIiLCJjMTMiLCJjMTQiLCJjMTUiLCJjMTYiLCJjMTciLCJjMTgiLCJjMTkiLCJjMjAiLCJjMjEiLCJjMjIiLCJjMjMiLCJjMjQiLCJjMjUiXSwiYWlvIjoiRTJSZ1lHalYrRmkxMkVONkhzZmpnMEt4T1VWMlpyTW1jU1pZSjhXMUpHNWZjYW4wMlZRQSIsImFtciI6WyJwd2QiXSwiYXBwX2Rpc3BsYXluYW1lIjoiUmVzcGEgTzM2NSIsImFwcGlkIjoiMzhmNTgwYjAtMjE0YS00OWU1LTk3ZTQtZjEyMDI3MTQ3YzUyIiwiYXBwaWRhY3IiOiIxIiwiZmFtaWx5X25hbWUiOiJWYW5jZSIsImdpdmVuX25hbWUiOiJBZGVsZSIsImlkdHlwIjoidXNlciIsImlwYWRkciI6IjkxLjE1Ny4yMTkuMjUwIiwibmFtZSI6IkFkZWxlIFZhbmNlIiwib2lkIjoiOTdiMTRlYTYtZmRhNC00YzMyLWJkZjItY2M4YzY2MmI2NGVjIiwicGxhdGYiOiIxNCIsInB1aWQiOiIxMDAzMjAwMEUwNjA2NDlGIiwicmgiOiIwLkFBQUEzNTBiQlBkSDRFLVpNWW5aNEdvaWk3Q0E5VGhLSWVWSmwtVHhJQ2NVZkZKekFPVS4iLCJzY3AiOiJDYWxlbmRhcnMuUmVhZFdyaXRlIFVzZXIuUmVhZCBwcm9maWxlIG9wZW5pZCBlbWFpbCIsInNpZ25pbl9zdGF0ZSI6WyJrbXNpIl0sInN1YiI6InBnWkI0dVE3eHBtOHZWemRmVVNFVjNaMXJmeTQxTExpZ0VQZ0lQbXBQdnMiLCJ0ZW5hbnRfcmVnaW9uX3Njb3BlIjoiRVUiLCJ0aWQiOiIwNDFiOWRkZi00N2Y3LTRmZTAtOTkzMS04OWQ5ZTA2YTIyOGIiLCJ1bmlxdWVfbmFtZSI6IkFkZWxlVkBqb2hsaW5kcS5vbm1pY3Jvc29mdC5jb20iLCJ1cG4iOiJBZGVsZVZAam9obGluZHEub25taWNyb3NvZnQuY29tIiwidXRpIjoiRFBSdTkxQ09Da0tWOXA4Q3o4bWtBQSIsInZlciI6IjEuMCIsIndpZHMiOlsiYjc5ZmJmNGQtM2VmOS00Njg5LTgxNDMtNzZiMTk0ZTg1NTA5Il0sInhtc19zdCI6eyJzdWIiOiJNb2xHLTU1OHdXNkJGV0M0MmVYQnUyb09FNnFtQUNRQ2c0b0R3ZDdNdHhvIn0sInhtc190Y2R0IjoxNTk5NDI3MzY5fQ.Ghn4mT-j2hGGqCvFH61-ptouNaDowNlKEdSwxvBthWZGMSC_7aFyHzA6VAbFak7abhOx5jkWXP_7wmbGDrj7gOw1Hy1TquAs-FqD7wXRSH6oMSu3GOeUymy4p8BDpazicFHwhjLKMaISJuo_T0KZaduLbIYOv4ucGgrnLqJkQtwDchTQvINLYJg_Do_3uqlqg9CVpG3hTtP475UpfItLzOa9DDfFj4peRSYZ1yBjp-5-Z65cQ0CRSRoizeBlD8FcqLXBDcmSmFi4VCjthfgg2-jo8aRkwp8YJVCzaiRhTt7EfnVfZx1i_m_bHJu1q4watUxUho8UFc8jKatbblZj4Q", "refresh_token": "0.AAAA350bBPdH4E-ZMYnZ4Goii7CA9ThKIeVJl-TxICcUfFJzAOU.AgABAAAAAAB2UyzwtQEKR7-rWbgdcBZIAQDs_wMA9P8i22t3BgIa4avsvjxavxm6cgH3FNu0yzzA6usW6sJFEzXeZvfO58UQcs3iujaSzLtYFkx-iA0VsKJ4u3jAdLSV1FOafAeBBmjJZ88MCX0NXM49eF2SZQ37_Ih_GQlMLJ-FcmKQTiQeBMb9nd_OThgSDD1orWSsMxneiize3w5IpozHo4Z79bcypGdrbg8pUvDlC2i8mPIftS8OpthAnIb1Jyp6TfgLi1DnkU2ngmnUne051Ml2fTnsNLBprCQcdXoXGVUiQO1kZY2miqiyr4wlsWEF85y1UtgGEFJXpYQxwixbYaicIG8lpZ-l7tICB9QJlASiHb-i53_L_9vo14x7WzZEPg335YNN7pEnjwwjFtvCUiBLAUVhtcmMFVEXxPntTL8EiuCKx0bVojQnnPQSjs1_E5S4NxPb1jnhIBREr7peeORubXftDfk_RULII8lIywrIaNc_-cPzlGfGKR0mbXejAHNsER4i4j-ZqUfrCS0Noiagmfe46FqIPoZ4KH8QXaz-e9yemJec2wpF5pvl0XhcJdmtpY4lOqRqzl6LQ8k3D43a9rXP1CvrMsN0QmP08a19V_PjblIf_mu61ze-VUVcnTC2e6XjP-cI9TpHJWVv9pZZsZcutwnwdUWjXAJbDXVDnvdr6DLv3d8pblgiOwwPmLmPTgT-WGuJ4Xrramu21dR2iqw3pszOynru937uNkPbIqvbBIXcLlNNg1l6Qvk9mwKdWcZYFq1aAQq8K91eIRHbQAK1QDwhIVznfZCxZnxZKjB-H-VTbfhsbPF53tCoO4Y7IXN6Yb6ab3Daj76T1jnLMj7kQFr4wC9ze2oLOo5VOaupZ889PVEADYYVnpS-ICJ7vi4UUSqJkAYEV1BV8afKhhWjbTjsNVIKEBIGqaPsB30YUxf9iDOhNrERYAScDt6VrPG9UhI0L-tqE1q9LZvC13T2B4uqzNj769BHGA", "expires_at": 1608018334.8416443}"""
    client_id="38f580b0-214a-49e5-97e4-f12027147c52"
    client_secret="75qfd8_.h.9E_QjmLOU~~Ikt56rgyT5_N3"
    auth_url="https://login.microsoftonline.com/041b9ddf-47f7-4fe0-9931-89d9e06a228b/oauth2/v2.0/authorize"
    token_url="https://login.microsoftonline.com/041b9ddf-47f7-4fe0-9931-89d9e06a228b/oauth2/v2.0/token"
    api_url = "https://graph.microsoft.com/v1.0"
    api = MicrosoftApi(token=token, token_url=token_url, client_id=client_id, client_secret=client_secret, api_url=api_url)
    return api

# This requires that there is actually a listener behind TSL. Otherwise subscription creation fails.
url = "https://fgno8xsw1i.execute-api.eu-north-1.amazonaws.com/v1/o365/notification_callback"


@pytest.mark.skip("API parameters need to be set manually")
def test__ensure_notification():
    s = O365Notifications(create_api())
    clear_all_subscriptions()
    id1, created1 = s.ensureNotifications(notification_url=url, resource="me/events", events=["updated", "deleted", "created"], client_state="tila1")
    id2, created2 = s.ensureNotifications(notification_url=url, resource="me/events", events=["updated", "deleted", "created"], client_state="tila1")
    assert id1 == id2
    assert created1
    assert not created2


@pytest.mark.skip("API parameters need to be set manually and there needs to be working endpoint with TSL")
def test__notification_manipulations():
    s = O365Notifications(create_api())
    startCount = len(s.list())


    id = s.create(
        resource="me/events",
        events=["updated", "deleted", "created"],
        notification_url=url,
        client_state="tila1"
    )
    r = s.get(id)
    s.renew(id)

    assert r.get("resource") == "me/events"
    subscriptions = s.list()
    assert len(subscriptions)-startCount == 1
    assert id in {i.get("id"):i for i in s.list()}
    s.delete(id)
    subscriptions = s.list()
    assert len(subscriptions)-startCount == 0
    clear_all_subscriptions()


def clear_all_subscriptions():
    s = O365Notifications(create_api())
    for i in s.list():
        s.delete(i.get("id"))
