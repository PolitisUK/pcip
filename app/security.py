import hashlib, secrets
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .config import settings

pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")

def hash_password(value: str) -> str: return pwd.hash(value)
def verify_password(value: str, hashed: str) -> bool: return pwd.verify(value, hashed)
def new_token() -> str: return secrets.token_urlsafe(32)
def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()
def encode_session(user_id: int) -> str: return serializer.dumps({"user_id": user_id})
def decode_session(value: str, max_age: int = 60*60*12) -> int | None:
    try: return int(serializer.loads(value, max_age=max_age)["user_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError): return None
