import asyncio, json, logging, os, random, re, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv("lamix_env.txt")
BOT_TOKEN = os.environ["BOT_TOKEN"]
KEY = os.environ["LAMIX_KEY"]
MESSAGES_URL = os.environ["MESSAGES_URL"]
NUMBER_URL = os.environ.get("NUMBER_URL", "").strip()
AUTH_MODE = os.environ.get("AUTH_MODE", "auto").lower()
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
SUPPORT = os.environ.get("SUPPORT", "@Monir12255")
BASE = MESSAGES_URL.rsplit("/", 1)[0]
NUMBERS_URL = os.environ.get("NUMBERS_URL", BASE + "/numbers")
RANGES_URL = os.environ.get("RANGES_URL", BASE + "/ranges")
NUMBERS_EVERY, NUMBERS_PAGES = 60, 10

SERVICES = {"fb": "📘 FACEBOOK", "ig": "📸 INSTAGRAM", "wa": "💬 WHATSAPP", "tg": "✈️ TELEGRAM"}
KEYWORDS = {"fb": ["facebook", "fb-", "fb "], "ig": ["instagram"], "wa": ["whatsapp"], "tg": ["telegram"]}
BLOCKED_PREFIXES = [x for x in os.environ.get("BLOCKED_PREFIXES", "44").replace(" ", "").split(",") if x]
POLL_EVERY, IDLE_EVERY, POLL_MAX = 5, 20, 20 * 60
KEEP = 6 * 3600          # ৬ ঘণ্টা না দেখা নাম্বার পুল থেকে বাদ
WINDOW = 30 * 60         # hits গোনার সময়
TOP_N = 3
CODES = {  # কান্ট্রি কোড -> (নাম, ISO)
 "1":("USA/Canada","US"),"7":("Russia","RU"),"20":("Egypt","EG"),"27":("South Africa","ZA"),"30":("Greece","GR"),"31":("Netherlands","NL"),
 "32":("Belgium","BE"),"33":("France","FR"),"34":("Spain","ES"),"36":("Hungary","HU"),"39":("Italy","IT"),"40":("Romania","RO"),"41":("Switzerland","CH"),
 "43":("Austria","AT"),"44":("United Kingdom","GB"),"45":("Denmark","DK"),"46":("Sweden","SE"),"47":("Norway","NO"),"48":("Poland","PL"),"49":("Germany","DE"),
 "51":("Peru","PE"),"52":("Mexico","MX"),"54":("Argentina","AR"),"55":("Brazil","BR"),"56":("Chile","CL"),"57":("Colombia","CO"),"58":("Venezuela","VE"),
 "60":("Malaysia","MY"),"61":("Australia","AU"),"62":("Indonesia","ID"),"63":("Philippines","PH"),"64":("New Zealand","NZ"),"65":("Singapore","SG"),"66":("Thailand","TH"),
 "81":("Japan","JP"),"82":("South Korea","KR"),"84":("Vietnam","VN"),"86":("China","CN"),"90":("Turkey","TR"),"91":("India","IN"),"92":("Pakistan","PK"),
 "93":("Afghanistan","AF"),"94":("Sri Lanka","LK"),"95":("Myanmar","MM"),"98":("Iran","IR"),"212":("Morocco","MA"),"213":("Algeria","DZ"),"216":("Tunisia","TN"),
 "218":("Libya","LY"),"220":("Gambia","GM"),"221":("Senegal","SN"),"222":("Mauritania","MR"),"223":("Mali","ML"),"224":("Guinea","GN"),"225":("Ivory Coast","CI"),
 "226":("Burkina Faso","BF"),"227":("Niger","NE"),"228":("Togo","TG"),"229":("Benin","BJ"),"230":("Mauritius","MU"),"231":("Liberia","LR"),"232":("Sierra Leone","SL"),
 "233":("Ghana","GH"),"234":("Nigeria","NG"),"235":("Chad","TD"),"236":("Central African Rep.","CF"),"237":("Cameroon","CM"),"238":("Cape Verde","CV"),
 "240":("Equatorial Guinea","GQ"),"241":("Gabon","GA"),"242":("Congo","CG"),"243":("DR Congo","CD"),"244":("Angola","AO"),"245":("Guinea-Bissau","GW"),
 "249":("Sudan","SD"),"250":("Rwanda","RW"),"251":("Ethiopia","ET"),"252":("Somalia","SO"),"253":("Djibouti","DJ"),"254":("Kenya","KE"),"255":("Tanzania","TZ"),
 "256":("Uganda","UG"),"257":("Burundi","BI"),"258":("Mozambique","MZ"),"260":("Zambia","ZM"),"261":("Madagascar","MG"),"263":("Zimbabwe","ZW"),"264":("Namibia","NA"),
 "265":("Malawi","MW"),"266":("Lesotho","LS"),"267":("Botswana","BW"),"268":("Eswatini","SZ"),"351":("Portugal","PT"),"353":("Ireland","IE"),"358":("Finland","FI"),
 "359":("Bulgaria","BG"),"374":("Armenia","AM"),"375":("Belarus","BY"),"380":("Ukraine","UA"),"381":("Serbia","RS"),"420":("Czechia","CZ"),"421":("Slovakia","SK"),
 "508":("Saint Pierre & Miquelon","PM"),"855":("Cambodia","KH"),"856":("Laos","LA"),"880":("Bangladesh","BD"),"960":("Maldives","MV"),"962":("Jordan","JO"),
 "963":("Syria","SY"),"964":("Iraq","IQ"),"965":("Kuwait","KW"),"966":("Saudi Arabia","SA"),"967":("Yemen","YE"),"968":("Oman","OM"),"971":("UAE","AE"),
 "972":("Israel","IL"),"973":("Bahrain","BH"),"974":("Qatar","QA"),"977":("Nepal","NP"),"992":("Tajikistan","TJ"),"993":("Turkmenistan","TM"),
 "994":("Azerbaijan","AZ"),"995":("Georgia","GE"),"996":("Kyrgyzstan","KG"),"998":("Uzbekistan","UZ"),
}

logging.basicConfig(level=logging.INFO)
http = httpx.AsyncClient(timeout=20)
watchers: dict[str, dict] = {}
chat_number: dict[int, str] = {}
auth_ok: str | None = None

# ---------- API (auth নিজে খুঁজে নেয়) ----------
def _variants(params):
    p = dict(params or {})
    return {
        "bearer": ({"Authorization": f"Bearer {KEY}"}, p),
        "x-api-key": ({"X-API-Key": KEY}, p),
        "query": ({}, {**p, "api_key": KEY}),
    }

async def api(method, url, params=None, body=None):
    global auth_ok
    v = _variants(params)
    order = [auth_ok] if auth_ok else ([AUTH_MODE] if AUTH_MODE in v else list(v))
    last = None
    for mode in order:
        h, p = v[mode]
        try:
            r = await http.request(method, url, headers=h, params=p, json=body)
        except Exception as e:
            last = e; continue
        if r.status_code in (401, 403):
            last = RuntimeError(f"{r.status_code} (auth: {mode})"); continue
        r.raise_for_status()
        auth_ok = mode
        return r.json()
    raise last or RuntimeError("API ব্যর্থ")

def first(d, keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None

def find_list(j):
    if isinstance(j, list): return j
    if isinstance(j, dict):
        for k in ("data", "messages", "results", "items", "records", "sms"):
            if k in j:
                r = find_list(j[k])
                if r is not None: return r
    return None

def digits(x): return re.sub(r"\D", "", str(x))

def parse_messages(j):
    out = []
    for it in find_list(j) or []:
        num = first(it, ("number", "phone", "to", "recipient", "msisdn", "destination", "receiver"))
        txt = first(it, ("text", "message", "body", "content", "sms", "otp", "code"))
        if num is None or txt is None: continue
        uid = first(it, ("id", "uuid", "nid", "message_id")) or f"{num}:{txt}"
        out.append((digits(num), str(txt), str(uid)))
    return out

def parse_numbers(j):
    out = []
    for it in find_list(j) or []:
        num = first(it, ("number", "msisdn", "phone", "did", "num")) if isinstance(it, dict) else it
        if num is None: continue
        if isinstance(it, dict):
            if it.get("assigned") is True: continue
            if it.get("clientId") not in (None, "", 0, "0"): continue
        out.append(digits(num))
    return [n for n in out if n]

def next_cursor(j):
    if not isinstance(j, dict): return None
    for box in (j, j.get("meta") or {}, j.get("paging") or {}, j.get("pagination") or {}):
        if isinstance(box, dict):
            v = first(box, ("next", "after", "next_cursor", "nextCursor", "cursor"))
            if v: return str(v)
    return None

async def request_number(service_key):
    if not NUMBER_URL:
        raise RuntimeError("NUMBER_URL বসানো হয়নি")
    j = await api("POST", NUMBER_URL, body={"service": service_key})
    d = j.get("data", j) if isinstance(j, dict) else {}
    num = first(d, ("full_number", "number", "phone", "msisdn"))
    if not num:
        raise RuntimeError("নাম্বার পাওয়া যায়নি")
    return digits(num), str(first(d, ("country",)) or ""), str(first(d, ("operator", "carrier")) or "")

# ---------- নাম্বার পুল (messages API থেকে নিজে তৈরি হয়) ----------
pool: dict[str, dict] = {}      # number -> {"seen": ts, "svc": set, "hits": [ts...], "uids": set}
assigned: dict[str, int] = {}   # number -> chat (একজনকে একটাই, মিশে যাওয়া ঠেকাতে)

def country_of(num):
    for n in (3, 2, 1):
        if num[:n] in CODES: return CODES[num[:n]]
    return ("Unknown", "??")

def flag(code):
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code) if len(code) == 2 and code.isalpha() else "🌍"

def svc_of(txt):
    t = txt.lower()
    return {k for k, kws in KEYWORDS.items() if any(w in t for w in kws)}

def blocked(num): return any(num.startswith(p) for p in BLOCKED_PREFIXES)

def ingest(msgs):
    """নতুন মেসেজ পুলে ঢোকায়; ইউজার থাকলে OTP ঠিকানা সহ ফেরত দেয়"""
    now, fresh = time.time(), []
    for num, txt, uid in msgs:
        if blocked(num): continue
        e = pool.setdefault(num, {"seen": now, "svc": set(), "hits": [], "uids": set()})
        if uid in e["uids"]: continue
        e["uids"].add(uid); e["seen"] = now; e["svc"] |= svc_of(txt); e["hits"].append(now)
        fresh.append((num, txt, uid))
    for n in [n for n, e in pool.items() if now - e["seen"] > KEEP and n not in assigned]:
        del pool[n]
    return fresh

def country_groups(key):
    now = time.time(); groups = {}
    for n, e in pool.items():
        if n in assigned: continue
        name, iso = country_of(n)
        g = groups.setdefault(iso, {"name": name, "nums": [], "hits": 0})
        g["nums"].append(n)
        if key in e["svc"]: g["hits"] += sum(1 for t in e["hits"] if now - t <= WINDOW)
    return sorted(groups.items(), key=lambda kv: (-kv[1]["hits"], -len(kv[1]["nums"])))

def take_number(key, iso):
    g = dict(country_groups(key)).get(iso)
    if not g: raise RuntimeError("এই দেশে এখন ফ্রি নাম্বার নেই")
    return random.choice(g["nums"]), g["name"]

async def numbers_loop():
    """প্যানেলে আপনার হাতে থাকা (ক্লায়েন্টে না দেওয়া) নাম্বার পুলে আনে"""
    while True:
        try:
            after, total = None, 0
            for _ in range(NUMBERS_PAGES):
                params = {"limit": 500, "assigned": "false"}
                if after: params["after"] = after
                j = await api("GET", NUMBERS_URL, params=params)
                now = time.time()
                for n in parse_numbers(j):
                    if blocked(n): continue
                    e = pool.setdefault(n, {"seen": now, "svc": set(), "hits": [], "uids": set()})
                    e["seen"] = now; total += 1
                after = next_cursor(j)
                if not after: break
            logging.info("numbers loaded: %d", total)
        except Exception as e:
            logging.warning("numbers error: %s", e)
        await asyncio.sleep(NUMBERS_EVERY)

# ---------- OTP (সব ইউজারের জন্য একটাই পোলার) ----------
def add_watcher(chat_id, number):
    drop_watcher(chat_id)
    seen = set(pool.get(number, {}).get("uids", ()))   # আগের মেসেজ নতুন বলে ধরা হবে না
    watchers[number] = {"chat": chat_id, "expires": time.time() + POLL_MAX, "seen": seen, "got": False}
    chat_number[chat_id] = number; assigned[number] = chat_id

def drop_watcher(chat_id):
    n = chat_number.pop(chat_id, None)
    if n: watchers.pop(n, None); assigned.pop(n, None)

async def otp_loop(app):
    while True:
        try:
            for num, txt, uid in ingest(parse_messages(await api("GET", MESSAGES_URL))):
                w = watchers.get(num)
                if not w or uid in w["seen"]: continue
                w["seen"].add(uid); w["got"] = True
                m = re.search(r"\b\d{4,8}\b", txt)
                code = m.group(0) if m else "?"
                try:
                    await app.bot.send_message(w["chat"], f"✅ OTP পাওয়া গেছে!\n📞 `+{num}`\n🔑 কোড: `{code}`\n\n💬 {txt}", parse_mode="Markdown")
                except Exception as e:
                    logging.warning("send: %s", e)
        except Exception as e:
            logging.warning("messages error: %s", e)
        now = time.time()
        for n, w in list(watchers.items()):
            if now > w["expires"]:
                watchers.pop(n, None); chat_number.pop(w["chat"], None); assigned.pop(n, None)
                if not w["got"]:
                    try: await app.bot.send_message(w["chat"], "⌛ সময় শেষ, OTP আসেনি। নতুন নাম্বার নিন।")
                    except Exception: pass
        await asyncio.sleep(POLL_EVERY if watchers else IDLE_EVERY)

# ---------- UI ----------
MAIN_KB = ReplyKeyboardMarkup([["📱 GET NUMBER"], ["🆘 SUPPORT"]], resize_keyboard=True)

def service_kb():
    rows = [[B(v, callback_data=f"svc:{k}")] for k, v in SERVICES.items()]
    rows.append([B("❌ CLOSE", callback_data="close")])
    return M(rows)

async def safe_edit(q, text, **kw):
    try:
        await q.edit_message_text(text, **kw)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            await q.message.reply_text(text, **kw)

async def start(u: Update, c): await u.message.reply_text("স্বাগতম! নিচের মেনু থেকে বেছে নিন 👇", reply_markup=MAIN_KB)
async def menu(u: Update, c): await u.message.reply_text("📍 Select a service:", reply_markup=service_kb())
async def support(u: Update, c): await u.message.reply_text(f"🆘 সাপোর্ট: {SUPPORT}")
async def my_id(u: Update, c): await u.message.reply_text(f"আপনার id: {u.effective_user.id}")

async def test(u: Update, c):
    """অ্যাডমিন: API-র আসল response দেখায় (ডিবাগের জন্য)"""
    if u.effective_user.id not in ADMIN_IDS:
        await u.message.reply_text("শুধু অ্যাডমিন। ADMIN_IDS-এ আপনার id বসান (/id)।"); return
    for name, url, params in (("messages", MESSAGES_URL, {"limit": 3}), ("numbers", NUMBERS_URL, {"limit": 3}), ("ranges", RANGES_URL, None)):
        try:
            j = await api("GET", url, params=params)
            await u.message.reply_text(f"[{name}] auth: {auth_ok}\n{json.dumps(j, ensure_ascii=False)[:1200]}")
        except Exception as e:
            await u.message.reply_text(f"[{name}] ❌ {e}")
    await u.message.reply_text(f"পুলে নাম্বার: {len(pool)} | ফ্রি দেশ (fb): {len(country_groups('fb'))}")

def country_view(key):
    groups = country_groups(key)[:TOP_N]
    name = SERVICES[key]
    if not groups:
        return f"❌ {name}-এর জন্য এখন কোনো নাম্বার নেই।\nসাপোর্ট: {SUPPORT}", M([[B("⬅️ BACK", callback_data="back")]])
    lines = [f"🌍 Select a country for {name}:", "", f"Top {len(groups)} countries by hits"]; btns = []
    for i, (iso, g) in enumerate(groups, 1):
        fire = " 🔥" if i == 1 and g["hits"] > 0 else ""
        lines.append(f"{i}. {flag(iso)} {g['name']} ({iso}) • {g['hits']} hits{fire}")
        btns.append(B(f"{flag(iso)} {iso} · {g['hits']}", callback_data=f"cty:{key}:{iso}"))
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [[B("⬅️ BACK", callback_data="back")]]
    return "\n".join(lines), M(rows)

async def on_cb(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    chat = q.message.chat_id
    if q.data == "close":
        await q.message.delete(); return
    if q.data == "back":
        drop_watcher(chat); await safe_edit(q, "📍 Select a service:", reply_markup=service_kb()); return
    if q.data.startswith("svc:"):
        drop_watcher(chat); text, kb = country_view(q.data[4:]); await safe_edit(q, text, reply_markup=kb); return
    if q.data.startswith("cty:"):
        _, key, iso = q.data.split(":"); drop_watcher(chat)
        try:
            num, cname = take_number(key, iso)
        except Exception as e:
            text, kb = country_view(key); await safe_edit(q, f"❌ {e}\n\n" + text, reply_markup=kb); return
        kb = M([[B("🔄 Change Number", callback_data=f"cty:{key}:{iso}")], [B("⬅️ Back", callback_data=f"svc:{key}"), B("❌ Close", callback_data="close")]])
        await safe_edit(q, f"{SERVICES[key]}\n📞 নাম্বার: `+{num}`\n🌍 {flag(iso)} {cname}\n\n⏳ OTP-র জন্য অপেক্ষা করছি...", parse_mode="Markdown", reply_markup=kb)
        add_watcher(chat, num)

# ---------- Render ----------
def start_health_server():
    port = os.environ.get("PORT")
    if not port: return
    class H(BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        do_HEAD = do_GET
        def log_message(self, *a): pass
    threading.Thread(target=HTTPServer(("0.0.0.0", int(port)), H).serve_forever, daemon=True).start()

async def keepalive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while url:
        await asyncio.sleep(600)
        try: await http.get(url)
        except Exception as e: logging.warning("keepalive: %s", e)

async def post_init(app):
    asyncio.create_task(otp_loop(app)); asyncio.create_task(numbers_loop()); asyncio.create_task(keepalive())

def main():
    start_health_server()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(MessageHandler(filters.Regex("GET NUMBER$"), menu))
    app.add_handler(MessageHandler(filters.Regex("SUPPORT$"), support))
    app.add_handler(CallbackQueryHandler(on_cb))
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling()

if __name__ == "__main__":
    main()
