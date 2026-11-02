#!/home/froca/.local/opt/cast-env/bin/python3
# -*- coding: utf-8 -*-
"""
Módulo de apertura remota de videoportero EZVIZ (HP7 / CP7 / EP7 / Cerraduras)
Usa pyezvizapi con caché de sesión en .ezviz_credentials.json para apertura en <0.5s.
"""

import json
import os
import sys
from pyezvizapi.client import EzvizClient
from pyezvizapi.exceptions import EzvizAuthVerificationCode, PyEzvizError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE_DIR, ".ezviz_credentials.json")
DEFAULT_REGION = "apiieu.ezvizlife.com"


def load_creds():
    if os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_creds(data):
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(CRED_FILE, 0o600)


def get_client(creds):
    account = creds.get("account", "")
    password = creds.get("password", "")
    region = creds.get("region", DEFAULT_REGION)
    token = creds.get("token")

    if token and isinstance(token, dict) and token.get("session_id"):
        try:
            client = EzvizClient(token=token, url=region)
            client.login()
            return client
        except Exception:
            pass

    if not account or not password:
        raise RuntimeError("Cuenta EZVIZ no configurada. Pulsa '🔑 Config EZVIZ' en el panel SOC.")

    sms_code = creds.get("sms_code") or None
    client = EzvizClient(account, password, region)
    token_data = client.login(sms_code=sms_code)
    creds["token"] = token_data
    creds.pop("sms_code", None)
    save_creds(creds)
    return client


def discover_intercom(client, creds):
    serial = creds.get("serial")
    user_id = creds.get("user_id")
    if serial and user_id:
        return serial, user_id

    # Buscar en la cuenta EZVIZ el videoportero / cerradura
    devices = client.load_devices()
    chosen_serial = None
    for s, d in devices.items():
        chosen_serial = s
        cat = str(d.get("device_category", "")).lower()
        sub = str(d.get("device_sub_category", "")).lower()
        name = str(d.get("name", "")).lower()
        if any(k in cat or k in sub or k in name for k in ["doorbell", "intercom", "hp7", "cp7", "ep7", "lock", "dp", "db"]):
            break

    if not chosen_serial:
        raise RuntimeError("No se encontraron dispositivos en tu cuenta EZVIZ.")

    user_id = str(creds.get("token", {}).get("username") or creds.get("account"))
    try:
        pagelist = client.get_user_id()
        if pagelist:
            user_id = str(pagelist)
    except Exception:
        pass

    creds["serial"] = chosen_serial
    creds["user_id"] = user_id
    save_creds(creds)
    return chosen_serial, user_id


def unlock_door(lock_no=1):
    creds = load_creds()
    client = get_client(creds)
    serial, user_id = discover_intercom(client, creds)
    try:
        ok = client.remote_unlock(serial, user_id, int(lock_no), terminal_filter_name=None)
        return {"ok": bool(ok), "serial": serial, "lock_no": lock_no, "msg": f"Puerta #{lock_no} abierta en {serial}"}
    finally:
        try:
            client.close_session()
        except Exception:
            pass


def configure_account(account, password, serial="", sms_code="", region=DEFAULT_REGION):
    creds = load_creds()
    creds["account"] = account.strip()
    creds["password"] = password
    creds["region"] = region.strip() or DEFAULT_REGION
    if serial.strip():
        creds["serial"] = serial.strip().upper()
    if sms_code.strip():
        creds["sms_code"] = sms_code.strip()
    creds.pop("token", None)
    save_creds(creds)

    try:
        client = get_client(creds)
        found_serial, user_id = discover_intercom(client, creds)
        client.close_session()
        return {"ok": True, "serial": found_serial, "user_id": user_id, "msg": f"Conectado con éxito al telefonillo {found_serial}"}
    except EzvizAuthVerificationCode:
        return {"ok": False, "needs_2fa": True, "msg": "EZVIZ ha enviado un código de verificación 2FA a tu correo/SMS. Introdúcelo en el campo Código 2FA y vuelve a guardar."}
    except PyEzvizError as e:
        err_str = str(e) or repr(e)
        if "1226" in err_str:
            return {
                "ok": False,
                "msg": "La cuenta jumpstyleroca@gmail.com existe en Europa (apiieu.ezvizlife.com), pero la contraseña no coincide (Código 1226). Si iniciaste sesión con Google en la app EZVIZ, pon la contraseña propia de EZVIZ.",
            }
        return {"ok": False, "msg": f"Error EZVIZ: {err_str}"}
    except Exception as e:
        return {"ok": False, "msg": f"Error: {str(e) or repr(e)}"}


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "unlock":
        lno = int(sys.argv[2]) if len(sys.argv) >= 3 else 1
        try:
            res = unlock_door(lno)
            print(json.dumps(res, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"ok": False, "msg": str(e)}, ensure_ascii=False))
            sys.exit(1)
    elif len(sys.argv) >= 4 and sys.argv[1] == "config":
        acc = sys.argv[2]
        pwd = sys.argv[3]
        ser = sys.argv[4] if len(sys.argv) >= 5 else ""
        sms = sys.argv[5] if len(sys.argv) >= 6 else ""
        res = configure_account(acc, pwd, ser, sms)
        print(json.dumps(res, ensure_ascii=False))
    else:
        print("Uso: ezviz_unlock.py unlock [1|2] | config <usuario> <password> [serial] [codigo_2fa]")
