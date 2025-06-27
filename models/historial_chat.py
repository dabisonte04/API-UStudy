from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey
from config import Base
import uuid
from datetime import datetime

def generate_uuid():
    return str(uuid.uuid4())

class HistorialChat(Base):
    __tablename__ = "historial_chat"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    usuario_id = Column(String(64), ForeignKey("usuarios.id"), nullable=False)
    mensaje_usuario = Column(Text, nullable=False)
    respuesta_ia = Column(Text, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    recomendacion_formulario = Column(Boolean, default=False)
