package otelfeature.poc.model;

public record WeatherResponse(
        double latitude,
        double longitude,
        double temperature,
        double windspeed,
        int weatherCode,
        String weatherDescription
) {}
