#!/usr/bin/env python
"""
Prepara la cuenta de AWS para el primer despliegue.

Comprueba la identidad y el entorno, avisa de recursos que ya existan y carga
los secretos en SSM Parameter Store.

Usa boto3, que ya es dependencia del proyecto: no hace falta el AWS CLI.

    python scripts/setup_aws.py --check          # solo diagnostica
    python scripts/setup_aws.py --ses-email no-reply@midominio.com

Los secretos se piden por teclado y no se escriben en ningún archivo, así que
no acaban en el historial de la terminal ni en un commit.
"""

import argparse
import base64
import getpass
import os
import secrets
import sys

import boto3
import botocore

TABLAS_LOGICAS = ["Users", "Categories", "BankFunds", "UserBankFunds", "UserBankFundsAudit"]

VERDE, AMARILLO, ROJO, AZUL, FIN = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    VERDE = AMARILLO = ROJO = AZUL = FIN = ""


def titulo(texto):
    print(f"\n{AZUL}{texto}{FIN}")


def ok(texto):
    print(f"  {VERDE}[ok]{FIN}   {texto}")


def aviso(texto):
    print(f"  {AMARILLO}[!]{FIN}    {texto}")


def fallo(texto):
    print(f"  {ROJO}[ERR]{FIN}  {texto}")


def codigo_error(error):
    return error.response.get("Error", {}).get("Code", "Error")


def comprobar_identidad(session):
    titulo("1. Identidad")
    try:
        ident = session.client("sts").get_caller_identity()
    except botocore.exceptions.ClientError as e:
        fallo(f"las credenciales no autentican: {codigo_error(e)}")
        return None
    except botocore.exceptions.ProfileNotFound as e:
        fallo(str(e))
        return None

    ok(f"cuenta {ident['Account']}")
    ok(ident["Arn"])
    return ident


def revisar_recursos(session, service, stage):
    titulo("2. Recursos que ya existen")

    prefijo = f"{service}-{stage}-"
    try:
        tablas = session.client("dynamodb").list_tables()["TableNames"]
    except botocore.exceptions.ClientError as e:
        aviso(f"no se pudieron listar las tablas: {codigo_error(e)}")
        tablas = []

    antiguas = [t for t in tablas if t in TABLAS_LOGICAS]
    nuevas = [t for t in tablas if t.startswith(prefijo)]

    if antiguas:
        aviso(f"tablas con nombres antiguos: {', '.join(antiguas)}")
        print("         El despliegue NO las toca. Las nuevas llevan prefijo de stage,")
        print("         así que sus datos quedan aparte. Ver DEPLOY.md.")
    if nuevas:
        ok(f"ya hay {len(nuevas)} tablas de este stage: el despliegue las actualizará")
    if not antiguas and not nuevas:
        ok("ninguna tabla previa")

    try:
        pools = session.client("cognito-idp").list_user_pools(MaxResults=60)["UserPools"]
        esperado = f"{service}-{stage}-user-pool"
        if any(p["Name"] == esperado for p in pools):
            ok(f"el user pool '{esperado}' ya existe")
        elif pools:
            aviso(f"hay {len(pools)} user pool(s) ajenos al stack; se creará uno nuevo")
            for p in pools:
                print(f"           - {p['Name']} ({p['Id']})")
    except botocore.exceptions.ClientError as e:
        aviso(f"no se pudo consultar Cognito: {codigo_error(e)}")

    try:
        cf = session.client("cloudformation")
        stacks = [
            s["StackName"]
            for s in cf.list_stacks()["StackSummaries"]
            if s["StackStatus"] != "DELETE_COMPLETE"
        ]
        destino = f"{service}-{stage}"
        if destino in stacks:
            aviso(f"el stack '{destino}' ya existe: se actualizará en sitio")
        else:
            ok(f"el stack '{destino}' se creará desde cero")
    except botocore.exceptions.ClientError as e:
        aviso(f"no se pudieron listar los stacks: {codigo_error(e)}")


def cargar_secretos(session, service, stage, ses_email, smtp_host, solo_comprobar):
    base = f"/{service}/{stage}"
    titulo(f"3. Secretos en {base}")

    ssm = session.client("ssm")
    try:
        existentes = {
            p["Name"] for p in ssm.get_parameters_by_path(Path=base, Recursive=True)["Parameters"]
        }
        ok(f"{len(existentes)} parámetro(s) ya cargados" if existentes else "ninguno cargado aún")
    except botocore.exceptions.ClientError as e:
        aviso(f"no se pudo leer la ruta: {codigo_error(e)}")
        existentes = set()

    if solo_comprobar:
        aviso("modo --check: no se escribe nada")
        return

    def guardar(nombre, valor, tipo):
        if not valor:
            aviso(f"{nombre} omitido (sin valor)")
            return
        try:
            ssm.put_parameter(Name=f"{base}/{nombre}", Value=valor, Type=tipo, Overwrite=True)
            ok(f"{nombre} guardado")
        except botocore.exceptions.ClientError as e:
            fallo(f"{nombre}: {codigo_error(e)}")

    print("  (deja en blanco lo que quieras omitir)")

    # Una clave aleatoria es mejor que una inventada a mano.
    guardar(
        "JWT_SECRET_KEY",
        base64.b64encode(secrets.token_bytes(48)).decode(),
        "SecureString",
    )

    if not ses_email:
        ses_email = input("  Email remitente verificado en SES: ").strip()
    guardar("SES_VERIFIED_EMAIL", ses_email, "String")

    region = session.region_name or "us-east-2"
    guardar("AWS_SMTP_HOST", smtp_host or f"email-smtp.{region}.amazonaws.com", "String")
    guardar("AWS_SMTP_USER", getpass.getpass("  Usuario SMTP de SES: ").strip(), "SecureString")
    guardar("AWS_SMTP_PASS", getpass.getpass("  Contraseña SMTP de SES: ").strip(), "SecureString")


def revisar_permisos(session, service):
    """
    Prueba las operaciones concretas que hace `serverless deploy`.

    Es mas rapido y barato que lanzar el despliegue para descubrir que falta un
    permiso, y el mensaje dice exactamente cual.
    """
    titulo("4. Permisos que necesita el despliegue")

    def probar(descripcion, fn, denegados=("AccessDenied", "AccessDeniedException")):
        try:
            fn()
        except botocore.exceptions.ClientError as e:
            code = codigo_error(e)
            if code in denegados:
                fallo(f"{descripcion}: DENEGADO")
                return False
            # Cualquier otro error significa que el permiso si esta.
        except Exception:
            pass
        ok(descripcion)
        return True

    ssm = session.client("ssm")
    cf = session.client("cloudformation")
    s3 = session.client("s3")

    faltan = 0
    faltan += not probar(
        "ssm:GetParameter en /serverless-framework/* (bucket de artefactos)",
        lambda: ssm.get_parameter(Name="/serverless-framework/deployment/s3-bucket"),
    )
    faltan += not probar(
        f"ssm:GetParameter en /{service}/* (secretos)",
        lambda: ssm.get_parameter(Name=f"/{service}/_probe"),
    )
    faltan += not probar(
        "cloudformation:DescribeStacks",
        lambda: cf.describe_stacks(StackName=f"{service}-_probe"),
    )
    faltan += not probar("s3:ListAllMyBuckets", lambda: s3.list_buckets())
    faltan += not probar(
        "lambda:ListFunctions", lambda: session.client("lambda").list_functions(MaxItems=1)
    )
    faltan += not probar(
        "cognito-idp:ListUserPools",
        lambda: session.client("cognito-idp").list_user_pools(MaxResults=1),
    )

    if faltan:
        print(f"\n  Faltan {faltan} permiso(s). Actualiza la politica del usuario con")
        print("  infra/deploy-user-policy-inline.json y vuelve a ejecutar esto.")
    return faltan == 0


def imprimir_politica(session, nombre):
    """
    Vuelca una politica de infra/ con el ID de cuenta ya sustituido.

    Los archivos se versionan con <AWS_ACCOUNT_ID> como marcador para no
    publicar el numero de cuenta en un repositorio publico.
    """
    import pathlib

    ruta = pathlib.Path(__file__).resolve().parent.parent / "infra" / nombre
    if not ruta.exists():
        disponibles = sorted(p.name for p in ruta.parent.glob("deploy-user-policy*.json"))
        fallo(f"no existe {ruta.name}. Disponibles: {', '.join(disponibles)}")
        return 1

    try:
        cuenta = session.client("sts").get_caller_identity()["Account"]
    except botocore.exceptions.ClientError as e:
        fallo(f"no se pudo obtener el ID de cuenta: {codigo_error(e)}")
        return 1

    print(ruta.read_text(encoding="utf-8").replace("<AWS_ACCOUNT_ID>", cuenta))
    return 0


def revisar_entorno():
    titulo("5. Entorno local")

    import shutil

    for herramienta in ("node", "npm", "docker"):
        ruta = shutil.which(herramienta)
        if ruta:
            ok(f"{herramienta} disponible")
        else:
            fallo(f"{herramienta} no está en el PATH")

    # `dockerizePip: true` compila las dependencias con extensiones nativas
    # contra Linux; sin el demonio en marcha el empaquetado falla.
    try:
        import subprocess

        subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20, check=True
        )
        ok("el demonio de Docker responde")
    except Exception:
        fallo("Docker no responde: arranca Docker Desktop antes de desplegar")
        print("         serverless.yml usa dockerizePip para compilar cryptography")
        print("         y pydantic-core contra Linux.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE", "btg-pactual"))
    parser.add_argument("--region", default=os.getenv("AWS_DEPLOY_REGION", "us-east-2"))
    parser.add_argument("--service", default="fastapi-app")
    parser.add_argument("--stage", default="prod", choices=["dev", "prod"])
    parser.add_argument("--ses-email", default="")
    parser.add_argument("--smtp-host", default="")
    parser.add_argument("--check", action="store_true", help="solo diagnostica, no escribe")
    parser.add_argument(
        "--print-policy",
        nargs="?",
        const="deploy-user-policy-inline.json",
        metavar="ARCHIVO",
        help="imprime una politica de infra/ con tu ID de cuenta ya sustituido, "
             "lista para pegar en la consola de IAM",
    )
    args = parser.parse_args()

    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
    except botocore.exceptions.ProfileNotFound:
        fallo(f"el perfil '{args.profile}' no existe en ~/.aws/credentials")
        return 1

    if args.print_policy:
        return imprimir_politica(session, args.print_policy)

    if comprobar_identidad(session) is None:
        return 1

    revisar_recursos(session, args.service, args.stage)
    cargar_secretos(session, args.service, args.stage, args.ses_email, args.smtp_host, args.check)
    revisar_permisos(session, args.service)
    revisar_entorno()

    titulo("Siguiente paso")
    print(f"  Región {args.region}, stage {args.stage}")
    print("  npx serverless login     (obligatorio con Serverless v4)")
    print("  npm run deploy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
