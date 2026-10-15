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
| Credits Remaining | credits | Remaining allowance on the key's credit limit |
| Account Balance | USD | `total_credits - total_usage` (needs a management key) |
| Key Usage (all time) | credits | |
| Key Usage Today / This Week / This Month | credits | UTC windows |
| Key Credit Limit | credits | Only if a limit is set on the key |
| Key Limit Used | % | Only if a limit is set on the key |
| Free Model Requests Used | requests | Daily free-model request count |

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

- A regular API key works for the key/usage sensors via `GET /api/v1/key`.
- The **Account Balance** sensor needs a **management key**, which can call
  `GET /api/v1/credits`. Without one, the other sensors still publish and a
  warning is printed.

## Endpoints used

- `GET https://openrouter.ai/api/v1/key` — key limits and usage
- `GET https://openrouter.ai/api/v1/credits` — account credits purchased/used

## Scheduling

Run it from cron, a systemd timer, or however you schedule `kiro-usage`:

```
*/15 * * * * cd /path/to/openrouter-usage && make run >/dev/null 2>&1
```

## License

MIT
