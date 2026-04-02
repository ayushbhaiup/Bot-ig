import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []

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

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵","🎶","🎸","🎹","🎤","🎧"]
FUNNY = ["Hahaha 😂","LOL 😂","Mast 😆","Pagal 🤪","King 👑😂"]
MASTI = ["Party 🎉","Masti 🥳","Dhamaal 💃","Full ON 🔥","Enjoy 🎊"]

# ================= BOT ================= (same as before - no changes)
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        cl.login_by_sessionid(session_token)
        me = cl.account_info().username
        log(f"Session login success: @{me}")
    except Exception as e:
        log("Session login failed: " + str(e))
        return

    km = {}
    lm = {}

    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group ready: " + gid)
        except:
            km[gid] = set()
            lm[gid] = None

    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
            try:
                g = cl.direct_thread(gid)

                if BOT_CONFIG["spam_active"].get(gid):
                    t = BOT_CONFIG["target_spam"].get(gid)
                    if t:
                        cl.direct_send(
                            "@" + t["username"] + " " + t["message"],
                            thread_ids=[gid]
                        )
                        log("Spam sent")
                        time.sleep(2)

                if ecmd or BOT_CONFIG["auto_reply_active"]:
                    new_msgs = []
                    if lm[gid]:
                        for m in g.messages:
                            if m.id == lm[gid]:
                                break
                            new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == cl.user_id:
                            continue

                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        su = sender.username.lower()
                        ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                        t = (m.text or "").strip()
                        tl = t.lower()

                        if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                            cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])

                        if not ecmd:
                            continue

                        if tl in ["/help","!help"]:
                            cl.direct_send(
                                "COMMANDS:"
                                "/help /ping /time /about"
                                "/stats /count /welcome"
                                "/autoreply key msg/stopreply"
                                "/music /funny /masti"
                                "/spam @user msg/stopspam",
                                thread_ids=[gid]
                            )

                        elif tl in ["/ping","!ping"]:
                            cl.direct_send("Pong! ✅", thread_ids=[gid])

                        elif tl in ["/time","!time"]:
                            cl.direct_send(datetime.now().strftime("%I:%M %p"), thread_ids=[gid])

                        elif tl in ["/about","!about"]:
                            cl.direct_send("Instagram Premium Bot v4.0 (SESSION)", thread_ids=[gid])

                        elif tl.startswith("/autoreply "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                BOT_CONFIG["auto_reply_active"] = True

                        elif tl in ["/stopreply","!stopreply"]:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}

                        elif tl in ["/music","!music"]:
                            cl.direct_send(" ".join(random.choices(MUSIC_EMOJIS,k=5)), thread_ids=[gid])

                        elif tl in ["/funny","!funny"]:
                            cl.direct_send(random.choice(FUNNY), thread_ids=[gid])

                        elif tl in ["/masti","!masti"]:
                            cl.direct_send(random.choice(MASTI), thread_ids=[gid])

                        elif ia and tl.startswith("/spam "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["target_spam"][gid] = {
                                    "username": p[1].replace("@",""),
                                    "message": p[2]
                                }
                                BOT_CONFIG["spam_active"][gid] = True

                        elif ia and tl in ["/stopspam","!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False

                    if g.messages:
                        lm[gid] = g.messages[0].id

                cm = {u.pk for u in g.users}
                new_users = cm - km[gid]

                for u in g.users:
                    if u.pk in new_users:
                        for msg in wm:
                            final = f"@{u.username} {msg}" if ucn else msg
                            cl.direct_send(final, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            time.sleep(dly)

                km[gid] = cm

            except:
                pass

        time.sleep(pol)

    log("BOT STOPPED")

# ================= FLASK ================= (same as before)
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message":"Already running"})

    token = request.form.get("session")
    welcome = [x.strip() for x in request.form.get("welcome","").splitlines() if x.strip()]
    gids = [x.strip() for x in request.form.get("group_ids","").split(",") if x.strip()]
    admins = [x.strip() for x in request.form.get("admin_ids","").split(",") if x.strip()]

    if not token or not welcome or not gids:
        return jsonify({"message":"Fill all fields"})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            token,
            welcome,
            gids,
            int(request.form.get("delay",3)),
            int(request.form.get("poll",5)),
            request.form.get("use_custom_name")=="yes",
            request.form.get("enable_commands")=="yes",
            admins
        ),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message":"Started!"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    return jsonify({"message":"Stopped!"})

@app.route("/logs")
def logs():
    return jsonify({"logs": LOGS[-200:]})

# ================= ULTIMATE PREMIUM LIGHT UI =================
PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Premium Instagram Bot</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #f59e0b;
            --accent: #10b981;
            --glass-bg: rgba(255, 255, 255, 0.95);
            --glass-dark: rgba(255, 255, 255, 0.85);
            --border-light: rgba(0, 0, 0, 0.08);
            --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
            --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
            --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
            --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
            --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --gradient-success: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #cbd5e1 100%);
            color: #1e293b;
            position: relative;
            overflow-x: hidden;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: 
                radial-gradient(circle at 15% 25%, rgba(99, 102, 241, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 85% 75%, rgba(245, 158, 11, 0.06) 0%, transparent 50%),
                radial-gradient(circle at 50% 10%, rgba(16, 185, 129, 0.05) 0%, transparent 50%);
            z-index: -1;
            animation: shimmer 15s ease-in-out infinite;
        }

        @keyframes shimmer {
            0%, 100% { opacity: 0.8; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.02); }
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem 1rem;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            gap: 2.5rem;
        }

        .glass-card {
            background: var(--glass-bg);
            backdrop-filter: blur(25px);
            border: 1px solid var(--border-light);
            border-radius: 28px;
            padding: 3rem;
            box-shadow: var(--shadow-xl);
            position: relative;
            overflow: hidden;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .glass-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25);
        }

        .glass-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: var(--gradient-primary);
            opacity: 0.8;
        }

        .header {
            text-align: center;
            margin-bottom: 2.5rem;
            position: relative;
        }

        .logo {
            font-size: clamp(3rem, 6vw, 4.5rem);
            font-weight: 800;
            background: var(--gradient-primary);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.75rem;
            letter-spacing: -0.025em;
            position: relative;
        }

        .logo::after {
            content: '';
            position: absolute;
            bottom: -10px;
            left: 50%;
            transform: translateX(-50%);
            width: 80px;
            height: 4px;
            background: var(--gradient-primary);
            border-radius: 2px;
        }

        .subtitle {
            color: #64748b;
            font-size: 1.25rem;
            font-weight: 400;
            letter-spacing: -0.025em;
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1.5rem;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 50px;
            font-size: 0.95rem;
            font-weight: 500;
            margin-top: 1rem;
            color: #059669;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s infinite;
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 1);
        }

        @keyframes pulse {
            0% { 
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            }
            70% {
                box-shadow: 0 0 0 10px rgba(16, 185, 129, 0);
            }
            100% {
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
            }
        }

        .form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 2rem;
            margin-bottom: 3rem;
        }

        .form-group {
            position: relative;
        }

        .form-group.full-width {
            grid-column: 1 / -1;
        }

        label {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            font-size: 0.95rem;
            font-weight: 600;
            color: #374151;
            letter-spacing: 0.025em;
            text-transform: uppercase;
        }

        .input-wrapper {
            position: relative;
        }

        input, textarea, select {
            width: 100%;
            padding: 1.25rem 1.5rem;
            background: rgba(255, 255, 255, 0.7);
            border: 2px solid rgba(0, 0, 0, 0.05);
            border-radius: 20px;
            color: #1e293b;
            font-size: 1rem;
            font-weight: 500;
            font-family: inherit;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            backdrop-filter: blur(15px);
        }

        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            background: rgba(255, 255, 255, 0.95);
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
            transform: translateY(-2px);
        }

        input::placeholder, textarea::placeholder {
            color: #9ca3af;
        }

        textarea {
            resize: vertical;
            min-height: 140px;
            font-family: 'Poppins', sans-serif;
            line-height: 1.6;
        }

        .btn-group {
            display: flex;
            gap: 1.5rem;
            justify-content: center;
            margin-top: 2.5rem;
        }

        .btn {
            padding: 1.25rem 3rem;
            border: none;
            border-radius: 24px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            text-transform: uppercase;
            letter-spacing: 1px;
            position: relative;
            overflow: hidden;
            min-width: 160px;
            font-family: inherit;
            box-shadow: var(--shadow-lg);
        }

        .btn-start {
            background: var(--gradient-success);
            color: white;
        }

        .btn-stop {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-4px) scale(1.02);
            box-shadow: var(--shadow-xl);
        }

        .btn:active {
            transform: translateY(-2px) scale(1);
        }

        .logs-container {
            height: 350px;
            overflow-y: auto;
            background: rgba(255, 255, 255, 0.6);
            border-radius: 20px;
            padding: 2rem;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.9rem;
            line-height: 1.7;
            border: 2px solid rgba(0, 0, 0, 0.05);
            backdrop-filter: blur(20px);
            box-shadow: var(--shadow-lg);
            position: relative;
        }

        .logs-container::-webkit-scrollbar {
            width: 8px;
        }

        .logs-container::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.02);
            border-radius: 4px;
        }

        .logs-container::-webkit-scrollbar-thumb {
            background: rgba(99, 102, 241, 0.3);
            border-radius: 4px;
        }

        .logs-container::-webkit-scrollbar-thumb:hover {
            background: rgba(99, 102, 241, 0.5);
        }

        @media (max-width: 768px) {
            .container {
                padding: 1.5rem 1rem;
            }
            
            .glass-card {
                padding: 2rem 1.5rem;
                border-radius: 24px;
            }
            
            .form-grid {
                grid-template-columns: 1fr;
                gap: 1.5rem;
            }
            
            .btn-group {
                flex-direction: column;
                gap: 1rem;
            }
            
            .btn {
                padding: 1.25rem 2rem;
            }
        }

        /* Loading animation */
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="glass-card">
            <div class="header">
                <h1 class="logo">✨ PREMIUM BOT</h1>
                <p class="subtitle">Instagram Direct Messenger • Professional Edition</p>
                <div class="status-indicator">
                    <div class="status-dot"></div>
                    <span>Ready for deployment</span>
                </div>
            </div>

            <form id="botForm">
                <div class="form-grid">
                    <div class="form-group">
                        <label><i class="fas fa-key text-blue-600"></i> Session Token</label>
                        <input type="password" name="session" placeholder="Enter your Instagram session token" required>
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-users text-amber-500"></i> Admin Usernames</label>
                        <input type="text" name="admin_ids" placeholder="username1,username2,username3">
                    </div>

                    <div class="form-group full-width">
                        <label><i class="fas fa-comment-dots text-green-500"></i> Welcome Messages</label>
                        <textarea name="welcome" placeholder="🌟 Welcome to our group @{username}!&#10;🎉 Have fun & stay active!&#10;💎 Enjoy premium experience!&#10;🔥 Let's grow together!"></textarea>
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-at text-purple-500"></i> Mention Users</label>
                        <select name="use_custom_name">
                            <option value="yes">✅ Yes</option>
                            <option value="no">❌ No</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-robot text-indigo-500"></i> Bot Commands</label>
                        <select name="enable_commands">
                            <option value="yes">✅ Enabled</option>
                            <option value="no">❌ Disabled</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-hashtag text-pink-500"></i> Group IDs</label>
                        <input type="text" name="group_ids" placeholder="123456789,987654321,111222333" required>
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-clock text-orange-500"></i> Delay (seconds)</label>
                        <input type="number" name="delay" value="3" min="1" max="10">
                    </div>

                    <div class="form-group">
                        <label><i class="fas fa-sync-alt text-teal-500"></i> Poll Rate (seconds)</label>
                        <input type="number" name="poll" value="5" min="1" max="30">
                    </div>
                </div>

                <div class="btn-group">
                    <button type="button" class="btn btn-start" onclick="startBot()">
                        <i class="fas fa-play mr-2"></i>🚀 Deploy Bot
                    </button>
                    <button type="button" class="btn btn-stop" onclick="stopBot()">
                        <i class="fas fa-stop mr-2"></i>🛑 Stop Bot
                    </button>
                </div>
            </form>

            <div class="logs-container" id="logs">
                <div style="color: #94a3b8; text-align: center; padding: 3rem 1rem; font-weight: 500;">
                    📊 Real-time logs will appear here automatically<br>
                    <small style="opacity: 0.7;">Refresh rate: 2 seconds</small>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function startBot() {
            const btn = event.target;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Deploying...';
            btn.disabled = true;
            
            try {
                const formData = new FormData(document.getElementById('botForm'));
                const response = await fetch('/start', { method: 'POST', body: formData });
                const data = await response.json();
                alert('✅ ' + data.message);
            } catch (error) {
                alert('❌ ' + error.message);
            } finally {
                btn.innerHTML = '<i class="fas fa-play mr-2"></i>🚀 Deploy Bot';
                btn.disabled = false;
            }
        }

        async function stopBot() {
            const btn = event.target;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Stopping...';
            btn.disabled = true;
            
            try {
                const response = await fetch('/stop', { method: 'POST' });
                const data = await response.json();
                alert('🛑 ' + data.message);
            } catch (error) {
                alert('❌ ' + error.message);
            } finally {
                btn.innerHTML = '<i class="fas fa-stop mr-2"></i>🛑 Stop Bot';
                btn.disabled = false;
            }
        }

        // Auto-refresh logs with smooth animation
        setInterval(async () => {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsEl = document.getElementById('logs');
                const newLogs = data.logs.slice(-50).join('\');
                
                if (newLogs && logsEl.children.length === 1) {
                    logsEl.innerHTML = '';
                }
                
                logsEl.textContent = newLogs || 'No logs yet...';
                logsEl.scrollTop = logsEl.scrollHeight;
            } catch (error) {
                document.getElementById('logs').textContent = '⚠️ Connection error - retrying...';
            }
        }, 2000);

        // Auto-scroll logs
        const logsEl = document.getElementById('logs');
        logsEl.addEventListener('scroll', function() {
            if (logsEl.scrollTop + logsEl.clientHeight >= logsEl.scrollHeight - 10) {
                // Auto-scroll if near bottom
                setTimeout(() => logsEl.scrollTop = logsEl.scrollHeight, 100);
            }
        });
    </script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
