"""
Creación / ajuste idempotente de tablas DynamoDB.

En producción la fuente de verdad es CloudFormation (resources/dynamodb.yml).
Este módulo es la red de seguridad equivalente para desarrollo local, DynamoDB
Local y arranques en frío donde alguna tabla pudiera faltar: crea lo que no
existe y ajusta lo que ya existe sin destruir datos.
"""

import logging
import botocore

from app.config import dynamodb_client

logger = logging.getLogger(__name__)


def _describe(table_name):
    try:
        return dynamodb_client.describe_table(TableName=table_name)["Table"]
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return None


def _create(table_name, key_schema, attribute_definitions, global_secondary_indexes, provisioned_throughput):
    params = {
        "TableName": table_name,
        "KeySchema": key_schema,
        "AttributeDefinitions": attribute_definitions,
        "BillingMode": "PAY_PER_REQUEST" if provisioned_throughput is None else "PROVISIONED",
    }

    if provisioned_throughput:
        params["ProvisionedThroughput"] = provisioned_throughput

    if global_secondary_indexes:
        params["GlobalSecondaryIndexes"] = [
            {k: v for k, v in gsi.items() if k != "ProvisionedThroughput" or provisioned_throughput}
            for gsi in global_secondary_indexes
        ]

    try:
        dynamodb_client.create_table(**params)
        logger.info("Tabla '%s' creada", table_name)
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            # Otra Lambda concurrente la creó primero: no es un error.
            logger.info("Tabla '%s' ya existe", table_name)
            return False
        raise


def _add_missing_indexes(table_name, description, attribute_definitions, global_secondary_indexes):
    """
    Añade los GSI que falten. DynamoDB solo admite una creación de índice por
    llamada, así que se agrega el primero pendiente y el resto quedará para el
    siguiente arranque (o despliegue) una vez el índice esté activo.
    """
    if not global_secondary_indexes:
        return

    existing = {gsi["IndexName"] for gsi in description.get("GlobalSecondaryIndexes", [])}
    pending = [gsi for gsi in global_secondary_indexes if gsi["IndexName"] not in existing]
    if not pending:
        return

    if description.get("TableStatus") != "ACTIVE":
        logger.info("Tabla '%s' no está ACTIVE, se aplaza la creación de índices", table_name)
        return

    gsi = pending[0]
    try:
        dynamodb_client.update_table(
            TableName=table_name,
            AttributeDefinitions=attribute_definitions,
            GlobalSecondaryIndexUpdates=[{"Create": {k: v for k, v in gsi.items() if k != "ProvisionedThroughput"}}],
        )
        logger.info("Índice '%s' añadido a '%s'", gsi["IndexName"], table_name)
    except botocore.exceptions.ClientError as e:
        # LimitExceeded / ResourceInUse: ya hay un índice creándose. Se reintenta
        # en el próximo arranque.
        logger.warning("No se pudo crear el índice '%s' en '%s': %s", gsi["IndexName"], table_name, e)


def _ensure_billing_mode(table_name, description, provisioned_throughput):
    expected = "PAY_PER_REQUEST" if provisioned_throughput is None else "PROVISIONED"
    current = description.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
    if current == expected:
        return

    try:
        params = {"TableName": table_name, "BillingMode": expected}
        if provisioned_throughput:
            params["ProvisionedThroughput"] = provisioned_throughput
        dynamodb_client.update_table(**params)
        logger.info("Billing mode de '%s' ajustado a %s", table_name, expected)
    except botocore.exceptions.ClientError as e:
        logger.warning("No se pudo ajustar el billing mode de '%s': %s", table_name, e)


def ensure_table(
    table_name,
    key_schema,
    attribute_definitions,
    global_secondary_indexes=None,
    provisioned_throughput=None,
):
    """
    Garantiza que la tabla exista con la forma esperada.

    - Si no existe, la crea (con sus GSI).
    - Si existe, ajusta el billing mode y añade los GSI que falten.
    - Nunca borra ni reemplaza datos.
    """
    description = _describe(table_name)

    if description is None:
        created = _create(
            table_name,
            key_schema,
            attribute_definitions,
            global_secondary_indexes,
            provisioned_throughput,
        )
        if created:
            return
        description = _describe(table_name)
        if description is None:
            return

    _ensure_billing_mode(table_name, description, provisioned_throughput)
    _add_missing_indexes(table_name, description, attribute_definitions, global_secondary_indexes)


# Alias retrocompatible con el nombre anterior de la función.
create_table = ensure_table

__all__ = ["ensure_table", "create_table"]
