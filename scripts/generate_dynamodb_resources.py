#!/usr/bin/env python
"""
Genera resources/dynamodb.yml a partir de los modelos declarados.

Los modelos (app/schemas/*.py, app/models/*.py) son la única fuente de verdad:
si añades una clase que hereda de DynamoModel con su `table_name`, al ejecutar
este script aparece su tabla en la plantilla de CloudFormation, y `serverless
deploy` la crea (o la ajusta) en AWS.

Uso:
    python scripts/generate_dynamodb_resources.py
    python scripts/generate_dynamodb_resources.py --check   # falla si está desactualizado

`npm run deploy` lo ejecuta automáticamente antes de desplegar.
"""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.models.registry import iter_models  # noqa: E402

OUTPUT = ROOT / "resources" / "dynamodb.yml"

# Expresiones que resuelve Serverless al desplegar (ver `custom` en serverless.yml)
TABLE_PREFIX_VAR = "${self:custom.tablePrefix}"
PITR_VAR = "${self:custom.pitr.${sls:stage}, self:custom.pitr.default}"
SERVICE_VAR = "${self:service}"
STAGE_VAR = "${sls:stage}"

HEADER = """# ---------------------------------------------------------------------------
# ARCHIVO GENERADO - no editar a mano.
#
# Se produce con:  python scripts/generate_dynamodb_resources.py
# a partir de los modelos que heredan de DynamoModel (app/schemas, app/models).
# Para añadir o cambiar una tabla, cambia el modelo y vuelve a generar.
#
# DeletionPolicy/UpdateReplacePolicy = Retain -> los datos nunca se borran,
# ni al eliminar el stack ni si CloudFormation reemplaza el recurso.
# ---------------------------------------------------------------------------
"""


def table_resource(model):
    definition = model.table_definition()

    properties = {
        "TableName": f"{TABLE_PREFIX_VAR}{definition['logical_name']}",
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": definition["attribute_definitions"],
        "KeySchema": definition["key_schema"],
    }

    if definition["global_secondary_indexes"]:
        properties["GlobalSecondaryIndexes"] = definition["global_secondary_indexes"]

    properties["PointInTimeRecoverySpecification"] = {"PointInTimeRecoveryEnabled": PITR_VAR}
    properties["SSESpecification"] = {"SSEEnabled": True}
    properties["Tags"] = [
        {"Key": "Service", "Value": SERVICE_VAR},
        {"Key": "Stage", "Value": STAGE_VAR},
        {"Key": "Model", "Value": f"{model.__module__}.{model.__name__}"},
    ]

    return definition["resource_name"], {
        "Type": "AWS::DynamoDB::Table",
        "DeletionPolicy": "Retain",
        "UpdateReplacePolicy": "Retain",
        "Properties": properties,
    }


def build_template():
    models = iter_models()
    if not models:
        raise SystemExit("No se encontró ningún modelo DynamoModel registrado.")

    resources = {}
    outputs = {}

    for model in models:
        resource_name, resource = table_resource(model)
        resources[resource_name] = resource
        outputs[f"{resource_name}Name"] = {"Value": {"Ref": resource_name}}

    return {"Resources": resources, "Outputs": outputs}


def render():
    body = yaml.safe_dump(
        build_template(),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return HEADER + "\n" + body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="No escribe nada; termina con error si el archivo está desactualizado.",
    )
    args = parser.parse_args()

    content = render()

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print(
                f"{OUTPUT.relative_to(ROOT)} está desactualizado. "
                "Ejecuta: python scripts/generate_dynamodb_resources.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} está al día.")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")

    print(f"Generado {OUTPUT.relative_to(ROOT)} con {len(build_template()['Resources'])} tablas:")
    for model in iter_models():
        print(f"  - {model.table_name:<22} <- {model.__module__}.{model.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
