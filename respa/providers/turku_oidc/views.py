from allauth.socialaccount.providers.oauth2.views import (
    OAuth2LoginView, OAuth2CallbackView,
)
from respa.providers.turku_oidc.provider import OIDCOAuth2Adapter


oauth2_login = OAuth2LoginView.adapter_view(OIDCOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(OIDCOAuth2Adapter)