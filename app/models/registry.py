"""
Registro central de modelos DynamoDB.

Cualquier clase que herede de `DynamoModel` y declare `table_name` queda
registrada aquí automáticamente. A partir de este registro se derivan:

  - la creación/ajuste de tablas en runtime (app/dynamo_db.py)
  - los recursos CloudFormation del despliegue
    (scripts/generate_dynamodb_resources.py)

Es decir: se define un modelo y la tabla aparece sola en los dos sitios.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

# Paquetes que se recorren buscando modelos.
MODEL_PACKAGES = ("app.schemas", "app.models")

_REGISTRY = {}
_discovered = False


def register(model):
    """Añade un modelo al registro. Lo llama DynamoModel.__init_subclass__."""
    logical_name = model.table_name
    existing = _REGISTRY.get(logical_name)

    if existing is not None and existing is not model:
        raise RuntimeError(
            f"Dos modelos declaran table_name='{logical_name}': "
            f"{existing.__module__}.{existing.__name__} y "
            f"{model.__module__}.{model.__name__}"
        )

    _REGISTRY[logical_name] = model
    return model


def discover(packages=MODEL_PACKAGES, force=False):
    """
    Importa los módulos de los paquetes de modelos para que se registren.

    Sin esto el registro solo contiene los modelos que alguien ya haya
    importado; con esto están todos, sin listarlos a mano en ningún sitio.
    """
    global _discovered
    if _discovered and not force:
        return _REGISTRY

    for package_name in packages:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            logger.debug("Paquete de modelos '%s' no encontrado", package_name)
            continue

        for module in pkgutil.iter_modules(package.__path__):
            if module.name.startswith("_"):
                continue
            importlib.import_module(f"{package_name}.{module.name}")

    _discovered = True
    return _REGISTRY


def iter_models(auto_discover=True):
    """Devuelve los modelos registrados, ordenados por nombre de tabla."""
    if auto_discover:
        discover()
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def get_model(logical_name, auto_discover=True):
    if auto_discover:
        discover()
    return _REGISTRY.get(logical_name)


__all__ = ["register", "discover", "iter_models", "get_model", "MODEL_PACKAGES"]
