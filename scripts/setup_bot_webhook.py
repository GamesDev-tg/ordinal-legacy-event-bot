import sys
import os
import httpx
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def configure_webhook(bot_token: str, public_url: str):
    public_url = public_url.rstrip("/")
    webhook_url = f"{public_url}/webhook"
    
    print("=" * 60)
    print("   ORDINAL LEGACY EVENT BOT — TELEGRAM WEBHOOK SETUP")
    print("=" * 60)
    print(f"📡 Setting Webhook to: {webhook_url}\n")
    
    set_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    info_url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    me_url = f"https://api.telegram.org/bot{bot_token}/getMe"
    
    try:
        with httpx.Client(timeout=15.0) as client:
            # 1. Verify Bot Token
            me_resp = client.get(me_url)
            if me_resp.status_code != 200:
                print(f"❌ Invalid Telegram Bot Token: {me_resp.text}")
                return False
            bot_info = me_resp.json().get("result", {})
            print(f"✅ Bot Verified: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            
            # 2. Set Webhook
            resp = client.post(set_url, json={"url": webhook_url})
            res_data = resp.json()
            if not res_data.get("ok"):
                print(f"❌ Failed to set webhook: {res_data}")
                return False
            print(f"✅ Webhook successfully configured: {res_data.get('description', 'OK')}")
            
            # 3. Verify Webhook Info
            info_resp = client.get(info_url)
            info_data = info_resp.json().get("result", {})
            print(f"🔗 Current Active URL: {info_data.get('url')}")
            print(f"⏳ Pending Updates Count: {info_data.get('pending_update_count', 0)}")
            print("\n🎉 Maha Deepotsav Bot is now LIVE and receiving Telegram messages!\n")
            return True
    except Exception as e:
        print(f"❌ Error communicating with Telegram API: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure Telegram Webhook for Ordinal Legacy Event Bot")
    parser.add_argument("--token", required=True, help="Telegram Bot Token from @BotFather")
    parser.add_argument("--url", required=True, help="Public HTTPS URL (e.g. https://your-domain.com or https://xxxx.loca.lt)")
    args = parser.parse_args()
    configure_webhook(args.token, args.url)
