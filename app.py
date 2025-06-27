from fastapi import FastAPI, Request
from routers import usuario as usuario_router
from routers import estado_psicologico as estado_psicologico_router
from routers import chat_ia as chat_ia_router
from routers import tareas as tareas_router

from models import usuario as usuario_model
from models import estado_psicologico as estado_psicologico_model
from models import historial_chat as historialchat_model
from models import respuestas_psicologicas as respuesta_psicologica_model
from config import engine, Base

Base.metadata.create_all(bind=engine)

# Crear instancia de FastAPI
app = FastAPI()

# Ruta base para verificar que la API está funcionando
@app.get("/")
async def root():
    return {
        "message": "UStudy API is running! 🚀",
        "status": "active",
        "version": "1.0.0",
        "endpoints": {
            "usuarios": "/usuarios",
            "estado_psicologico": "/estado-psicologico", 
            "chat_ia": "/chat/ia",
            "tareas": "/tareas"
        }
    }

# Registrar rutas
app.include_router(usuario_router.router, prefix="/usuarios")
app.include_router(estado_psicologico_router.router, prefix="/estado-psicologico")
app.include_router(chat_ia_router.router)
app.include_router(tareas_router.router)

