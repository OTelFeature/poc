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

// Requests per interval for the geocode and weather scenarios: 1 is the
// stage load; the measurement harness raises it with BENCH_RATE (UC-003).
const REQUEST_RATE = Number(__ENV.REQUEST_RATE) || 1;

// Health checks: GET /health on both services, like a kubelet probe, so
// Demo 2 has health-check spans to drop (OTelFeature/poc#38). Requests per
// second, per service; 0 turns the scenario off. k6 sends no traceparent, so
// every check is a root SERVER span. /health makes no outgoing calls, so the
// rate is independent of the external-API limits above.
const HEALTHCHECK_RATE_RAW = (__ENV.HEALTHCHECK_RATE || '').trim();
if (HEALTHCHECK_RATE_RAW !== '' && !/^\d+$/.test(HEALTHCHECK_RATE_RAW)) {
  throw new Error(`HEALTHCHECK_RATE must be a whole number >= 0, got "${__ENV.HEALTHCHECK_RATE}"`);
}
const HEALTHCHECK_RATE = HEALTHCHECK_RATE_RAW === '' ? 2 : Number(HEALTHCHECK_RATE_RAW);

// The cross-service path (FR-026): geocode's POST /forecast calls weather,
// so these traces span both services and geocode decides their sampling.
// Deliberately rare: every 15 s puts at most one request into any 10 s
// error-rate interval, so a weather incident can't push geocode's own error
// rate over 5% (UC-005 A7). 0 turns it off.
const FORECAST_INTERVAL_RAW = (__ENV.FORECAST_INTERVAL_SECONDS || '').trim();
if (FORECAST_INTERVAL_RAW !== '' && !/^\d+$/.test(FORECAST_INTERVAL_RAW)) {
  throw new Error(`FORECAST_INTERVAL_SECONDS must be a whole number >= 0, got "${__ENV.FORECAST_INTERVAL_SECONDS}"`);
}
const FORECAST_INTERVAL_SECONDS = FORECAST_INTERVAL_RAW === '' ? 15 : Number(FORECAST_INTERVAL_RAW);

const scenarios = {
  geocode: {
    exec: 'geocode',
    executor: 'constant-arrival-rate',
    rate: REQUEST_RATE,
    timeUnit: `${REQUEST_INTERVAL_SECONDS}s`,
    duration: DURATION,
    preAllocatedVUs: 2,
    maxVUs: 20,
  },
  weather: {
    exec: 'weather',
    executor: 'constant-arrival-rate',
    rate: REQUEST_RATE,
    timeUnit: `${REQUEST_INTERVAL_SECONDS}s`,
    duration: DURATION,
    preAllocatedVUs: 2,
    maxVUs: 20,
  },
};

if (HEALTHCHECK_RATE > 0) {
  scenarios.healthchecks = {
    exec: 'healthchecks',
    executor: 'constant-arrival-rate',
    rate: HEALTHCHECK_RATE,
    timeUnit: '1s',
    duration: DURATION,
    preAllocatedVUs: 2,
    maxVUs: 10,
  };
}

if (FORECAST_INTERVAL_SECONDS > 0) {
  scenarios.forecast = {
    exec: 'forecast',
    executor: 'constant-arrival-rate',
    rate: 1,
    timeUnit: `${FORECAST_INTERVAL_SECONDS}s`,
    duration: DURATION,
    preAllocatedVUs: 1,
    maxVUs: 3,
  };
}

export const options = { scenarios };

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

// One iteration = one probe of each service, sent in parallel.
export function healthchecks() {
  const [geo, wea] = http.batch([
    ['GET', `${GEOCODE_BASE_URL}/health`],
    ['GET', `${WEATHER_BASE_URL}/health`],
  ]);
  check(geo, { 'geocode health is 200': (r) => r.status === 200 });
  check(wea, { 'weather health is 200': (r) => r.status === 200 });
}

export function forecast() {
  const res = http.post(
    `${GEOCODE_BASE_URL}/forecast`,
    JSON.stringify(randomLocation()),
    { headers: HEADERS },
  );
  check(res, { 'forecast status is 200': (r) => r.status === 200 });
}
