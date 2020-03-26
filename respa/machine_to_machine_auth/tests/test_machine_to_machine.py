import pytest
import jwt
from users.models import User
from rest_framework_jwt.settings import api_settings

jwt_decode_handler = api_settings.JWT_DECODE_HANDLER

@pytest.mark.django_db
def test_get_auth_token(client):
    username = 'john_doe'
    User.objects.create_user(username=username, password='pass123')
    response = client.post('/api-token-auth/', {'username': 'john_doe', 'password': 'pass123'})
    assert response.status_code == 200
    assert response.data['token'] != None
    payload = jwt_decode_handler(response.data['token'])
    assert payload['username'] == username
