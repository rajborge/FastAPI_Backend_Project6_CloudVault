from pwdlib import PasswordHash
import secrets

password_hash=PasswordHash.recommended()

def hash_password(password:str)->str:
    return password_hash.hash(password)

def verify_password(password:str,hashed_password:str)->str:
    return password_hash.verify(password,hashed_password)

def generate_share_token(length:int=32)->str:
    return secrets.token_urlsafe(length)