package otelfeature.poc;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import otelfeature.poc.model.WeatherResponse;

/**
 * Resolves current weather for a city/country pair.
 *
 * <p>Flow:
 * <ol>
 *   <li>Check the <code>weather</code> cache table in Postgres — return on hit.</li>
 *   <li>On a miss, look up coordinates in the <code>coordinates</code> table
 *       (populated by the <strong>geocode</strong> service). If not found
 *       there either, fall back to the Open-Meteo geocoding API and persist
 *       the coordinates for next time.</li>
 *   <li>Query the Open-Meteo forecast API with the coordinates.</li>
 *   <li>Persist the weather result and return it.</li>
 * </ol>
 *
 * <p>Uses <a href="https://open-meteo.com/">Open-Meteo</a> — a free, no-API-key
 * weather API with generous rate limits — instead of Nominatim, so running
 * alongside <strong>geocode</strong> won't cause rate-limiting on either side.
 */
@Service
public class WeatherService {

    private static final Logger log = LoggerFactory.getLogger(WeatherService.class);

    private final String geocodingApi;
    private final String forecastApi;
    private final JdbcTemplate jdbcTemplate;
    private final HttpClient httpClient;
    private final JsonMapper jsonMapper;

    public WeatherService(JdbcTemplate jdbcTemplate, JsonMapper jsonMapper,
                          @Value("${weather.open-meteo.geocoding-url}") String geocodingApi,
                          @Value("${weather.open-meteo.forecast-url}") String forecastApi) {
        this.geocodingApi = geocodingApi;
        this.forecastApi = forecastApi;
        this.jdbcTemplate = jdbcTemplate;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.jsonMapper = jsonMapper;
    }

    public WeatherResponse getWeather(String city, String country) {
        // 1. Check weather cache
        WeatherResponse cached = checkWeatherCache(city, country);
        if (cached != null) {
            log.debug("Weather cache hit for {}/{}", city, country);
            return cached;
        }

        // 2. Get coordinates (from coordinates table or geocoding API)
        double[] coords = getCoordinates(city, country);

        // 3. Query forecast API
        WeatherResponse weather = queryForecast(coords[0], coords[1]);

        // 4. Persist weather
        persistWeather(city, country, weather);

        return weather;
    }

    // ── Weather cache ──────────────────────────────────────────────

    private WeatherResponse checkWeatherCache(String city, String country) {
        try {
            Map<String, Object> row = jdbcTemplate.queryForMap(
                    "SELECT latitude, longitude, temperature, windspeed, weather_code, weather_description "
                            + "FROM weather WHERE city = ? AND country = ?",
                    city, country);
            return new WeatherResponse(
                    ((Number) row.get("latitude")).doubleValue(),
                    ((Number) row.get("longitude")).doubleValue(),
                    ((Number) row.get("temperature")).doubleValue(),
                    ((Number) row.get("windspeed")).doubleValue(),
                    ((Number) row.get("weather_code")).intValue(),
                    (String) row.get("weather_description"));
        } catch (EmptyResultDataAccessException e) {
            return null;
        } catch (Exception e) {
            log.warn("Failed to read weather cache: {}", e.getMessage());
            return null;
        }
    }

    private void persistWeather(String city, String country, WeatherResponse weather) {
        try {
            jdbcTemplate.update(
                    "INSERT INTO weather (city, country, latitude, longitude, temperature, windspeed, weather_code, weather_description) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                            + "ON CONFLICT (city, country) DO UPDATE SET "
                            + "  latitude = EXCLUDED.latitude, "
                            + "  longitude = EXCLUDED.longitude, "
                            + "  temperature = EXCLUDED.temperature, "
                            + "  windspeed = EXCLUDED.windspeed, "
                            + "  weather_code = EXCLUDED.weather_code, "
                            + "  weather_description = EXCLUDED.weather_description, "
                            + "  cached_at = CURRENT_TIMESTAMP",
                    city, country,
                    weather.latitude(), weather.longitude(),
                    weather.temperature(), weather.windspeed(),
                    weather.weatherCode(), weather.weatherDescription());
        } catch (Exception e) {
            log.warn("Failed to persist weather: {}", e.getMessage());
        }
    }

    // ── Coordinates lookup ──────────────────────────────────────────

    private double[] getCoordinates(String city, String country) {
        // Try the coordinates table first (shared with geocode service)
        try {
            Map<String, Object> row = jdbcTemplate.queryForMap(
                    "SELECT latitude, longitude FROM coordinates WHERE city = ? AND country = ?",
                    city, country);
            return new double[]{
                    Double.parseDouble(row.get("latitude").toString()),
                    Double.parseDouble(row.get("longitude").toString())
            };
        } catch (EmptyResultDataAccessException e) {
            // Not cached — fall through to geocoding API
        } catch (Exception e) {
            log.warn("Failed to read coordinates from DB: {}", e.getMessage());
        }

        // Query Open-Meteo geocoding API
        double[] coords = queryGeocodingApi(city, country);

        // Persist coordinates for future lookups (same table geocode uses)
        try {
            jdbcTemplate.update(
                    "INSERT INTO coordinates (city, country, latitude, longitude) "
                            + "VALUES (?, ?, ?, ?) ON CONFLICT (latitude, longitude) DO NOTHING",
                    city, country,
                    String.valueOf(coords[0]), String.valueOf(coords[1]));
        } catch (Exception e) {
            log.warn("Failed to persist coordinates: {}", e.getMessage());
        }

        return coords;
    }

    private double[] queryGeocodingApi(String city, String country) {
        try {
            String url = String.format(
                    "%s?name=%s&country=%s&count=1&language=en&format=json",
                    geocodingApi,
                    URLEncoder.encode(city, StandardCharsets.UTF_8),
                    URLEncoder.encode(country, StandardCharsets.UTF_8));

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode root = jsonMapper.readTree(response.body());
            JsonNode results = root.path("results");

            if (results.isArray() && results.size() > 0) {
                JsonNode first = results.get(0);
                return new double[]{
                        first.get("latitude").asDouble(),
                        first.get("longitude").asDouble()
                };
            }
        } catch (Exception e) {
            log.error("Failed to query Open-Meteo geocoding API", e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "Geocoding API request failed", e);
        }

        throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                "No location found for " + city + ", " + country);
    }

    // ── Forecast API ───────────────────────────────────────────────

    private WeatherResponse queryForecast(double latitude, double longitude) {
        try {
            String url = String.format(
                    "%s?latitude=%.4f&longitude=%.4f&current=temperature_2m,wind_speed_10m,weather_code",
                    forecastApi, latitude, longitude);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode root = jsonMapper.readTree(response.body());
            JsonNode current = root.path("current");

            double temperature = current.path("temperature_2m").asDouble();
            double windspeed = current.path("wind_speed_10m").asDouble();
            int weatherCode = current.path("weather_code").asInt();

            return new WeatherResponse(
                    latitude, longitude,
                    temperature, windspeed,
                    weatherCode, wmoCodeToString(weatherCode));
        } catch (Exception e) {
            log.error("Failed to query Open-Meteo forecast API", e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "Forecast API request failed", e);
        }
    }

    /**
     * Maps WMO weather interpretation codes to human-readable descriptions.
     *
     * @see <a href="https://open-meteo.com/en/docs">Open-Meteo API docs</a>
     */
    private String wmoCodeToString(int code) {
        return switch (code) {
            case 0 -> "Clear sky";
            case 1, 2, 3 -> "Partly cloudy";
            case 45, 48 -> "Fog";
            case 51, 53, 55 -> "Drizzle";
            case 56, 57 -> "Freezing drizzle";
            case 61, 63, 65 -> "Rain";
            case 66, 67 -> "Freezing rain";
            case 71, 73, 75 -> "Snow";
            case 77 -> "Snow grains";
            case 80, 81, 82 -> "Rain showers";
            case 85, 86 -> "Snow showers";
            case 95 -> "Thunderstorm";
            case 96, 99 -> "Thunderstorm with hail";
            default -> "Unknown";
        };
    }
}
