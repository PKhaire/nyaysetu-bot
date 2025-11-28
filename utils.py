# utils.py
import uuid
from db import SessionLocal
from models import User, Conversation
from datetime import datetime

def generate_case_id():
    return f"NS-{uuid.uuid4().hex[:8].upper()}"

def register_user_if_missing(whatsapp_id, name=None, language="English"):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(whatsapp_id=whatsapp_id).first()
        if user:
            return user
        case_id = generate_case_id()
        user = User(whatsapp_id=whatsapp_id, case_id=case_id, name=name, language=language)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

def store_message(whatsapp_id, direction, text):
    db = SessionLocal()
    try:
        conv = Conversation(user_whatsapp_id=whatsapp_id, direction=direction, text=text, timestamp=datetime.utcnow())
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv
    finally:
        db.close()

def user_message_count(whatsapp_id):
    db = SessionLocal()
    try:
        return db.query(Conversation).filter_by(user_whatsapp_id=whatsapp_id, direction='user').count()
    finally:
        db.close()
