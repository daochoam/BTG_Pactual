"""
Base declarativa para las entidades persistidas en DynamoDB.

Un modelo solo declara su forma:

    class UserSchema(DynamoModel):
        table_name = "Users"
        partition_key = "id"
        indexes = (GSI("email"), GSI("nit"))

y con eso queda:

  - registrado (app/models/registry.py)
  - creado/ajustado al arrancar en local (app/dynamo_db.py)
  - incluido en la plantilla CloudFormation del despliegue
    (scripts/generate_dynamodb_resources.py)

El nombre físico de la tabla lo decide la infraestructura, nunca el modelo:
`table_name` es el nombre lógico y `physical_name()` le aplica el prefijo de
stage o la variable de entorno que inyecta serverless.yml.
"""

from app.models.registry import register

# Tipos de atributo válidos como clave en DynamoDB
STRING = "S"
NUMBER = "N"
BINARY = "B"


def _normalize_key(key):
    """Acepta "id" o ("amount", NUMBER) y devuelve siempre (nombre, tipo)."""
    if key is None:
        return None
    if isinstance(key, str):
        return (key, STRING)
    name, key_type = key
    return (name, key_type)


class GSI:
    """
    Índice secundario global.

    El nombre se deduce de las claves si no se indica: `GSI("email")` produce
    el índice "email-index".
    """

    def __init__(self, hash_key, range_key=None, name=None, projection="ALL", non_key_attributes=None):
        self.hash_key = _normalize_key(hash_key)
        self.range_key = _normalize_key(range_key)
        self.projection = projection
        self.non_key_attributes = tuple(non_key_attributes or ())

        if name:
            self.name = name
        elif self.range_key:
            self.name = f"{self.hash_key[0]}-{self.range_key[0]}-index"
        else:
            self.name = f"{self.hash_key[0]}-index"

    def keys(self):
        keys = [self.hash_key]
        if self.range_key:
            keys.append(self.range_key)
        return keys

    def key_schema(self):
        schema = [{"AttributeName": self.hash_key[0], "KeyType": "HASH"}]
        if self.range_key:
            schema.append({"AttributeName": self.range_key[0], "KeyType": "RANGE"})
        return schema

    def projection_spec(self):
        spec = {"ProjectionType": self.projection}
        if self.projection == "INCLUDE":
            spec["NonKeyAttributes"] = list(self.non_key_attributes)
        return spec

    def to_dict(self):
        return {
            "IndexName": self.name,
            "KeySchema": self.key_schema(),
            "Projection": self.projection_spec(),
        }


class _TableDescriptor:
    """Expone `Modelo.table` como el recurso boto3, resuelto una sola vez."""

    def __init__(self):
        self._cache = {}

    def __get__(self, instance, owner):
        if owner not in self._cache:
            # Import diferido: describir un modelo no debe exigir boto3 ni
            # credenciales (el generador de CloudFormation corre sin AWS).
            from app.config import dynamodb

            self._cache[owner] = dynamodb.Table(owner.physical_name())
        return self._cache[owner]


class DynamoModel:
    """Clase base declarativa. No aporta comportamiento de instancia."""

    # Nombre lógico de la tabla. Declararlo es lo que registra el modelo.
    table_name = None
    # "id" o ("id", STRING)
    partition_key = "id"
    # Clave de ordenación opcional
    sort_key = None
    # Tupla de GSI(...)
    indexes = ()

    table = _TableDescriptor()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Solo se registra la clase que declara su propia tabla: así una
        # subclase que hereda comportamiento (p. ej. la de auditoría) no
        # duplica la tabla del padre por accidente.
        if "table_name" in cls.__dict__ and cls.table_name:
            register(cls)

    # -- Nombres -----------------------------------------------------------

    @classmethod
    def physical_name(cls):
        from app.config import table_name

        return table_name(cls.table_name)

    @classmethod
    def resource_name(cls):
        """Id lógico del recurso en CloudFormation (p. ej. 'UsersTable')."""
        return f"{cls.table_name}Table"

    # -- Esquema -----------------------------------------------------------

    @classmethod
    def key_schema(cls):
        schema = [{"AttributeName": _normalize_key(cls.partition_key)[0], "KeyType": "HASH"}]
        sort_key = _normalize_key(cls.sort_key)
        if sort_key:
            schema.append({"AttributeName": sort_key[0], "KeyType": "RANGE"})
        return schema

    @classmethod
    def attribute_definitions(cls):
        """
        Solo los atributos que son clave (de la tabla o de algún índice).
        DynamoDB rechaza la definición de cualquier otro.
        """
        keys = [_normalize_key(cls.partition_key)]
        sort_key = _normalize_key(cls.sort_key)
        if sort_key:
            keys.append(sort_key)
        for index in cls.indexes:
            keys.extend(index.keys())

        definitions = {}
        for name, key_type in keys:
            definitions.setdefault(name, key_type)

        return [
            {"AttributeName": name, "AttributeType": key_type}
            for name, key_type in definitions.items()
        ]

    @classmethod
    def global_secondary_indexes(cls):
        return [index.to_dict() for index in cls.indexes]

    @classmethod
    def table_definition(cls):
        """Forma consumible tanto por boto3 como por el generador de CloudFormation."""
        return {
            "logical_name": cls.table_name,
            "physical_name": cls.physical_name(),
            "resource_name": cls.resource_name(),
            "key_schema": cls.key_schema(),
            "attribute_definitions": cls.attribute_definitions(),
            "global_secondary_indexes": cls.global_secondary_indexes(),
        }


__all__ = ["DynamoModel", "GSI", "STRING", "NUMBER", "BINARY"]
