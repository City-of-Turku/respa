from datetime import timezone, datetime, timedelta
import pytest
from respa_o365.o365_calendar import O365Calendar, MicrosoftApi, Event
from respa_o365.o365_reservation_repository import O365ReservationRepository
from respa_o365.reservation_repository_contract import ReservationRepositoryContract
from respa_o365.reservation_sync_item import ReservationSyncItem


def api_client():
    token = """{"token_type": "Bearer", "scope": ["Calendars.ReadWrite", "User.Read", "profile", "openid", "email"], "expires_in": 3599, "ext_expires_in": 3599, "access_token": "eyJ0eXAiOiJKV1QiLCJub25jZSI6Ik03OVo0UmstYmhjak5JZV9MXy1nRlEzemx0QVU1NzNnX0YxZXpiTVhiSlEiLCJhbGciOiJSUzI1NiIsIng1dCI6ImtnMkxZczJUMENUaklmajRydDZKSXluZW4zOCIsImtpZCI6ImtnMkxZczJUMENUaklmajRydDZKSXluZW4zOCJ9.eyJhdWQiOiIwMDAwMDAwMy0wMDAwLTAwMDAtYzAwMC0wMDAwMDAwMDAwMDAiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC8wNDFiOWRkZi00N2Y3LTRmZTAtOTkzMS04OWQ5ZTA2YTIyOGIvIiwiaWF0IjoxNjA4MDE0NDM3LCJuYmYiOjE2MDgwMTQ0MzcsImV4cCI6MTYwODAxODMzNywiYWNjdCI6MCwiYWNyIjoiMSIsImFjcnMiOlsidXJuOnVzZXI6cmVnaXN0ZXJzZWN1cml0eWluZm8iLCJ1cm46bWljcm9zb2Z0OnJlcTEiLCJ1cm46bWljcm9zb2Z0OnJlcTIiLCJ1cm46bWljcm9zb2Z0OnJlcTMiLCJjMSIsImMyIiwiYzMiLCJjNCIsImM1IiwiYzYiLCJjNyIsImM4IiwiYzkiLCJjMTAiLCJjMTEiLCJjMTIiLCJjMTMiLCJjMTQiLCJjMTUiLCJjMTYiLCJjMTciLCJjMTgiLCJjMTkiLCJjMjAiLCJjMjEiLCJjMjIiLCJjMjMiLCJjMjQiLCJjMjUiXSwiYWlvIjoiRTJSZ1lHalYrRmkxMkVONkhzZmpnMEt4T1VWMlpyTW1jU1pZSjhXMUpHNWZjYW4wMlZRQSIsImFtciI6WyJwd2QiXSwiYXBwX2Rpc3BsYXluYW1lIjoiUmVzcGEgTzM2NSIsImFwcGlkIjoiMzhmNTgwYjAtMjE0YS00OWU1LTk3ZTQtZjEyMDI3MTQ3YzUyIiwiYXBwaWRhY3IiOiIxIiwiZmFtaWx5X25hbWUiOiJWYW5jZSIsImdpdmVuX25hbWUiOiJBZGVsZSIsImlkdHlwIjoidXNlciIsImlwYWRkciI6IjkxLjE1Ny4yMTkuMjUwIiwibmFtZSI6IkFkZWxlIFZhbmNlIiwib2lkIjoiOTdiMTRlYTYtZmRhNC00YzMyLWJkZjItY2M4YzY2MmI2NGVjIiwicGxhdGYiOiIxNCIsInB1aWQiOiIxMDAzMjAwMEUwNjA2NDlGIiwicmgiOiIwLkFBQUEzNTBiQlBkSDRFLVpNWW5aNEdvaWk3Q0E5VGhLSWVWSmwtVHhJQ2NVZkZKekFPVS4iLCJzY3AiOiJDYWxlbmRhcnMuUmVhZFdyaXRlIFVzZXIuUmVhZCBwcm9maWxlIG9wZW5pZCBlbWFpbCIsInNpZ25pbl9zdGF0ZSI6WyJrbXNpIl0sInN1YiI6InBnWkI0dVE3eHBtOHZWemRmVVNFVjNaMXJmeTQxTExpZ0VQZ0lQbXBQdnMiLCJ0ZW5hbnRfcmVnaW9uX3Njb3BlIjoiRVUiLCJ0aWQiOiIwNDFiOWRkZi00N2Y3LTRmZTAtOTkzMS04OWQ5ZTA2YTIyOGIiLCJ1bmlxdWVfbmFtZSI6IkFkZWxlVkBqb2hsaW5kcS5vbm1pY3Jvc29mdC5jb20iLCJ1cG4iOiJBZGVsZVZAam9obGluZHEub25taWNyb3NvZnQuY29tIiwidXRpIjoiRFBSdTkxQ09Da0tWOXA4Q3o4bWtBQSIsInZlciI6IjEuMCIsIndpZHMiOlsiYjc5ZmJmNGQtM2VmOS00Njg5LTgxNDMtNzZiMTk0ZTg1NTA5Il0sInhtc19zdCI6eyJzdWIiOiJNb2xHLTU1OHdXNkJGV0M0MmVYQnUyb09FNnFtQUNRQ2c0b0R3ZDdNdHhvIn0sInhtc190Y2R0IjoxNTk5NDI3MzY5fQ.Ghn4mT-j2hGGqCvFH61-ptouNaDowNlKEdSwxvBthWZGMSC_7aFyHzA6VAbFak7abhOx5jkWXP_7wmbGDrj7gOw1Hy1TquAs-FqD7wXRSH6oMSu3GOeUymy4p8BDpazicFHwhjLKMaISJuo_T0KZaduLbIYOv4ucGgrnLqJkQtwDchTQvINLYJg_Do_3uqlqg9CVpG3hTtP475UpfItLzOa9DDfFj4peRSYZ1yBjp-5-Z65cQ0CRSRoizeBlD8FcqLXBDcmSmFi4VCjthfgg2-jo8aRkwp8YJVCzaiRhTt7EfnVfZx1i_m_bHJu1q4watUxUho8UFc8jKatbblZj4Q", "refresh_token": "0.AAAA350bBPdH4E-ZMYnZ4Goii7CA9ThKIeVJl-TxICcUfFJzAOU.AgABAAAAAAB2UyzwtQEKR7-rWbgdcBZIAQDs_wMA9P8i22t3BgIa4avsvjxavxm6cgH3FNu0yzzA6usW6sJFEzXeZvfO58UQcs3iujaSzLtYFkx-iA0VsKJ4u3jAdLSV1FOafAeBBmjJZ88MCX0NXM49eF2SZQ37_Ih_GQlMLJ-FcmKQTiQeBMb9nd_OThgSDD1orWSsMxneiize3w5IpozHo4Z79bcypGdrbg8pUvDlC2i8mPIftS8OpthAnIb1Jyp6TfgLi1DnkU2ngmnUne051Ml2fTnsNLBprCQcdXoXGVUiQO1kZY2miqiyr4wlsWEF85y1UtgGEFJXpYQxwixbYaicIG8lpZ-l7tICB9QJlASiHb-i53_L_9vo14x7WzZEPg335YNN7pEnjwwjFtvCUiBLAUVhtcmMFVEXxPntTL8EiuCKx0bVojQnnPQSjs1_E5S4NxPb1jnhIBREr7peeORubXftDfk_RULII8lIywrIaNc_-cPzlGfGKR0mbXejAHNsER4i4j-ZqUfrCS0Noiagmfe46FqIPoZ4KH8QXaz-e9yemJec2wpF5pvl0XhcJdmtpY4lOqRqzl6LQ8k3D43a9rXP1CvrMsN0QmP08a19V_PjblIf_mu61ze-VUVcnTC2e6XjP-cI9TpHJWVv9pZZsZcutwnwdUWjXAJbDXVDnvdr6DLv3d8pblgiOwwPmLmPTgT-WGuJ4Xrramu21dR2iqw3pszOynru937uNkPbIqvbBIXcLlNNg1l6Qvk9mwKdWcZYFq1aAQq8K91eIRHbQAK1QDwhIVznfZCxZnxZKjB-H-VTbfhsbPF53tCoO4Y7IXN6Yb6ab3Daj76T1jnLMj7kQFr4wC9ze2oLOo5VOaupZ889PVEADYYVnpS-ICJ7vi4UUSqJkAYEV1BV8afKhhWjbTjsNVIKEBIGqaPsB30YUxf9iDOhNrERYAScDt6VrPG9UhI0L-tqE1q9LZvC13T2B4uqzNj769BHGA", "expires_at": 1608018334.8416443}"""
    client_id="38f580b0-214a-49e5-97e4-f12027147c52"
    client_secret="75qfd8_.h.9E_QjmLOU~~Ikt56rgyT5_N3"
    auth_url="https://login.microsoftonline.com/041b9ddf-47f7-4fe0-9931-89d9e06a228b/oauth2/v2.0/authorize"
    token_url="https://login.microsoftonline.com/041b9ddf-47f7-4fe0-9931-89d9e06a228b/oauth2/v2.0/token"
    api_url = "https://graph.microsoft.com/v1.0"
    return MicrosoftApi(token=token, token_url=token_url, client_id=client_id, client_secret=client_secret, api_url=api_url)

class RememberCreatedItems:

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._ids = []

    def create_item(self, item):
        item_id, change_key = self._wrapped.create_item(item)
        self._ids.append(item_id)
        return item_id, change_key

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def created_item_ids(self):
        return self._ids


@pytest.mark.skip(reason="Possible calendar id and microsoft API settings needs to be obtained manually")
class TestO365ReservationRepository(ReservationRepositoryContract):

    @pytest.fixture
    def a_repo(self):
        api = api_client()
        cal = O365Calendar(microsoft_api=api)
        # cal = O365Calendar(calendar_id="AAMkADQ2NDBkOGU5LWIwMjctNGE1NC1hYTkzLTVkNTVkNTkwYWVjYgBGAAAAAACChAIIGzkZTZEGveyb2ATGBwA1Oe2EuAOdRLcbg3PDQyqhAAAAAAEGAAA1Oe2EuAOdRLcbg3PDQyqhAAA_zXX1AAA=", microsoft_api=api)
        repo = RememberCreatedItems(O365ReservationRepository(cal))
        yield repo
        # Remove ids that were created
        ids = repo.created_item_ids()
        for item_id in ids:
            cal.remove_event(item_id)



def create_events(count):
    cal=O365Calendar(microsoft_api=api_client())
    now = datetime.now()
    begin = datetime(year=now.year,month=now.month,day=now.day,hour=0,minute=0,tzinfo=timezone(timedelta(hours=2)))
    print("{}".format(begin))
    for i in range(0, count):
        e = Event()
        e.subject = "#{}: {}".format(i, begin)
        e.begin = begin + timedelta(hours=1*i)
        e.end = e.begin + timedelta(minutes=10)
        event_id, change_key = cal.create_event(e)

def list_events():
    cal=O365Calendar(microsoft_api=api_client())
    events = cal.get_events()
    count = 0
    print("\n")
    for id, e1 in events.items():
        count += 1
        e2 = cal.get_event(id)
        print("{}: {}".format(id, e1))
        print("{}: {}".format(id, e2))
    print("\nThere are {} events.".format(count))
    assert count == 55

def remove_events():
    cal=O365Calendar(microsoft_api=api_client())
    events = cal.get_events()
    for id, e in events.items():
        cal.remove_event(id)
