#!/usr/bin/env python3
"""
Bons Plans Bot
==============
Recupere les meilleures promos (>70%) et les jeux gratuits du jour sur
Steam, Epic Games Store et GOG via l'API IsThereAnyDeal, puis envoie un
digest formate sur un canal/chat Telegram. Les offres deja envoyees sont
memorisees pour ne jamais etre renotifiees.

Usage :
    python3 bons_plans_bot.py

Fichiers attendus a cote de ce script :
    config.json       identifiants (voir config.example.json)
    sent_offers.json  cree/mis a jour automatiquement (historique des envois)
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "sent_offers.json"

ITAD_BASE_URL = "https://api.isthereanydeal.com"
TELEGRAM_BASE_URL = "https://api.telegram.org"

# IDs de boutiques IsThereAnyDeal (verifies via /service/shops/v1)
SHOPS = {
    "Steam": 61,
    "Epic Games Store": 16,
    "GOG": 35,
}

MIN_DISCOUNT_PERCENT = 70
DEALS_PER_SHOP = 200  # maximum autorise par l'API en une seule requete
TELEGRAM_MAX_LEN = 4096

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bons-plans-bot")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            config = json.load(f)
    else:
        # Pas de config.json (ex: runner GitHub Actions) -> on lit les secrets
        # depuis les variables d'environnement injectees par le workflow.
        config = {
            "itad_api_key": os.environ.get("ITAD_API_KEY"),
            "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
            "itad_country": os.environ.get("ITAD_COUNTRY", "FR"),
            "channel_link": os.environ.get("CHANNEL_LINK", ""),
        }

    missing = [k for k in ("itad_api_key", "telegram_bot_token", "telegram_chat_id") if not config.get(k)]
    if missing:
        raise SystemExit(
            f"Cle(s) manquante(s) : {', '.join(missing)}\n"
            "En local : renseigne-les dans config.json.\n"
            "En CI : verifie les secrets du repo GitHub."
        )
    return config


def load_seen_offers() -> set:
    if not SEEN_PATH.exists():
        return set()
    with SEEN_PATH.open(encoding="utf-8") as f:
        return set(json.load(f))


def save_seen_offers(seen: set) -> None:
    with SEEN_PATH.open("w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def fetch_shop_deals(api_key: str, shop_id: int, country: str) -> list:
    response = requests.get(
        f"{ITAD_BASE_URL}/deals/v2",
        params={"shops": shop_id, "country": country, "sort": "-cut", "limit": DEALS_PER_SHOP},
        headers={"ITAD-API-Key": api_key},
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("list", [])


def is_good_deal(entry: dict) -> bool:
    deal = entry["deal"]
    cut = deal.get("cut", 0)
    price_amount = deal.get("price", {}).get("amount")
    return cut > MIN_DISCOUNT_PERCENT or price_amount == 0


def offer_id(shop_name: str, entry: dict) -> str:
    price_cents = entry["deal"]["price"]["amountInt"]
    return f"{shop_name}:{entry['slug']}:{price_cents}"


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_offer_line(entry: dict) -> str:
    deal = entry["deal"]
    title = escape_html(entry["title"])
    cut = deal.get("cut", 0)
    price = deal["price"]["amount"]
    currency = deal["price"]["currency"]
    regular = deal["regular"]["amount"]
    url = deal["url"]

    if price == 0:
        price_part = f"GRATUIT \U0001F381 (au lieu de {regular:.2f} {currency})"
    else:
        price_part = f"-{cut}% : {regular:.2f} {currency} → {price:.2f} {currency}"

    return f'\U0001F3AE <a href="{url}">{title}</a>\n   {price_part}'


def build_digest(offers_by_shop: dict) -> str:
    date_str = datetime.now().strftime("%d/%m/%Y")
    sections = [f"\U0001F525 <b>Bons plans du {date_str}</b>"]
    for shop_name, entries in offers_by_shop.items():
        if not entries:
            continue
        sections.append(f"\n<b>{escape_html(shop_name)}</b>")
        sections.extend(format_offer_line(entry) for _, entry in entries)
    return "\n".join(sections)


def build_footer(config: dict) -> str:
    # Attribution ITAD recommandee par leurs conditions d'utilisation (pas obligatoire, mais correcte)
    lines = ['\n\U0001F4E1 via <a href="https://isthereanydeal.com">IsThereAnyDeal</a>']

    channel_link = config.get("channel_link")
    if channel_link:
        lines.append(f"\U0001F4E2 Partage ce canal : {escape_html(channel_link)}")

    affiliate_links = config.get("affiliate_links") or []
    parts = [
        f'<a href="{a["url"]}">{escape_html(a["label"])}</a>'
        for a in affiliate_links
        if a.get("url") and a.get("label")
    ]
    if parts:
        lines.append("\U0001F6D2 Plus de deals : " + " | ".join(parts))

    return "\n".join(lines)


def chunk_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list:
    if len(text) <= max_len:
        return [text]

    chunks, current = [], ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"{TELEGRAM_BASE_URL}/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}

    for _ in range(2):  # une seule reprise en cas de rate-limit Telegram
        response = requests.post(url, data=payload, timeout=20)
        if response.status_code == 429:
            retry_after = response.json().get("parameters", {}).get("retry_after", 5)
            log.warning("Rate limit Telegram atteint, pause de %ss", retry_after)
            time.sleep(retry_after)
            continue
        response.raise_for_status()
        return
    response.raise_for_status()


def main() -> None:
    config = load_config()
    country = config.get("itad_country", "FR")
    seen = load_seen_offers()

    offers_by_shop = {}
    new_ids = []
    for shop_name, shop_id in SHOPS.items():
        try:
            deals = fetch_shop_deals(config["itad_api_key"], shop_id, country)
        except requests.RequestException as exc:
            log.error("Erreur API IsThereAnyDeal pour %s : %s", shop_name, exc)
            continue

        shop_offers = []
        for entry in deals:
            if entry.get("type") != "game":
                continue
            if not is_good_deal(entry):
                continue
            oid = offer_id(shop_name, entry)
            if oid in seen:
                continue
            shop_offers.append((oid, entry))
            new_ids.append(oid)

        if shop_offers:
            offers_by_shop[shop_name] = shop_offers

    if not new_ids:
        log.info("Aucune nouvelle offre a envoyer.")
        return

    message = build_digest(offers_by_shop) + "\n" + build_footer(config)

    try:
        for chunk in chunk_message(message):
            send_telegram_message(config["telegram_bot_token"], config["telegram_chat_id"], chunk)
            time.sleep(1)
    except requests.RequestException as exc:
        log.error("Echec d'envoi Telegram, rien n'est marque comme envoye : %s", exc)
        return

    seen.update(new_ids)
    save_seen_offers(seen)
    log.info("%d nouvelle(s) offre(s) envoyee(s).", len(new_ids))


if __name__ == "__main__":
    main()
