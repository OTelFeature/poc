import http from 'k6/http';
import { check } from 'k6';

const GEOCODE_BASE_URL = __ENV.GEOCODE_BASE_URL || 'http://geocode:8000';
const WEATHER_BASE_URL = __ENV.WEATHER_BASE_URL || 'http://weather:8001';

const LOCATIONS = [
  { city: 'linz', country: 'austria' },
  { city: 'graz', country: 'austria' },
  { city: 'berlin', country: 'germany' },
  { city: 'araraquara', country: 'brazil' },
  { city: 'paris', country: 'france' },
  { city: 'madrid', country: 'spain' },
  { city: 'rome', country: 'italy' },
  { city: 'amsterdam', country: 'netherlands' },
];

// Nominatim's public usage policy caps requests at ~1/s *shared across all
// users of the source IP*. geocode caches resolved coordinates in Postgres,
// but every new city/country pair still costs one live Nominatim lookup, so
// the default here stays well under that limit: 1 request every N seconds.
//
// Open-Meteo has no comparable rate limit, but using the same interval keeps
// the overall traffic predictable and the dashboard readable.
const REQUEST_INTERVAL_SECONDS = Number(__ENV.REQUEST_INTERVAL_SECONDS) || 5;

const DURATION = __ENV.DURATION || '1h';

export const options = {
  scenarios: {
    geocode: {
      exec: 'geocode',
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: `${REQUEST_INTERVAL_SECONDS}s`,
      duration: DURATION,
      preAllocatedVUs: 2,
      maxVUs: 5,
    },
    weather: {
      exec: 'weather',
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: `${REQUEST_INTERVAL_SECONDS}s`,
      duration: DURATION,
      preAllocatedVUs: 2,
      maxVUs: 5,
    },
  },
};

function randomLocation() {
  return LOCATIONS[Math.floor(Math.random() * LOCATIONS.length)];
}

const HEADERS = { 'Content-Type': 'application/json' };

export function geocode() {
  const res = http.post(
    `${GEOCODE_BASE_URL}/geocode`,
    JSON.stringify(randomLocation()),
    { headers: HEADERS },
  );
  check(res, { 'status is 200': (r) => r.status === 200 });
}

export function weather() {
  const res = http.post(
    `${WEATHER_BASE_URL}/weather`,
    JSON.stringify(randomLocation()),
    { headers: HEADERS },
  );
  check(res, { 'status is 200': (r) => r.status === 200 });
}
