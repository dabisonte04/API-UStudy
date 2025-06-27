import os
import requests
import uuid
import json
import re
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any

from config import SessionLocal
from models.estado_psicologico import EstadoPsicologico
from models.historial_chat import HistorialChat
from models.tareas import Tarea
from dotenv import load_dotenv

load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

router = APIRouter()

# ------------------ DB DEPENDENCY ------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------ HELPERS ------------------
def obtener_ultimo_estado_psicologico(db: Session, usuario_id: str):
    logger.info(f"Obteniendo último estado psicológico para usuario: {usuario_id}")
    estado = db.query(EstadoPsicologico)\
        .filter_by(usuario_id=usuario_id)\
        .order_by(EstadoPsicologico.fecha.desc())\
        .first()
    logger.info(f"Estado encontrado: {estado.nivel if estado else 'None'}")
    return estado

def obtener_historial_chat(db: Session, usuario_id: str, offset=0, limit=10):
    logger.info(f"Obteniendo historial de chat para usuario: {usuario_id}, offset: {offset}, limit: {limit}")
    historial = db.query(HistorialChat)\
        .filter_by(usuario_id=usuario_id)\
        .order_by(HistorialChat.fecha.desc())\
        .offset(offset)\
        .limit(limit)\
        .all()[::-1]  # orden cronológico
    logger.info(f"Historial obtenido: {len(historial)} mensajes")
    return historial

def extraer_bloque_tareas(contenido: str) -> list:
    logger.info("Extrayendo bloque de tareas del contenido")
    
    # Patrón para extraer JSON de bloques de código markdown
    patterns = [
        r'```json\s*(\[[\s\S]+?\])\s*```',  # JSON en bloque de código markdown
        r'```\s*(\[[\s\S]+?\])\s*```',      # JSON en bloque de código genérico
        r'Bloque de tareas sugeridas:\s*(\[[\s\S]+?\])',  # Formato original
        r'(\[[\s\S]*?"titulo"[\s\S]*?"descripcion"[\s\S]*?"prioridad"[\s\S]*?\])',  # JSON con campos específicos
    ]
    
    for pattern in patterns:
        match = re.search(pattern, contenido, re.IGNORECASE)
        if match:
            try:
                json_str = match.group(1).strip()
                logger.info(f"JSON encontrado con patrón: {pattern[:50]}...")
                logger.info(f"JSON extraído: {json_str[:200]}...")
                
                tareas = json.loads(json_str)
                if isinstance(tareas, list):
                    logger.info(f"Tareas extraídas: {len(tareas)} tareas")
                    return tareas
                else:
                    logger.warning("JSON encontrado pero no es una lista")
            except json.JSONDecodeError as e:
                logger.error(f"Error al parsear JSON: {e}")
                logger.error(f"JSON problemático: {json_str}")
                continue
            except Exception as e:
                logger.error(f"Error inesperado al parsear tareas: {e}")
                continue
    
    logger.info("No se encontraron tareas en el contenido")
    return []

def ya_recomendo_formulario(historial: list) -> bool:
    logger.info("Verificando si ya se recomendó el formulario")
    for h in historial:
        # Verificar el campo booleano primero
        if hasattr(h, 'recomendacion_formulario') and h.recomendacion_formulario:
            logger.info("Ya se recomendó el formulario previamente (campo booleano)")
            return True
        
        # Verificar frases variadas en el texto
        respuesta_lower = h.respuesta_ia.lower()
        frases_recomendacion = [
            "completar la evaluación emocional",
            "evaluación emocional",
            "cuestionario emocional",
            "formulario de evaluación",
            "evaluación inicial",
            "cuestionario inicial",
            "evaluación psicológica",
            "formulario psicológico",
            "evaluar tu estado emocional",
            "completar el formulario",
            "realizar la evaluación"
        ]
        
        for frase in frases_recomendacion:
            if frase in respuesta_lower:
                logger.info(f"Ya se recomendó el formulario previamente (frase: {frase})")
                return True
                
    logger.info("No se ha recomendado el formulario previamente")
    return False

def verificar_y_guardar_tareas_historial(db: Session, usuario_id: str, historial: list):
    """Verifica si las tareas mencionadas en el historial están en la BD y las guarda si no existen"""
    logger.info(f"Verificando tareas del historial para usuario: {usuario_id}")
    
    # Obtener todas las tareas existentes del usuario para evitar duplicados
    tareas_existentes = db.query(Tarea).filter_by(usuario_id=usuario_id, origen="ia").all()
    titulos_existentes = {tarea.titulo for tarea in tareas_existentes}
    
    logger.info(f"Tareas existentes en BD: {len(tareas_existentes)}")
    logger.info(f"Títulos existentes: {titulos_existentes}")
    
    tareas_guardadas = 0
    
    for h in historial:
        if h.respuesta_ia:
            logger.info(f"Procesando mensaje del historial: {h.respuesta_ia[:100]}...")
            
            # Primero intentar extraer tareas del JSON original (si existe)
            tareas_encontradas = extraer_bloque_tareas(h.respuesta_ia)
            if tareas_encontradas:
                logger.info(f"Encontradas {len(tareas_encontradas)} tareas en JSON del mensaje")
            else:
                # Si no hay JSON, buscar en texto limpio
                tareas_encontradas = buscar_tareas_en_texto_limpio(h.respuesta_ia)
                if tareas_encontradas:
                    logger.info(f"Encontradas {len(tareas_encontradas)} tareas en texto limpio")
            
            if tareas_encontradas:
                for tarea_data in tareas_encontradas:
                    titulo = tarea_data.get("titulo", "")
                    
                    # Verificar si ya existe una tarea con el mismo título
                    if titulo not in titulos_existentes:
                        logger.info(f"Guardando nueva tarea del historial: {titulo}")
                        nueva_tarea = Tarea(
                            id=str(uuid.uuid4()),
                            usuario_id=usuario_id,
                            titulo=titulo[:100],
                            descripcion=tarea_data.get("descripcion", ""),
                            prioridad=tarea_data.get("prioridad", "media"),
                            origen="ia",
                            fecha_creacion=datetime.utcnow(),
                            fecha_actualizacion=datetime.utcnow(),
                            sincronizada=False,
                            completada=False
                        )
                        db.add(nueva_tarea)
                        titulos_existentes.add(titulo)
                        tareas_guardadas += 1
                    else:
                        logger.info(f"Tarea ya existe en BD: {titulo}")
    
    if tareas_guardadas > 0:
        try:
            db.commit()
            logger.info(f"Tareas del historial procesadas correctamente: {tareas_guardadas} nuevas tareas guardadas")
        except Exception as e:
            logger.error(f"Error al guardar tareas del historial: {e}")
            db.rollback()
    else:
        logger.info("No se encontraron nuevas tareas para guardar")

def buscar_tareas_en_texto_limpio(texto: str) -> list:
    """Busca patrones de tareas en texto limpio (sin JSON)"""
    logger.info("Buscando tareas en texto limpio")
    
    tareas_encontradas = []
    
    # Buscar específicamente el patrón que vemos en los logs
    # "Aquí tienes algunas sugerencias sencillas por si quieres probarlas..."
    if "sugerencias" in texto.lower() or "tareas" in texto.lower():
        logger.info("Texto contiene sugerencias, buscando tareas específicas")
        
        # Buscar títulos específicos que sabemos que están en el mensaje
        titulos_conocidos = [
            "Reconectar con algo que te gustaba",
            "Desahogar preocupaciones", 
            "Microdescanso consciente"
        ]
        
        for titulo in titulos_conocidos:
            if titulo in texto:
                logger.info(f"Encontrado título conocido: {titulo}")
                
                # Buscar la descripción después del título
                # Buscar desde el título hasta el siguiente punto o salto de línea
                titulo_index = texto.find(titulo)
                if titulo_index != -1:
                    # Buscar la descripción después del título
                    texto_despues = texto[titulo_index + len(titulo):]
                    
                    # Buscar la descripción entre comillas o después de ":"
                    descripcion = ""
                    if '":' in texto_despues:
                        # Formato JSON
                        match = re.search(r'":\s*"([^"]+)"', texto_despues)
                        if match:
                            descripcion = match.group(1)
                    else:
                        # Formato texto normal
                        # Buscar hasta el siguiente punto o salto de línea
                        match = re.search(r'[:]\s*([^.]*?)(?=\n|\.|$)', texto_despues)
                        if match:
                            descripcion = match.group(1).strip()
                    
                    # Determinar prioridad basada en el contexto
                    prioridad = "media"
                    if "alta" in texto_despues.lower():
                        prioridad = "alta"
                    elif "baja" in texto_despues.lower():
                        prioridad = "baja"
                    
                    if descripcion:
                        tareas_encontradas.append({
                            "titulo": titulo,
                            "descripcion": descripcion,
                            "prioridad": prioridad
                        })
                        logger.info(f"Tarea extraída: {titulo} - {descripcion[:50]}...")
    
    # También buscar patrones generales
    patrones_tareas = [
        # Patrón: "Título: descripción (prioridad)"
        r'([A-Z][^:]+):\s*([^()]+?)\s*\((alta|media|baja)\)',
        # Patrón: "• Título - descripción"
        r'[•\-\*]\s*([^:]+?)\s*[:\-]\s*([^•\-\*]+?)(?=\s*[•\-\*]|$)',
        # Patrón: "1. Título: descripción"
        r'\d+\.\s*([^:]+?):\s*([^1-9]+?)(?=\s*\d+\.|$)',
    ]
    
    for patron in patrones_tareas:
        matches = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            if len(match) >= 2:
                titulo = match[0].strip()
                descripcion = match[1].strip()
                prioridad = match[2] if len(match) > 2 else "media"
                
                # Validar que el título tenga sentido
                if len(titulo) > 3 and len(descripcion) > 10:
                    tareas_encontradas.append({
                        "titulo": titulo,
                        "descripcion": descripcion,
                        "prioridad": prioridad.lower()
                    })
                    logger.info(f"Tarea encontrada por patrón: {titulo}")
    
    logger.info(f"Total tareas encontradas en texto limpio: {len(tareas_encontradas)}")
    return tareas_encontradas

def limpiar_respuesta_ia(contenido: str) -> str:
    """Limpia la respuesta de la IA removiendo bloques de código JSON"""
    logger.info("Limpiando respuesta de IA")
    
    # Patrones para remover bloques de código JSON
    patterns = [
        r'```json\s*\[[\s\S]+?\]\s*```',  # JSON en bloque de código markdown
        r'```\s*\[[\s\S]+?\]\s*```',      # JSON en bloque de código genérico
        r'Bloque de tareas sugeridas:\s*\[[\s\S]+?\]',  # Formato original
    ]
    
    contenido_limpio = contenido
    for pattern in patterns:
        contenido_limpio = re.sub(pattern, '', contenido_limpio, flags=re.IGNORECASE)
    
    # Limpiar líneas vacías múltiples
    contenido_limpio = re.sub(r'\n\s*\n\s*\n', '\n\n', contenido_limpio)
    contenido_limpio = contenido_limpio.strip()
    
    logger.info(f"Respuesta limpia: {contenido_limpio[:100]}...")
    return contenido_limpio

# ------------------ RUTA PRINCIPAL ------------------
@router.post("/chat/ia")
async def conversar_con_ia(payload: Dict[str, Any], db: Session = Depends(get_db)):
    usuario_id = payload.get("usuario_id")
    mensaje_usuario = payload.get("mensaje")

    logger.info(f"Conversación con IA iniciada para usuario: {usuario_id}")
    logger.info(f"Mensaje del usuario: {mensaje_usuario}")

    if not usuario_id or not mensaje_usuario:
        logger.error("usuario_id o mensaje faltantes")
        raise HTTPException(status_code=400, detail="usuario_id y mensaje son requeridos.")

    estado = obtener_ultimo_estado_psicologico(db, usuario_id)
    historial = obtener_historial_chat(db, usuario_id)
    recomendo_formulario_previamente = ya_recomendo_formulario(historial)
    historial_texto = "\n".join([
        f"Usuario: {h.mensaje_usuario}\nIA: {h.respuesta_ia}"
        for h in historial
    ])

    logger.info(f"Estado psicológico: {estado.nivel if estado else 'None'}")
    logger.info(f"Historial: {len(historial)} mensajes")
    logger.info(f"Ya recomendó formulario: {recomendo_formulario_previamente}")

    # Construir prompt base
    prompt_base = f"""
Actúa como un asistente terapéutico especializado en salud mental y bienestar emocional. Estás interactuando con un usuario que atraviesa un proceso de recuperación emocional. Tu propósito exclusivo es brindar apoyo conversacional empático, sin realizar diagnósticos clínicos ni emitir juicios.

⚠️ IMPORTANTE: Tu función está estrictamente limitada al contexto de salud mental. No puedes brindar información, consejos ni ayuda en temas que no sean emocionales o relacionados al bienestar personal.

📌 Temas estrictamente prohibidos (no debes responder sobre esto):
- Programación, código, desarrollo de software o IA
- Matemáticas, física o ciencia académica
- Ayuda en tareas, trabajos, exámenes o solución de ejercicios
- Historia, cultura general, geografía, idiomas o biología
- Tecnología, juegos, política o economía
- Opiniones sobre productos, gustos, películas o arte
- Religión, creencias personales o filosofía

⚠️ Si el usuario realiza una pregunta fuera del contexto emocional o busca ayuda en tareas, responde exclusivamente con una frase como alguna de las siguientes (elige la más adecuada):
1. "Mi función es acompañarte emocionalmente. ¿Quieres contarme cómo te has sentido últimamente?"
2. "Estoy aquí para escucharte y ayudarte en tu proceso emocional, ¿quieres que hablemos de cómo estás hoy?"
3. "Puedo ayudarte a entender lo que sientes o apoyarte si estás pasando por algo difícil. ¿Te gustaría que hablemos sobre eso?"
4. "No puedo ayudarte con ese tema, pero estoy aquí para hablar contigo sobre lo que sientes y cómo te afecta."
5. "Mi propósito no es resolver ejercicios ni responder preguntas técnicas, pero puedo escucharte si necesitas desahogarte."

✏️ Asegúrate de que tus respuestas varíen en longitud, estructura y tono. Algunas pueden ser breves y directas, otras un poco más reflexivas. No uses lenguaje robótico ni repitas frases.

🎯 Evita listas, repeticiones o respuestas artificiales. Sé humano, cercano, realista.

📜 Historial de conversación reciente:
{historial_texto}

Usuario: {mensaje_usuario}
"""

    if estado:
        logger.info("Construyendo prompt con estado psicológico")
        prompt = prompt_base + f"""

📋 Estado emocional del usuario:
Nivel: {estado.nivel}
Descripción: {estado.descripcion}

💡 Si consideras que es útil, incluye al final de tu respuesta un bloque con tareas sugeridas para el usuario en el siguiente formato JSON:
Bloque de tareas sugeridas:
[
  {{
    "titulo": "...",
    "descripcion": "...",
    "prioridad": "alta|media|baja"
  }},
  ...
]
"""
    else:
        if not recomendo_formulario_previamente:
            logger.info("Construyendo prompt con recomendación de formulario")
            prompt = prompt_base + """

⚠️ El usuario aún no ha completado su evaluación emocional inicial. 
Responde de forma empática, y al final incluye esta sugerencia (marcada para el sistema): 
[RECOMENDAR_FORMULARIO]
"""
        else:
            logger.info("Construyendo prompt sin recomendación (ya se recomendó)")
            prompt = prompt_base

    try:
        logger.info("Enviando petición a DeepSeek")
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Eres un asistente terapéutico de salud mental."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.6,
                "max_tokens": 700
            }
        )

        logger.info(f"Respuesta de DeepSeek recibida. Status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Error en DeepSeek API: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"Error en DeepSeek API: {response.text}")

        response.raise_for_status()
        data = response.json()
        contenido_ia = data["choices"][0]["message"]["content"]
        logger.info(f"Contenido de IA recibido: {contenido_ia[:100]}...")

        mostrar_sugerencia_formulario = "[RECOMENDAR_FORMULARIO]" in contenido_ia
        contenido_ia = contenido_ia.replace("[RECOMENDAR_FORMULARIO]", "").strip()
        logger.info(f"Mostrar sugerencia formulario: {mostrar_sugerencia_formulario}")

        # Extraer tareas antes de limpiar la respuesta
        tareas = []
        if estado:
            tareas = extraer_bloque_tareas(contenido_ia)
            logger.info(f"Tareas extraídas: {len(tareas)}")

        # Limpiar la respuesta para el usuario
        contenido_ia_limpio = limpiar_respuesta_ia(contenido_ia)
        logger.info(f"Respuesta limpia para usuario: {contenido_ia_limpio[:100]}...")

        logger.info("Guardando historial en BD")
        nuevo_chat = HistorialChat(
            id=str(uuid.uuid4()),
            usuario_id=usuario_id,
            mensaje_usuario=mensaje_usuario,
            respuesta_ia=contenido_ia_limpio,  # Guardar la versión limpia
            fecha=datetime.utcnow(),
            recomendacion_formulario=mostrar_sugerencia_formulario
        )
        db.add(nuevo_chat)

        if tareas:
            logger.info(f"Guardando {len(tareas)} tareas en BD")
            for t in tareas:
                tarea = Tarea(
                    id=str(uuid.uuid4()),
                    usuario_id=usuario_id,
                    titulo=t.get("titulo", "Sin título")[:100],
                    descripcion=t.get("descripcion"),
                    prioridad=t.get("prioridad", "media"),
                    origen="ia",
                    fecha_creacion=datetime.utcnow(),
                    fecha_actualizacion=datetime.utcnow(),
                    sincronizada=False,
                    completada=False
                )
                db.add(tarea)

        verificar_y_guardar_tareas_historial(db, usuario_id, historial)

        db.commit()
        logger.info("Conversación completada exitosamente")

        return {
            "mensaje": {
                "text": contenido_ia_limpio,  # Enviar la versión limpia
                "isUser": False,
                "esRecomendacion": mostrar_sugerencia_formulario
            },
            "tareas_generadas": tareas
        }

    except Exception as e:
        logger.error(f"Error en conversación con IA: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ------------------ NUEVO ENDPOINT CON PAGINACIÓN ------------------
@router.get("/chat/ia/historial/{usuario_id}")
def obtener_historial_chat_usuario(
    usuario_id: str,
    offset: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    logger.info(f"Obteniendo historial de chat para usuario: {usuario_id}, offset: {offset}, limit: {limit}")
    
    total = db.query(HistorialChat).filter_by(usuario_id=usuario_id).count()
    logger.info(f"Total de mensajes en BD: {total}")
    
    # Para paginación correcta desde los mensajes más recientes
    # Si offset=0, queremos los últimos 'limit' mensajes
    # Si offset>0, queremos los mensajes más antiguos
    if offset == 0:
        # Primera página: obtener los últimos 'limit' mensajes
        historial = db.query(HistorialChat)\
            .filter_by(usuario_id=usuario_id)\
            .order_by(HistorialChat.fecha.desc())\
            .limit(limit)\
            .all()
        # Invertir para orden cronológico
        historial = historial[::-1]
    else:
        # Páginas siguientes: obtener mensajes más antiguos
        # Calculamos cuántos mensajes saltar desde el final
        skip_count = total - offset
        if skip_count < 0:
            skip_count = 0
            
        historial = db.query(HistorialChat)\
            .filter_by(usuario_id=usuario_id)\
            .order_by(HistorialChat.fecha.asc())\
            .offset(skip_count)\
            .limit(limit)\
            .all()

    logger.info(f"Historial obtenido: {len(historial)} mensajes")
    
    # Solo procesar tareas en la primera carga (offset = 0) para evitar procesamiento repetitivo
    if offset == 0:
        logger.info("Procesando tareas del historial en primera carga")
        verificar_y_guardar_tareas_historial(db, usuario_id, historial)
    
    return {
        "total": total,
        "cantidad": len(historial),
        "mensajes": [
            {
                "mensaje_usuario": h.mensaje_usuario,
                "respuesta_ia": h.respuesta_ia,
                "fecha": h.fecha.isoformat()
            } for h in historial
        ]
    }

# ------------------ NUEVO ENDPOINT PARA PROCESAR TAREAS DEL HISTORIAL ------------------
@router.post("/chat/ia/procesar-tareas-historial/{usuario_id}")
def procesar_tareas_del_historial(usuario_id: str, db: Session = Depends(get_db)):
    """Procesa tareas del historial de chat y las guarda en la base de datos"""
    logger.info(f"Procesando tareas del historial para usuario: {usuario_id}")
    
    try:
        # Obtener todo el historial del usuario
        historial = db.query(HistorialChat)\
            .filter_by(usuario_id=usuario_id)\
            .order_by(HistorialChat.fecha.desc())\
            .all()
        
        logger.info(f"Historial total encontrado: {len(historial)} mensajes")
        
        # Procesar tareas del historial
        verificar_y_guardar_tareas_historial(db, usuario_id, historial)
        
        # Contar tareas totales del usuario
        total_tareas = db.query(Tarea).filter_by(usuario_id=usuario_id).count()
        tareas_ia = db.query(Tarea).filter_by(usuario_id=usuario_id, origen="ia").count()
        
        return {
            "mensaje": "Tareas del historial procesadas correctamente",
            "total_tareas": total_tareas,
            "tareas_ia": tareas_ia,
            "mensajes_procesados": len(historial)
        }
        
    except Exception as e:
        logger.error(f"Error al procesar tareas del historial: {e}")
        raise HTTPException(status_code=500, detail=str(e))
