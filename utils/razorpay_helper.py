import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import hmac
import hashlib
from UnderdogCrew.settings import RAZORPAY_API_KEY, RAZORPAY_API_SECRET


def create_razorpay_customer(email: str, contact: str):
    url = "https://api.razorpay.com/v1/customers"
    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "name": email.split('@')[0],  # Use email prefix as name
        "email": email,
        "contact": contact
    }
    response = requests.post(url,
                             auth=HTTPBasicAuth(RAZORPAY_API_KEY,
                                                RAZORPAY_API_SECRET),
                             json=payload, headers=headers)

    if response.status_code != 200:
        return None, response.json()

    return response.json(), None


def create_razorpay_subscription(plan_id: str, email: str, total_count: int):
    url = "https://api.razorpay.com/v1/subscriptions"
    headers = {
        "Content-Type": "application/json",
    }

    expire_by = int(datetime.utcnow().timestamp()) + 259200

    payload = {
        "plan_id": plan_id,
        "total_count": total_count,
        "quantity": 1,
        "customer_notify": 1,
        "expire_by": expire_by,
        "notify_info": {
            "notify_email": email
        }
    }
    response = requests.post(url,
                             auth=HTTPBasicAuth(RAZORPAY_API_KEY,
                                                RAZORPAY_API_SECRET),
                             json=payload, headers=headers)
    if response.status_code != 200:
        return None, response.json()

    return response.json(), None


def cancel_razorpay_subscription(subscription_id: str):
    url = f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel"
    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "cancel_at_cycle_end": 0  # Immediate cancellation
    }

    response = requests.post(url,
                             auth=HTTPBasicAuth(RAZORPAY_API_KEY,
                                                RAZORPAY_API_SECRET),
                             json=payload, headers=headers)

    if response.status_code != 200:
        return None, response.json()

    return response.json(), None


def get_subscription_invoices(subscription_id: str):
    url = f"https://api.razorpay.com/v1/invoices"
    headers = {
        "Content-Type": "application/json",
    }

    params = {
        "subscription_id": subscription_id
    }

    response = requests.get(
        url,
        auth=HTTPBasicAuth(RAZORPAY_API_KEY, RAZORPAY_API_SECRET),
        headers=headers,
        params=params
    )

    if response.status_code != 200:
        return None, response.json()

    return response.json(), None


def create_razorpay_order(amount: int, currency: str, receipt: str, notes: dict):
    url = "https://api.razorpay.com/v1/orders"
    headers = {
        "Content-Type": "application/json",
    }

    payload = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt,
        "notes": notes
    }

    response = requests.post(
        url,
        auth=HTTPBasicAuth(RAZORPAY_API_KEY, RAZORPAY_API_SECRET),
        json=payload,
        headers=headers
    )

    if response.status_code != 200:
        return None, response.json()
    
    return response.json(), None


def verify_razorpay_payment(payment_id: str, order_id: str):
    """
    Verify Razorpay payment by fetching payment details from Razorpay API
    
    Args:
        payment_id: Razorpay payment ID
        order_id: Razorpay order ID
    
    Returns:
        tuple: (payment_data, error)
    """
    url = f"https://api.razorpay.com/v1/payments/{payment_id}"
    headers = {
        "Content-Type": "application/json",
    }
    
    response = requests.get(
        url, 
        auth=HTTPBasicAuth(RAZORPAY_API_KEY, RAZORPAY_API_SECRET), 
        headers=headers
    )
    
    if response.status_code != 200:
        return None, response.json()
    
    return response.json(), None


def verify_payment_signature(params_dict: dict):
    """
    Verify Razorpay payment signature without using the Razorpay client
    
    Args:
        params_dict: Dictionary containing razorpay_order_id, razorpay_payment_id, and razorpay_signature
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        # Get the required parameters
        order_id = params_dict.get('razorpay_order_id', '')
        payment_id = params_dict.get('razorpay_payment_id', '')
        razorpay_signature = params_dict.get('razorpay_signature', '')

        # Create the message string
        msg = f"{order_id}|{payment_id}"

        # Generate signature using HMAC-SHA256
        generated_signature = hmac.new(
            RAZORPAY_API_SECRET.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()

        # Compare signatures using hmac.compare_digest to prevent timing attacks
        return hmac.compare_digest(generated_signature, razorpay_signature)

    except Exception as e:
        print(f"Signature verification error: {str(e)}")
        return False