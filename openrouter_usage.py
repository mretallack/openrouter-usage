import configparser
import json
import sys
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt

DEVICE_ID = "openrouter_usage_monitor"
DISCOVERY_PREFIX = "homeassistant"
API_BASE = "https://openrouter.ai/api/v1"

DEVICE = {
    "identifiers": [DEVICE_ID],
    "name": "OpenRouter Usage Monitor",
    "manufacturer": "OpenRouter",
    "model": "Credits API",
}

# (key, name, unit, icon, value_template, device_class)
SENSORS = [
    ("credits_remaining", "Credits Remaining", "credits", "mdi:credit-card-outline",
     "{{ value_json.credits_remaining }}", None),
    ("account_balance", "Account Balance", "USD", "mdi:cash",
     "{{ value_json.account_balance }}", "monetary"),
    ("key_usage", "Key Usage (all time)", "credits", "mdi:chart-line",
     "{{ value_json.key_usage }}", None),
    ("key_usage_daily", "Key Usage Today", "credits", "mdi:calendar-today",
     "{{ value_json.key_usage_daily }}", None),
    ("key_usage_weekly", "Key Usage This Week", "credits", "mdi:calendar-week",
     "{{ value_json.key_usage_weekly }}", None),
    ("key_usage_monthly", "Key Usage This Month", "credits", "mdi:calendar-month",
     "{{ value_json.key_usage_monthly }}", None),
    ("key_limit", "Key Credit Limit", "credits", "mdi:speedometer",
     "{{ value_json.key_limit }}", None),
    ("key_limit_percent", "Key Limit Used", "%", "mdi:percent",
     "{{ value_json.key_limit_percent }}", None),
    ("free_model_requests_used", "Free Model Requests Used", "requests",
     "mdi:gift-outline", "{{ value_json.free_model_requests_used }}", None),
]


def api_get(path, api_key):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_usage(api_key):
    key_data = api_get("/key", api_key).get("data", {})

    # OpenRouter returns the masked API key as the label when the key has no
    # human-set label. Never publish the credential itself over MQTT.
    label = key_data.get("label") or ""
    if api_key[:12] and api_key[:12] in label:
        label = "unnamed key"

    usage = {
        "key_label": label or "unnamed key",
        "key_usage": key_data.get("usage"),
        "key_usage_daily": key_data.get("usage_daily"),
        "key_usage_weekly": key_data.get("usage_weekly"),
        "key_usage_monthly": key_data.get("usage_monthly"),
        "key_limit": key_data.get("limit"),
        "credits_remaining": key_data.get("limit_remaining"),
        "is_free_tier": key_data.get("is_free_tier"),
    }

    # Percentage of the key's credit limit consumed (only when a limit is set).
    limit = key_data.get("limit")
    if limit:
        used = limit - (key_data.get("limit_remaining") or 0)
        usage["key_limit_percent"] = round(used / limit * 100, 1)

    free = key_data.get("free_model_daily_requests") or {}
    usage["free_model_requests_used"] = free.get("used")
    usage["free_model_requests_limit"] = free.get("limit")

    # Account balance needs a management key; degrade gracefully if unavailable.
    try:
        credits = api_get("/credits", api_key).get("data", {})
        total = credits.get("total_credits")
        used = credits.get("total_usage")
        if total is not None and used is not None:
            usage["account_balance"] = round(total - used, 4)
            usage["account_credits_purchased"] = total
            usage["account_credits_used"] = used
    except urllib.error.HTTPError as err:
        if err.code not in (401, 403):
            raise
        print(f"warning: /credits unavailable ({err.code}); "
              "balance sensors need a management key", file=sys.stderr)

    return usage


def publish(usage, config):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=DEVICE_ID)
    if config.get("mqtt", "username"):
        client.username_pw_set(config.get("mqtt", "username"), config.get("mqtt", "password"))
    client.connect(config.get("mqtt", "host"), config.getint("mqtt", "port"))
    client.loop_start()

    state_topic = f"{DEVICE_ID}/state"

    for key, name, unit, icon, value_template, device_class in SENSORS:
        if usage.get(key) is None:
            continue
        payload = {
            "name": name,
            "state_topic": state_topic,
            "unique_id": f"{DEVICE_ID}_{key}",
            "icon": icon,
            "device": DEVICE,
            "o": {"name": "openrouter-usage-monitor"},
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if value_template:
            payload["value_template"] = value_template
        if device_class:
            payload["device_class"] = device_class

        topic = f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/{key}/config"
        client.publish(topic, json.dumps(payload), retain=True).wait_for_publish()

    client.publish(state_topic, json.dumps(usage), retain=True).wait_for_publish()

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")

    api_key = config.get("openrouter", "api_key", fallback="").strip()
    if not api_key:
        sys.exit("error: set api_key under [openrouter] in config.ini")

    try:
        usage = get_usage(api_key)
    except urllib.error.HTTPError as err:
        if err.code == 401:
            sys.exit("error: OpenRouter rejected the API key (401 Unauthorized)")
        raise

    print(json.dumps(usage, indent=2))
    publish(usage, config)
