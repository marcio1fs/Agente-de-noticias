import base64
import os
import logging
from cryptography.fernet import Fernet
from app.core.config import settings

logger = logging.getLogger(__name__)

def _get_fernet() -> Fernet:
    # Tenta usar a chave de criptografia configurada
    try:
        return Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception:
        # Fallback apenas para desenvolvimento/simulação derivado da SECRET_KEY
        if settings.AGENT_MODE != "SIMULATION":
            logger.error("Chave de criptografia (ENCRYPTION_KEY) inválida ou ausente em modo não-simulado!")
        
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
        # Permitir strings legadas/plaintext apenas em modo SIMULATION
        if settings.AGENT_MODE == "SIMULATION":
            return cipher_text
        
        logger.warning("Falha ao descriptografar segredo. Texto cifrado ou corrompido.")
        return ""

