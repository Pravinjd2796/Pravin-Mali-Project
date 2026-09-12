"""
WhatsApp Bot - Pravin Mali Help Line
Built with FastAPI + Meta WhatsApp Business Cloud API
Phone: +91 9272511811
Language: Marathi
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
import httpx
import time
import json

# ─── Load Environment ────────────────────────────────────────────────────────
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

# ─── Complaint forwarding + manual reply relay ───────────────────────────────
# OWNER_PHONE receives every complaint and can reply to citizens with "#47 text".
# One or more owners, comma separated: "917620391327,919975802584"
OWNER_PHONES = [p.strip() for p in os.getenv("OWNER_PHONE", "").split(",") if p.strip()]
OWNER_PHONE = OWNER_PHONES[0] if OWNER_PHONES else ""
ALERT_TEMPLATE = os.getenv("ALERT_TEMPLATE", "complaint_forward").strip()
ALERT_TEMPLATE_LANG = os.getenv("ALERT_TEMPLATE_LANG", "en_US").strip()

# Google Sheet used as the complaint register
SHEET_ID = os.getenv("SHEET_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

# How long the bot stays quiet for a citizen after the owner takes over
HANDOFF_MINUTES = int(os.getenv("HANDOFF_MINUTES", "30"))

IST = timezone(timedelta(hours=5, minutes=30))
SHEET_HEADER = [
    "Ticket", "Date (IST)", "Citizen Phone", "Type",
    "Details", "Status", "Reply", "Replied At",
]

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ─── In-memory session store ─────────────────────────────────────────────────
# Tracks which user is at which step in the conversation flow
# Key: phone number, Value: dict with "state" and optional "selected_option"
user_sessions: dict[str, dict] = {}

# Deduplication: Track processed message IDs to prevent double-replies from Meta retries
# Note: In production, use a database/cache with a TTL. For now, we use a simple set.
PROCESSED_MESSAGES = set()
MAX_PROCESSED_HISTORY = 1000  # Prevent memory leak

# ─── Handoff / ticket state ──────────────────────────────────────────────────
# While the owner is talking to a citizen, the bot keeps quiet for that citizen.
# Key: citizen phone, Value: unix timestamp when the bot resumes
handoff_until: dict[str, float] = {}

# Ticket number <-> citizen phone. Rebuilt from the Sheet after a restart.
ticket_to_phone: dict[str, str] = {}
phone_to_ticket: dict[str, str] = {}

# WhatsApp message id of each alert we send the owner -> ticket.
# Lets the owner simply *reply to* an alert instead of typing "#12".
alert_msg_to_ticket: dict[str, str] = {}

# The most recent ticket, used when the owner just types a message with no tag.
last_ticket: str | None = None

# The first owner to reply to a ticket claims it, so a complainant never gets two
# answers. The claim lapses after HANDOFF_MINUTES so a forgotten ticket frees
# itself and somebody else can step in.
# Key: ticket, Value: (owner phone, unix time the claim expires)
ticket_claimed_by: dict[str, tuple[str, float]] = {}

# Tickets that were closed with "done". Replying to one is allowed — people do
# follow up — but every owner is told it was reopened.
closed_tickets: set[str] = set()

# Ticket numbers used when the Sheet is unavailable. Kept unique and clear of
# the Sheet's own row numbers, so two complaints can never share a ticket.
_fallback_seq = 0


def _next_fallback_ticket() -> str:
    global _fallback_seq
    while True:
        _fallback_seq += 1
        candidate = str(9000 + _fallback_seq)
        if candidate not in ticket_to_phone:
            return candidate

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Pravin Mali Help Line",
    description="नगरपालिका तक्रार व्यवस्थापन बॉट",
    version="1.0.0",
)


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS — WhatsApp Cloud API
# ═══════════════════════════════════════════════════════════════════════════════

async def send_text_message(to: str, text: str):
    """Send a simple text message to a WhatsApp user."""
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(WHATSAPP_API_URL, headers=headers, json=payload)
            logger.info(f"Text message sent to {to} — Status: {resp.status_code}")
            if resp.status_code != 200:
                logger.error(f"Error response: {resp.text}")
            return resp
    except Exception as exc:
        logger.error(f"Text send to {to} failed: {exc}")
        return None


async def send_interactive_buttons(to: str):
    """
    Send an interactive button list message with the 5 complaint options.
    WhatsApp interactive buttons support max 3 buttons per message,
    so we use an interactive LIST message instead (supports up to 10 items).
    """
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": "🏛️ नगरसेवक प्रविण माळी "
            },
            "body": {
                "text": (
                    "नमस्कार! 🙏\n\n"
                    "नगरसेवक प्रविण माळी हेल्पलाईनमध्ये आपले स्वागत आहे.\n\n"
                    "कृपया खालीलपैकी एक पर्याय निवडा:"
                )
            },
            "footer": {
                "text": "नगरसेवक प्रविण माळी | हेल्पलाईन"
            },
            "action": {
                "button": "पर्याय निवडा",
                "sections": [
                    {
                        "title": "तक्रार प्रकार",
                        "rows": [
                            {
                                "id": "option_1",
                                "title": "🚛 घंटा गाडी",
                                "description": "कचरा गाडी संबंधित तक्रार"
                            },
                            {
                                "id": "option_2",
                                "title": "💧 पाणी",
                                "description": "पाणी पुरवठा संबंधित तक्रार"
                            },
                            {
                                "id": "option_3",
                                "title": "💡 लाईट",
                                "description": "रस्ता दिवे संबंधित तक्रार"
                            },
                            {
                                "id": "option_4",
                                "title": "🧹 नाली सफाई",
                                "description": "नाली/गटार सफाई तक्रार"
                            },
                            {
                                "id": "option_5",
                                "title": "🐾 मृत प्राणी हटवणे",
                                "description": "मृत प्राणी हटवण्याची विनंती"
                            },
                        ],
                    }
                ],
            },
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WHATSAPP_API_URL, headers=headers, json=payload)
        logger.info(f"Interactive list sent to {to} — Status: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"Error response: {resp.text}")
        return resp

        
async def send_image_request(to: str, option_title: str):
    """Ask the user to upload details + photo for their complaint (options 4 & 5)."""
    
    text = (
        f"📸 तुम्ही *{option_title}* ही तक्रार निवडली आहे.\n\n"
        "कृपया खालील माहिती एकत्र पाठवा:\n"
        "👤 नाव\n"
        "🏠 पत्ता\n"
        "📞 मोबाईल नंबर\n"
        "📷 समस्येचा फोटो\n\n"
        "जेणेकरून आम्ही लवकरात लवकर कार्यवाही करू शकू. 🙏"
    )
    
    await send_text_message(to, text)


async def send_acknowledgement(to: str, option_title: str):
    """
    Acknowledge complaints for options 1, 2, 3 and ask for user details.
    """
    
    text = (
        f"✅ तुम्ही *{option_title}* तक्रार निवडली आहे.\n\n"
        "कृपया खालील माहिती पाठवा:\n"
        "👤 नाव\n"
        "🏠 पत्ता\n"
        "📞 मोबाईल नंबर\n\n"
        "आम्ही तुमची तक्रार नोंदवून लवकरच कार्यवाही करू.\n\n"
        "गैरसोयीबद्दल क्षमस्व. 🙏"
    )
    
    await send_text_message(to, text)

# async def send_image_request(to: str, option_title: str):
#     """Ask the user to upload a photo for their complaint (options 4 & 5)."""
#     text = (
#         f"📸 तुम्ही *{option_title}* ही तक्रार निवडली आहे.\n\n"
#         "कृपया समस्येचा एक फोटो पाठवा जेणेकरून आम्ही लवकरात लवकर कार्यवाही करू शकू. 🙏"
#     )
#     await send_text_message(to, text)


# async def send_acknowledgement(to: str, option_title: str):
#     """
#     Acknowledge complaints for options 1, 2, 3 (no image required).
#     """
#     text = (
#         f"✅ तुमची *{option_title}* तक्रार यशस्वीरित्या नोंदवली गेली आहे.\n\n"
#         "आम्ही लवकरच याबाबत कार्यवाही करू.\n\n"
#         "गैरसोयीबद्दल क्षमस्व. 🙏\n\n"
#         "अधिक मदतीसाठी कृपया खालील क्रमांकावर संपर्क साधा:\n"
#         "📞 *99758 02584*"
#     )
#     await send_text_message(to, text)


async def send_image_received_response(to: str):
    """Send response after receiving an image for option 4 or 5."""
    text = (
        "✅ फोटो मिळाला!\n\n"
        "तुमची तक्रार यशस्वीरित्या नोंदवली गेली आहे.\n\n"
        "गैरसोयीबद्दल क्षमस्व, आम्ही लवकरच याबाबत कार्यवाही करू. 🙏\n\n"
        "अधिक मदतीसाठी कृपया खालील क्रमांकावर संपर्क साधा:\n"
        "📞 *9272511811*"
    )
    await send_text_message(to, text)


# ═══════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEET — complaint register
# ═══════════════════════════════════════════════════════════════════════════════

_worksheet = None


def _get_worksheet():
    """Open (and cache) the first tab of the complaint Sheet. Blocking call."""
    global _worksheet
    if _worksheet is not None:
        return _worksheet
    if not (SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON):
        return None

    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        json.loads(GOOGLE_SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).sheet1

    # Write the header row once, on a blank sheet.
    # A blank sheet can come back as [] or as [[]], so check for real content.
    rows = ws.get_all_values()
    if not any(any(cell.strip() for cell in row) for row in rows):
        ws.update(values=[SHEET_HEADER], range_name="A1")

    _worksheet = ws
    return _worksheet


def _sheet_append_sync(row: list) -> int:
    """
    Append a complaint row and return its ticket number.

    The ticket is worked out before the write and placed in column A, so the
    row lands complete — no second call to fill it in afterwards.
    """
    ws = _get_worksheet()
    if ws is None:
        return 0
    ticket = max(1, len(ws.get_all_values()))   # header counts as row 1
    row = list(row)
    row[0] = str(ticket)
    ws.append_row(row, value_input_option="USER_ENTERED")
    return ticket


def _sheet_lookup_phone_sync(ticket: str) -> str | None:
    """Find the citizen's phone for a ticket — used after a restart."""
    ws = _get_worksheet()
    if ws is None:
        return None
    for row in ws.get_all_values()[1:]:
        if row and row[0] == ticket:
            return row[2] or None
    return None


def _sheet_record_reply_sync(ticket: str, reply: str) -> None:
    """Store the owner's reply against the ticket and mark it Replied."""
    ws = _get_worksheet()
    if ws is None:
        return
    for idx, row in enumerate(ws.get_all_values()[1:], start=2):
        if row and row[0] == ticket:
            ws.update(
                values=[["Replied", reply, datetime.now(IST).strftime("%d-%m-%Y %H:%M")]],
                range_name=f"F{idx}:H{idx}",
            )
            return


async def sheet_append(row: list) -> int:
    try:
        return await asyncio.to_thread(_sheet_append_sync, row)
    except Exception as exc:                      # never break the bot over logging
        logger.error(f"Sheet append failed: {exc}")
        return 0


async def sheet_lookup_phone(ticket: str) -> str | None:
    try:
        return await asyncio.to_thread(_sheet_lookup_phone_sync, ticket)
    except Exception as exc:
        logger.error(f"Sheet lookup failed: {exc}")
        return None


async def sheet_record_reply(ticket: str, reply: str) -> None:
    try:
        await asyncio.to_thread(_sheet_record_reply_sync, ticket, reply)
    except Exception as exc:
        logger.error(f"Sheet reply update failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
#  FORWARDING TO THE OWNER
# ═══════════════════════════════════════════════════════════════════════════════

async def send_template_alert(to: str, complaint_type: str, details: str, citizen: str):
    """
    Send the complaint to the owner using the approved template.
    Templates work outside the 24-hour window; plain text does not.
    """
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": ALERT_TEMPLATE,
            "language": {"code": ALERT_TEMPLATE_LANG},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": complaint_type},
                    {"type": "text", "text": details},
                    {"type": "text", "text": citizen},
                ],
            }],
        },
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(WHATSAPP_API_URL, headers=headers, json=payload)
        logger.info(f"Template alert to {to} — Status: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"Template alert failed: {resp.text}")
        return resp


async def notify_owner(ticket: str, complaint_type: str, details: str, citizen: str):
    """
    Tell the owner about a new complaint.

    Plain text is tried first because it carries the #ticket reply instructions.
    It only works inside the 24-hour window, so the template is the fallback.
    """
    if not OWNER_PHONES:
        return

    text = (
        f"🆕 *New complaint  #{ticket}*\n\n"
        f"प्रकार: {complaint_type}\n"
        f"माहिती: {details}\n"
        f"नागरिक: +{citizen}\n\n"
        f"उत्तर पाठवण्यासाठी: `{ticket} तुमचा संदेश`\n"
        f"किंवा या मेसेजला थेट Reply करा.\n"
        f"संभाषण संपवण्यासाठी: `{ticket} done`"
    )
    flat = details.replace("\n", " / ")
    for owner in OWNER_PHONES:
        resp = await send_text_message(owner, text)
        if resp is not None and resp.status_code == 200:
            # Remember this alert so a WhatsApp "reply" to it routes back to the
            # right citizen without the owner typing the ticket number.
            try:
                alert_msg_to_ticket[resp.json()["messages"][0]["id"]] = ticket
            except Exception:
                pass
            continue
        # Outside the 24-hour window — fall back to the approved template.
        logger.info(f"{owner} outside 24h window, sending template instead")
        await send_template_alert(owner, f"#{ticket} {complaint_type}", flat, f"+{citizen}")


async def register_complaint(citizen: str, complaint_type: str, details: str):
    """Log the complaint to the Sheet, then alert the owner."""
    row_no = await sheet_append([
        "",                                            # ticket, filled in below
        datetime.now(IST).strftime("%d-%m-%Y %H:%M"),
        citizen,
        complaint_type,
        details,
        "Open",
        "",
        "",
    ])
    ticket = str(row_no) if row_no else _next_fallback_ticket()

    global last_ticket
    ticket_to_phone[ticket] = citizen
    phone_to_ticket[citizen] = ticket
    last_ticket = ticket
    logger.info(f"Complaint #{ticket} registered from {citizen} ({complaint_type})")

    await notify_owner(ticket, complaint_type, details, citizen)


# ═══════════════════════════════════════════════════════════════════════════════
#  OWNER COMMANDS  —  "#47 message"  /  "#47 done"
# ═══════════════════════════════════════════════════════════════════════════════

OWNER_GREETINGS = {"hi", "hello", "hey", "नमस्कार", "नमस्ते", "हाय", "हॅलो", "menu", "मेनू"}


async def handle_owner_command(text: str, sender: str, reply_to: str | None = None) -> bool:
    """
    Handle a message from the owner. The ticket can be given three ways:

      1. "12 message"   — just the complaint number, easiest
      2. "#12 message"  — same thing with a hash
      3. replying to an alert in WhatsApp — ticket matched by message id

    Returns True if the message was handled as an owner command.
    """
    if text.lower() in OWNER_GREETINGS:
        return False                      # owner can still use the bot normally

    ticket, body = None, ""

    # "12 message" or "#12 message"
    parts = text.lstrip("#").split(maxsplit=1)
    if parts and parts[0].isdigit():
        ticket = parts[0]
        body = parts[1].strip() if len(parts) > 1 else ""

    # Replying to an alert in WhatsApp — no number needed at all.
    elif reply_to and reply_to in alert_msg_to_ticket:
        ticket = alert_msg_to_ticket[reply_to]
        body = text.strip()

    if not ticket:
        return False                      # not a reply — handle as a normal message

    citizen = ticket_to_phone.get(ticket) or await sheet_lookup_phone(ticket)
    if not citizen:
        # Unknown number — probably an ordinary message, not a reply.
        return False
    ticket_to_phone[ticket] = citizen

    if not body:
        await send_text_message(sender, f"⚠️ संदेश रिकामा आहे. वापरा: {ticket} तुमचा संदेश")
        return True

    # Whoever replied first owns this ticket, until the claim lapses.
    claim = ticket_claimed_by.get(ticket)
    if claim and claim[0] != sender and time.time() < claim[1]:
        mins = max(1, int((claim[1] - time.time()) // 60))
        await send_text_message(
            sender,
            f"🔒 *#{ticket}* आधीच +{claim[0]} हाताळत आहेत.\n"
            f"कृपया दुसरे उत्तर पाठवू नका.\n"
            f"({mins} मिनिटांनंतर तुम्ही उत्तर देऊ शकता.)",
        )
        return True

    # End the handoff — the bot takes over again.
    if body.lower() in {"done", "end", "close", "बंद"}:
        handoff_until.pop(citizen, None)
        ticket_claimed_by.pop(ticket, None)
        closed_tickets.add(ticket)
        user_sessions[citizen] = {"state": "idle"}
        for owner in OWNER_PHONES:
            await send_text_message(owner, f"✅ #{ticket} बंद केले. बॉट पुन्हा सुरू.")
        return True

    # Relay the owner's message to the citizen, from the helpline number.
    resp = await send_text_message(citizen, body)
    if resp is not None and resp.status_code == 200:
        handoff_until[citizen] = time.time() + HANDOFF_MINUTES * 60
        ticket_claimed_by[ticket] = (sender, time.time() + HANDOFF_MINUTES * 60)
        reopened = ticket in closed_tickets
        closed_tickets.discard(ticket)
        await sheet_record_reply(ticket, body)
        await send_text_message(sender, f"✅ #{ticket} ला पाठवले.")
        # Keep the other owners in the loop so nobody replies twice.
        note = f"⚠️ *#{ticket}* बंद झाले होते — +{sender} यांनी पुन्हा सुरू केले.\n" if reopened else ""
        for owner in OWNER_PHONES:
            if owner != sender:
                await send_text_message(owner, f"{note}↪️ *#{ticket}* +{sender} यांनी उत्तर दिले:\n{body}")
            elif reopened:
                await send_text_message(owner, f"⚠️ #{ticket} बंद झाले होते — पुन्हा सुरू केले.")
    else:
        await send_text_message(
            sender,
            f"❌ #{ticket} ला पाठवता आले नाही. नागरिकाने २४ तासांत संदेश पाठवलेला नसावा.",
        )
    return True


async def forward_citizen_reply(citizen: str, text: str) -> None:
    """During a handoff, pass what the citizen says straight to the owner."""
    ticket = phone_to_ticket.get(citizen, "?")
    for owner in OWNER_PHONES:
        await send_text_message(owner, f"💬 *#{ticket}* +{citizen}:\n{text}")


# ═══════════════════════════════════════════════════════════════════════════════
#  OPTION LABELS (Marathi)
# ═══════════════════════════════════════════════════════════════════════════════

OPTION_LABELS = {
    "option_1": "घंटा गाडी",
    "option_2": "पाणी",
    "option_3": "लाईट",
    "option_4": "नाली सफाई",
    "option_5": "मृत प्राणी हटवणे",
}

# Options that REQUIRE an image upload
IMAGE_REQUIRED_OPTIONS = {"option_4", "option_5"}


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGE PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

async def process_message(sender: str, message: dict):
    """
    Main message handler — processes incoming messages based on user session state.

    Flow:
        1. User sends "hi" / "hello" / "नमस्कार" → show options list
        2. User picks option 1/2/3 → acknowledge immediately
        3. User picks option 4/5 → ask for image
        4. User sends image (after picking 4/5) → acknowledge with sorry message
    """
    msg_type = message.get("type")
    session = user_sessions.get(sender, {"state": "idle"})

    # ── Owner commands: "#47 message" / "#47 done" ────────────────────────
    if sender in OWNER_PHONES and msg_type == "text":
        owner_text = message.get("text", {}).get("body", "").strip()
        reply_to = message.get("context", {}).get("id")
        if await handle_owner_command(owner_text, sender, reply_to):
            return

    # ── Handoff: owner is talking to this citizen, so the bot keeps quiet ──
    if handoff_until.get(sender, 0) > time.time():
        if msg_type == "text":
            await forward_citizen_reply(sender, message.get("text", {}).get("body", ""))
        else:
            await forward_citizen_reply(sender, f"[{msg_type} पाठवले]")
        return
    handoff_until.pop(sender, None)

    # ── Handle interactive list reply (button selection) ──────────────────
    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        interactive_type = interactive.get("type")

        if interactive_type == "list_reply":
            selected_id = interactive["list_reply"]["id"]
            option_label = OPTION_LABELS.get(selected_id, "अज्ञात")

            logger.info(f"User {sender} selected: {selected_id} ({option_label})")

            if selected_id in IMAGE_REQUIRED_OPTIONS:
                # Options 4 & 5 → ask for image
                user_sessions[sender] = {
                    "state": "awaiting_image",
                    "selected_option": selected_id,
                }
                await send_image_request(sender, option_label)
            else:
                # Options 1, 2, 3 → ask for details (awaiting_details state)
                user_sessions[sender] = {
                    "state": "awaiting_details",
                    "selected_option": selected_id,
                }
                await send_acknowledgement(sender, option_label)
            return

    # ── Handle image upload ───────────────────────────────────────────────
    if msg_type == "image" and session.get("state") == "awaiting_image":
        logger.info(f"Image received from {sender} for {session.get('selected_option')}")
        option_label = OPTION_LABELS.get(session.get("selected_option"), "अज्ञात")
        caption = message.get("image", {}).get("caption", "").strip()
        user_sessions[sender] = {"state": "idle"}
        await send_image_received_response(sender)
        await register_complaint(
            sender,
            option_label,
            f"{caption} [फोटो पाठवला]" if caption else "[फोटो पाठवला]",
        )
        return

    # ── Handle text messages ──────────────────────────────────────────────
    if msg_type == "text":
        text_body_raw = message.get("text", {}).get("body", "").strip()
        text_body = text_body_raw.lower()

        # Greetings trigger the menu
        greetings = {"hi", "hello", "hey", "नमस्कार", "नमस्ते", "हाय", "हॅलो"}
        if text_body in greetings:
            logger.info(f"Greeting received from {sender} — showing menu")
            user_sessions[sender] = {"state": "menu_shown"}
            await send_interactive_buttons(sender)
            return

        # Also handle plain-text number selection as fallback
        number_to_option = {
            "1": "option_1", "2": "option_2", "3": "option_3",
            "4": "option_4", "5": "option_5",
        }
        if text_body in number_to_option and session.get("state") == "menu_shown":
            selected_id = number_to_option[text_body]
            option_label = OPTION_LABELS[selected_id]
            logger.info(f"User {sender} typed number: {text_body} → {option_label}")

            if selected_id in IMAGE_REQUIRED_OPTIONS:
                user_sessions[sender] = {
                    "state": "awaiting_image",
                    "selected_option": selected_id,
                }
                await send_image_request(sender, option_label)
            else:
                user_sessions[sender] = {
                    "state": "awaiting_details",
                    "selected_option": selected_id,
                }
                await send_acknowledgement(sender, option_label)
            return

        # If awaiting image but user sent text instead
        if session.get("state") == "awaiting_image":
            await send_text_message(
                sender,
                "⚠️ कृपया फोटो पाठवा. तक्रार नोंदवण्यासाठी फोटो आवश्यक आहे. 📸"
            )
            return

        # Handle details being sent (Name, Address, etc.)
        if session.get("state") == "awaiting_details":
            option_label = OPTION_LABELS.get(session.get("selected_option"), "अज्ञात")
            user_sessions[sender] = {"state": "idle"}
            await send_text_message(
                sender,
                "✅ तुमची माहिती मिळाली आहे!\n\n"
                "तुमची तक्रार यशस्वीरित्या नोंदवली गेली आहे.\n\n"
                "गैरसोयीबद्दल क्षमस्व, आम्ही लवकरच याबाबत कार्यवाही करू. 🙏\n\n"
                "अधिक मदतीसाठी कृपया खालील क्रमांकावर संपर्क साधा:\n"
                "📞 *9272511811*"
            )
            await register_complaint(sender, option_label, text_body_raw)
            return

        # NEW: Only send the default greeting for unrecognized TEXT
        # (This prevents replying to Stickers, Reactions, etc.)
        await send_text_message(
            sender,
            "🙏 नमस्कार!\n\nतक्रार नोंदवण्यासाठी कृपया *hi* पाठवा. 🙏"
        )
        return

    # ── Default: Ignore other types (Stickers, Reactions, etc.) ─────────
    logger.info(f"Ignoring message of type: {msg_type}")


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta Webhook Verification Endpoint.
    When you register the webhook URL in the Meta Developer Portal,
    Meta sends a GET request with a challenge that you must echo back.
    """
    logger.info(f"Webhook verification request — mode={hub_mode}")

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        logger.info("✅ Webhook verified successfully!")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning("❌ Webhook verification failed — token mismatch")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Meta Webhook Event Receiver.
    All incoming WhatsApp messages arrive here as POST requests.
    """
    body = await request.json()
    logger.info(f"Webhook received: {body}")

    try:
        # Navigate the nested Meta webhook payload structure
        entry = body.get("entry", [])
        for e in entry:
            changes = e.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    msg_id = msg.get("id")
                    timestamp_str = msg.get("timestamp")
                    sender = msg.get("from")

                    # 1. Deduplication (Skip if already processed)
                    if msg_id in PROCESSED_MESSAGES:
                        logger.info(f"Skipping duplicate message: {msg_id}")
                        continue
                    
                    # 2. Expiry Check (Skip if message is older than 5 minutes)
                    if timestamp_str:
                        try:
                            msg_ts = int(timestamp_str)
                            now_ts = int(time.time())
                            if now_ts - msg_ts > 300: # 5 minutes
                                logger.info(f"Skipping expired message (old retry): {msg_id}")
                                continue
                        except Exception:
                            pass

                    # Mark as processed
                    PROCESSED_MESSAGES.add(msg_id)
                    
                    # Prevent memory leak by keeping only the last 1000 IDs
                    if len(PROCESSED_MESSAGES) > MAX_PROCESSED_HISTORY:
                        # Convert to list to pop first element (simple FIFO)
                        msg_list = list(PROCESSED_MESSAGES)
                        PROCESSED_MESSAGES.clear()
                        PROCESSED_MESSAGES.update(msg_list[-MAX_PROCESSED_HISTORY:])

                    logger.info(f"Processing message from {sender}: type={msg.get('type')} id={msg_id}")
                    await process_message(sender, msg)

    except Exception as exc:
        logger.exception(f"Error processing webhook: {exc}")

    # Always return 200 to Meta — otherwise they'll retry
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "running",
        "bot": "Pravin Mali Help Line",
        "phone": "+91 9272511811",
        "language": "Marathi (मराठी)",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting WhatsApp Bot Server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
