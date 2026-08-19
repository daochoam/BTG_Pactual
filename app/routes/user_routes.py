from fastapi import APIRouter, Depends, HTTPException
from app.controllers.user_controller import get_all_users_controller
from app.controllers.auth_decorators import auth_required
from app.documents.auth_models import SessionUserModel
from app.schemas.users import users_db

users_routes = APIRouter(prefix="/users",tags=["users"])

@users_routes.get("/")
def get_users(user_session: SessionUserModel = Depends(auth_required())):
    """
    Obtener todos los usuarios si el rol es ADMIN,
    de lo contrario devuelve solo la información del usuario autenticado
    """
    user_response = users_db.get_item(Key={"id": user_session.user_id})

    if not user_response.get("Item"):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user_session.role.lower() == "admin":
        return get_all_users_controller()
    else:
        return get_all_users_controller(user_session)