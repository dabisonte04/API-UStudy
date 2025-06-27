from sqlalchemy import Column, String
from config import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(String(64), primary_key=True, default=generate_uuid)
    nombre = Column(String(100), nullable=False)
    correo = Column(String(100), unique=True, nullable=False)
    contrasena_hash = Column(String(255), nullable=False)
    u_id = Column(String(64), nullable=True)
