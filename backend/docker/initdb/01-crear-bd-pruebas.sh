#!/bin/bash
# Se ejecuta solo la primera vez que se crea el volumen de datos: crea la BD de pruebas además de POSTGRES_DB.
set -e

BD_PRUEBAS="${POSTGRES_TEST_DB:-cajaclara_test}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
SELECT 'CREATE DATABASE "${BD_PRUEBAS}" OWNER "${POSTGRES_USER}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${BD_PRUEBAS}')\gexec
EOSQL
echo "BD de pruebas '${BD_PRUEBAS}' lista"
