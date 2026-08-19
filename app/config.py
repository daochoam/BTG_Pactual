import os
import boto3
import logging
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Cargar variables del .env
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    ENVIRONMENT_MODE = os.getenv("ENVIRONMENT_MODE", "development")
    STAGE = os.getenv("STAGE", "dev")
    # Configuración de Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")

    # Configuración de AWS
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", None)
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

    # Endpoint alterno para DynamoDB Local (ej: http://localhost:8000)
    DYNAMO_ENDPOINT_URL = os.getenv("DYNAMO_ENDPOINT_URL") or None

    # Prefijo de tablas. En AWS lo inyecta serverless.yml
    # (ej: "fastapi-app-prod-"); en local queda vacío.
    TABLE_PREFIX = os.getenv("TABLE_PREFIX", "")

    # Crear/ajustar las tablas al arrancar. En producción CloudFormation ya las
    # gestiona, esto solo actúa como red de seguridad si alguna falta.
    AUTO_CREATE_TABLES = os.getenv(
        "AUTO_CREATE_TABLES",
        "true" if ENVIRONMENT_MODE == "development" else "false",
    ).lower() in ("1", "true", "yes")

    # Nombre de tabla por defecto (legacy, se mantiene por compatibilidad)
    DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "Users")

    AWS_COGNITO_CLIENT_ID = os.getenv("AWS_COGNITO_CLIENT_ID", "")
    AWS_COGNITO_CLIENT_SECRET = os.getenv("AWS_COGNITO_CLIENT_SECRET", "")
    AWS_COGNITO_DOMAIN = os.getenv("AWS_COGNITO_DOMAIN", "")
    AWS_COGNITO_USER_POOL_ID = os.getenv("AWS_COGNITO_USER_POOL_ID", "")

    # S3 / CDN. En AWS los inyecta CloudFormation; en local se dejan vacíos.
    S3_UPLOADS_BUCKET = os.getenv("S3_UPLOADS_BUCKET", "")
    S3_STATIC_SITE_BUCKET = os.getenv("S3_STATIC_SITE_BUCKET", "")
    CDN_URL = os.getenv("CDN_URL", "")

    SES_VERIFIED_EMAIL = os.getenv("SES_VERIFIED_EMAIL", "noreply@btgpactual.com")
    AWS_SMTP_USER = os.getenv("AWS_SMTP_USER", "TU_SMTP_USER")
    AWS_SMTP_PASS = os.getenv("AWS_SMTP_PASS", "TU_SMTP_PASS")
    AWS_SMTP_HOST = os.getenv("AWS_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    AWS_SMTP_PORT = int(os.getenv("AWS_SMTP_PORT", 587))

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_jwt_secret_key")
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", 30))
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    # Usando zoneinfo
    TIME_ZONE = ZoneInfo(os.getenv("TIME_ZONE", "UTC"))


# ---------------------------------------------------------------------------
# Resolución de nombres de tabla
#
# El nombre real lo decide la infraestructura, no el código: primero se busca
# la variable de entorno que inyecta serverless.yml (salida de CloudFormation)
# y si no existe se compone con TABLE_PREFIX. Así el mismo código sirve para
# local, dev y prod sin tocar una línea.
# ---------------------------------------------------------------------------
TABLE_ENV_VARS = {
    "Users": "DYNAMO_TABLE_USERS",
    "Categories": "DYNAMO_TABLE_CATEGORIES",
    "BankFunds": "DYNAMO_TABLE_BANK_FUNDS",
    "UserBankFunds": "DYNAMO_TABLE_USER_BANK_FUNDS",
    "UserBankFundsAudit": "DYNAMO_TABLE_USER_BANK_FUNDS_AUDIT",
}


def table_name(logical_name: str) -> str:
    """Devuelve el nombre físico de una tabla a partir de su nombre lógico."""
    env_var = TABLE_ENV_VARS.get(logical_name)
    if env_var:
        resolved = os.getenv(env_var)
        if resolved:
            return resolved
    return f"{Config.TABLE_PREFIX}{logical_name}"


boto3_kwargs = {"region_name": Config.AWS_REGION}
if Config.ENVIRONMENT_MODE == "development":
    # En Lambda las credenciales llegan por el rol de ejecución; solo en local
    # se toman del .env.
    if Config.AWS_ACCESS_KEY_ID and Config.AWS_SECRET_ACCESS_KEY:
        boto3_kwargs.update({
            "aws_access_key_id": Config.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": Config.AWS_SECRET_ACCESS_KEY,
        })

dynamo_kwargs = dict(boto3_kwargs)
if Config.DYNAMO_ENDPOINT_URL:
    dynamo_kwargs["endpoint_url"] = Config.DYNAMO_ENDPOINT_URL

# Recurso para operaciones de datos (put_item, get_item, etc.)
dynamodb = boto3.resource("dynamodb", **dynamo_kwargs)
# Cliente para administración de tablas (create_table, list_tables, etc.)
dynamodb_client = boto3.client("dynamodb", **dynamo_kwargs)

cognito_client = boto3.client("cognito-idp", **boto3_kwargs)
s3_client = boto3.client("s3", **boto3_kwargs)


def _resolve_cognito_client_secret() -> str:
    """
    Obtiene el client secret de Cognito.

    Normalmente serverless.yml lo inyecta desde CloudFormation. Si no está
    disponible (por ejemplo, si se prefiere no guardarlo en variables de
    entorno) se consulta a Cognito una sola vez en el arranque en frío.
    """
    if Config.AWS_COGNITO_CLIENT_SECRET:
        return Config.AWS_COGNITO_CLIENT_SECRET

    # En local/tests el secreto viene del .env; no se consulta a AWS.
    if Config.ENVIRONMENT_MODE == "development":
        return ""

    if not (Config.AWS_COGNITO_USER_POOL_ID and Config.AWS_COGNITO_CLIENT_ID):
        return ""

    try:
        response = cognito_client.describe_user_pool_client(
            UserPoolId=Config.AWS_COGNITO_USER_POOL_ID,
            ClientId=Config.AWS_COGNITO_CLIENT_ID,
        )
        return response["UserPoolClient"].get("ClientSecret", "")
    except Exception:
        logger.warning("No se pudo resolver el client secret de Cognito", exc_info=True)
        return ""


Config.AWS_COGNITO_CLIENT_SECRET = _resolve_cognito_client_secret()

__all__ = [
    "Config",
    "dynamodb",
    "dynamodb_client",
    "cognito_client",
    "s3_client",
    "table_name",
]
