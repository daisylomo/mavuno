# Welcome to your Expo app 👋

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

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

Farmers cannot attach their own photograph yet, so each listing borrows the
closest of the bundled CC0 pictures, matched on what the farmer typed in the
title — English or Swahili, so both "Sukuma Wiki" and "Spinach" land on the
leafy-greens picture, and "Ndizi" on the bananas. When nothing matches, the
listing falls back to a picture for its category. These are illustrations, not
the farmer's actual harvest, and every such card says so underneath the image.

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
Only public listing and category reads are connected; there is **no live cart,
checkout or payment**. Network and malformed-response errors are displayed
with retry controls, never replaced with sample products.

The backend provides image *object keys*, not public image URLs. Until public
image hosting exists, live cards explicitly show "Photo unavailable".
If listing images are published at a public base URL, set
`EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL` to that prefix before starting Expo.
The client appends each listing's encoded relative object key; do not use this
setting for a private bucket or a URL requiring secrets.

Check the frontend API adapter from `frontend` with
`node --experimental-strip-types --test tests/customer-catalog-api.test.mjs tests/auth-api.test.mjs`.

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

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow our guide on ["Using ESLint and Prettier"](https://docs.expo.dev/guides/using-eslint/)
- If you'd like to set up unit testing, follow our guide on ["Unit Testing with Jest"](https://docs.expo.dev/develop/unit-testing/)
- Learn more about the TypeScript setup in this template in our guide on ["Using TypeScript"](https://docs.expo.dev/guides/typescript/)

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.
