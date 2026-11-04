# coordinates-db

Postgres cache for [geocode](../geocode) and [weather](../weather). It stores
resolved `city, country → latitude, longitude` lookups in `coordinates` and
weather results in `weather`, so repeat requests skip the external APIs.
Entries never expire.

## Schema

[init-coordinates-db.sh](init-coordinates-db.sh) runs on the first container
start (`docker-entrypoint-initdb.d`) and creates:

```sql
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
```

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` | `postgres` | Superuser created on first init |
| `POSTGRES_PASSWORD` | `password` | Password for `POSTGRES_USER` |
| `POSTGRES_DB` | `coordinates` | Database created on first init |

The services read the password as `POSTGRES_PWD`. If you change it, change
both in [compose.yaml](../../compose.yaml).

Data lives in the `coordinates-db-data` volume, mounted at
`/var/lib/postgresql` (the Postgres 18 layout; the older
`/var/lib/postgresql/data` mount fails to start). A `pg_isready` healthcheck
gates the start of `geocode` and `weather`.

## Troubleshooting

Inspect the cache:

```sh
docker exec -it $(docker compose ps -q coordinates-db) \
  psql -U postgres -d coordinates -c "SELECT * FROM coordinates;"

docker exec -it $(docker compose ps -q coordinates-db) \
  psql -U postgres -d coordinates -c "SELECT * FROM weather;"
```

Reset it with `docker compose --profile staging down -v`. The init script
only runs on an empty volume, so a schema change also needs the reset.

A `Failed to persist coordinates` exception (duplicate key) in the `geocode`
log is harmless. The primary key is `(latitude, longitude)`, so two
concurrent misses for the same city can both try to insert it. The request
still returns the coordinates.
