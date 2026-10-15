import base64
import os
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet() -> Fernet:
    # Gera uma chave Fernet determinística válida caso não tenha sido passada uma em base64 válida
    raw_key = settings.ENCRYPTION_KEY.encode()
    try:
        return Fernet(raw_key)
    except Exception:
        # Fallback seguro para desenvolvimento derivado da SECRET_KEY
        key_32 = (settings.SECRET_KEY * 4)[:32].encode()
        urlsafe_key = base64.urlsafe_b64encode(key_32)
        return Fernet(urlsafe_key)

def encrypt_secret(plain_text: str) -> str:
    """Criptografa tokens de acesso e credenciais antes de persistir no banco."""
    if not plain_text:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(plain_text.encode()).decode()

def decrypt_secret(cipher_text: str) -> str:
    """Descriptografa credenciais apenas no momento do uso em memória."""
    if not cipher_text:
        return ""
    try:
        fernet = _get_fernet()
        return fernet.decrypt(cipher_text.encode()).decode()
    except Exception:
        # Se não for um token cifrado por Fernet (ex: string legada de simulação), retorna o próprio texto
        return cipher_text

