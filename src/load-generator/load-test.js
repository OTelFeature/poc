import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = __ENV.GEOCODE_BASE_URL || 'http://geocode:8000';

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
const REQUEST_INTERVAL_SECONDS = Number(__ENV.REQUEST_INTERVAL_SECONDS) || 5;

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: 1,
      timeUnit: `${REQUEST_INTERVAL_SECONDS}s`,
      duration: __ENV.DURATION || '1h',
      preAllocatedVUs: 2,
      maxVUs: 5,
    },
  },
};

export default function () {
  const location = LOCATIONS[Math.floor(Math.random() * LOCATIONS.length)];

  const res = http.post(`${BASE_URL}/geocode`, JSON.stringify(location), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, { 'status is 200': (r) => r.status === 200 });
}
