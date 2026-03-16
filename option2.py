import logging
import sqlite3
import threading
import io
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest
from flask import Flask, render_template_string, send_file
import openpyxl

# --- CONFIGURATION ---
# REPLACE THIS WITH YOUR ACTUAL BOT TOKEN FROM @BotFather
BOT_TOKEN = "6214348776:AAEa4xHl0jP_pNNoA45EYi-4KyJh7rLDPf0" 
CHANNEL_USERNAME = "@testchannel123494" 

# --- DATABASE SETUP ---
DB_NAME = "referrals.db"

def init_db():
    """Initialize the SQLite database with necessary tables."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS referrals
                     (user_id INTEGER PRIMARY KEY, 
                      referrer_id INTEGER, 
                      join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()

def record_referral(user_id, referrer_id):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO referrals (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"DB Error: {e}")
        return False

# --- TELEGRAM BOT LOGIC ---

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    # Check if user was referred by someone
    if args and args[0].isdigit():
        potential_referrer = int(args[0])
        if potential_referrer != user.id:
            is_new = record_referral(user.id, potential_referrer)
            if is_new:
                try:
                    # Fetch the referrer's name for a warmer welcome
                    referrer_chat = await context.bot.get_chat(potential_referrer)
                    ref_name = referrer_chat.first_name if referrer_chat.first_name else "a friend"
                    
                    # Notify the new user explicitly about who invited them
                    await update.message.reply_text(f"🤝 <b>Welcome! You were invited by {ref_name}.</b>", parse_mode='HTML')
                    
                    # Notify the referrer
                    await context.bot.send_message(
                        chat_id=potential_referrer, 
                        text=f"🎉 <b>New Referral!</b> {user.first_name} just joined via your link.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Failed to send referral notifications: {e}")

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton("🔗 Get My Referral Link", callback_data="get_link"),
         InlineKeyboardButton("📊 My Stats", callback_data="my_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"Hello {user.first_name}! Welcome to the community.\n\n"
        "Generate your own link to invite friends and track your referral stats below!"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to check personal stats via /stats"""
    await send_stats(update.message.reply_text, update.effective_user, context)

async def send_stats(reply_method, user, context):
    """Helper function to fetch and send stats"""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user.id,))
        total_invites = c.fetchone()[0]
        
    bot_username = context.bot.username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"
    
    stats_msg = (
        f"📊 <b>Your Referral Dashboard</b>\n\n"
        f"👥 <b>Total Users Invited:</b> {total_invites}\n\n"
        f"🔗 <b>Your Invite Link:</b>\n<code>{ref_link}</code>"
    )
    await reply_method(text=stats_msg, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    await query.answer()

    if data == "get_link":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        
        msg = (
            f"Here is your unique referral link:\n\n<code>{ref_link}</code>\n\n"
            "Share this on TikTok or Instagram. When people join via this link, "
            "you'll see them in your stats!"
        )
        await query.edit_message_text(text=msg, parse_mode='HTML')

    elif data == "my_stats":
        await send_stats(query.edit_message_text, user, context)


# --- FLASK DASHBOARD LOGIC (PRO UI) ---

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        :root {
            --sidebar-bg: #1a1c23;
            --main-bg: #f4f6f9;
            --card-bg: #ffffff;
            --primary: #4f46e5;
        }
        body { background-color: var(--main-bg); font-family: 'Segoe UI', sans-serif; }
        .navbar { background: var(--card-bg); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 1rem; }
        .brand-text { font-weight: 700; color: var(--primary); font-size: 1.25rem; }
        .stat-card {
            background: var(--card-bg);
            border: none;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: transform 0.2s;
            height: 100%;
        }
        .stat-card:hover { transform: translateY(-3px); }
        .stat-icon {
            width: 48px; height: 48px;
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.5rem; margin-bottom: 1rem;
        }
        .icon-users { background: #e0e7ff; color: var(--primary); }
        .stat-value { font-size: 2rem; font-weight: 700; color: #111827; }
        .stat-label { color: #6b7280; font-weight: 500; font-size: 0.9rem; }
        .custom-card {
            background: var(--card-bg);
            border: none;
            border-radius: 12px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            overflow: hidden;
            margin-bottom: 1.5rem;
        }
        .card-header {
            background: transparent;
            border-bottom: 1px solid #f3f4f6;
            padding: 1.25rem;
            font-weight: 600;
            color: #374151;
        }
        .table thead th {
            border-bottom: 2px solid #f3f4f6;
            color: #6b7280;
            font-size: 0.85rem;
            text-transform: uppercase;
        }
    </style>
</head>
<body>
    <nav class="navbar fixed-top">
        <div class="container-fluid">
            <div class="d-flex align-items-center">
                <span class="brand-text me-3"><i class="bi bi-people me-2"></i>Referral Tracker</span>
                <span class="badge bg-success rounded-pill">Active</span>
            </div>
            <a href="/export" class="btn btn-success btn-sm">
                <i class="bi bi-file-earmark-excel me-2"></i>Export Excel
            </a>
        </div>
    </nav>

    <div class="container" style="margin-top: 100px;">
        <div class="row g-4 mb-4">
            <div class="col-12 col-md-6">
                <div class="stat-card">
                    <div class="stat-icon icon-users"><i class="bi bi-person-plus-fill"></i></div>
                    <div class="stat-value">{{ total_refs }}</div>
                    <div class="stat-label">Total Users in Database</div>
                </div>
            </div>
            <div class="col-12 col-md-6">
                <div class="stat-card">
                    <div class="stat-icon icon-users" style="background:#fef9c3; color:#f59e0b;"><i class="bi bi-diagram-3-fill"></i></div>
                    <div class="stat-value">{{ referral_count }}</div>
                    <div class="stat-label">Total Successful Invites</div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-12">
                <div class="custom-card">
                    <div class="card-header">
                        <span><i class="bi bi-trophy-fill text-warning me-2"></i>Top 10 Referrers</span>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead><tr><th>User ID</th><th class="text-end">Total Invitations</th></tr></thead>
                            <tbody>
                                {% for row in top_referrers %}
                                <tr>
                                    <td><span class="badge bg-secondary bg-opacity-10 text-secondary rounded-pill">#{{ row[0] }}</span></td>
                                    <td class="text-end fw-bold">{{ row[1] }}</td>
                                </tr>
                                {% else %}
                                <tr><td colspan="2" class="text-center text-muted py-4">No data yet</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        setTimeout(function(){ location.reload(); }, 60000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM referrals")
        total_refs = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id IS NOT NULL")
        referral_count = c.fetchone()[0]
        
        c.execute('''SELECT referrer_id, COUNT(user_id) as count 
                     FROM referrals 
                     WHERE referrer_id IS NOT NULL
                     GROUP BY referrer_id 
                     ORDER BY count DESC LIMIT 10''')
        top_referrers = c.fetchall()
    
    return render_template_string(DASHBOARD_HTML, 
                                  total_refs=total_refs, 
                                  referral_count=referral_count,
                                  top_referrers=top_referrers)

@app.route('/export')
def export_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Referrals"
        cursor.execute("SELECT * FROM referrals")
        headers = [description[0] for description in cursor.description]
        ws.append(headers)
        for row in cursor.fetchall():
            ws.append(row)
        conn.close()
        
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='referral_report.xlsx')
    except Exception as e:
        return f"Error: {e}", 500

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    init_db()
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = Application.builder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=60, read_timeout=60)).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", my_stats_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)