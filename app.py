import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, RateLimitError, ClientError, ClientForbiddenError, 
    ClientNotFoundError, ChallengeRequired, PleaseWaitFewMinutes
)

app = Flask(__name__)

# Global variables
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
START_TIME = None
CLIENT = None
SESSION_TOKEN = None
LOGIN_SUCCESS = False

STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}

BOT_CONFIG = {
    "auto_replies": {},
    "auto_reply_active": False,
    "target_spam": {},
    "spam_active": {},
    "media_library": {}
}

def uptime():
    if not START_TIME:
        return "00:00:00"
    delta = datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    if len(LOGS) > 500:
        LOGS[:] = LOGS[-500:]
    print(lm)

def clear_logs():
    global LOGS
    LOGS.clear()
    log("🧹 Logs cleared by user!")

def create_stable_client():
    cl = Client()
    cl.delay_range = [8, 15]
    cl.request_timeout = 90
    cl.max_retries = 1
    ua = "Instagram 380.0.0.28.104 Android (35/14; 600dpi; 1440x3360; samsung; SM-S936B; dm5q; exynos2500; en_IN; 380000028)"
    cl.set_user_agent(ua)
    return cl

def safe_login(cl, token, max_retries=3):
    global LOGIN_SUCCESS, SESSION_TOKEN
    for attempt in range(max_retries):
        try:
            log(f"🔐 Login attempt {attempt+1}/{max_retries}")
            cl.login_by_sessionid(token)
            account = cl.account_info()
            if account and hasattr(account, 'username') and account.username:
                username = account.username
                log(f"✅ Login SUCCESS: @{username}")
                LOGIN_SUCCESS = True
                SESSION_TOKEN = token
                time.sleep(3)
                return True, username
        except Exception as e:
            error_msg = str(e).lower()
            if "session" in error_msg or "login required" in error_msg:
                log("❌ Session expired!")
                return False, None
            elif "rate limit" in error_msg:
                log("⏳ Rate limited - 60s wait")
                time.sleep(60)
            elif "challenge" in error_msg:
                log("❌ Challenge required")
                time.sleep(30)
            else:
                log(f"⚠️ Login error: {str(e)[:50]}")
                time.sleep(15 * (attempt + 1))
    return False, None

def session_health_check():
    global CLIENT, LOGIN_SUCCESS
    try:
        if CLIENT:
            CLIENT.account_info()
            return True
    except:
        pass
    LOGIN_SUCCESS = False
    return False

def refresh_session(token):
    global CLIENT, LOGIN_SUCCESS
    log("🔄 Auto session refresh...")
    new_client = create_stable_client()
    success, _ = safe_login(new_client, token)
    if success:
        CLIENT = new_client
        return True
    return False

# ================= MAIN BOT WITH ADMIN COMMANDS =================
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global START_TIME, CLIENT, LOGIN_SUCCESS
    
    START_TIME = datetime.now()
    consecutive_errors = 0
    max_errors = 12
    
    log("🚀 Premium Bot v4.5 with ADMIN COMMANDS starting...")
    
    CLIENT = create_stable_client()
    success, username = safe_login(CLIENT, session_token)
    if not success:
        log("💥 Login failed - Bot STOPPED")
        return
    
    km = {gid: set() for gid in gids}
    lm = {gid: None for gid in gids}
    
    log("📱 Initializing groups...")
    for i, gid in enumerate(gids):
        try:
            time.sleep(10)
            thread = CLIENT.direct_thread(gid)
            km[gid] = {u.pk for u in thread.users}
            if thread.messages:
                lm[gid] = thread.messages[0].id
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {i+1}: {gid[:12]}...")
        except Exception as e:
            log(f"⚠️ Group error: {str(e)[:30]}")
    
    log("🎉 Bot running with FULL FEATURES!")
    
    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
                
            try:
                if not session_health_check():
                    if refresh_session(SESSION_TOKEN):
                        consecutive_errors = 0
                    else:
                        log("💥 Session recovery failed")
                        return
                
                time.sleep(random.uniform(12, 20))
                thread = CLIENT.direct_thread(gid)
                consecutive_errors = 0
                
                # ========== COMMANDS PROCESSING ==========
                if ecmd:
                    new_msgs = []
                    if lm[gid] and thread.messages:
                        for msg in thread.messages[:10]:
                            if msg.id == lm[gid]:
                                break
                            new_msgs.append(msg)
                    
                    for msg_obj in reversed(new_msgs[:3]):
                        try:
                            if not msg_obj or msg_obj.user_id == CLIENT.user_id:
                                continue
                                
                            sender = next((u for u in thread.users if u.pk == msg_obj.user_id), None)
                            if not sender or not hasattr(sender, 'username'):
                                continue
                                
                            text = (msg_obj.text or "").strip().lower()
                            sender_username = sender.username.lower()
                            
                            # ADMIN CHECK
                            is_admin = sender_username in [aid.lower() for aid in admin_ids] if admin_ids else False
                            
                            # ADMIN COMMANDS
                            if is_admin:
                                if text.startswith('/spam '):
                                    parts = msg_obj.text.split(" ", 2)
                                    if len(parts) == 3:
                                        BOT_CONFIG["target_spam"][gid] = {
                                            "username": parts[1].replace("@", ""),
                                            "message": parts[2]
                                        }
                                        BOT_CONFIG["spam_active"][gid] = True
                                        CLIENT.direct_send("🔥 Spam ON!", thread_ids=[gid])
                                        
                                elif text in ['/stopspam', '!stopspam']:
                                    BOT_CONFIG["spam_active"][gid] = False
                                    CLIENT.direct_send("🛑 Spam OFF!", thread_ids=[gid])
                                    
                            # PUBLIC COMMANDS
                            if text in ['/ping', '!ping']:
                                CLIENT.direct_send(f"🏓 Pong! Uptime: {uptime()}", thread_ids=[gid])
                            elif text in ['/uptime', '!uptime']:
                                CLIENT.direct_send(f"⏱️ Uptime: {uptime()}", thread_ids=[gid])
                            elif text in ['/help', '!help']:
                                help_msg = """📋 COMMANDS:
/ping - Bot status
/uptime - Running time
/help - This help

👑 ADMIN:
/spam @user message
/stopspam"""
                                CLIENT.direct_send(help_msg, thread_ids=[gid])
                        
                        except:
                            pass
                    
                    if thread.messages:
                        lm[gid] = thread.messages[0].id

                # ========== SPAM (Admin only) ==========
                if BOT_CONFIG["spam_active"].get(gid):
                    target = BOT_CONFIG["target_spam"].get(gid)
                    if target:
                        try:
                            msg = f"@{target['username']} {target['message']}"
                            CLIENT.direct_send(msg, thread_ids=[gid])
                            time.sleep(4)
                        except:
                            pass

                # ========== WELCOME NEW USERS ==========
                current_members = {u.pk for u in thread.users}
                new_users = current_members - km[gid]
                
                for user in thread.users:
                    if user.pk in new_users and hasattr(user, 'username') and user.username:
                        try:
                            welcome_msg = f"@{user.username} {wm[0]}" if ucn else wm[0]
                            CLIENT.direct_send(welcome_msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            log(f"👋 NEW: @{user.username}")
                            time.sleep(dly * 2)
                            break
                        except:
                            break
                km[gid] = current_members

            except RateLimitError:
                consecutive_errors += 1
                log("⏳ Rate limit - 2min cooldown")
                time.sleep(120)
            except Exception as e:
                consecutive_errors += 1
                log(f"⚠️ Error: {str(e)[:40]}")
                time.sleep(15)
        
        if consecutive_errors > max_errors:
            log("🔄 Emergency restart...")
            if not refresh_session(SESSION_TOKEN):
                break
        
        time.sleep(pol + random.uniform(3, 7))

    log("🛑 Bot stopped")

# ================= FLASK ROUTES =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "❌ Bot already running!"})
    
    try:
        token = request.form.get("session", "").strip()
        welcome = [x.strip() for x in request.form.get("welcome", "").splitlines() if x.strip()]
        gids = [x.strip() for x in request.form.get("group_ids", "").split(",") if x.strip()]
        admins = [x.strip() for x in request.form.get("admin_ids", "").split(",") if x.strip()]
        
        if not all([token, welcome, gids]):
            return jsonify({"message": "❌ Fill Token, Welcome & Groups!"})

        global STOP_EVENT
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(
            target=run_bot,
            args=(token, welcome, gids,
                  int(request.form.get("delay", 5)),
                  int(request.form.get("poll", 25)),
                  request.form.get("use_custom_name") == "yes",
                  request.form.get("enable_commands") == "yes",
                  admins),
            daemon=True
        )
        BOT_THREAD.start()
        log("🚀 Bot v4.5 STARTED with Admin support!")
        return jsonify({"message": "✅ Bot started! Admin commands ready!"})
    except Exception as e:
        return jsonify({"message": f"❌ Error: {str(e)}"})

@app.route("/stop", methods=["POST"])
def stop():
    global STOP_EVENT, CLIENT
    STOP_EVENT.set()
    CLIENT = None
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("🛑 Bot STOPPED!")
    return jsonify({"message": "✅ Bot stopped!"})

@app.route("/logs")
def logs():
    return jsonify({
        "logs": LOGS[-200:],
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped"
    })

@app.route("/clear_logs", methods=["POST"])
def clear_logs_route():
    clear_logs()
    return jsonify({"message": "✅ Logs cleared!"})

@app.route("/stats")
def stats():
    return jsonify({
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped",
        "total_welcomed": STATS["total_welcomed"],
        "today_welcomed": STATS["today_welcomed"]
    })

# ================= COMPLETE HTML WITH ADMIN FIELD =================
PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Premium Instagram Bot v4.5 - Admin Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;padding:20px;color:#333;}
        .container{max-width:1000px;margin:0 auto;background:white;border-radius:20px;box-shadow:0 25px 50px rgba(0,0,0,0.15);overflow:hidden;}
        .header{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;padding:35px;text-align:center;}
        .header h1{font-size:2.8rem;margin-bottom:10px;}
        .status-bar{display:flex;justify-content:space-between;align-items:center;padding:25px 35px;background:#f8fafc;border-bottom:2px solid #e2e8f0;}
        .status-item{display:flex;align-items:center;gap:12px;font-weight:600;}
        .status-running{color:#10b981;}.status-stopped{color:#ef4444;}
        .status-dot{width:14px;height:14px;border-radius:50%;background:#10b981;animation:pulse 2s infinite;}
        @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}
        .content{padding:35px;}
        .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-bottom:30px;}
        .form-group{position:relative;}
        .form-group.full{grid-column:1/-1;}
        label{display:block;margin-bottom:10px;font-weight:600;color:#374151;font-size:1rem;}
        input,textarea{width:100%;padding:16px 18px;border:2px solid #e5e7eb;border-radius:14px;font-size:1rem;background:white;transition:all 0.3s;box-shadow:0 2px 8px rgba(0,0,0,0.05);}
        input:focus,textarea:focus{outline:none;border-color:#4f46e5;box-shadow:0 0 0 4px rgba(79,70,229,0.1);}
        textarea{resize:vertical;min-height:140px;}
        .admin-section{background:#fef3c7;border:2px solid #f59e0b;border-radius:16px;padding:25px;margin-bottom:30px;}
        .checkbox-group{display:flex;align-items:center;gap:15px;padding:20px;background:#f8fafc;border:2px solid #e5e7eb;border-radius:14px;cursor:pointer;transition:all 0.3s;}
        .checkbox-group:hover{border-color:#4f46e5;transform:translateY(-2px);}
        .controls{display:flex;gap:20px;justify-content:center;margin:50px 0;flex-wrap:wrap;}
        .btn{padding:18px 40px;border:none;border-radius:16px;font-size:1.15rem;font-weight:600;cursor:pointer;transition:all 0.3s;display:flex;align-items:center;gap:12px;}
        .btn-start{background:linear-gradient(135deg,#10b981,#059669);color:white;box-shadow:0 10px 25px rgba(16,185,129,0.4);}
        .btn-stop{background:linear-gradient(135deg,#ef4444,#dc2626);color:white;box-shadow:0 10px 25px rgba(239,68,68,0.4);}
        .btn-clear{background:linear-gradient(135deg,#6b7280,#4b5563);color:white;box-shadow:0 10px 25px rgba(107,114,128,0.4);}
        .btn:hover{transform:translateY(-3px);box-shadow:0 15px 35px rgba(0,0,0,0.3);}
        .logs-container{background:#1e293b;border-radius:20px;padding:30px;margin-top:30px;}
        #logs{background:#0f172a;color:#e2e8f0;border-radius:16px;padding:25px;height:380px;overflow-y:auto;font-family:monospace;font-size:0.95rem;line-height:1.6;white-space:pre-wrap;border:1px solid #475569;}
        .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:25px;margin-bottom:30px;}
        .stat-card{background:#f8fafc;padding:30px;border-radius:16px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.1);transition:all 0.3s;}
        .stat-number{font-size:3rem;font-weight:700;color:#4f46e5;margin-bottom:10px;}
        @media(max-width:768px){.form-grid{grid-template-columns:1fr;}.controls{flex-direction:column;}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-robot"></i> Premium Bot v4.5</h1>
            <p>✅ Admin Panel • Commands • Anti-Logout • Render Ready</p>
        </div>

        <div class="status-bar status-stopped" id="statusBar">
            <div class="status-item">
                <div class="status-dot"></div>
                <span>Status: Stopped</span>
            </div>
            <div class="status-item">
                <span id="uptime">00:00:00</span>
            </div>
        </div>

        <div class="content">
            <div class="stats-grid" id="statsGrid" style="display:none;">
                <div class="stat-card">
                    <div class="stat-number" id="totalWelcomed">0</div>
                    <div>Total Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="todayWelcomed">0</div>
                    <div>Today Welcomed</div>
                </div>
            </div>

            <form id="botForm">
                <div class="form-grid">
                    <div class="form-group">
                        <label><i class="fas fa-key"></i> Session Token <span style="color:#ef4444">*</span></label>
                        <input type="password" name="session" placeholder="Fresh session token" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-hashtag"></i> Group IDs <span style="color:#ef4444">*</span></label>
                        <input type="text" name="group_ids" placeholder="1234567890,0987654321" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-users-crown"></i> Admin IDs</label>
                        <input type="text" name="admin_ids" placeholder="admin1,admin2,you">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-clock"></i> Welcome Delay (sec)</label>
                        <input type="number" name="delay" value="5" min="3" max="15">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-sync"></i> Poll Interval <span style="color:#f59e0b">(25s recommended)</span></label>
                        <input type="number" name="poll" value="25" min="20" max="45">
                    </div>
                    <div class="form-group full">
                        <label><i class="fas fa-comment-dots"></i> Welcome Messages <span style="color:#ef4444">*</span></label>
                        <textarea name="welcome">Welcome bro! 🔥
Have fun! 🎉
Enjoy group! 😊
Follow rules! 👮</textarea>
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-bottom:35px;">
                    <div class="checkbox-group" onclick="toggleCheckbox('use_custom_name')">
                        <input type="checkbox" id="use_custom_name" name="use_custom_name" value="yes" checked>
                        <label for="use_custom_name" style="cursor:pointer;flex:1;margin:0;font-weight:600;">
                            <i class="fas fa-user-tag"></i> Mention @username
                        </label>
                    </div>
                    <div class="checkbox-group" onclick="toggleCheckbox('enable_commands')">
                        <input type="checkbox" id="enable_commands" name="enable_commands" value="yes" checked>
                        <label for="enable_commands" style="cursor:pointer;flex:1;margin:0;font-weight:600;">
                            <i class="fas fa-terminal"></i> Enable Commands
                        </label>
                    </div>
                </div>

                <div class="admin-section">
                    <h3 style="color:#b45309;margin-bottom:15px;"><i class="fas fa-crown"></i> 👑 Admin Commands</h3>
                    <div style="font-size:0.95rem;color:#92400e;line-height:1.6;">
                        <strong>/spam @user message</strong> - Spam user<br>
                        <strong>/stopspam</strong> - Stop spam<br>
                        <strong>/ping, /uptime, /help</strong> - Public commands
                    </div>
                </div>

                <div class="controls">
                    <button type="button" class="btn btn-start" onclick="startBot()">
                        <i class="fas fa-play"></i> Start Bot
                    </button>
                    <button type="button" class="btn btn-stop" onclick="stopBot()">
                        <i class="fas fa-stop"></i> Stop Bot
                    </button>
                    <button type="button" class="btn btn-clear" onclick="clearLogs()">
                        <i class="fas fa-trash"></i> Clear Logs
                    </button>
                </div>
            </form>

            <div class="logs-container">
                <div style="display:flex;justify-content:space-between;align-items:center;color:white;margin-bottom:20px;font-weight:600;">
                    <div><i class="fas fa-list"></i> Live Logs</div>
                    <button onclick="clearLogs()" style="background:#6b7280;color:white;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-weight:600;">Clear</button>
                </div>
                <div id="logs">🚀 Premium Bot v4.5 ready! Admin features enabled ✅</div>
            </div>
        </div>
    </div>

    <script>
        function toggleCheckbox(id) {
            document.getElementById(id).click();
        }
        
        async function startBot() {
            try {
                const formData = new FormData(document.getElementById('botForm'));
                const response = await fetch('/start', {method: 'POST', body: formData});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/stop', {method: 'POST'});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function clearLogs() {
            try {
                await fetch('/clear_logs', {method: 'POST'});
                document.getElementById('logs').textContent = '🧹 Logs cleared!';
            } catch (error) {}
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                document.getElementById('uptime').textContent = data.uptime;
                
                const statusBar = document.getElementById('statusBar');
                const statusDot = statusBar.querySelector('.status-dot');
                const statusText = statusBar.querySelector('span');
                
                if (data.status === 'running') {
                    statusBar.className = 'status-bar status-running';
                    statusDot.style.background = '#10b981';
                    statusText.textContent = 'Status: Running';
                    document.getElementById('statsGrid').style.display = 'grid';
                    document.getElementById('totalWelcomed').textContent = data.total_welcomed;
                    document.getElementById('todayWelcomed').textContent = data.today_welcomed;
                } else {
                    statusBar.className = 'status-bar status-stopped';
                    statusDot.style.background = '#ef4444';
                    statusText.textContent = 'Status: Stopped';
                    document.getElementById('statsGrid').style.display = 'none';
                }
            } catch (error) {}
        }
        
        async function updateLogs() {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                logsDiv.textContent = data.logs.join('\
');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch (error) {}
        }
        
        setInterval(() => {
            updateStatus();
            updateLogs();
        }, 3000);
        
        updateStatus();
        updateLogs();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log("🌟 Premium Instagram Bot v4.5 - COMPLETE!")
    log("✅ Admin IDs field ADDED!")
    log("✅ Commands 100% WORKING!")
    log("✅ Render.com ready - Copy paste karo!")
    app.run(host="0.0.0.0", port=port, debug=False)
