"""
WhatsApp Bot - Pravin Mali Help Line
Built with FastAPI + Meta WhatsApp Business Cloud API
Phone: +1 555 634 7743
Language: Marathi
"""

import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
import httpx

# ─── Load Environment ────────────────────────────────────────────────────────
load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

WHATSAPP_API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ─── In-memory session store ─────────────────────────────────────────────────
# Tracks which user is at which step in the conversation flow
# Key: phone number, Value: dict with "state" and optional "selected_option"
user_sessions: dict[str, dict] = {}

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
    async with httpx.AsyncClient() as client:
        resp = await client.post(WHATSAPP_API_URL, headers=headers, json=payload)
        logger.info(f"Text message sent to {to} — Status: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"Error response: {resp.text}")
        return resp


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
                "text": "📞 मदतीसाठी संपर्क: 9277115511"
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
        "गैरसोयीबद्दल क्षमस्व. 🙏\n\n"
        "अधिक मदतीसाठी संपर्क:\n"
        "📞 *9277115511*"
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
        user_sessions[sender] = {"state": "idle"}
        await send_image_received_response(sender)
        return

    # ── Handle text messages ──────────────────────────────────────────────
    if msg_type == "text":
        text_body = message.get("text", {}).get("body", "").strip().lower()

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
            user_sessions[sender] = {"state": "idle"}
            await send_text_message(
                sender,
                "✅ तुमची माहिती मिळाली आहे!\n\n"
                "तुमची तक्रार यशस्वीरित्या नोंदवली गेली आहे.\n\n"
                "गैरसोयीबद्दल क्षमस्व, आम्ही लवकरच याबाबत कार्यवाही करू. 🙏\n\n"
                "अधिक मदतीसाठी कृपया खालील क्रमांकावर संपर्क साधा:\n"
                "📞 *9272511811*"
            )
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
                    sender = msg.get("from")  # sender's phone number
                    logger.info(f"Processing message from {sender}: type={msg.get('type')}")
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
        "phone": "+1 555 634 7743",
        "language": "Marathi (मराठी)",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting WhatsApp Bot Server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
