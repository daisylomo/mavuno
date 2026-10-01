# Mavuno 🌾

<img src="frontend/assets/images/mavuno-icon.png" alt="Mavuno wheat icon" width="160" />

Mavuno connects Kenyan farmers directly with buyers. Farmers list produce and
receive orders; buyers discover local harvests, place orders and coordinate with
farmers. RevenueCat powers optional Premium access for future harvest requests
and farmer insights.

## Try the Android app

Download the APK and `SHA256SUMS.txt` from the
[v1.0.0-rc.8 sandbox release](https://github.com/daisylomo/mavuno/releases/tag/v1.0.0-rc.8).
The release appears after the tagged CI build finishes. This build includes the
wheat launcher/splash icon and Premium renewal verification.

This is a test release with test signing, RevenueCat Test Store and sandbox
M-Pesa. No real payments are collected. It is not a Google Play listing.

## Premium walkthrough

1. Create a buyer account and open **Premium → See Premium plans**.
2. Select a plan and complete a valid RevenueCat Test Store purchase.
3. Confirm Premium access; use **Manage subscription** for Customer Center and
   purchase restoration.
4. Create an active produce listing with a separate farmer account. As the
   Premium buyer, open the listing and request a future harvest with a quantity,
   future date window and proposed price.
5. As the farmer, open **Premium → Harvest requests** and accept or decline.
   Return as the buyer to see the response. Farmers can respond for free.

Harvest requests do not collect payment or reserve current stock. RevenueCat
sells digital Premium access; produce checkout is a separate M-Pesa flow.

The SDK uses the signed-in Mavuno account ID. Purchases and restores are verified
by the backend against the `mavuno_premium` entitlement. Webhooks synchronize
subscription changes, and Premium screens reverify inactive access before
showing an upgrade. Test Store subscription periods are accelerated.

Purchase unlock, restore and the buyer/farmer request flow were verified in the
rc.7 APK. Successful real-money produce payment and fulfilment are not claimed.

## Development

- `frontend/`: Expo SDK 57, React Native and TypeScript.
- `backend/`: FastAPI, MySQL and Redis-compatible services; see
  [backend setup](backend/README.md).
- `api_client/`: Python API client.

Use Node.js 22.13 or later in the Node 22 series, or a supported newer Node version.

```bash
cd frontend
npm ci
npm run android
```

RevenueCat purchases require a native development build or the released APK;
Expo Go and the web preview do not validate the native purchase flow.
Set `EXPO_PUBLIC_MAVUNO_API_URL` and the public
`EXPO_PUBLIC_REVENUECAT_API_KEY` before building. Never put a RevenueCat secret
key in a client environment variable. CI reads the public SDK key from the
`REVENUECAT_ANDROID_API_KEY` repository secret. A `test_` key enables the
Test Store-compatible debuggable build; a `goog_` key selects Google Play.

```bash
npx tsc --noEmit
node --experimental-strip-types --test tests/*.test.mjs
```

The launcher, splash screen, iOS icon and web favicon use the supplied wheat
asset in `frontend/assets/images/mavuno-icon.png` (1024 × 1024 PNG).

### Customer marketplace

From `frontend`, run `npm run web`, then open `http://localhost:8081/customer`.
With no API URL configured, the page shows sample data. Every step of the
purchase flow is labelled as a demo ("Place demo order", "Demo total"), and its
sample products, cart and checkout are local only: no order is created and no
payment is taken. Sample quantities and units match the backend listing units
(`kg`, `g`, `crate`, `piece`, `bunch`, `bag`): avocados are priced individually
and a jar of honey is counted as one `piece`. The sample product photographs are bundled illustrations,
not photographs of real farmers' stock. Their [CC0 sources on Wikimedia
Commons](https://commons.wikimedia.org/) are:
[tomatoes](https://commons.wikimedia.org/wiki/File:Tomatoes.jpg),
[spinach](https://commons.wikimedia.org/wiki/File:Spinach_Plant_Nourishment_Meal_Fresh_Healthy_Bio.jpg),
[mangoes](https://commons.wikimedia.org/wiki/File:Mangoes_-_Massachusetts.jpg),
[bananas](https://commons.wikimedia.org/wiki/File:Bananas_-_Massachusetts.jpg),
[carrots](https://commons.wikimedia.org/wiki/File:Carrots_-_San_Francisco,_CA.jpg),
[avocados](https://commons.wikimedia.org/wiki/File:Avocados_Fruit.jpg),
[potatoes](https://commons.wikimedia.org/wiki/File:Potatoes_-_Massachusetts.jpg), and
[honey](https://commons.wikimedia.org/wiki/File:Small_Honey_Jar_with_Honeycomb.jpg).

Anything a farmer lists on the farmer screen appears at the top of the customer
marketplace, priced by that farmer rather than by the sample data. The two
screens share the same on-device storage, so no server is needed: add a listing
under **Farmer → New listing**, then return to `/customer` to see it. Only
listings that are `active` or `low_stock` and have both a price and stock above
zero are offered. The farmer form has more categories than the customer filters,
so `Grains & Cereals` and `Dairy & Poultry` are shown under **Pantry**, and
`Tubers & Roots` under **Vegetables**.

In the offline demo, each farmer listing borrows the closest of the bundled CC0
pictures, matched on what the farmer typed in the title — English or Swahili, so
both "Sukuma Wiki" and "Spinach" land on the leafy-greens picture, and "Ndizi" on
the bananas. When nothing matches, the listing falls back to a picture for its
category. These are illustrations, not the farmer's actual harvest, and every
such card says so underneath the image.

With the live API, farmers add their own photo when listing produce: they take one
with the camera or choose one from the gallery (on the web, from a file). The app
resizes it to about 1280 px before uploading, and buyers see that photo. A farmer
without a photo can pick a bundled illustration instead; buyers are told it is not
the farmer's own photo. Listings never get a description the farmer did not write,
and the harvest option the farmer picks is sent as a harvest date.

Every live listing shows who is selling it: the farmer's name, area, verification
status, completed orders and whether they offer pickup or delivery. Tapping through
opens the farmer's profile with their bio, farm details and everything else they
have on sale. Farmers fill these in under **Profile → What buyers see about your farm**.

Buyers see how long their produce is reserved while paying, the page checks the
M-Pesa payment by itself while the prompt is open, and an unpaid order can be
cancelled to release the stock straight away. In an order with produce from
several farmers, each farmer confirms and hands over only their own items, and
the buyer confirms receipt per farmer.

The hosted API sleeps when idle. The sign-in screen starts waking it as soon as it
opens, requests wait up to a minute, and a gateway error while it starts is retried
once, with a message that explains the delay instead of blaming the connection.

Without an API URL, the demo cart is saved on the device and trimmed against
the demo catalogue. With an API URL, signed-in buyers use the backend cart,
addresses, order checkout, M-Pesa payment initiation, and order history.

To browse **real active listings**, start the [backend](./backend/README.md)
with MySQL configured and migrations applied. Restart Expo with the public
API URL set (from PowerShell in `frontend`):

```powershell
$env:EXPO_PUBLIC_MAVUNO_API_URL = "http://127.0.0.1:8000/api/v1"
npm run web
```

Set `MAVUNO_CORS_ORIGINS='["http://localhost:8081"]'` in the backend
environment for the web preview. For a phone, use your computer's LAN IP in
the public API URL (not `127.0.0.1`); permit that address through the firewall.
The URL is baked into the Expo client, so restart Expo after changing it.
Live mode uses the API for listings, cart, checkout, payment status, and farmer
listing management. Checkout and payment initiation use idempotency keys.
Network and malformed-response errors are displayed with retry controls.

The hosted test API is `https://mavuno-api.onrender.com/api/v1`. It uses free
Render and Aiven services, so its first request after inactivity can be slow.
The configured Daraja account is **sandbox only**: no real M-Pesa payment is
collected. An APK for this environment must set both
`EXPO_PUBLIC_MAVUNO_API_URL=https://mavuno-api.onrender.com/api/v1` and
`EXPO_PUBLIC_MAVUNO_PAYMENTS_SANDBOX=1` at build time. Production payments
require production Daraja credentials and a separate end-to-end validation.

### Android APK CI

`.github/workflows/android-apk.yml` checks TypeScript and frontend tests on
pull requests. On changes to the frontend on `main`, or a manual run, it
generates the Android project and builds a test APK on GitHub's runner. The
APK is available in the Actions run for 14 days. Pushing a `v*` tag also
attaches it to the corresponding GitHub Release. CI uses the hosted API and
sandbox M-Pesa settings above. Update the workflow and `frontend/eas.json`
before building for another environment. The CI APK uses Expo's generated
debug signing key; use the `release-apk` EAS profile or a private release
keystore for a production-signed APK.

The backend provides image *object keys*, not public image URLs. Until public
image hosting exists, live cards explicitly show "Photo unavailable".
If listing images are published at a public base URL, set
`EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL` to that prefix before starting Expo.
The client appends each listing's encoded relative object key; do not use this
setting for a private bucket or a URL requiring secrets.

Check the frontend from `frontend` with
`node --experimental-strip-types --test tests/customer-catalog-api.test.mjs tests/auth-api.test.mjs tests/farmer-listings-bridge.test.mjs tests/customer-cart-storage.test.mjs tests/customer-live-catalog-format.test.mjs`.

### Sign up and log in

`/` redirects to `/auth/login`. After signing in, the account's role decides the
destination: farmers land on `/farmer`, admins on `/admin`, and everyone else on
the customer marketplace.

Like the marketplace, auth has two modes. Without `EXPO_PUBLIC_MAVUNO_API_URL`
the screens keep working against on-device storage so the app can be demoed with
no server. With the URL set, `src/services/auth-api.ts` calls the real
`/auth/register`, `/auth/login`, `/auth/me` and `/auth/logout` endpoints, and
these backend rules apply:

- **Passwords must be at least 10 characters.** The signup screen enforces the
  same minimum so the form fails fast instead of being rejected by the server.
- **The app's `customer` role is the backend's `buyer` role.** Registration sends
  `buyer`, and the roles list returned by the API is mapped back to a single app
  role (`admin` wins, then `farmer`, otherwise `customer`).
- **Registering needs an email address or a phone number**, and blank values are
  omitted rather than sent as empty strings. Phone numbers are normalised to
  E.164 (`0712345678` becomes `+254712345678`).
- **The backend stores no display name or location.** Those are cached on the
  device and re-attached at sign-in, so the greeting still shows a real name.
- Signing in stores the access and refresh tokens, never the password. Logging
  out revokes the refresh token before clearing the local session.

There is no `admin` option when registering, because the backend only accepts
`buyer` and `farmer`.
