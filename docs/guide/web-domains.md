# Where an app's website lives

An app's `www/` pages are mounted once per process:

| Setting (`sites/<site>/grunt.site`) | Pages of app `portal` |
|---|---|
| nothing | `/portal`, `/portal/news`, … |
| `"primary_web_app": "portal"` | `/`, `/news`, … on every host of the bench |
| `"web_domains": {"portal.example.org": "portal"}` | `/`, `/news`, … on `portal.example.org`; `/portal/…` elsewhere |

`primary_web_app` is bench-wide: routes are mounted once, so the first site
that sets it wins. `web_domains` is per host - one site can give several apps
their own domains, and the main host keeps serving the Desk and the primary
app.

```json
{
  "installed_apps": ["grunt", "mlt_portal", "opendata"],
  "primary_web_app": "mlt_portal",
  "web_domains": {"opendata.example.org": "opendata"}
}
```

Both need a restart (`grunt serve` / the production units) to take effect.
A domain is skipped - and logged - when its app isn't installed on the site,
when it is the name of a site, or when another site already claims it.

## On an app's domain

The request's host picks the site, then the path is routed for the app:

- `/datasets` serves the app's `/opendata/datasets` page; the app's page wins
  over a core page of the same path (an app may have its own `/login`).
- A path no route takes - web view documents, `website_resolvers`, the 404 -
  goes to the app too: `www/_404.html` of the app renders.
- The API (`/api/...`), the Desk (`/app`, `/login`, `/reset-password`, …),
  `/sitemap.xml`, `/robots.txt`, mounted assets and root static files stay
  where they are.
- `/opendata/...` answers **301** to the address without the prefix, so every
  page has one URL there.

Links: build them with `app_mount(app)` - `""` on the app's own domain and for
the primary app, `/<app>` elsewhere. In Python:
`from grunt.website.generator import app_mount`; in templates the same
function is a global: `<a href="{{ app_mount('opendata') }}/datasets">`.
Web view documents (`route_prefix`, `web_url`) use it already.

`/sitemap.xml` lists the pages of the host it is asked on: on an app's domain
that app's pages only, on the main host every app except those with a domain
of their own. A `website_sitemap` source belongs to the app whose package
holds it.

The reverse proxy only has to send the domain to the same backend (with its
`Host` header) - no path rewriting.
