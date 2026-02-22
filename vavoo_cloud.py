from flask import Flask, Response, jsonify, request
import requests
import threading
from datetime import datetime, timedelta

app = Flask(__name__)

VAVOO_TOKEN = "tosFwQCJMS8qrW_AjLoHPQ41646J5dRNha6ZWHnijoYQQQoADQoXYSo7ki7O5-CsgN4CH0uRk6EEoJ0728ar9scCRQW3ZkbfrPfeCXW2VgopSW2FWDqPOoVYIuVPAOnXCZ5g"

channels_cache = []
auth_signature = None
last_auth_time = None
auth_lock = threading.Lock()

def get_auth_signature():
    global auth_signature, last_auth_time
    with auth_lock:
        if auth_signature and last_auth_time:
            if datetime.now() - last_auth_time < timedelta(minutes=50):
                return auth_signature
        try:
            headers = {"user-agent": "okhttp/4.11.0", "accept": "application/json", "content-type": "application/json; charset=utf-8"}
            data = {"token": VAVOO_TOKEN, "reason": "app-blur", "locale": "de", "theme": "dark", "metadata": {"device": {"type": "Handset", "brand": "google", "model": "Nexus", "name": "21081111RG", "uniqueId": "d10e5d99ab665233"}, "os": {"name": "android", "version": "7.1.2", "abis": ["arm64-v8a", "armeabi-v7a", "armeabi"], "host": "android"}, "app": {"platform": "android", "version": "3.1.20", "buildId": "289515000", "engine": "hbc85", "signatures": ["6e8a975e3cbf07d5de823a760d4c2547f86c1403105020adee5de67ac510999e"], "installer": "app.revanced.manager.flutter"}, "version": {"package": "tv.vavoo.app", "binary": "3.1.20", "js": "3.1.20"}}, "appFocusTime": 0, "playerActive": False, "playDuration": 0, "devMode": False, "hasAddon": True, "castConnected": False, "package": "tv.vavoo.app", "version": "3.1.20", "process": "app", "firstAppStart": int(__import__('time').time() * 1000), "lastAppStart": int(__import__('time').time() * 1000), "ipLocation": "", "adblockEnabled": True, "proxy": {"supported": ["ss", "openvpn"], "engine": "ss", "ssVersion": 1, "enabled": True, "autoServer": True, "id": "pl-waw"}, "iap": {"supported": False}}
            resp = requests.post("https://www.vavoo.tv/api/app/ping", json=data, headers=headers, timeout=15)
            auth_signature = resp.json().get("addonSig")
            last_auth_time = datetime.now()
            print(f"Auth OK: {auth_signature[:20]}...")
            return auth_signature
        except Exception as e:
            print(f"Auth error: {e}")
            return None

def fetch_country(country, signature):
    headers = {"user-agent": "okhttp/4.11.0", "accept": "application/json", "content-type": "application/json; charset=utf-8", "mediahubmx-signature": signature, "accept-encoding": "gzip"}
    channels = []
    cursor = 0
    while True:
        data = {"language": "de", "region": "AT", "catalogId": "iptv", "id": "iptv", "adult": False, "search": "", "sort": "name", "filter": {"group": country}, "cursor": cursor, "clientVersion": "3.0.2"}
        try:
            resp = requests.post("https://vavoo.to/mediahubmx-catalog.json", json=data, headers=headers, timeout=10)
            r = resp.json()
            items = r.get("items", [])
            for item in items:
                item['_country'] = country
            channels.extend(items)
            cursor = r.get("nextCursor")
            if not cursor:
                break
        except:
            break
    return channels

def load_all_channels():
    global channels_cache
    print("Loading channels...")
    signature = get_auth_signature()
    if not signature:
        return False
    countries = ["Turkey", "Germany", "United Kingdom", "United States", "France"]
    all_channels = []
    for country in countries:
        try:
            ch = fetch_country(country, signature)
            all_channels.extend(ch)
            print(f"  {country}: {len(ch)}")
        except Exception as e:
            print(f"  {country} error: {e}")
    channels_cache = all_channels
    print(f"Total: {len(all_channels)} channels")
    return True

def generate_m3u():
    if not channels_cache:
        return ""
    lines = ["#EXTM3U"]
    host = request.headers.get('Host', 'localhost')
    for ch in sorted(channels_cache, key=lambda x: (0 if x.get('_country') == 'Turkey' else 1, x.get('name', ''))):
        name = ch.get("name", "Unknown").strip()
        ch_id = ch.get("ids", {}).get("id", "")
        if not ch_id:
            continue
        group = ch.get("group", "General")
        clean_name = name.replace('"', "'").replace(',', ' ')
        proxy_url = f"https://{host}/stream/{ch_id}"
        lines.append(f'#EXTINF:-1 group-title="{group}",{clean_name}')
        lines.append(proxy_url)
    return "\n".join(lines)

@app.route('/')
def index():
    host = request.headers.get('Host', 'localhost')
    return f"<h1>VAVOO Proxy Running</h1><p>Channels: {len(channels_cache)}</p><p>Playlist: https://{host}/playlist.m3u</p>"

@app.route('/playlist.m3u')
def playlist():
    m3u = generate_m3u()
    if not m3u:
        return "No channels", 503
    return Response(m3u, mimetype='application/x-mpegURL', headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'})

@app.route('/stream/<channel_id>')
def stream(channel_id):
    try:
        vavoo_url = f"https://vavoo.to/vavoo-iptv/play/{channel_id}"
        headers = {'User-Agent': 'VAVOO/2.6', 'Referer': 'https://vavoo.to/', 'Origin': 'https://vavoo.to', 'Accept': '*/*', 'Accept-Language': 'de-DE,de;q=0.9', 'Accept-Encoding': 'gzip, deflate, br', 'Connection': 'keep-alive', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Site': 'same-origin', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        resp = requests.get(vavoo_url, headers=headers, timeout=15, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            return f"Stream error: {resp.status_code}", 502
        def generate():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        response = Response(generate(), mimetype=resp.headers.get('Content-Type', 'video/mp2t'))
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/status')
def status():
    return jsonify({"status": "running", "channels": len(channels_cache)})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

print("="*50)
print("VAVOO PROXY STARTING")
print("="*50)
load_all_channels()

if __name__ == '__main__':
    port = int(__import__('os').environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
