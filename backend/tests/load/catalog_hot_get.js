import http from "k6/http";
import { check, sleep } from "k6";

// Representative smoke/load artifact; LISTING_ID must refer to a seeded active listing.
// This is deliberately not part of pytest and does not require another runtime service.
export const options = {
  scenarios: {
    hot_listing: {
      executor: "constant-vus",
      vus: 20,
      duration: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<250"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://127.0.0.1:8000";
const listingId = __ENV.LISTING_ID;

export default function () {
  const response = http.get(`${baseUrl}/api/v1/listings/${listingId}`);
  check(response, {
    "listing returned": (value) => value.status === 200,
    "cache status present": (value) => ["HIT", "MISS"].includes(value.headers["X-Cache"]),
  });
  sleep(0.1);
}
