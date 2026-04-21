"""
Módulo de licenciamento offline.

Formato da chave: AAAAA-BBBBB-CCCCC-DDDDD-EEEEE  (25 chars base32, 5 grupos de 5)
Payload (8 bytes):
    [0:4]  uint32 big-endian  → unix timestamp de expiração
    [4:6]  uint16 big-endian  → máx ativações (0 = ilimitado)
    [6:8]  uint16 big-endian  → flags reservadas
Assinatura (7 bytes): primeiros 7 bytes do HMAC-SHA256(SECRET, payload)
Total: 15 bytes → base32 = 24 chars, formatado em 5 grupos de 5 (25 com hífens).
"""

import hmac
import hashlib
import struct
import base64
import os
from datetime import datetime, timedelta

def _carregar_secret() -> bytes:
    secret_file = os.path.join(os.path.dirname(__file__), 'secret.key')
    if os.path.isfile(secret_file):
        with open(secret_file, 'rb') as f:
            return f.read().strip()
    # Fallback para desenvolvimento — NUNCA use em produção sem secret.key
    return b'__dev_secret_inseguro__'

_SECRET = _carregar_secret()

_LIC_FILE = os.path.join(os.path.dirname(__file__), '.license')


# ---------------------------------------------------------------------------
# Geração e codificação
# ---------------------------------------------------------------------------

def _pack(exp_ts: int, max_ativ: int) -> bytes:
    payload = struct.pack('>IHH', exp_ts, max_ativ, 0)  # 8 bytes
    sig = hmac.new(_SECRET, payload, hashlib.sha256).digest()[:7]
    return payload + sig  # 15 bytes


def _unpack(raw_bytes: bytes) -> tuple[int, int, bool]:
    """Retorna (exp_ts, max_ativ, assinatura_ok)."""
    if len(raw_bytes) != 15:
        return 0, 0, False
    payload = raw_bytes[:8]
    sig_stored = raw_bytes[8:]
    sig_expected = hmac.new(_SECRET, payload, hashlib.sha256).digest()[:7]
    ok = hmac.compare_digest(sig_stored, sig_expected)
    exp_ts, max_ativ, _ = struct.unpack('>IHH', payload)
    return exp_ts, max_ativ, ok


def _bytes_para_chave(raw: bytes) -> str:
    b32 = base64.b32encode(raw).decode().rstrip('=')  # 24 chars
    # Formata em 5 grupos de 5 (último grupo tem 4, completamos com X de padding visual)
    padded = b32.ljust(25, 'X')
    return '-'.join(padded[i:i+5] for i in range(0, 25, 5))


def _chave_para_bytes(chave: str) -> bytes:
    raw = chave.replace('-', '').upper().rstrip('X')
    padded = raw + '=' * ((8 - len(raw) % 8) % 8)
    try:
        return base64.b32decode(padded)
    except Exception:
        return b''


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def gerar_chave(dias_validade: int = 365, max_ativacoes: int = 1) -> str:
    exp_ts = int((datetime.now() + timedelta(days=dias_validade)).timestamp())
    return _bytes_para_chave(_pack(exp_ts, max_ativacoes))


def validar_chave(chave: str) -> tuple[bool, str]:
    """Retorna (válida, mensagem)."""
    raw = _chave_para_bytes(chave)
    if not raw:
        return False, 'Formato de chave inválido.'

    exp_ts, max_ativ, sig_ok = _unpack(raw)
    if not sig_ok:
        return False, 'Chave inválida — assinatura incorreta.'

    exp_dt = datetime.fromtimestamp(exp_ts)
    if exp_dt < datetime.now():
        return False, f'Chave expirada em {exp_dt.strftime("%d/%m/%Y")}.'

    dias_rest = (exp_dt - datetime.now()).days
    ativ_str = 'ilimitadas' if max_ativ == 0 else str(max_ativ)
    msg = f'Válida até {exp_dt.strftime("%d/%m/%Y")} ({dias_rest}d restantes) · Ativações: {ativ_str}'
    return True, msg


def inspecionar_chave(chave: str) -> dict:
    raw = _chave_para_bytes(chave)
    if not raw:
        return {'valida': False, 'erro': 'Formato inválido'}
    exp_ts, max_ativ, sig_ok = _unpack(raw)
    exp_dt = datetime.fromtimestamp(exp_ts) if exp_ts else None
    return {
        'valida': sig_ok,
        'expiracao': exp_dt.strftime('%d/%m/%Y %H:%M') if exp_dt else '—',
        'max_ativacoes': 'ilimitadas' if max_ativ == 0 else max_ativ,
        'expirada': exp_dt < datetime.now() if exp_dt else True,
        'assinatura_ok': sig_ok,
    }


# ---------------------------------------------------------------------------
# Persistência local
# ---------------------------------------------------------------------------

def salvar_chave_local(chave: str):
    with open(_LIC_FILE, 'w', encoding='utf-8') as f:
        f.write(chave.strip().upper())


def carregar_chave_local() -> str:
    if not os.path.isfile(_LIC_FILE):
        return ''
    with open(_LIC_FILE, encoding='utf-8') as f:
        return f.read().strip()


def verificar_ativacao() -> tuple[bool, str]:
    """Verifica se há chave salva e válida. Retorna (ok, mensagem)."""
    chave = carregar_chave_local()
    if not chave:
        return False, 'Nenhuma chave de ativação encontrada.'
    return validar_chave(chave)
