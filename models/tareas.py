from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from config import Base
import uuid
from datetime import datetime

def generate_uuid():
    return str(uuid.uuid4())

class Tarea(Base):
    __tablename__ = "tareas"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    usuario_id = Column(String(64), ForeignKey("usuarios.id"), nullable=False)

    titulo = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)

    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sincronizada = Column(Boolean, default=False)  # Si ya fue sincronizada con la API
    completada = Column(Boolean, default=False)    # Si el usuario la ha marcado como completada

    prioridad = Column(String(20), nullable=True)  # Ej: "alta", "media", "baja"
    fecha_recordatorio = Column(DateTime, nullable=True)  # Para alertas o notificaciones futuras
    origen = Column(String(20), default="usuario")  # "usuario" o "ia"
