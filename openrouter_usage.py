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

# Account-wide sensors, sourced from GET /api/v1/credits.
#
# Per-key usage sensors are deliberately absent: reading /credits (and therefore
# running at all) requires a management key, and management keys are barred from
# OpenRouter's completion endpoints, so their own usage counters are always 0.
# A management key can never report per-key usage, so those entities would only
# ever read zero.
#
# (key, name, unit, icon, value_template, device_class)
SENSORS = [
    ("account_balance", "Account Balance", "USD", "mdi:cash",
     "{{ value_json.account_balance }}", "monetary"),
    ("account_credits_used", "Account Credits Used", "USD", "mdi:chart-line",
     "{{ value_json.account_credits_used }}", "monetary"),
    ("account_credits_purchased", "Account Credits Purchased", "USD", "mdi:credit-card-outline",
     "{{ value_json.account_credits_purchased }}", "monetary"),
    ("account_credits_remaining_percent", "Account Credits Remaining", "%", "mdi:percent",
     "{{ value_json.account_credits_remaining_percent }}", None),
]


def api_get(path, api_key):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_usage(api_key):
    credits = api_get("/credits", api_key).get("data", {})
    total = credits.get("total_credits")
    used = credits.get("total_usage")

    if total is None or used is None:
        raise RuntimeError(f"unexpected /credits response: {credits!r}")

    usage = {
        "account_credits_purchased": total,
        "account_credits_used": used,
        "account_balance": round(total - used, 4),
    }

    if total:
        usage["account_credits_remaining_percent"] = round((total - used) / total * 100, 1)

    # Free-model request counts come from /key; they are not usage and are
    # valid for any key type, so they are still reported.
    try:
        key_data = api_get("/key", api_key).get("data", {}) or {}
    except urllib.error.HTTPError as err:
        if err.code not in (401, 403):
            raise
        print(f"warning: /key unavailable ({err.code})", file=sys.stderr)
        return usage

    free = key_data.get("free_model_daily_requests") or {}
    usage["free_model_requests_used"] = free.get("used")
    usage["free_model_requests_limit"] = free.get("limit")
    usage["is_free_tier"] = key_data.get("is_free_tier")

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
