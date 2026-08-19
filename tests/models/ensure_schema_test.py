"""
Comprueba contra un DynamoDB simulado (moto) que ensure_schema() crea de verdad
lo que declaran los modelos, y que volver a ejecutarlo no rompe nada.

Es la misma ruta de código que usa el arranque en local y el respaldo en runtime
de la Lambda cuando AUTO_CREATE_TABLES está activo.
"""

import boto3
import pytest
from moto import mock_aws

from app.models.registry import iter_models

REGION = "us-east-2"


@pytest.fixture
def dynamo(monkeypatch):
    """DynamoDB simulado, con los clientes de la app apuntando a él."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")

    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        monkeypatch.setattr("app.config.dynamodb_client", client)
        monkeypatch.setattr("app.utils.create_table.dynamodb_client", client)
        yield client


def _physical_names(prefix):
    return {f"{prefix}{model.table_name}" for model in iter_models()}


def test_ensure_schema_crea_todas_las_tablas(dynamo, monkeypatch):
    monkeypatch.setattr("app.config.Config.TABLE_PREFIX", "test-")
    for model in iter_models():
        monkeypatch.delenv(f"DYNAMO_TABLE_{model.table_name.upper()}", raising=False)

    from app.dynamo_db import ensure_schema

    ensure_schema(force=True)

    creadas = set(dynamo.list_tables()["TableNames"])
    assert _physical_names("test-") <= creadas


def test_ensure_schema_es_idempotente(dynamo, monkeypatch):
    monkeypatch.setattr("app.config.Config.TABLE_PREFIX", "test-")

    from app.dynamo_db import ensure_schema

    ensure_schema(force=True)
    antes = sorted(dynamo.list_tables()["TableNames"])

    # Segunda pasada: no debe lanzar ni duplicar nada.
    ensure_schema(force=True)
    assert sorted(dynamo.list_tables()["TableNames"]) == antes


def test_los_indices_declarados_existen_en_la_tabla(dynamo, monkeypatch):
    monkeypatch.setattr("app.config.Config.TABLE_PREFIX", "test-")

    from app.dynamo_db import ensure_schema

    ensure_schema(force=True)

    for model in iter_models():
        esperados = {index["IndexName"] for index in model.global_secondary_indexes()}
        if not esperados:
            continue

        descripcion = dynamo.describe_table(TableName=f"test-{model.table_name}")["Table"]
        reales = {i["IndexName"] for i in descripcion.get("GlobalSecondaryIndexes", [])}
        assert esperados <= reales, f"faltan índices en {model.table_name}"


def test_ensure_schema_respeta_auto_create_tables(dynamo, monkeypatch):
    monkeypatch.setattr("app.config.Config.AUTO_CREATE_TABLES", False)

    from app.dynamo_db import ensure_schema

    ensure_schema()  # sin force: no debe crear nada

    assert dynamo.list_tables()["TableNames"] == []
