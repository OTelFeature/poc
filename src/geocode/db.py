import logging
import os

import psycopg2

logger = logging.getLogger(__name__)

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "coordinates-db")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PWD = os.environ.get("POSTGRES_PWD", "password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "coordinates")


def get_db_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PWD,
        dbname=POSTGRES_DB,
    )


def get_coordinates_from_db(city: str, country: str) -> tuple[float, float] | None:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT latitude, longitude FROM coordinates WHERE city = %s AND country = %s;",
                (city, country),
            )
            row = cur.fetchone()
    except psycopg2.Error:
        logger.exception("Failed to read coordinates from the database")
        return None

    if row is None:
        return None
    return float(row[0]), float(row[1])


def insert_coordinates_into_db(city: str, country: str, latitude: float, longitude: float) -> None:
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO coordinates (city, country, latitude, longitude) VALUES (%s, %s, %s, %s);",
                (city, country, latitude, longitude),
            )
            conn.commit()
    except psycopg2.Error:
        logger.exception("Failed to persist coordinates into the database")
