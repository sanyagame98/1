import os, secrets, json, logging
from decimal import Decimal, InvalidOperation
from flask import Flask, request, jsonify
import psycopg
from psycopg.rows import dict_row
import requests

app=Flask(__name__)
logging.basicConfig(level=logging.INFO)
TOKEN=os.getenv("BOT_TOKEN","").strip()
DB=os.getenv("DATABASE_URL","").strip()
BASE=os.getenv("RENDER_EXTERNAL_URL","").rstrip("/")
try: ADMINS={int(v) for v in os.getenv("ADMIN_IDS","").split(",") if v.strip()}
except ValueError: ADMINS=set()
API=f"https://api.telegram.org/bot{TOKEN}/"
def api(method, **data):
    if not TOKEN: return None
    try:
        r=requests.post(API+method,json=data,timeout=15)
        if not r.ok: logging.warning("Telegram %s failed: %s",method,r.status_code)
        return r.json()
    except Exception: logging.exception("Telegram request error")
def buttons(rows):
    return {"inline_keyboard":[[{"text":t,**({"callback_data":v} if not v.startswith("https://") else {"url":v})} for t,v in row] for row in rows]}
def send(cid,txt,rows=None):
    return api("sendMessage",chat_id=cid,text=txt,parse_mode="HTML",reply_markup=buttons(rows) if rows else None,disable_web_page_preview=True)
def db():
    return psycopg.connect(DB,row_factory=dict_row)
SCHEMA="""
CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY, username TEXT, name TEXT NOT NULL,balance BIGINT NOT NULL DEFAULT 10000 CHECK(balance>=0));
CREATE TABLE IF NOT EXISTS checks (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, owner BIGINT NOT NULL REFERENCES users(id), amount BIGINT NOT NULL CHECK(amount>0), max_claims INT NOT NULL CHECK(max_claims BETWEEN 1 AND 500), claimed INT NOT NULL DEFAULT 0, cancelled BOOLEAN NOT NULL DEFAULT FALSE);
CREATE TABLE IF NOT EXISTS claims (check_id BIGINT NOT NULL REFERENCES checks(id), user_id BIGINT NOT NULL REFERENCES users(id), PRIMARY KEY(check_id,user_id));
CREATE TABLE IF NOT EXISTS state (id BIGINT PRIMARY KEY, action TEXT NOT NULL, amount BIGINT NOT NULL DEFAULT 0);
"""
def init():
    if not DB: return
    with db() as c:
        for s in SCHEMA.split(";"):
            if s.strip(): c.execute(s)
        c.commit()
def user(c,u):
    uid=u["id"]; name=(u.get("first_name") or "User")[:120]; username=u.get("username")
    c.execute("INSERT INTO users(id,username,name) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE SET username=EXCLUDED.username,name=EXCLUDED.name",(uid,username,name))
def money(s):
    try:
        n=Decimal(s.replace(",","."))
        v=n*100
        if n<=0 or v!=int(v) or n>1000000: return None
        return int(v)
    except (InvalidOperation,ValueError): return None
def fmt(v):return f"{Decimal(v)/100:,.2f}".replace(","," ")
def menu(uid):
    send(uid,"<b>💎 DEMO WALLET</b>\n\nБаланс виртуальный. DEMO USDT не настоящая криптовалюта.",[[("💼 Кошелёк","wallet"),("🎁 Чеки","checks")],[("➕ Создать чек","new"),("📋 Мои чеки","mine")],[("ℹ️ О проекте","about")]])
def wallet(uid):
    with db() as c: b=c.execute("SELECT balance FROM users WHERE id=%s",(uid,)).fetchone()
    send(uid,f"<b>💼 Кошелёк</b>\n\nБаланс: <b>{fmt(b['balance'])} DEMO USDT</b>\n\n⚠️ Только виртуальные единицы.",[[("🎁 Создать чек","new")],[("🏠 Меню","home")]])
def checksmenu(uid):
    send(uid,"<b>🎁 DEMO-чеки</b>\n\nСоздайте чек и отправьте ссылку другу. Сумма резервируется при создании.",[[("🎁 Создать чек","new")],[("📋 Мои чеки","mine")],[("🏠 Назад","home")]])
def mine(uid):
    with db() as c: rows=c.execute("SELECT * FROM checks WHERE owner=%s ORDER BY id DESC LIMIT 12",(uid,)).fetchall()
    if not rows:return send(uid,"У вас ещё нет чеков.",[[("➕ Создать","new")],[("🏠 Меню","home")]])
    lines=["<b>📋 Ваши чеки</b>"]; btn=[]
    for x in rows:
        lines.append(f"#{x['id']}: {fmt(x['amount'])} DEMO × {x['max_claims']}; получено {x['claimed']}; {'отменён' if x['cancelled'] else 'активен'}")
        if not x["cancelled"] and x["claimed"]<x["max_claims"]: btn.append([(f"❌ Отменить #{x['id']}",f"cancel:{x['id']}")])
    btn.append([("🏠 Меню","home")])
    send(uid,"\n".join(lines),btn)
def begin(uid):
    with db() as c:
        c.execute("INSERT INTO state(id,action) VALUES(%s,'amount') ON CONFLICT(id) DO UPDATE SET action='amount',amount=0",(uid,))
    send(uid,"<b>🎁 Новый DEMO-чек</b>\n\nВведите сумму на одну активацию, например <code>5</code>:",[[("❌ Отмена","checks")]])
def msg(update):
    u=update.get("from") or {}; uid=u.get("id")
    if not uid or update.get("chat",{}).get("type")!="private":return
    text=(update.get("text") or "").strip()
    with db() as c: user(c,u)
    if text.startswith("/start"):
        arg=text.split(maxsplit=1)[1] if len(text.split(maxsplit=1))>1 else ""
        if arg.startswith("check_"): return claim(uid,arg[6:])
        return menu(uid)
    if text in ("/wallet",):return wallet(uid)
    if text in ("/checks",):return checksmenu(uid)
    if text.startswith("/"):return menu(uid)
    with db() as c:
        row=c.execute("SELECT * FROM state WHERE id=%s",(uid,)).fetchone()
        if not row:return menu(uid)
        if row["action"]=="amount":
            amount=money(text)
            if amount is None:return send(uid,"Некорректная сумма. Пример: 5.50")
            c.execute("UPDATE state SET action='count',amount=%s WHERE id=%s",(amount,uid))
            return send(uid,"Сколько активаций? От 1 до 500.",[[("1","count:1"),("5","count:5"),("10","count:10")],[("❌ Отмена","checks")]])
        if row["action"]=="count":
            if not text.isdigit():return send(uid,"Введите количество активаций числом (1–500).")
            return create(uid,int(text),c)
def create(uid,count,existing=None):
    if count<1 or count>500:return send(uid,"Количество активаций должно быть от 1 до 500.")
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)",(uid,))
        st=c.execute("SELECT * FROM state WHERE id=%s FOR UPDATE",(uid,)).fetchone()
        if not st or st["action"]!="count":return send(uid,"Сначала выберите сумму.",[[("Создать чек","new")]])
        amount=st["amount"]; total=amount*count
        bal=c.execute("SELECT balance FROM users WHERE id=%s FOR UPDATE",(uid,)).fetchone()["balance"]
        if total>bal:return send(uid,f"Недостаточно DEMO USDT. Нужно {fmt(total)}, доступно {fmt(bal)}.")
        code=secrets.token_urlsafe(14)
        c.execute("UPDATE users SET balance=balance-%s WHERE id=%s",(total,uid))
        c.execute("INSERT INTO checks(code,owner,amount,max_claims) VALUES(%s,%s,%s,%s) RETURNING id",(code,uid,amount,count))
        cid=c.fetchone()["id"]
        c.execute("DELETE FROM state WHERE id=%s",(uid,))
    bot=api("getMe")
    username=((bot or {}).get("result") or {}).get("username")
    link=f"https://t.me/{username}?start=check_{code}" if username else "Ссылка будет доступна после настройки токена"
    send(uid,f"<b>✅ DEMO-чек #{cid} создан</b>\n\n{fmt(amount)} DEMO USDT × {count}\nЗарезервировано: {fmt(total)} DEMO USDT\n\n{link}\n\n⚠️ Не настоящая криптовалюта.",[[("📤 Поделиться",f"https://t.me/share/url?url={link}")],[("📋 Мои чеки","mine"),("🏠 Меню","home")]])
def claim(uid,code):
    with db() as c:
        row=c.execute("SELECT * FROM checks WHERE code=%s FOR UPDATE",(code,)).fetchone()
        if not row:return send(uid,"Чек не найден.")
        if row["cancelled"] or row["claimed"]>=row["max_claims"]:return send(uid,"Чек уже недоступен.")
        if row["owner"]==uid:return send(uid,"Создатель чека не может активировать свой чек.")
        taken=c.execute("SELECT 1 FROM claims WHERE check_id=%s AND user_id=%s",(row["id"],uid)).fetchone()
        if taken:return send(uid,"Вы уже активировали этот чек.")
        c.execute("INSERT INTO claims(check_id,user_id) VALUES(%s,%s)",(row["id"],uid))
        c.execute("UPDATE checks SET claimed=claimed+1 WHERE id=%s",(row["id"],))
        c.execute("UPDATE users SET balance=balance+%s WHERE id=%s",(row["amount"],uid))
    send(uid,f"<b>🎉 DEMO-чек активирован!</b>\n\n+{fmt(row['amount'])} DEMO USDT\n\n⚠️ Виртуальный баланс.",[[("💼 Кошелёк","wallet")]])
def cancel(uid,cid):
    with db() as c:
        x=c.execute("SELECT * FROM checks WHERE id=%s FOR UPDATE",(cid,)).fetchone()
        if not x or x["owner"]!=uid:return send(uid,"Чек не найден.")
        if x["cancelled"]:return send(uid,"Чек уже отменён.")
        left=x["amount"]*(x["max_claims"]-x["claimed"])
        c.execute("UPDATE checks SET cancelled=TRUE WHERE id=%s",(cid,))
        c.execute("UPDATE users SET balance=balance+%s WHERE id=%s",(left,uid))
    send(uid,f"✅ Чек #{cid} отменён. Возврат: {fmt(left)} DEMO USDT.",[[("📋 Мои чеки","mine")]])
def callback(q):
    uid=q["from"]["id"]; data=q.get("data","")
    with db() as c:user(c,q["from"])
    api("answerCallbackQuery",callback_query_id=q["id"])
    if data=="home":menu(uid)
    elif data=="wallet":wallet(uid)
    elif data=="checks":checksmenu(uid)
    elif data=="mine":mine(uid)
    elif data=="new":begin(uid)
    elif data.startswith("count:"):create(uid,int(data.split(":")[1]))
    elif data.startswith("cancel:"):cancel(uid,int(data.split(":")[1]))
    elif data=="about":send(uid,"<b>DEMO WALLET</b> — учебный бот. Все балансы и чеки виртуальные и не имеют денежной стоимости.",[[("🏠 Меню","home")]])
@app.get("/healthz")
def health():return jsonify({"status":"ok","mode":"demo","configured":bool(TOKEN and DB)})
@app.post("/telegram")
def telegram():
    if not TOKEN or request.headers.get("X-Telegram-Bot-Api-Secret-Token")!=os.getenv("WEBHOOK_SECRET",""):return ("Forbidden",403)
    try:
        up=request.get_json(force=True) or {}
        if "message" in up:msg(up["message"])
        if "callback_query" in up:callback(up["callback_query"])
    except Exception: logging.exception("Error processing update")
    return ("OK",200)
if DB:
    try:init()
    except Exception:logging.exception("Database initialization failed")
if TOKEN and BASE and DB:
    api("setWebhook",url=BASE+"/telegram",secret_token=os.getenv("WEBHOOK_SECRET",""),allowed_updates=["message","callback_query"])
