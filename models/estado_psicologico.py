from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from config import Base
import uuid
from datetime import datetime

def generate_uuid():
    return str(uuid.uuid4())

class EstadoPsicologico(Base):
    __tablename__ = "estado_psicologico"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    usuario_id = Column(String(64), ForeignKey("usuarios.id"), nullable=False)
    nivel = Column(String(20), nullable=False)  # Ej: "verde", "amarillo_claro", "amarillo", "naranja", "rojo"
    descripcion = Column(Text, nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
