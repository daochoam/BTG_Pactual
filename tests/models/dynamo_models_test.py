"""
Garantiza que el registro de modelos y la plantilla de CloudFormation generada
no se desincronicen: si alguien añade un modelo y no regenera
resources/dynamodb.yml, estos tests fallan.
"""

import importlib.util
from pathlib import Path

import pytest

from app.models.base import GSI, DynamoModel
from app.models.registry import iter_models

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_dynamodb_resources.py"

EXPECTED_TABLES = {
    "Users",
    "Categories",
    "BankFunds",
    "UserBankFunds",
    "UserBankFundsAudit",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_dynamodb_resources", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_todos_los_modelos_quedan_registrados():
    assert {model.table_name for model in iter_models()} == EXPECTED_TABLES


@pytest.mark.parametrize("model", iter_models(), ids=lambda m: m.table_name)
def test_attribute_definitions_cubren_todas_las_claves(model):
    declared = {item["AttributeName"] for item in model.attribute_definitions()}

    used = {item["AttributeName"] for item in model.key_schema()}
    for index in model.global_secondary_indexes():
        used.update(item["AttributeName"] for item in index["KeySchema"])

    # DynamoDB rechaza tanto una clave sin definir como una definición sobrante.
    assert declared == used


@pytest.mark.parametrize("model", iter_models(), ids=lambda m: m.table_name)
def test_los_indices_tienen_nombres_unicos(model):
    names = [index["IndexName"] for index in model.global_secondary_indexes()]
    assert len(names) == len(set(names))


def test_el_nombre_fisico_usa_el_prefijo(monkeypatch):
    monkeypatch.setenv("DYNAMO_TABLE_USERS", "")
    monkeypatch.setattr("app.config.Config.TABLE_PREFIX", "mi-servicio-prod-")

    from app.schemas.users import UserSchema

    assert UserSchema.physical_name() == "mi-servicio-prod-Users"


def test_gsi_deduce_su_nombre():
    assert GSI("email").name == "email-index"
    assert GSI("user_id", "created_at").name == "user_id-created_at-index"
    assert GSI("email", name="custom").name == "custom"


def test_una_subclase_sin_tabla_propia_no_se_registra():
    antes = {model.table_name for model in iter_models()}

    class SinTabla(DynamoModel):  # hereda table_name = None
        pass

    assert {model.table_name for model in iter_models()} == antes


def test_la_plantilla_generada_esta_al_dia():
    generator = _load_generator()
    actual = generator.OUTPUT.read_text(encoding="utf-8")

    assert actual == generator.render(), (
        "resources/dynamodb.yml está desactualizado. "
        "Ejecuta: python scripts/generate_dynamodb_resources.py"
    )
