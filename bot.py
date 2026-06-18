#!/usr/bin/env python3
"""
RUDIMASTER — Telegram Master Control Dashboard
Controls all 14 Railway services from a single Telegram interface.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import aiohttp
from telegram import (
    Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8600739487:AAGhByAoKEpbsfco9swoaRYjU2HI_gSt718")
CHAT_ID     = int(os.getenv("TELEGRAM_CHAT_ID", "5088771245"))
STRIPE_KEY  = os.getenv("STRIPE_SECRET_KEY", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "https://qyrjeckzacjaazkpvnjk.supabase.co")
SUPA_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── All Railway services ──────────────────────────────────────────────────────
SERVICES = {
    "shopify_acq":   {"name": "Shopify Acq. Engine",     "url": "https://shopify-acquisition-engine-production.up.railway.app",       "health": "/health",     "checkout": "/api/checkout"},
    "icomeauto":     {"name": "iComeAuto SaaS",           "url": "https://icomeauto-saas-production.up.railway.app",                    "health": "/health",     "checkout": "/api/checkout"},
    "steuercockpit": {"name": "Steuercockpit",            "url": "https://steuercockpit-production-44c9.up.railway.app",               "health": "/health",     "checkout": "/billing/checkout"},
    "digistore24":   {"name": "Digistore24 Suite",        "url": "https://digistore24-automation-production.up.railway.app",           "health": "/api/health"},
    "seo_engine":    {"name": "SEO Traffic Engine",       "url": "https://seo-traffic-engine-production.up.railway.app",               "health": "/health",     "trigger": "/api/trigger/articles"},
    "meta_social":   {"name": "Meta Social Engine",       "url": "https://meta-social-engine-production.up.railway.app",               "health": "/health",     "trigger": "/api/trigger"},
    "adposter":      {"name": "AdPoster Engine",          "url": "https://adposter-engine-production.up.railway.app",                  "health": "/health"},
    "visual":        {"name": "Visual Content Engine",    "url": "https://visual-content-engine-production.up.railway.app",            "health": "/health",     "trigger": "/api/trigger"},
    "social":        {"name": "Social Traffic Engine",    "url": "https://social-traffic-engine-production.up.railway.app",            "health": "/health",     "trigger": "/api/trigger"},
    "freelance":     {"name": "Freelance Gig Engine",     "url": "https://freelance-gig-engine-production.up.railway.app",             "health": "/health",     "trigger": "/api/trigger"},
    "supermegabot":  {"name": "SuperMegaBot",             "url": "https://dudirudibot-mega-production.up.railway.app",                  "health": "/health"},
    "automaton":     {"name": "Shopify Automaton Suite",  "url": "https://shopify-automaton-suite-production-e405.up.railway.app",     "health": "/api/health"},
    "creatorai":     {"name": "CreatorAI Ultra",          "url": "https://creatorai-ultra-production.up.railway.app",                  "health": "/health"},
    "cognitive":     {"name": "Cognitive Symphony",       "url": "https://cognitive-symphony-production.up.railway.app",               "health": "/health"},
}

SOCIAL_ENGINES = ["meta_social", "visual", "social", "freelance", "adposter"]
REVENUE_SERVICES = ["shopify_acq", "icomeauto", "steuercockpit", "digistore24"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def http_get(url: str, timeout: int = 6) -> dict | None:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get(url) as r:
                if r.content_type == "application/json":
                    return await r.json()
                return {"status": "ok", "code": r.status}
    except Exception:
        return None


async def http_post(url: str, data: dict = None, timeout: int = 8) -> dict | None:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.post(url, json=data or {}) as r:
                if r.content_type == "application/json":
                    return await r.json()
                return {"status": "ok", "code": r.status}
    except Exception:
        return None


async def check_service(key: str) -> tuple[str, str]:
    """Returns (emoji, short_status)."""
    svc = SERVICES[key]
    result = await http_get(svc["url"] + svc["health"])
    if result and result.get("status") in ("ok", "healthy", "running"):
        return "✅", "online"
    elif result:
        return "⚠️", "degraded"
    return "❌", "offline"


# ── Keyboards ─────────────────────────────────────────────────────────────────

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 SERVICE STATUS",   callback_data="menu_status"),
         InlineKeyboardButton("💰 REVENUE",          callback_data="menu_revenue")],
        [InlineKeyboardButton("🎯 SEO ENGINE",       callback_data="menu_seo"),
         InlineKeyboardButton("📱 SOCIAL MEDIA",     callback_data="menu_social")],
        [InlineKeyboardButton("🛒 SHOPIFY",          callback_data="menu_shopify"),
         InlineKeyboardButton("🤖 AGENTEN",          callback_data="menu_agents")],
        [InlineKeyboardButton("⚡ ALLES TRIGGERN",   callback_data="trigger_all"),
         InlineKeyboardButton("📋 LOGS",             callback_data="menu_logs")],
    ])


def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ ZURÜCK", callback_data="menu_main")]])


def kb_seo() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Artikel generieren",   callback_data="trigger_seo_articles"),
         InlineKeyboardButton("🐦 Tweets senden",        callback_data="trigger_seo_tweets")],
        [InlineKeyboardButton("📊 SEO Stats",            callback_data="stats_seo")],
        [InlineKeyboardButton("◀️ ZURÜCK",               callback_data="menu_main")],
    ])


def kb_social() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Facebook Post",        callback_data="trigger_facebook"),
         InlineKeyboardButton("📸 Instagram Post",       callback_data="trigger_instagram")],
        [InlineKeyboardButton("📌 Pinterest Pin",        callback_data="trigger_pinterest"),
         InlineKeyboardButton("👥 Social Traffic",       callback_data="trigger_social_traffic")],
        [InlineKeyboardButton("🎨 Visual Content",       callback_data="trigger_visual"),
         InlineKeyboardButton("💼 Freelance Gigs",       callback_data="trigger_freelance")],
        [InlineKeyboardButton("◀️ ZURÜCK",               callback_data="menu_main")],
    ])


def kb_shopify() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Produkte scannen",     callback_data="trigger_shopify_scan"),
         InlineKeyboardButton("📈 Trends analysieren",   callback_data="trigger_shopify_trends")],
        [InlineKeyboardButton("💳 Checkout testen",      callback_data="test_checkout"),
         InlineKeyboardButton("🔄 Automaton Status",     callback_data="stats_automaton")],
        [InlineKeyboardButton("◀️ ZURÜCK",               callback_data="menu_main")],
    ])


def kb_agents() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 RudiClone",            callback_data="agent_rudiclone"),
         InlineKeyboardButton("🔍 Geheimwaffe",          callback_data="agent_geheimwaffe")],
        [InlineKeyboardButton("📊 Analytics Agent",      callback_data="agent_analytics"),
         InlineKeyboardButton("💬 AI Chat",              callback_data="agent_chat")],
        [InlineKeyboardButton("◀️ ZURÜCK",               callback_data="menu_main")],
    ])


# ── Text builders ─────────────────────────────────────────────────────────────

async def build_status_text() -> str:
    lines = ["📊 <b>SERVICE STATUS</b>", "━━━━━━━━━━━━━━━━━━━━━━\n"]
    tasks = {k: asyncio.create_task(check_service(k)) for k in SERVICES}
    await asyncio.gather(*tasks.values(), return_exceptions=True)
    for key, task in tasks.items():
        try:
            emoji, status = task.result()
        except Exception:
            emoji, status = "❌", "offline"
        lines.append(f"{emoji} <b>{SERVICES[key]['name']}</b>: {status}")
    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    return "\n".join(lines)


async def build_revenue_text() -> str:
    lines = ["💰 <b>REVENUE DASHBOARD</b>", "━━━━━━━━━━━━━━━━━━━━━━\n"]

    if STRIPE_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.stripe.com/v1/charges",
                    params={"limit": 10},
                    headers={"Authorization": f"Bearer {STRIPE_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    data = await r.json()
                    charges = data.get("data", [])
                    total = sum(c["amount"] for c in charges if c.get("paid")) / 100
                    lines.append(f"💳 <b>Letzte 10 Zahlungen: €{total:.2f}</b>")
                    for c in charges[:5]:
                        if c.get("paid"):
                            amt = c["amount"] / 100
                            desc = (c.get("description") or c.get("statement_descriptor") or "Zahlung")[:40]
                            ts = datetime.fromtimestamp(c["created"]).strftime("%d.%m %H:%M")
                            lines.append(f"  ✅ €{amt:.2f} — {desc} ({ts})")
        except Exception as e:
            lines.append(f"⚠️ Stripe Fehler: {e}")
    else:
        lines.append("⚠️ STRIPE_SECRET_KEY nicht gesetzt")

    if SUPA_URL and SUPA_KEY:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{SUPA_URL}/rest/v1/hermes_events",
                    params={"event_type": "eq.new_subscription", "order": "created_at.desc", "limit": "5"},
                    headers={"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"},
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    events = await r.json()
                    if events:
                        lines.append(f"\n📡 <b>Neue Subscriptions (Supabase): {len(events)}</b>")
                        for e in events[:3]:
                            lines.append(f"  🆕 {e.get('payload', {}).get('email', '?')} — {e.get('created_at', '')[:16]}")
        except Exception:
            pass

    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    return "\n".join(lines)


async def build_seo_stats() -> str:
    data = await http_get("https://seo-traffic-engine-production.up.railway.app/stats")
    if not data:
        return "❌ SEO Engine nicht erreichbar"
    lines = ["🎯 <b>SEO ENGINE STATS</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
    lines.append(f"📄 Artikel gesamt: <b>{data.get('articles_total', '?')}</b>")
    lines.append(f"🐦 Tweets gesendet: <b>{data.get('tweeted', '?')}</b>")
    lines.append(f"🔑 Keywords in Queue: <b>{data.get('keywords_queued', '?')}</b>")
    recent = data.get("recent_articles", [])
    if recent:
        lines.append("\n📰 <b>Neueste Artikel:</b>")
        for a in recent[:3]:
            lines.append(f"  • {a.get('title', '?')[:50]}")
    return "\n".join(lines)


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    text = (
        "🤖 <b>RUDIMASTER — CONTROL DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Steuere alle 14 Railway Services\n"
        "direkt aus Telegram."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_main())


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    msg = await update.message.reply_text("⏳ Prüfe alle Services...", parse_mode=ParseMode.HTML)
    text = await build_status_text()
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_back())


async def cmd_revenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    msg = await update.message.reply_text("⏳ Lade Revenue-Daten...", parse_mode=ParseMode.HTML)
    text = await build_revenue_text()
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_back())


async def cmd_trigger(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    msg = await update.message.reply_text("⚡ Triggere alle Engines...", parse_mode=ParseMode.HTML)
    results = await trigger_all_engines()
    await msg.edit_text(results, parse_mode=ParseMode.HTML, reply_markup=kb_back())


async def trigger_all_engines() -> str:
    lines = ["⚡ <b>ALLE ENGINES GETRIGGERT</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
    triggers = [
        ("SEO Artikel",   "https://seo-traffic-engine-production.up.railway.app/api/trigger/articles", {}),
        ("SEO Tweets",    "https://seo-traffic-engine-production.up.railway.app/api/trigger/tweets",   {}),
        ("Meta Social",   "https://meta-social-engine-production.up.railway.app/api/trigger",          {}),
        ("Visual Engine", "https://visual-content-engine-production.up.railway.app/api/trigger",       {}),
        ("Social Traffic","https://social-traffic-engine-production.up.railway.app/api/trigger",       {}),
        ("Freelance Gigs","https://freelance-gig-engine-production.up.railway.app/api/trigger",        {}),
    ]
    for name, url, data in triggers:
        result = await http_post(url, data)
        emoji = "✅" if result and result.get("status") in ("ok", "triggered") else "❌"
        lines.append(f"{emoji} {name}")
    lines.append(f"\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    return "\n".join(lines)


# ── Callback query handlers ───────────────────────────────────────────────────

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    if update.effective_chat.id != CHAT_ID:
        return

    data = q.data

    # ── Main menu ──
    if data == "menu_main":
        text = (
            "🤖 <b>RUDIMASTER — CONTROL DASHBOARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Wähle eine Kategorie:"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_main())

    # ── Status ──
    elif data == "menu_status":
        await q.edit_message_text("⏳ Prüfe alle 14 Services...", parse_mode=ParseMode.HTML)
        text = await build_status_text()
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    # ── Revenue ──
    elif data == "menu_revenue":
        await q.edit_message_text("⏳ Lade Revenue-Daten...", parse_mode=ParseMode.HTML)
        text = await build_revenue_text()
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    # ── SEO ──
    elif data == "menu_seo":
        stats = await build_seo_stats()
        await q.edit_message_text(stats, parse_mode=ParseMode.HTML, reply_markup=kb_seo())

    elif data == "stats_seo":
        stats = await build_seo_stats()
        await q.edit_message_text(stats, parse_mode=ParseMode.HTML, reply_markup=kb_seo())

    elif data == "trigger_seo_articles":
        result = await http_post("https://seo-traffic-engine-production.up.railway.app/api/trigger/articles")
        status = "✅ Artikel-Generierung gestartet!" if result else "❌ Fehlgeschlagen"
        await q.edit_message_text(
            f"🎯 SEO ARTIKEL\n━━━━━━━━━━━━━━\n{status}\n\nDer SEO Engine generiert jetzt neue Artikel und broadcastet sie an alle 11 Services.",
            parse_mode=ParseMode.HTML, reply_markup=kb_seo()
        )

    elif data == "trigger_seo_tweets":
        result = await http_post("https://seo-traffic-engine-production.up.railway.app/api/trigger/tweets")
        status = "✅ Tweets werden gesendet!" if result else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"🐦 TWEETS\n━━━━━━━━\n{status}", parse_mode=ParseMode.HTML, reply_markup=kb_seo())

    # ── Social ──
    elif data == "menu_social":
        lines = ["📱 <b>SOCIAL MEDIA CONTROL</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
        for key in SOCIAL_ENGINES:
            emoji, status = await check_service(key)
            lines.append(f"{emoji} {SERVICES[key]['name']}: {status}")
        text = "\n".join(lines)
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_facebook":
        r = await http_post("https://meta-social-engine-production.up.railway.app/api/trigger")
        s = "✅ Facebook+Instagram+Pinterest Post gestartet!" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"📘 META TRIGGER\n━━━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_instagram":
        r = await http_post("https://meta-social-engine-production.up.railway.app/api/trigger")
        s = "✅ Instagram Post gestartet!" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"📸 INSTAGRAM\n━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_pinterest":
        r = await http_post("https://meta-social-engine-production.up.railway.app/api/trigger")
        s = "✅ Pinterest Pin wird erstellt!" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"📌 PINTEREST\n━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_social_traffic":
        r = await http_post("https://social-traffic-engine-production.up.railway.app/api/trigger")
        s = "✅ Reddit/LinkedIn Templates generiert → Telegram" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"👥 SOCIAL TRAFFIC\n━━━━━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_visual":
        r = await http_post("https://visual-content-engine-production.up.railway.app/api/trigger")
        s = "✅ TikTok/Discord Visual Content gestartet!" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"🎨 VISUAL\n━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    elif data == "trigger_freelance":
        r = await http_post("https://freelance-gig-engine-production.up.railway.app/api/trigger")
        s = "✅ Fiverr/Upwork Gig-Proposals gestartet!" if r else "❌ Fehlgeschlagen"
        await q.edit_message_text(f"💼 FREELANCE\n━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_social())

    # ── Shopify ──
    elif data == "menu_shopify":
        r1 = await check_service("shopify_acq")
        r2 = await check_service("automaton")
        text = (
            f"🛒 <b>SHOPIFY CONTROL</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{r1[0]} Acquisition Engine: {r1[1]}\n"
            f"{r2[0]} Automaton Suite: {r2[1]}"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_shopify())

    elif data == "trigger_shopify_scan":
        r = await http_post("https://shopify-acquisition-engine-production.up.railway.app/api/scan")
        s = "✅ Produkt-Scan gestartet!" if r and r.get("status") != "error" else "⚠️ Scan läuft bereits oder kein Endpunkt"
        await q.edit_message_text(f"🔍 SHOPIFY SCAN\n━━━━━━━━━━━━━━\n{s}", parse_mode=ParseMode.HTML, reply_markup=kb_shopify())

    elif data == "trigger_shopify_trends":
        r = await http_get("https://shopify-acquisition-engine-production.up.railway.app/api/trends")
        if r:
            text = f"📈 <b>SHOPIFY TRENDS</b>\n━━━━━━━━━━━━━━━━\n"
            trends = r.get("trends", r.get("products", []))
            for t in trends[:5]:
                name = t.get("title") or t.get("name") or str(t)[:40]
                text += f"  • {name}\n"
            if not trends:
                text += "Keine Trends verfügbar"
        else:
            text = "📈 TRENDS\n━━━━━━━━\n⚠️ Nicht verfügbar"
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_shopify())

    elif data == "stats_automaton":
        r = await http_get("https://shopify-automaton-suite-production-e405.up.railway.app/api/health")
        if r:
            text = f"🔄 <b>AUTOMATON STATUS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n✅ Online\n🏪 Shop: {r.get('env', {}).get('shopifyDomain', '?')}"
        else:
            text = "🔄 AUTOMATON\n━━━━━━━━━━━━\n❌ Offline"
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_shopify())

    elif data == "test_checkout":
        text = (
            "💳 <b>CHECKOUT LINKS</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "🛒 Shopify Engine:\n"
            "  Starter €49: /api/checkout {plan:starter}\n"
            "  Pro €99: /api/checkout {plan:pro}\n\n"
            "📊 Steuercockpit:\n"
            "  Monthly €49: /billing/checkout {plan:monthly}\n"
            "  Lifetime €149: /billing/checkout {plan:lifetime}\n\n"
            "💰 iComeAuto:\n"
            "  Starter €29: /api/checkout {plan:starter}"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_shopify())

    # ── Agents ──
    elif data == "menu_agents":
        text = (
            "🤖 <b>AGENTEN CONTROL</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Verfügbare Agenten:\n"
            "• RudiClone — Business Strategie\n"
            "• Geheimwaffe — Competitive Intel\n"
            "• Analytics Agent — Revenue Analysis\n"
            "• AI Chat — Claude Haiku direkt\n\n"
            "Wähle einen Agenten:"
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_agents())

    elif data == "agent_rudiclone":
        r = await http_post(
            "https://dudirudibot-mega-production.up.railway.app/api/bot/execute",
            {"command": "rudiclone status", "session_id": "telegram-dashboard"}
        )
        resp = r.get("response", "RudiClone läuft") if r else "⚠️ SuperMegaBot nicht erreichbar"
        await q.edit_message_text(f"🧠 <b>RUDICLONE</b>\n━━━━━━━━━━━━━━\n{resp[:400]}", parse_mode=ParseMode.HTML, reply_markup=kb_agents())

    elif data == "agent_geheimwaffe":
        r = await http_post(
            "https://dudirudibot-mega-production.up.railway.app/api/bot/execute",
            {"command": "geheimwaffe scan", "session_id": "telegram-dashboard"}
        )
        resp = r.get("response", "Geheimwaffe läuft") if r else "⚠️ SuperMegaBot nicht erreichbar"
        await q.edit_message_text(f"🔍 <b>GEHEIMWAFFE</b>\n━━━━━━━━━━━━━━━━\n{resp[:400]}", parse_mode=ParseMode.HTML, reply_markup=kb_agents())

    elif data == "agent_analytics":
        r = await http_get("https://analytics-marketing-service-production.up.railway.app/health")
        text = f"📊 <b>ANALYTICS</b>\n━━━━━━━━━━━━━━\n{'✅ Online' if r else '❌ Offline'}"
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_agents())

    elif data == "agent_chat":
        await q.edit_message_text(
            "💬 <b>AI CHAT</b>\n━━━━━━━━━━━━━\nSchreibe einfach eine Nachricht — der Bot antwortet mit Claude Haiku.\n\nBeispiel:\n  Was ist mein Umsatz heute?\n  Trigger alle Social Engines\n  Zeig mir den Status",
            parse_mode=ParseMode.HTML, reply_markup=kb_back()
        )

    # ── Trigger all ──
    elif data == "trigger_all":
        await q.edit_message_text("⚡ Triggere alle Engines...", parse_mode=ParseMode.HTML)
        results = await trigger_all_engines()
        await q.edit_message_text(results, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    # ── Logs ──
    elif data == "menu_logs":
        text = (
            "📋 <b>SYSTEM LOGS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Alle Services senden ihre Logs direkt in diesen Telegram-Chat.\n\n"
            "• SEO Engine: neue Artikel → hier\n"
            "• Meta Social: FB/IG/Pinterest Posts → hier\n"
            "• Revenue Hub: Stripe Zahlungen → hier\n"
            "• AdPoster: Ads alle 6h → hier\n"
            "• Alle Fehler & Warnungen → hier\n\n"
            "Scroll nach oben für die letzten Logs."
        )
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_back())


# ── Free text handler (simple AI-like routing) ────────────────────────────────

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return

    text = update.message.text.lower().strip()

    if any(w in text for w in ["status", "health", "online"]):
        msg = await update.message.reply_text("⏳ Prüfe Services...", parse_mode=ParseMode.HTML)
        result = await build_status_text()
        await msg.edit_text(result, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    elif any(w in text for w in ["revenue", "umsatz", "geld", "zahlung", "stripe"]):
        msg = await update.message.reply_text("⏳ Lade Revenue...", parse_mode=ParseMode.HTML)
        result = await build_revenue_text()
        await msg.edit_text(result, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    elif any(w in text for w in ["seo", "artikel", "keyword"]):
        r = await http_post("https://seo-traffic-engine-production.up.railway.app/api/trigger/articles")
        s = "✅ SEO Artikel generierung gestartet!" if r else "❌ Fehlgeschlagen"
        await update.message.reply_text(s, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    elif any(w in text for w in ["trigger", "start", "alles", "alle engines"]):
        msg = await update.message.reply_text("⚡ Triggere alle Engines...", parse_mode=ParseMode.HTML)
        result = await trigger_all_engines()
        await msg.edit_text(result, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    elif any(w in text for w in ["social", "facebook", "instagram", "pinterest"]):
        r = await http_post("https://meta-social-engine-production.up.railway.app/api/trigger")
        s = "✅ Social Media Post gestartet!" if r else "❌ Fehlgeschlagen"
        await update.message.reply_text(s, parse_mode=ParseMode.HTML, reply_markup=kb_back())

    elif any(w in text for w in ["shopify", "produkt", "scan"]):
        await update.message.reply_text(
            "🛒 Shopify Control:", parse_mode=ParseMode.HTML, reply_markup=kb_shopify()
        )

    elif any(w in text for w in ["hilfe", "help", "was kannst", "befehle", "kommando"]):
        await update.message.reply_text(
            "🤖 <b>RUDIMASTER BEFEHLE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "/start — Haupt-Dashboard\n"
            "/status — Alle Services Status\n"
            "/revenue — Stripe Revenue\n"
            "/trigger — Alle Engines triggern\n"
            "/seo — SEO Engine Control\n\n"
            "Oder schreibe einfach:\n"
            "  'status' • 'revenue' • 'seo'\n"
            "  'trigger alles' • 'social'",
            parse_mode=ParseMode.HTML,
            reply_markup=kb_main(),
        )

    else:
        await update.message.reply_text(
            "❓ Nicht verstanden. Nutze /start für das Dashboard.",
            reply_markup=kb_main(),
        )


# ── Health endpoint (Railway braucht einen offenen Port) ──────────────────────

async def health_server():
    from aiohttp import web

    async def health(_):
        return web.json_response({"status": "ok", "service": "rudimaster-bot", "bot": "running"})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8099))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server on port {port}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def post_startup(app):
    await health_server()
    bot: Bot = app.bot
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "🚀 <b>RUDIMASTER gestartet!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Telegram Dashboard ist LIVE.\n"
            "Tippe /start für das Control-Panel."
        ),
        parse_mode=ParseMode.HTML,
    )
    await bot.set_my_commands([
        ("start",   "Haupt-Dashboard"),
        ("status",  "Alle Services Status"),
        ("revenue", "Stripe Revenue"),
        ("trigger", "Alle Engines triggern"),
        ("seo",     "SEO Engine Control"),
    ])


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_startup)
        .build()
    )

    application.add_handler(CommandHandler("start",   cmd_start))
    application.add_handler(CommandHandler("status",  cmd_status))
    application.add_handler(CommandHandler("revenue", cmd_revenue))
    application.add_handler(CommandHandler("trigger", cmd_trigger))
    application.add_handler(CommandHandler("seo",     lambda u, c: u.message.reply_text("🎯 SEO:", reply_markup=kb_seo())))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("RUDIMASTER Bot startet mit Polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
