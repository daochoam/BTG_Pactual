# app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Config
from app.dynamo_db import ensure_schema
from app.routes.routes import main_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Arranque de la aplicación.

    En AWS la infraestructura la crea `serverless deploy` (CloudFormation), así
    que esto normalmente no hace nada. Si AUTO_CREATE_TABLES está activo se
    verifica el esquema y se crea/ajusta lo que falte: útil en local y como red
    de seguridad en el primer arranque en frío tras un despliegue.
    """
    if Config.AUTO_CREATE_TABLES:
        try:
            ensure_schema()
        except Exception:
            logger.error("Fallo al verificar el esquema de DynamoDB", exc_info=True)
    yield


DESCRIPCION = """
API de fondos de inversión de BTG Pactual.

### Cómo probar los endpoints protegidos

1. Crea una cuenta con `POST /api/auth/register`.
2. Llama a `POST /api/auth/login`. La respuesta trae dos cabeceras:
   `Authorization` (el token de acceso) y `X-Refresh-Token`.
3. Pulsa **Authorize** arriba a la derecha y pega cada uno en su campo.
   En *AccessToken* va solo el token, sin el prefijo `Bearer`.

Los endpoints con candado necesitan ambos. Los marcados como de administrador
exigen además que el usuario tenga `custom:role = ADMIN` en Cognito.
"""

TAGS = [
    {"name": "auth", "description": "Registro, inicio y cierre de sesión contra Cognito."},
    {"name": "users", "description": "Consulta de usuarios. Requiere sesión."},
    {"name": "category", "description": "Categorías de fondos. Crear y editar es de administrador."},
    {"name": "bank-funds", "description": "Fondos de inversión. Crear y editar es de administrador."},
    {"name": "user-bank-funds", "description": "Suscripción y retiro de fondos por parte del usuario."},
    {"name": "user-bank-funds-audit", "description": "Histórico de movimientos sobre los fondos."},
    {"name": "health", "description": "Estado del servicio."},
]


def create_app() -> FastAPI:
    """
    Crea y configura la aplicación FastAPI
    """
    app = FastAPI(
        title="BTG API",
        description=DESCRIPCION,
        version="2.0.0",
        openapi_tags=TAGS,
        contact={
            "name": "Daniel Ochoa",
            "email": "dfom89@gmail.com",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        docs_url="/swagger",  # cambia la ruta de swagger (por defecto /docs)
        redoc_url="/redocs",  # cambia la ruta de redoc (por defecto /redoc)
        swagger_ui_parameters={
            # El token sobrevive a recargar la página: evita tener que
            # reautenticarse en cada prueba.
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "docExpansion": "none",
            "filter": True,
            "tryItOutEnabled": True,
        },
        lifespan=lifespan,
    )

    # Guardar configuración global en app.state
    app.state.config = Config

    @app.get("/")
    def read_root():
        return {"message": "Hola desde FastAPI BTG_Pactual"}

    @app.get("/health", tags=["health"])
    def health():
        return {
            "status": "ok",
            "stage": Config.STAGE,
            "environment": Config.ENVIRONMENT_MODE,
        }

    # Registrar routers automáticamente
    for router in main_routes:
        app.include_router(router, prefix="/api")

    return app


# Crear instancia de la app para uvicorn
app = create_app()
