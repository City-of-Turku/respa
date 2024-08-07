from rest_framework_simplejwt.authentication import (
    JWTAuthentication as SimpleJWTAuthentication
)

from helusers._oidc_auth_impl import JWT as _JWT, ValidationError
from jose import jwt


class JWT(_JWT):
    def validate(self, keys, audience, **args):
        options = {
            "verify_at_hash": False
        }
        for required_claim in ["aud", "exp"]:
            options[f"require_{required_claim}"] = True

        jwt.decode(
            self._encoded_jwt,
            keys,
            algorithms=self.settings.ALLOWED_ALGORITHMS,
            options=options,
            audience=self.settings.AUDIENCE
        )

        claims = self.claims
        if "aud" not in claims:
            raise ValidationError("Missing required 'aud' claim.")

        if "aud" in claims:
            claim_audiences = claims["aud"]
            if isinstance(claim_audiences, str):
                claim_audiences = {claim_audiences}
            if isinstance(audience, str):
                audience = {audience}
            if len(set(audience).intersection(claim_audiences)) == 0:
                raise ValidationError("Invalid audience.")

class JWTAuthentication(SimpleJWTAuthentication):
    def authenticate(self, request):
        return super().authenticate(request)
