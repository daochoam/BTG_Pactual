"""
Esquema DynamoDB derivado de los modelos.

No hay ninguna lista de tablas escrita a mano: se recorre el registro de
`app/models/registry.py`, que se llena solo con cada clase que hereda de
`DynamoModel` y declara `table_name`.

En AWS la fuente de verdad es CloudFormation (resources/dynamodb.json, que se
genera desde este mismo registro). Esto se usa en local y como respaldo en
runtime cuando AUTO_CREATE_TABLES está activo.
"""

import logging

from app.config import Config
from app.models.registry import iter_models
from app.utils.create_table import ensure_table

logger = logging.getLogger(__name__)


def table_definitions():
    """Definición de todas las tablas declaradas por los modelos."""
    return [model.table_definition() for model in iter_models()]


def ensure_schema(force: bool = False):
    """
    Crea las tablas que falten y ajusta las existentes.

    Es idempotente y tolerante a fallos: un error de permisos o una carrera
    entre Lambdas concurrentes no debe tumbar el arranque de la API.
    """
    if not force and not Config.AUTO_CREATE_TABLES:
        logger.debug("AUTO_CREATE_TABLES desactivado, se omite ensure_schema()")
        return

    for definition in table_definitions():
        try:
            ensure_table(
                table_name=definition["physical_name"],
                key_schema=definition["key_schema"],
                attribute_definitions=definition["attribute_definitions"],
                global_secondary_indexes=definition["global_secondary_indexes"],
            )
        except Exception:
            logger.error(
                "No se pudo asegurar la tabla '%s'", definition["physical_name"], exc_info=True
            )


def tables():
    """Nombres lógicos de las tablas registradas."""
    return [model.table_name for model in iter_models()]


# Alias retrocompatible con el nombre anterior.
def dynamo_db():
    ensure_schema(force=True)


__all__ = ["table_definitions", "ensure_schema", "tables", "dynamo_db"]
