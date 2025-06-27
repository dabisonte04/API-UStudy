import os
import base64
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from models.usuario import Usuario
from config import SessionLocal
from utils.passwords_utils import hash_password, verify_password

router = APIRouter()

# ------------------ DB DEPENDENCY ------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------ SCHEMAS ------------------

class UsuarioCreate(BaseModel):
    nombre: str
    correo: EmailStr
    contrasena: str  # en texto plano, se guarda hasheada

class UsuarioLogin(BaseModel):
    correo: EmailStr
    contrasena: str

class UsuarioOut(BaseModel):
    id: str
    nombre: str
    correo: EmailStr
    u_id: Optional[str] = None

    class Config:
        from_attributes = True

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    correo: Optional[EmailStr] = None

class PasswordUpdate(BaseModel):
    contrasena_actual: str
    contrasena_nueva: str

class UIdUpdate(BaseModel):
    u_id: str

    class Config:
        from_attributes = True

# ------------------ RUTAS ------------------

@router.post("/register", response_model=UsuarioOut)
def register(request: Request, data: UsuarioCreate, db: Session = Depends(get_db)):
    if db.query(Usuario).filter_by(correo=data.correo).first():
        raise HTTPException(status_code=400, detail="Correo ya registrado.")
    nuevo = Usuario(
        id=str(uuid.uuid4()),
        nombre=data.nombre,
        correo=data.correo,
        contrasena_hash=hash_password(data.contrasena)
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@router.post("/login")
def login(request: Request, data: UsuarioLogin, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter_by(correo=data.correo).first()
    if not user or not verify_password(data.contrasena, user.contrasena_hash):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas.")

    return {
        "usuario": UsuarioOut.from_orm(user)
    }

@router.get("/{user_id}", response_model=UsuarioOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return user

@router.get("/", response_model=List[UsuarioOut])
def get_all_users(request: Request, db: Session = Depends(get_db)):
    return db.query(Usuario).all()

@router.put("/{user_id}", response_model=UsuarioOut)
def update_user(request: Request, user_id: str, data: UsuarioUpdate, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if data.correo and data.correo != user.correo:
        if db.query(Usuario).filter_by(correo=data.correo).first():
            raise HTTPException(status_code=400, detail="Ese correo ya está en uso.")

    if data.nombre:
        user.nombre = data.nombre
    if data.correo:
        user.correo = data.correo

    db.commit()
    db.refresh(user)
    return user

@router.patch("/{user_id}/password")
def update_password(request: Request, user_id: str, data: PasswordUpdate, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if not verify_password(data.contrasena_actual, user.contrasena_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta.")

    user.contrasena_hash = hash_password(data.contrasena_nueva)
    db.commit()
    return {"message": "Contraseña actualizada correctamente."}

@router.post("/{user_id}/u_id")
def update_u_id(request: Request, user_id: str, data: UIdUpdate, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    user.u_id = data.u_id
    db.commit()
    db.refresh(user)  # refrescar para asegurar datos actualizados

    return {"usuario": UsuarioOut.from_orm(user)}
