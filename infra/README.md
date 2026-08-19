# infra/

Infraestructura que vive **fuera** del stack de la aplicación: los permisos y el
pipeline. Lo que sí gestiona `serverless deploy` está en [../resources/](../resources/).

## Plantillas de CloudFormation

| Archivo | Qué crea | Cuándo se aplica |
|---|---|---|
| [bootstrap.yml](bootstrap.yml) | Proveedores OIDC, rol de despliegue del CI, política de permisos compartida y (opcional) un rol para despliegue manual | Una vez, antes de configurar el CI |
| [codepipeline.yml](codepipeline.yml) | CodePipeline + CodeBuild + bucket de artefactos + avisos por SNS | Solo si eliges CodePipeline en vez de GitHub Actions o GitLab CI |

```bash
npm run bootstrap -- --parameter-overrides GitHubRepo=mi-org/mi-repo
npm run pipeline  -- --parameter-overrides ConnectionArn=... RepositoryId=...
```

## Políticas para el usuario que despliega a mano

Estas **no** se despliegan: se pegan en la consola de IAM sobre el usuario o rol
que vaya a ejecutar `serverless deploy` desde un equipo. El rol del CI no las
necesita, porque `bootstrap.yml` ya le adjunta la suya.

| Archivo | Tamaño | Para qué |
|---|---|---|
| [deploy-user-policy.json](deploy-user-policy.json) | ~3,2 KB | La completa, acotada por recurso y con un statement por servicio. Solo cabe como **política administrada** (límite 6144) |
| [deploy-user-policy-inline.json](deploy-user-policy-inline.json) | ~1,2 KB | Lo mismo, comprimido agrupando recursos. Cabe como **política en línea** (límite 2048) |
| [deploy-user-policy-global.json](deploy-user-policy-global.json) | ~0,4 KB | Sin acotar: los servicios con `*` sobre `*`. Equivale a `AdministratorAccess`, así que normalmente conviene más adjuntar esa directamente |
| [deploy-user-policy-serverless-bucket.json](deploy-user-policy-serverless-bucket.json) | ~0,3 KB | Solo el permiso sobre `/serverless-framework/*`. Útil para **añadirla** a una política anterior sin reemplazarla |

Los archivos llevan `<AWS_ACCOUNT_ID>` como marcador para no publicar el número
de cuenta. Para obtener una versión lista para pegar:

```bash
python scripts/setup_aws.py --print-policy
python scripts/setup_aws.py --print-policy deploy-user-policy.json
```

Sustituye el marcador por el ID real de la cuenta con la que estés autenticado.

## Comprobar qué falta

```bash
python scripts/setup_aws.py --check
```

Prueba una a una las operaciones que hace `serverless deploy` y dice cuáles
están denegadas, en vez de descubrirlo a mitad del despliegue.
