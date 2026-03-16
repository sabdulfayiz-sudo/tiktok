import logging
import sqlite3
import threading
import json
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

# NEW: Manager and Admin Settings
MANAGER_USERNAME = "@s17aj_04" # Customer will be told to DM this person
ADMIN_ID = 1322755444 # REPLACE WITH YOUR TELEGRAM ID (Only this ID can approve sales)

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
        
        c.execute('''CREATE TABLE IF NOT EXISTS purchases
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      product_name TEXT,
                      amount REAL,
                      purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES referrals(user_id))''')
        conn.commit()

def get_referrer(user_id):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT referrer_id FROM referrals WHERE user_id=?", (user_id,))
            result = c.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"DB Error: {e}")
        return None

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

def log_purchase(user_id, product, amount):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO purchases (user_id, product_name, amount) VALUES (?, ?, ?)", 
                  (user_id, product, amount))
        conn.commit()

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
    
    if args and args[0].isdigit():
        potential_referrer = int(args[0])
        if potential_referrer != user.id:
            is_new = record_referral(user.id, potential_referrer)
            if is_new:
                try:
                    await context.bot.send_message(
                        chat_id=potential_referrer, 
                        text=f"🎉 New Referral! {user.first_name} just joined via your link."
                    )
                except Exception:
                    pass

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton("🔗 Get My Referral Link", callback_data="get_link")],
        [InlineKeyboardButton("🛒 Buy Premium Plan", callback_data="buy_plan")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"Hello {user.first_name}! Welcome to the official bot.\n\n"
        "We track referrals and rewards here. "
        "Join our channel for updates or generate your own link to invite friends!"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if query.data == "get_link":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        
        # CHANGED TO HTML TO PREVENT UNDERSCORE ERRORS
        msg = (
            f"Here is your unique referral link:\n\n<code>{ref_link}</code>\n\n"
            "Share this on TikTok or Instagram. When people join via this link, "
            "we will know you sent them!"
        )
        await query.edit_message_text(text=msg, parse_mode='HTML')

    elif query.data == "buy_plan":
        # CHANGED TO HTML TO PREVENT UNDERSCORE ERRORS
        msg = (
            f"🛍️ <b>How to Purchase:</b>\n\n"
            f"Please contact our manager {MANAGER_USERNAME} to complete your payment.\n\n"
            f"⚠️ <b>Important:</b> Please send them your User ID so they can process your order and credit your referrer.\n\n"
            f"Your User ID is: <code>{user.id}</code>"
        )
        await query.edit_message_text(text=msg, parse_mode='HTML')

async def approve_sale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_user = update.effective_user
    
    if admin_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    try:
        target_user_id = int(context.args[0])
        amount = float(context.args[1])
        product = "Premium Plan"
    except (IndexError, ValueError):
        # CHANGED TO HTML TO PREVENT UNDERSCORE ERRORS
        await update.message.reply_text("❌ Usage: /approve <user_id> <amount>\nExample: <code>/approve 123456789 49.99</code>", parse_mode='HTML')
        return

    log_purchase(target_user_id, product, amount)
    referrer_id = get_referrer(target_user_id)

    response_text = f"✅ Sale approved successfully for User ID {target_user_id} (${amount}).\n"

    if referrer_id:
        response_text += f"Attribution: User was referred by {referrer_id}. They will be notified."
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"💰 Cha-ching! Your referral (User ID {target_user_id}) just made a purchase! You have earned credit for this sale."
            )
        except Exception:
            pass
    else:
        response_text += "Attribution: Organic (No referrer found)."

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="🎉 Your purchase has been approved by the manager! Thank you for your business."
        )
    except Exception:
        pass

    await update.message.reply_text(response_text)


# --- FLASK DASHBOARD LOGIC (PRO UI) ---

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <!-- Bootstrap 5 -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <style>
        :root {
            --sidebar-bg: #1a1c23;
            --main-bg: #f4f6f9;
            --card-bg: #ffffff;
            --primary: #4f46e5;
        }
        body { background-color: var(--main-bg); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        
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
        .icon-sales { background: #dcfce7; color: #10b981; }
        .icon-rate { background: #fef9c3; color: #f59e0b; }
        
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
            letter-spacing: 0.05em;
        }
        .table td { vertical-align: middle; padding: 1rem 0.75rem; }
        
        @media (max-width: 768px) {
            .stat-value { font-size: 1.5rem; }
        }
    </style>
</head>
<body>
    <nav class="navbar fixed-top">
        <div class="container-fluid">
            <div class="d-flex align-items-center">
                <span class="brand-text me-3"><i class="bi bi-robot me-2"></i>ReferralBot Admin</span>
                <span class="badge bg-success rounded-pill">Active</span>
            </div>
            
            <a href="/export" class="btn btn-success btn-sm">
                <i class="bi bi-file-earmark-excel me-2"></i>Download Report
            </a>
        </div>
    </nav>

    <div class="container" style="margin-top: 100px;">
        <div class="row g-4 mb-4">
            <div class="col-12 col-md-4">
                <div class="stat-card">
                    <div class="stat-icon icon-users"><i class="bi bi-people-fill"></i></div>
                    <div class="stat-value">{{ total_refs }}</div>
                    <div class="stat-label">Total Referrals</div>
                </div>
            </div>
            <div class="col-12 col-md-4">
                <div class="stat-card">
                    <div class="stat-icon icon-sales"><i class="bi bi-currency-dollar"></i></div>
                    <div class="stat-value">${{ total_sales }}</div>
                    <div class="stat-label">Total Revenue</div>
                </div>
            </div>
            <div class="col-12 col-md-4">
                <div class="stat-card">
                    <div class="stat-icon icon-rate"><i class="bi bi-cart-check-fill"></i></div>
                    <div class="stat-value">{{ purchase_count }}</div>
                    <div class="stat-label">Total Transactions</div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-12 col-lg-6">
                <div class="custom-card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-trophy-fill text-warning me-2"></i>Top Referrers</span>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead><tr><th>ID</th><th class="text-end">Invites</th></tr></thead>
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
            
            <div class="col-12 col-lg-6">
                <div class="custom-card h-100">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-bag-check-fill text-primary me-2"></i>Recent Sales</span>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead><tr><th>Product</th><th>Amt</th><th>Referrer</th></tr></thead>
                            <tbody>
                                {% for p in purchases %}
                                <tr>
                                    <td>{{ p[1] }}</td>
                                    <td class="text-success fw-bold">${{ p[2] }}</td>
                                    <td>
                                        {% if p[3] %}
                                            <span class="badge bg-primary rounded-pill">#{{ p[3] }}</span>
                                        {% else %}
                                            <span class="badge bg-light text-dark border">Organic</span>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% else %}
                                <tr><td colspan="3" class="text-center text-muted py-4">No sales yet</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="text-center text-muted small mt-4 mb-5">
            System Status: <span class="text-success">● Online</span> | Auto-refresh: Active (30s)
        </div>
    </div>

    <script>
        setTimeout(function(){ location.reload(); }, 30000);
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
        
        c.execute("SELECT COUNT(*) FROM purchases")
        purchase_count = c.fetchone()[0]

        c.execute("SELECT SUM(amount) FROM purchases")
        sales_res = c.fetchone()[0]
        total_sales = round(sales_res, 2) if sales_res else 0.0
        
        c.execute('''SELECT referrer_id, COUNT(user_id) as count 
                     FROM referrals 
                     GROUP BY referrer_id 
                     ORDER BY count DESC LIMIT 10''')
        top_referrers = c.fetchall()
        
        c.execute('''SELECT p.user_id, p.product_name, p.amount, r.referrer_id 
                     FROM purchases p
                     LEFT JOIN referrals r ON p.user_id = r.user_id
                     ORDER BY p.purchase_date DESC LIMIT 10''')
        purchases = c.fetchall()
    
    return render_template_string(DASHBOARD_HTML, 
                                  total_refs=total_refs, 
                                  total_sales=total_sales,
                                  purchase_count=purchase_count,
                                  top_referrers=top_referrers,
                                  purchases=purchases)

@app.route('/export')
def export_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        wb = openpyxl.Workbook()
        
        ws1 = wb.active
        ws1.title = "Referrals"
        cursor.execute("SELECT * FROM referrals")
        headers = [description[0] for description in cursor.description]
        ws1.append(headers)
        for row in cursor.fetchall():
            ws1.append(row)
            
        ws2 = wb.create_sheet(title="Purchases")
        cursor.execute("SELECT * FROM purchases")
        headers = [description[0] for description in cursor.description]
        ws2.append(headers)
        for row in cursor.fetchall():
            ws2.append(row)
            
        conn.close()
        
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'referral_report_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    except Exception as e:
        return f"Error creating export: {e}", 500

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    init_db()
    print("Database initialized.")

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Dashboard running at http://localhost:5000")

    print("Starting Telegram Bot...")
    
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    application = Application.builder().token(BOT_TOKEN).request(t_request).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("approve", approve_sale))
    application.add_error_handler(error_handler)
    
    print("Polling started. Press Ctrl+C to stop.")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to start bot polling. Error: {e}")