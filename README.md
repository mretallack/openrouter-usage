# openrouter-usage

Publish [OpenRouter](https://openrouter.ai) credit usage to Home Assistant over
MQTT using discovery. A sibling of
[kiro-usage](https://github.com/mark-kiro/kiro-usage), but instead of shelling
out to a CLI it queries the OpenRouter HTTP API directly with an API key.

## Sensors

Discovery entities are created automatically (retained), and skipped when the
API does not return a value for them:

| Sensor | Unit | Notes |
| --- | --- | --- |
| Account Balance | USD | `total_credits - total_usage` |
| Account Credits Used | USD | `total_usage` — all-time, account-wide |
| Account Credits Purchased | USD | `total_credits` |
| Account Credits Remaining | % | Share of purchased credits remaining |
| Free Model Requests Used | requests | Daily free-model request count |

### Why there are no per-key sensors

OpenRouter has two mutually exclusive key types:

- **Inference keys** call model endpoints and accrue usage.
- **Management keys** administer the account. They are the only kind that can
  read `/api/v1/credits`, but they are
  [barred from completion endpoints](https://openrouter.ai/docs/guides/overview/auth/management-api-keys),
  so their own `usage`/`usage_daily`/`usage_weekly`/`usage_monthly` counters are
  structurally always `0`.

Because this tool needs a management key to report anything at all, publishing
per-key usage entities would mean creating sensors that can only ever read zero.
They are therefore omitted, and all spend is reported account-wide.

If you want true per-key *daily / weekly / monthly* breakdowns, that requires an
inference key as well as a management key — the two-key setup is not currently
supported.

## Setup

```sh
cp config.ini.template config.ini
$EDITOR config.ini          # add your API key and MQTT broker details
make run
```

`config.ini`:

```ini
[openrouter]
api_key = sk-or-v1-...

[mqtt]
host = localhost
port = 1883
username =
password =
```

### API key type

This tool requires a **management key**, which is the only type that can read
`GET /api/v1/credits`. A regular inference key will be rejected (`403`) by that
endpoint.

## Endpoints used

- `GET https://openrouter.ai/api/v1/credits` — account credits purchased/used
- `GET https://openrouter.ai/api/v1/key` — free-model request counts only

## Scheduling

Run it from cron, a systemd timer, or however you schedule `kiro-usage`:

```
*/15 * * * * cd /path/to/openrouter-usage && make run >/dev/null 2>&1
```

## License

MIT
