# app/routes/auth_ns.py
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.controllers.auth_controller import register_user, login_user, logout_user
from app.controllers.auth_decorators import access_token_scheme, refresh_token_scheme
from app.documents.auth_models import RegisterUserModel, LoginUserModel


auth_routes = APIRouter(prefix="/auth", tags=["auth"])

@auth_routes.post('/register')
def register(data: RegisterUserModel):
    response = register_user(data)
    return response

@auth_routes.post('/login')
def login(data: LoginUserModel):
    return login_user(data)


@auth_routes.post('/logout', summary="Cerrar sesión y revocar el refresh token")
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(access_token_scheme),
    refresh_token: Optional[str] = Depends(refresh_token_scheme),
):
    # Se reconstruye la cabecera completa para no cambiar el contrato del
    # controlador, que espera "Bearer <token>".
    authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
    return logout_user(authorization, refresh_token)

