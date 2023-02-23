from rest_framework_simplejwt.authentication import (
    JWTAuthentication as SimpleJWTAuthentication
)

class JWTAuthentication(SimpleJWTAuthentication):
    def authenticate(self, request):
        return super().authenticate(request)
