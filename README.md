# 🏛️ Pravin Mali Help Line

A WhatsApp chatbot for municipal complaint management built with **Python** and **FastAPI**.

**Phone:** +918788450489  
**Language:** Marathi (मराठी)

---

## 🔄 Bot Conversation Flow

```
User sends "hi" / "hello" / "नमस्कार"
        │
        ▼
┌───────────────────────────────┐
│   Select complaint type:      │
│   1. 🚛 घंटा गाडी             │
│   2. 💧 पाणी                   │
│   3. 💡 लाईट                   │
│   4. 🧹 नाली सफाई              │
│   5. 🐾 मृत प्राणी हटवणे       │
└───────────────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
Options    Options
 1,2,3      4,5
   │         │
   ▼         ▼
 ✅ Ack    📸 Ask for
 message    image
              │
              ▼
         User uploads
           photo
              │
              ▼
         ✅ "Sorry for
         inconvenience"
         + contact number
```

---

## 🛠️ Setup Instructions

### Step 1: Meta Developer Account Setup

1. Go to [Meta for Developers](https://developers.facebook.com)
2. Create a new App → Select **Business** type
3. Add **WhatsApp** product to your app
4. In **WhatsApp → API Setup**:
   - Note down your **Phone Number ID**
   - Generate a **Permanent Access Token**
   - Add your phone number `+918788450489` as a sender

### Step 2: Project Setup

```bash
# Navigate to the project folder
cd "/Users/pravinjadhav/Desktop/Pravin/OWN BOT"

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Edit the `.env` file with your actual credentials:

```env
WHATSAPP_TOKEN=your_actual_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
VERIFY_TOKEN=my_secret_verify_token_123
```

> **Note:** `VERIFY_TOKEN` can be any string you choose — you'll use the same value when registering the webhook in Meta Developer Portal.

### Step 4: Run the Server

```bash
python main.py
```

The server will start at `http://localhost:8000`

### Step 5: Expose Your Server (for development)

Since Meta needs a public HTTPS URL, use **ngrok**:

```bash
# Install ngrok (if not installed)
brew install ngrok

# Expose your local server
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL.

### Step 6: Register Webhook in Meta Developer Portal

1. Go to **WhatsApp → Configuration** in your Meta app
2. Set **Callback URL** to: `https://your-ngrok-url.ngrok-free.app/webhook`
3. Set **Verify Token** to the same value as `VERIFY_TOKEN` in your `.env`
4. Subscribe to these webhook fields:
   - `messages`

---

## 📁 Project Structure

```
OWN BOT/
├── main.py              # FastAPI application (bot logic)
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (DO NOT COMMIT)
├── .env.example         # Template for environment variables
├── README.md            # This file
└── venv/                # Python virtual environment
```

---

## 🔌 API Endpoints

| Method | Path       | Description                        |
|--------|------------|------------------------------------|
| GET    | `/`        | Health check                       |
| GET    | `/webhook` | Meta webhook verification          |
| POST   | `/webhook` | Receive incoming WhatsApp messages  |

---

## 📞 Support Contact

For any issues: **7620391327**
