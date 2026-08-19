# app/controllers/auth_decorators.py
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import Config, cognito_client
from app.documents.auth_models import SessionUserModel

# ---------------------------------------------------------------------------
# Esquemas de seguridad
#
# Declararlos así (en vez de leer las cabeceras del Request a mano) es lo que
# hace que aparezcan en el OpenAPI: Swagger dibuja el botón "Authorize", marca
# con candado los endpoints protegidos y permite probarlos desde la propia
# documentación.
#
# auto_error=False para seguir devolviendo nuestros propios mensajes de error
# en vez del 403 genérico de FastAPI.
# ---------------------------------------------------------------------------
access_token_scheme = HTTPBearer(
    scheme_name="AccessToken",
    description=(
        "Token de acceso de Cognito. Lo devuelve POST /api/auth/login en la "
        "cabecera `Authorization`. Pega aquí solo el token, sin el prefijo Bearer."
    ),
    auto_error=False,
)

refresh_token_scheme = APIKeyHeader(
    name="X-Refresh-Token",
    scheme_name="RefreshToken",
    description=(
        "Refresh token de Cognito. Lo devuelve POST /api/auth/login en la "
        "cabecera `X-Refresh-Token`. Se usa para renovar el acceso cuando expira."
    ),
    auto_error=False,
)

def validate_tokens(access_header, refresh_token):
    if not access_header or not access_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token requerido")

    access_token = access_header.split(" ")[1]

    try:
        user_info = cognito_client.get_user(AccessToken=access_token)
        attributes = {attr["Name"]: attr["Value"] for attr in user_info["UserAttributes"]}
    except cognito_client.exceptions.NotAuthorizedException:
        try:
            response = cognito_client.initiate_auth(
                ClientId=Config.AWS_COGNITO_CLIENT_ID,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": refresh_token}
            )
            access_token = response["AuthenticationResult"]["AccessToken"]
            refresh_token = response["AuthenticationResult"].get("RefreshToken", refresh_token)
            user_info = cognito_client.get_user(AccessToken=access_token)
            attributes = {attr["Name"]: attr["Value"] for attr in user_info["UserAttributes"]}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token inválido o refresh token expirado: {str(e)}")

    payload = {
        "user_id": attributes.get("sub"),
        "role": attributes.get("custom:role"),
    }
    return payload


def get_auth_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(access_token_scheme),
    refresh_token: Optional[str] = Depends(refresh_token_scheme),
):
    # validate_tokens sigue recibiendo la cabecera completa, tal y como llega
    # por HTTP, para no cambiar su contrato.
    access_header = f"{credentials.scheme} {credentials.credentials}" if credentials else None
    return validate_tokens(access_header, refresh_token)


def auth_required(require_admin: bool = False):
    def dependency(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(access_token_scheme),
        refresh_token: Optional[str] = Depends(refresh_token_scheme),
    ):
        payload = get_auth_payload(credentials, refresh_token)
        if require_admin and payload.get("role", "").lower() != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acceso denegado")
        return SessionUserModel(**payload)

    return dependency
