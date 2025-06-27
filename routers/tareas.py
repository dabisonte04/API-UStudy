import uuid
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from config import SessionLocal
from models.tareas import Tarea
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# ------------------ DB DEPENDENCY ------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------ SCHEMAS ------------------
class TareaCreate(BaseModel):
    usuario_id: str
    titulo: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = None
    prioridad: Optional[str] = "media"
    fecha_recordatorio: Optional[datetime] = None
    origen: Optional[str] = "usuario"

    @validator('prioridad')
    def validar_prioridad(cls, value):
        if value not in ["alta", "media", "baja"]:
            raise ValueError("prioridad debe ser 'alta', 'media' o 'baja'")
        return value

    @validator('origen')
    def validar_origen(cls, value):
        if value not in ["usuario", "ia"]:
            raise ValueError("origen debe ser 'usuario' o 'ia'")
        return value

class TareaUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = None
    prioridad: Optional[str] = None
    fecha_recordatorio: Optional[datetime] = None
    completada: Optional[bool] = None
    sincronizada: Optional[bool] = None

    @validator('prioridad')
    def validar_prioridad(cls, value):
        if value and value not in ["alta", "media", "baja"]:
            raise ValueError("prioridad debe ser 'alta', 'media' o 'baja'")
        return value

class MarcarSincronizadasRequest(BaseModel):
    tarea_ids: List[str]

# ------------------ HELPER FUNCTIONS ------------------
def tarea_to_dict(tarea: Tarea) -> dict:
    """Convierte un objeto Tarea de SQLAlchemy a diccionario"""
    return {
        'id': tarea.id,
        'usuario_id': tarea.usuario_id,
        'titulo': tarea.titulo,
        'descripcion': tarea.descripcion,
        'completada': tarea.completada,
        'sincronizada': tarea.sincronizada,
        'prioridad': tarea.prioridad,
        'fecha_recordatorio': tarea.fecha_recordatorio.isoformat() if tarea.fecha_recordatorio else None,
        'origen': tarea.origen,
        'fecha_creacion': tarea.fecha_creacion.isoformat(),
        'fecha_actualizacion': tarea.fecha_actualizacion.isoformat(),
    }

# ------------------ RUTAS CRUD ------------------

# GET todas las tareas de un usuario
@router.get("/tareas/usuario/{usuario_id}", response_model=List[dict])
def obtener_tareas(usuario_id: str, db: Session = Depends(get_db)):
    if not usuario_id:
        raise HTTPException(status_code=400, detail="El usuario_id es requerido.")
    tareas = db.query(Tarea).filter_by(usuario_id=usuario_id).order_by(Tarea.fecha_creacion.desc()).all()
    
    # Convertir objetos SQLAlchemy a diccionarios
    tareas_dict = []
    for tarea in tareas:
        tarea_dict = tarea_to_dict(tarea)
        tareas_dict.append(tarea_dict)
    
    return tareas_dict

# POST crear nueva tarea
@router.post("/tareas/", response_model=dict)
def crear_tarea(data: TareaCreate, db: Session = Depends(get_db)):
    if not data.usuario_id:
        raise HTTPException(status_code=400, detail="usuario_id es obligatorio.")
    nueva_tarea = Tarea(
        id=str(uuid.uuid4()),
        usuario_id=data.usuario_id,
        titulo=data.titulo[:100],
        descripcion=data.descripcion,
        prioridad=data.prioridad,
        fecha_recordatorio=data.fecha_recordatorio,
        origen=data.origen,
        completada=False,
        sincronizada=False,
        fecha_creacion=datetime.utcnow(),
        fecha_actualizacion=datetime.utcnow()
    )
    db.add(nueva_tarea)
    db.commit()
    
    # Convertir objeto SQLAlchemy a diccionario
    return tarea_to_dict(nueva_tarea)

# PATCH actualizar parcialmente una tarea
@router.patch("/tareas/{tarea_id}", response_model=dict)
def actualizar_tarea(tarea_id: str, data: TareaUpdate, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter_by(id=tarea_id).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")

    campos_actualizables = data.dict(exclude_unset=True)
    if not campos_actualizables:
        raise HTTPException(status_code=400, detail="No se proporcionaron campos para actualizar.")

    for campo, valor in campos_actualizables.items():
        setattr(tarea, campo, valor)

    tarea.fecha_actualizacion = datetime.utcnow()
    db.commit()
    return tarea_to_dict(tarea)

# DELETE eliminar tarea
@router.delete("/tareas/{tarea_id}")
def eliminar_tarea(tarea_id: str, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter_by(id=tarea_id).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")
    db.delete(tarea)
    db.commit()
    return {"mensaje": "Tarea eliminada correctamente."}

# GET una tarea por ID
@router.get("/tareas/{tarea_id}", response_model=dict)
def obtener_tarea_por_id(tarea_id: str, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter_by(id=tarea_id).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")
    return tarea_to_dict(tarea)

# GET tareas completadas o no completadas de un usuario
@router.get("/tareas/usuario/{usuario_id}/completadas", response_model=List[dict])
def obtener_tareas_completadas(usuario_id: str, completadas: bool, db: Session = Depends(get_db)):
    tareas = db.query(Tarea)\
        .filter_by(usuario_id=usuario_id, completada=completadas)\
        .order_by(Tarea.fecha_creacion.desc())\
        .all()
    return [tarea_to_dict(t) for t in tareas]

# POST marcar tarea como completada o no
@router.post("/tareas/{tarea_id}/completar", response_model=dict)
def marcar_tarea_completada(tarea_id: str, completada: bool = True, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter_by(id=tarea_id).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")

    tarea.completada = completada
    tarea.fecha_actualizacion = datetime.utcnow()
    db.commit()
    return tarea_to_dict(tarea)

# GET tareas por prioridad y/o origen
@router.get("/tareas/usuario/{usuario_id}/filtrar", response_model=List[dict])
def filtrar_tareas(
    usuario_id: str,
    prioridad: Optional[str] = None,
    origen: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Tarea).filter_by(usuario_id=usuario_id)
    if prioridad:
        query = query.filter_by(prioridad=prioridad)
    if origen:
        query = query.filter_by(origen=origen)
    tareas = query.order_by(Tarea.fecha_creacion.desc()).all()
    return [tarea_to_dict(t) for t in tareas]

# POST sincronización masiva de tareas (desde cliente)
@router.post("/tareas/sync", response_model=dict)
def sincronizar_tareas(payload: List[dict], db: Session = Depends(get_db)):
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=400, detail="Se requiere una lista de tareas para sincronizar.")

    resultados = {"creadas": 0, "actualizadas": 0}

    for t in payload:
        if "id" not in t:
            continue

        tarea = db.query(Tarea).filter_by(id=t["id"]).first()
        if tarea:
            # actualizar campos existentes
            for campo in [
                "titulo", "descripcion", "prioridad", "completada",
                "fecha_recordatorio", "sincronizada", "origen"
            ]:
                if campo in t:
                    setattr(tarea, campo, t[campo])
            tarea.fecha_actualizacion = datetime.utcnow()
            resultados["actualizadas"] += 1
        else:
            nueva = Tarea(
                id=t["id"],
                usuario_id=t["usuario_id"],
                titulo=t.get("titulo", "Sin título")[:100],
                descripcion=t.get("descripcion"),
                prioridad=t.get("prioridad", "media"),
                completada=t.get("completada", False),
                sincronizada=True,
                origen=t.get("origen", "usuario"),
                fecha_recordatorio=t.get("fecha_recordatorio"),
                fecha_creacion=datetime.utcnow(),
                fecha_actualizacion=datetime.utcnow()
            )
            db.add(nueva)
            resultados["creadas"] += 1

    db.commit()
    return {
        "mensaje": "Sincronización completa.",
        "resultado": resultados
    }

# GET sincronización desde servidor hacia cliente
@router.get("/tareas/usuario/{usuario_id}/sync", response_model=dict)
def obtener_tareas_para_sincronizacion(
    usuario_id: str, 
    ultima_sincronizacion: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    Obtiene las tareas del servidor que necesitan ser sincronizadas con el cliente.
    Útil para cuando el cliente vuelve a estar online y necesita obtener las tareas
    generadas por la IA durante su tiempo offline.
    """
    query = db.query(Tarea).filter_by(usuario_id=usuario_id)
    
    # Si se proporciona fecha de última sincronización, solo obtener tareas más recientes
    if ultima_sincronizacion:
        query = query.filter(Tarea.fecha_creacion > ultima_sincronizacion)
    
    # Ordenar por fecha de creación (más recientes primero)
    tareas = query.order_by(Tarea.fecha_creacion.desc()).all()
    
    return {
        "mensaje": f"Se encontraron {len(tareas)} tareas para sincronizar",
        "tareas": [tarea_to_dict(t) for t in tareas],
        "total": len(tareas),
        "ultima_sincronizacion": datetime.utcnow().isoformat()
    }

# POST marcar tareas como sincronizadas en el cliente
@router.post("/tareas/usuario/{usuario_id}/marcar-sincronizadas", response_model=dict)
def marcar_tareas_sincronizadas(
    usuario_id: str, 
    request: MarcarSincronizadasRequest,
    db: Session = Depends(get_db)
):
    """
    Marca las tareas como sincronizadas en el cliente.
    Útil para confirmar que las tareas fueron recibidas correctamente.
    """
    if not request.tarea_ids:
        raise HTTPException(status_code=400, detail="Se requiere una lista de IDs de tareas.")
    
    tareas_actualizadas = 0
    for tarea_id in request.tarea_ids:
        tarea = db.query(Tarea).filter_by(id=tarea_id, usuario_id=usuario_id).first()
        if tarea:
            tarea.sincronizada = True
            tarea.fecha_actualizacion = datetime.utcnow()
            tareas_actualizadas += 1
    
    db.commit()
    
    return {
        "mensaje": f"Se marcaron {tareas_actualizadas} tareas como sincronizadas",
        "tareas_actualizadas": tareas_actualizadas
    }

