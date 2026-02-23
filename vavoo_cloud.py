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

def get_auth():
    global auth_signature, last_auth_time
    with auth_lock:
        if auth_signature and last_auth_time:
            if datetime.now() - last_auth_time < timedelta(minutes=30):
                return auth_signature
        try:
            headers = {"user-agent": "okhttp/4.11.0", "accept": "application/json", "content-type": "application/json; charset=utf-8"}
            data = {"token": VAVOO_TOKEN, "reason": "app-blur", "locale": "de", "theme": "dark", "metadata": {"device": {"type": "Handset", "brand": "google", "model": "Nexus", "name": "21081111RG", "uniqueId": "d10e5d99ab665233"}, "os": {"name": "android", "version": "7.1.2", "abis": ["arm64-v8a", "armeabi-v7a", "armeabi"], "host": "android"}, "app": {"platform": "android", "version": "3.1.20", "buildId": "289515000", "engine": "hbc85", "signatures": ["6e8a975e3cbf07d5de823a760d4c2547f86c1403105020adee5de67ac510999e"], "installer": "app.revanced.manager.flutter"}, "version": {"package": "tv.vavoo.app", "binary": "3.1.20", "js": "3.1.20"}}, "appFocusTime": 0, "playerActive": False, "playDuration": 0, "devMode": False, "hasAddon": True, "castConnected": False, "package": "tv.vavoo.app", "version": "3.1.20", "process": "app", "firstAppStart": 0, "lastAppStart": 0, "ipLocation": "", "adblockEnabled": True, "proxy": {"supported": ["ss", "openvpn"], "engine": "ss", "ssVersion": 1, "enabled": True, "autoServer": True, "id": "pl-waw"}, "iap": {"supported": False}}
            resp = requests.post("https://www.vavoo.tv/api/app/ping", json=data, headers=headers, timeout=15)
            auth_signature = resp.json().get("addonSig")
            last_auth_time = datetime.now()
            return auth_signature
        except:
            return None

def load_channels():
    global channels_cache
    sig = get_auth()
    if not sig:
        return False
    
    countries = ["Turkey", "Germany"]
    all_ch = []
    
    for country in countries:
        try:
            headers = {"user-agent": "okhttp/4.11.0", "accept": "application/json", "content-type": "application/json; charset=utf-8", "mediahubmx-signature": sig}
            data = {"language": "de", "region": "AT", "catalogId": "iptv", "id": "iptv", "adult": False, "search": "", "sort": "name", "filter": {"group": country}, "cursor": 0, "clientVersion": "3.0.2"}
            resp = requests.post("https://vavoo.to/mediahubmx-catalog.json", json=data, headers=headers, timeout=10)
            items = resp.json().get("items", [])
            for item in items:
                item['_country'] = country
                if isinstance(item.get("ids"), dict) and item["ids"].get("id"):
                    item['url'] = f"https://vavoo.to/vavoo-iptv/play/{item['ids']['id']}"
            all_ch.extend(items)
        except:
            pass
    
    channels_cache = [c for c in all_ch if c.get('url')]
    return True

def gen_m3u():
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
        proxy_url = f"https://{host}/play/{ch_id}"
        lines.append(f'#EXTINF:-1 group-title="{group}",{clean_name}')
        lines.append(proxy_url)
    return "\n".join(lines)

@app.route('/')
def index():
    return f"<h1>VAVOO Proxy</h1><p>Channels: {len(channels_cache)}</p><p>Playlist: /playlist.m3u</p>"

@app.route('/playlist.m3u')
def playlist():
    m3u = gen_m3u()
    if not m3u:
        return "No channels", 503
    return Response(m3u, mimetype='application/x-mpegURL', headers={'Access-Control-Allow-Origin': '*'})

@app.route('/play/<ch_id>')
def play(ch_id):
    try:
        # Finde Kanal
        ch = None
        for c in channels_cache:
            if c.get("ids", {}).get("id") == ch_id:
                ch = c
                break
        
        if not ch:
            return "Channel not found", 404
        
        url = ch.get('url', '')
        if not url:
            return "No URL", 404
        
        # Proxy mit Headers
        headers = {'User-Agent': 'VAVOO/2.6', 'Referer': 'https://vavoo.to/', 'Origin': 'https://vavoo.to'}
        resp = requests.get(url, headers=headers, timeout=15, stream=True)
        
        if resp.status_code != 200:
            return f"Error: {resp.status_code}", 502
        
        def gen():
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        return Response(gen(), mimetype='video/mp2t', headers={'Access-Control-Allow-Origin': '*'})
    
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/status')
def status():
    return jsonify({"status": "running", "channels": len(channels_cache)})

load_channels()

if __name__ == '__main__':
    port = int(__import__('os').environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
