from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from config import Base
import uuid
from datetime import datetime

def generate_uuid():
    return str(uuid.uuid4())

class RespuestaPsicologica(Base):
    __tablename__ = "respuestas_psicologicas"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    usuario_id = Column(String(64), ForeignKey("usuarios.id"), nullable=False)
    pregunta = Column(String(256), nullable=False)
    valor_respuesta = Column(Integer, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
