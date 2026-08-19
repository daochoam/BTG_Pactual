# Despliegue

Toda la infraestructura está declarada como código. No hay que crear nada a
mano en la consola de AWS.

```bash
npm install
npx serverless deploy --stage prod
```

Ese único comando crea (o actualiza) el stack de CloudFormation con:

| Recurso | Definido en | Comportamiento |
|---|---|---|
| Tablas DynamoDB + sus GSI | Los modelos (`app/schemas/*.py`) | Se crean si no existen, se ajustan si ya existen |
| Cognito User Pool | [resources/cognito.yml](resources/cognito.yml) | Incluye el atributo `custom:role` y verificación por email |
| Cognito App Client (con secreto) | [resources/cognito.yml](resources/cognito.yml) | `USER_PASSWORD_AUTH`, `REFRESH_TOKEN_AUTH`, revocación de tokens |
| Dominio de Cognito | [resources/cognito.yml](resources/cognito.yml) | `<service>-<stage>-<accountId>.auth.<region>.amazoncognito.com` |
| Bucket S3 de archivos | [resources/s3.yml](resources/s3.yml) | Privado, cifrado, versionado, con reglas de ciclo de vida |
| Bucket S3 del frontend + CloudFront | [resources/s3.yml](resources/s3.yml) | Bucket privado servido solo por CloudFront (OAC) |
| Rol IAM de la Lambda | [serverless.yml](serverless.yml) | Permisos acotados a esas tablas, ese user pool y ese bucket |
| API Gateway HTTP API + Lambda | [serverless.yml](serverless.yml) | |
| Bucket de artefactos | Serverless | Se crea solo; ya no hay que provisionarlo |

## Requisitos previos

| | Estado tipico | Como se resuelve |
|---|---|---|
| Node 20+ y npm | Instalado, pero a veces fuera del PATH de la terminal abierta | Abrir una terminal nueva |
| Python 3.12 | | `.python-version` |
| AWS CLI v2 | **No viene con Windows** | `winget install Amazon.AWSCLI` |
| Docker | Solo para desarrollo local | Docker Desktop en marcha |
| Cuenta de Serverless Framework | **Obligatoria desde la v4** | Ver abajo |

### Serverless Framework v4 exige iniciar sesion

Desde la version 4, el comando falla sin autenticacion:

```
Error: You must sign in or use a license key with Serverless Framework V.4
```

Es gratuito para organizaciones por debajo de cierto volumen de facturacion,
pero hay que crear una cuenta:

```bash
npx serverless login                    # en tu equipo, una vez
```

Para el CI se genera un access key en el panel de Serverless y se guarda como
secreto `SERVERLESS_ACCESS_KEY` (los tres pipelines ya lo pasan).

Si no quieres depender de ese servicio, la alternativa es quedarse en la v3, que
no pide login: hay que bajar `serverless-offline` a `^13` (la 14 exige v4) y
poner `serverless: ^3` en las devDependencies. El resto de la configuracion
funciona igual, salvo que la v3 necesita `useDotenv: true` para cargar el `.env`.

## Credenciales para desplegar a mano

El IAM **si** sale de aqui: roles, politicas y permisos estan en
[infra/bootstrap.yml](infra/bootstrap.yml). Lo que no puede estar en el
repositorio es el material de la credencial (la clave secreta o la sesion de
SSO); eso vive en `~/.aws`, protegido por el sistema operativo.

El proyecto trae un archivo oculto que dice **que identidad usar**, no cual es:

```bash
cp .aws.env.example .aws.env      # esta en .gitignore
```

Y despues, para comprobar que todo esta en su sitio y cargar los secretos:

```bash
python scripts/setup_aws.py --check                          # solo diagnostica
python scripts/setup_aws.py --ses-email no-reply@midominio.com
```

Usa boto3, asi que **no hace falta el AWS CLI**. Verifica la identidad, avisa de
tablas o user pools que ya existan, carga los cinco parametros en SSM (pidiendo
los secretos por teclado, nunca desde un archivo) y comprueba que Docker este en
marcha, que `dockerizePip` lo necesita.

```ini
AWS_PROFILE=btg-pactual
AWS_DEPLOY_REGION=us-east-2
```

[scripts/with-aws-env.js](scripts/with-aws-env.js) lo lee y lo exporta antes de
lanzar cada comando, asi que todos los scripts de npm ya despliegan con la
identidad correcta sin depender de lo que tengas en el shell:

```bash
npm run whoami      # comprueba con que identidad estas
npm run deploy      # serverless deploy --stage prod con ese perfil
npm run bootstrap
```

Si el archivo no existe no pasa nada: se usa la cadena de credenciales normal de
AWS. Es lo que ocurre en el CI, donde las credenciales llegan del rol asumido.
Y una variable definida en el shell gana sobre el archivo, para desplegar
puntualmente contra otra cuenta sin editar nada.

### Que poner en ~/.aws/config

**Opcion recomendada: AWS SSO (IAM Identity Center).** Credenciales temporales,
nada que rotar, nada que se pueda filtrar:

```ini
[profile btg-pactual]
sso_start_url = https://mi-org.awsapps.com/start
sso_region = us-east-2
sso_account_id = 123456789012
sso_role_name = DeveloperAccess
region = us-east-2
```

```bash
aws sso login --profile btg-pactual
```

**Opcion con rol asumido.** El stack de bootstrap puede crear un rol con los
mismos permisos que el CI, para que una persona no lleve encima una identidad
con permiso permanente sobre produccion:

```bash
npm run bootstrap -- --parameter-overrides   DeveloperPrincipals=arn:aws:iam::123456789012:user/daniel
```

La salida `DeveloperDeployRoleArn` se usa asi:

```ini
[profile btg-pactual]
role_arn = arn:aws:iam::123456789012:role/fastapi-app-developer-deploy
source_profile = mi-usuario-base
region = us-east-2
```

Las claves de `mi-usuario-base` pueden tener permisos minimos: lo unico que
necesitan es `sts:AssumeRole` sobre ese rol. La sesion caduca en una hora.

### Lo que no conviene hacer

Meter `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` en un archivo del proyecto,
aunque este en `.gitignore`. Antes o despues alguien lo commitea, lo copia a un
Slack o lo deja en un backup. Por eso `.aws.env` guarda solo el nombre del
perfil, y `.gitignore` cubre `.aws.env` y `.aws.local`.

## Las tablas salen de los modelos

No hay ninguna lista de tablas escrita a mano. Una clase que herede de
`DynamoModel` y declare `table_name` queda registrada sola, y de ese registro
salen tanto las tablas de CloudFormation como las que se crean en local:

```python
# app/schemas/invoices.py
from app.models import DynamoModel, GSI

class InvoiceSchema(DynamoModel):
    table_name = "Invoices"          # nombre lógico; el prefijo lo pone el stage
    partition_key = "id"             # o ("id", STRING)
    sort_key = None                  # o ("created_at", STRING)
    indexes = (GSI("user_id"), GSI("status", "created_at"))
```

Con eso, y sin tocar nada más:

```bash
npm run resources     # regenera resources/dynamodb.yml desde los modelos
npm run deploy        # lo regenera y despliega (script `predeploy`)
```

Piezas:

| Archivo | Rol |
|---|---|
| [app/models/base.py](app/models/base.py) | `DynamoModel` y `GSI`: la declaración |
| [app/models/registry.py](app/models/registry.py) | Registro automático + descubrimiento de `app.schemas` y `app.models` |
| [scripts/generate_dynamodb_resources.py](scripts/generate_dynamodb_resources.py) | Vuelca el registro a CloudFormation |
| [resources/dynamodb.yml](resources/dynamodb.yml) | **Generado**, no editar a mano |
| [app/dynamo_db.py](app/dynamo_db.py) | Recorre el mismo registro para crear/ajustar en runtime |

`resources/dynamodb.yml` se commitea. Para no olvidarse de regenerarlo hay un
test que lo verifica ([tests/models/dynamo_models_test.py](tests/models/dynamo_models_test.py))
y el comando `npm run resources:check`, útil en CI.

## Lo que ya no hay que poner en el `.env`

`AWS_COGNITO_USER_POOL_ID`, `AWS_COGNITO_CLIENT_ID`, `AWS_COGNITO_CLIENT_SECRET`,
`AWS_COGNITO_DOMAIN` y los nombres de tabla se resuelven en el propio
CloudFormation y se inyectan como variables de entorno de la Lambda
(`provider.environment` en [serverless.yml](serverless.yml)).

Los secretos de negocio (`JWT_SECRET_KEY`, `SES_VERIFIED_EMAIL`,
`AWS_SMTP_*`) se leen de **SSM Parameter Store**, con la variable de entorno
como alternativa para desarrollo local:

```yaml
JWT_SECRET_KEY: ${env:JWT_SECRET_KEY, ssm:${self:custom.secretsPath}/JWT_SECRET_KEY}
```

Se cargan una vez por stage:

```bash
aws ssm put-parameter --type SecureString --name /fastapi-app/prod/JWT_SECRET_KEY --value '...'
aws ssm put-parameter --type String       --name /fastapi-app/prod/SES_VERIFIED_EMAIL --value 'no-reply@...'
aws ssm put-parameter --type String       --name /fastapi-app/prod/AWS_SMTP_HOST --value 'email-smtp...'
aws ssm put-parameter --type SecureString --name /fastapi-app/prod/AWS_SMTP_USER --value '...'
aws ssm put-parameter --type SecureString --name /fastapi-app/prod/AWS_SMTP_PASS --value '...'
```

Por eso ningún pipeline necesita conocer los secretos: el rol de despliegue
tiene permiso de lectura sobre `/<servicio>/*` y Serverless los resuelve al
desplegar. En local siguen viniendo del `.env`, que gana sobre SSM.

> Ojo: `${ssm:...}` resuelve **en tiempo de despliegue** y deja el valor en la
> variable de entorno de la Lambda, visible para quien pueda ver la función. Si
> necesitas que el secreto no quede ahí, hay que leerlo desde el código en
> runtime (como ya se hace con el client secret de Cognito en
> [app/config.py](app/config.py)).

## Nombres de tabla

Por defecto llevan prefijo de servicio y stage:

```
fastapi-app-prod-Users
fastapi-app-prod-Categories
fastapi-app-prod-BankFunds
fastapi-app-prod-UserBankFunds
fastapi-app-prod-UserBankFundsAudit
```

Así conviven varios stages (`--stage dev`, `--stage prod`) en la misma cuenta
sin pisarse. El modelo solo conoce su nombre lógico (`Users`); el nombre real lo
resuelve `DynamoModel.physical_name()` leyendo la variable de entorno que
inyecta CloudFormation, con `TABLE_PREFIX` como respaldo.

### Si ya tienes tablas en producción con los nombres antiguos

CloudFormation falla si intenta crear una tabla cuyo nombre ya existe. Dos
caminos:

**A. Adoptar las tablas existentes en el stack** (conserva los datos y los
nombres `Users`, `Categories`, ...):

1. En [serverless.yml](serverless.yml) pon `custom.tablePrefix: ''`.
2. Genera la plantilla sin desplegar: `npx serverless package --stage prod`.
3. Importa los recursos existentes al stack con la consola de CloudFormation
   (*Stack actions → Import resources into stack*) usando
   `.serverless/cloudformation-template-update-stack.json`, indicando el
   `TableName` de cada tabla.
4. A partir de ahí, `npx serverless deploy --stage prod` ya las gestiona.

**B. Empezar con los nombres nuevos y migrar los datos** (más simple si el
volumen es bajo): despliega tal cual y copia los items con un script de
`scan` + `batch_write_item`, o con una exportación S3 + import de DynamoDB.

## Red de seguridad en runtime

`AUTO_CREATE_TABLES=true` hace que la app, en el arranque en frío, recorra el
registro de modelos y cree/ajuste lo que falte
([app/dynamo_db.py](app/dynamo_db.py)). Es
idempotente y tolerante a fallos. En producción normalmente no hace nada porque
CloudFormation ya dejó todo listo; ponlo en `false` si prefieres ahorrar esa
llamada a `DescribeTable` por arranque en frío.

## Despliegue continuo

Hay tres pipelines listos; elige uno. Todos hacen lo mismo: tests, regenerar la
plantilla desde los modelos, `serverless deploy` y publicar el frontend en S3 +
CloudFront si existe una carpeta `frontend/`.

### Paso 0 (comun): stack de arranque

El CI necesita un rol de AWS que asumir, y ese rol no puede crearse a si mismo.
Es la unica ejecucion manual, y tambien sale del repositorio:

```bash
aws cloudformation deploy   --template-file infra/bootstrap.yml   --stack-name fastapi-app-cicd-bootstrap   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides GitHubRepo=mi-org/mi-repo
```

Crea el proveedor OIDC, el rol de despliegue y la politica de permisos
(reutilizada por los tres pipelines). Parametros útiles:

| Parametro | Para que |
|---|---|
| `GitHubRepo` | `owner/repo`. Vacio = no crea el rol de GitHub |
| `GitHubRefFilter` | Que ramas/entornos pueden desplegar (por defecto solo `main`) |
| `CreateGitHubOidcProvider` | `false` si la cuenta ya tiene el proveedor OIDC |
| `GitLabProject` | `grupo/proyecto`. Vacio = no crea el rol de GitLab |

Las politicas para desplegar a mano estan en [infra/](infra/), con su indice en
[infra/README.md](infra/README.md). Se versionan con `<AWS_ACCOUNT_ID>` como
marcador; para obtener una lista para pegar:

```bash
python scripts/setup_aws.py --print-policy
```

La salida `GitHubDeployRoleArn` / `GitLabDeployRoleArn` es lo que se pega en el
CI. **No hay access keys en ningun sitio**: el pipeline pide un token OIDC y
asume el rol.

## La API

`serverless.yml` expone una sola Lambda con FastAPI detrás de Mangum:

- **Rutas**: dos eventos `httpApi` (`/{proxy+}` y `/`) en vez del comodín `'*'`.
  El comodín crea la ruta `$default`, que no cubre la raíz de forma explícita y
  deja el enrutado sin declarar. Declarar cada endpoint aquí no aporta:
  duplicaría el router de FastAPI y habría que mantener los dos sincronizados.
- **CORS**: resuelto en API Gateway (`provider.httpApi.cors`), así el preflight
  `OPTIONS` no invoca la Lambda. La app **no** lleva `CORSMiddleware` a
  propósito: se duplicarían las cabeceras y el navegador rechazaría la
  respuesta. `exposedResponseHeaders` incluye `Authorization` y
  `X-Refresh-Token`, que es lo que devuelve el login; sin eso el frontend no
  puede leerlos. El origen permitido sale de `CORS_ALLOWED_ORIGIN`.
- **Throttling**: `resources/api.yml` limita el stage a 100 rps (200 de ráfaga),
  ajustable con `API_RATE_LIMIT` / `API_BURST_LIMIT`.
- **Logs de acceso**: `provider.logs.httpApi` en formato JSON, con latencia y
  errores de integración, listo para consultar con CloudWatch Insights.

### Opcion A — GitHub Actions

[.github/workflows/deploy.yml](.github/workflows/deploy.yml). Push a `main` va a
`prod`, push a `develop` va a `dev`, los PR solo corren tests. Secretos del
repositorio:

```
AWS_DEPLOY_ROLE_ARN     <- salida del stack de bootstrap
SERVERLESS_ACCESS_KEY   <- solo si usas Serverless Framework v4 con licencia
```

Y nada mas: los secretos de la aplicacion viven en Parameter Store.

### Opcion B — AWS CodePipeline + CodeBuild

Todo dentro de AWS: [infra/codepipeline.yml](infra/codepipeline.yml) +
[buildspec.yml](buildspec.yml).

```bash
aws cloudformation deploy   --template-file infra/codepipeline.yml   --stack-name fastapi-app-pipeline   --capabilities CAPABILITY_NAMED_IAM   --parameter-overrides       ConnectionArn=arn:aws:codeconnections:us-east-2:123456789012:connection/xxxx       RepositoryId=mi-org/mi-repo       NotificationEmail=equipo@empresa.com
```

Con `NotificationEmail` se crea un topic SNS y una regla de EventBridge que
avisa cuando el pipeline falla.

> La conexion a GitHub (`ConnectionArn`) es lo unico que exige un handshake
> OAuth en la consola (*Developer Tools > Settings > Connections*), porque
> autoriza a AWS contra tu cuenta de GitHub. Se crea una vez y vale para todos
> los pipelines. Es una limitacion de CodeConnections, no de esta plantilla.

### Opcion C — GitLab CI

[.gitlab-ci.yml](.gitlab-ci.yml), tambien por OIDC. Unica variable del
proyecto: `AWS_DEPLOY_ROLE_ARN`.

### El frontend

Los tres pipelines buscan `frontend/package.json`; si no existe, saltan ese paso
sin fallar. Si existe, hacen `npm ci && npm run build`, sincronizan
`frontend/dist` al bucket estatico e invalidan CloudFront. Los assets con hash se
cachean un año y el `index.html` no se cachea nunca.

La URL del sitio sale en `serverless info` como `StaticSiteUrl`.

## Lo que NO se puede automatizar

Dos cosas, y ambas por como funciona AWS, no por esta configuracion:

- **La conexion de CodeConnections** (solo si eliges CodePipeline): ver arriba.
- **SES / SMTP**: verificar un dominio o un remitente exige confirmar por DNS o
  por email, y salir del sandbox de SES es una solicitud manual a AWS. Por eso
  `SES_VERIFIED_EMAIL` y `AWS_SMTP_*` siguen viniendo de los secretos del CI.

El bucket de despliegue ya **no** es un requisito previo: se quito
`provider.deploymentBucket` de [serverless.yml](serverless.yml) y Serverless
gestiona el suyo. El bucket `btg-pactual-deploy` puede borrarse cuando el primer
despliegue con esta configuracion termine bien.
