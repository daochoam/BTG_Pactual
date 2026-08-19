#!/usr/bin/env node
/**
 * Ejecuta un comando con el entorno de AWS de ESTE proyecto.
 *
 *   node scripts/with-aws-env.js serverless deploy --stage prod
 *
 * Lee `.aws.env` (oculto y fuera del control de versiones) y exporta lo que
 * contenga antes de lanzar el comando. Ese archivo guarda QUE perfil usar,
 * nunca las claves: las credenciales siguen viviendo en ~/.aws, que es donde
 * el sistema operativo puede protegerlas.
 *
 * Si el archivo no existe no hace nada y ejecuta el comando tal cual: es lo
 * que ocurre en el CI, donde las credenciales llegan del rol asumido.
 *
 * Las variables que ya esten definidas en el shell mandan sobre el archivo,
 * para poder desplegar puntualmente contra otra cuenta sin editar nada.
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const ENV_FILES = ['.aws.env', '.aws.local'];

function parseEnvFile(filePath) {
  const values = {};

  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;

    const separator = line.indexOf('=');
    if (separator === -1) continue;

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (key) values[key] = value;
  }

  return values;
}

function loadProjectEnv() {
  for (const name of ENV_FILES) {
    const filePath = path.join(ROOT, name);
    if (fs.existsSync(filePath)) {
      return { name, values: parseEnvFile(filePath) };
    }
  }
  return null;
}

const [command, ...args] = process.argv.slice(2);

if (!command) {
  console.error('Uso: node scripts/with-aws-env.js <comando> [argumentos...]');
  process.exit(1);
}

const env = { ...process.env };
const loaded = loadProjectEnv();

if (loaded) {
  for (const [key, value] of Object.entries(loaded.values)) {
    // El shell gana: permite un despliegue puntual contra otra cuenta.
    if (env[key] === undefined) env[key] = value;
  }
  console.log(`[aws-env] ${loaded.name}: perfil=${env.AWS_PROFILE || '(cadena de credenciales por defecto)'} region=${env.AWS_DEPLOY_REGION || env.AWS_REGION || '(la de serverless.yml)'}`);
} else {
  console.log('[aws-env] sin .aws.env: se usa la cadena de credenciales por defecto de AWS.');
}

/**
 * Hace falta `shell: true` porque en Windows `serverless` y `aws` son scripts
 * .cmd y Node no puede lanzarlos directamente. Pero pasar `args` junto a
 * `shell: true` deja que el shell reinterprete comillas y espacios, asi que se
 * construye la linea a mano con cada argumento entrecomillado.
 */
function quoteArg(arg) {
  if (arg === '') return '""';
  if (!/[\s"'&|<>^()`$]/.test(arg)) return arg;
  // Duplica las barras que preceden a una comilla y escapa la comilla.
  const escaped = arg.replace(/(\\*)"/g, '$1$1\\"').replace(/(\\*)$/, '$1$1');
  return `"${escaped}"`;
}

const commandLine = [command, ...args].map(quoteArg).join(' ');
const child = spawn(commandLine, { stdio: 'inherit', env, shell: true, cwd: ROOT });

child.on('error', (error) => {
  console.error(`[aws-env] no se pudo ejecutar "${command}": ${error.message}`);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
