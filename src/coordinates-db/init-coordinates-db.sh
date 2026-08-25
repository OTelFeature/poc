#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS coordinates (
        city TEXT,
        country TEXT,
        latitude TEXT NOT NULL,
        longitude TEXT NOT NULL,
        PRIMARY KEY (latitude, longitude)
    );

    CREATE TABLE IF NOT EXISTS weather (
        city TEXT NOT NULL,
        country TEXT NOT NULL,
        latitude DOUBLE PRECISION NOT NULL,
        longitude DOUBLE PRECISION NOT NULL,
        temperature DOUBLE PRECISION,
        windspeed DOUBLE PRECISION,
        weather_code INTEGER,
        weather_description TEXT,
        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (city, country)
    );
EOSQL
