import pytest
from users.models import User
from rest_framework_simplejwt.authentication import JWTAuthentication

@pytest.mark.django_db
def test_get_auth_token(client):
    jwt = JWTAuthentication()
    username = 'john_doe'
    User.objects.create_user(username=username, password='pass123')
    response = client.post('/api-token-auth/', {'username': 'john_doe', 'password': 'pass123'})
    assert response.status_code == 200
    assert response.data['access'] != None
    validated_token = jwt.get_validated_token(response.data['access'])
    user = jwt.get_user(validated_token)
    assert user.username == username
