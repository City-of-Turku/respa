from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class TokenObtainSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs['token'] = attrs['access']
        return attrs


class TokenObtainView(TokenObtainPairView):
    serializer_class = TokenObtainSerializer

obtain_jwt_token = TokenObtainView.as_view()