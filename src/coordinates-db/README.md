# coordinates-db

A Postgres instance used by [geocode](../geocode) and [weather](../weather)
as a cache: previously resolved `city, country → latitude, longitude` lookups
are stored here so repeat requests skip external APIs entirely. The `weather`
service also caches weather results in a separate `weather` table.

## Schema

[init-coordinates-db.sh](init-coordinates-db.sh) runs once, on first
container start (via Postgres's `docker-entrypoint-initdb.d` convention), and
creates:

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

> [!NOTE]
> The primary key is on `(latitude, longitude)`, not `(city, country)`. Two
> concurrent cache misses for the same city/country pair can therefore both
> attempt to insert the same coordinates; the second insert fails on the
> duplicate key, but `geocode` only logs it — the request still returns the
> correct coordinates either way.

## Configuration

| Environment variable  | Default        | Description                          |
|-----------------------|----------------|--------------------------------------|
| `POSTGRES_USER`       | `postgres`     | Superuser created on first init      |
| `POSTGRES_PASSWORD`   | `password`     | Password for `POSTGRES_USER`         |
| `POSTGRES_DB`         | `coordinates`  | Database created on first init       |

> [!NOTE]
> This container reads `POSTGRES_PASSWORD` (the official Postgres image's
> variable). `geocode` reads the same value as `POSTGRES_PWD` — see
> [compose.yaml](../../compose.yaml). If you change the password, update it
> in both places.

## Persistence

Data lives in the `coordinates-db-data` named volume, mounted at
`/var/lib/postgresql` (Postgres 18+'s data directory convention — mounting at
the older `/var/lib/postgresql/data` path fails to start on this image). It
survives `docker compose down` / `up` cycles; use `docker compose down -v` to
reset the cache.

## Health

A `pg_isready` healthcheck gates `geocode`'s and `weather`'s startup
(`depends_on: ... condition: service_healthy` in [compose.yaml](../../compose.yaml)),
so they don't attempt to connect before Postgres is actually accepting
connections.

## Inspecting the cache

```sh
docker exec -it $(docker compose ps -q coordinates-db) \
  psql -U postgres -d coordinates -c "SELECT * FROM coordinates;"

docker exec -it $(docker compose ps -q coordinates-db) \
  psql -U postgres -d coordinates -c "SELECT * FROM weather;"
```
