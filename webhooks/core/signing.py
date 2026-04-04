"""
Firma HMAC estilo Stripe-like.

Formato soportado: t=<timestamp>,v1=<digest>
"""
import hmac, hashlib

def sign(secret, timestamp, body):
    payload = f"{timestamp}.{body.decode()}".encode()
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"