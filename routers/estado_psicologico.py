import os
import requests
import uuid
import logging
import json
import re
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import List, Dict, Any

from config import SessionLocal
from models.estado_psicologico import EstadoPsicologico
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

# ------------------ REQUEST SCHEMA ------------------
class RespuestaItem(BaseModel):
    pregunta: str
    valor_respuesta: int

class RespuestaFormulario(BaseModel):
    usuario_id: str
    respuestas: List[RespuestaItem]

    class Config:
        extra = "forbid"

class ActivarEvaluacionRequest(BaseModel):
    usuario_id: str

    class Config:
        extra = "forbid"

# ------------------ PROMPT TEMPLATE ------------------
def construir_prompt(respuestas: List[RespuestaItem]) -> str:
    logger.info(f"Construyendo prompt para {len(respuestas)} respuestas")
    respuestas_texto = "\n".join(
        [f"- {r.pregunta} → {r.valor_respuesta}" for r in respuestas]
    )

    prompt = f"""
Actúa como un psicólogo clínico especializado en bienestar emocional.

A continuación se presentan las respuestas de un usuario a un cuestionario estructurado en 4 dimensiones: ánimo (depresión), ansiedad, estrés y apoyo emocional. Cada pregunta tiene una respuesta entre 0 (nunca) y 3 (siempre).

Analiza las respuestas y realiza lo siguiente:

1. Calcula el promedio por dimensión (depresión, ansiedad, estrés y apoyo).
2. Estima el estado psicológico general del usuario según el siguiente sistema de niveles:
   - verde: usuario estable y emocionalmente bien
   - amarillo_claro: señales leves de afectación emocional
   - amarillo: síntomas moderados que requieren atención
   - naranja: signos graves que requieren acciones urgentes
   - rojo: síntomas críticos, posible riesgo emocional

3. Genera una descripción empática y profesional del estado del usuario.
4. Sugiere al menos 3 recomendaciones prácticas para su bienestar emocional.

⚠️ IMPORTANTE: Responde ÚNICAMENTE con el JSON en el formato especificado. No incluyas texto adicional, explicaciones, ni bloques de código markdown.

Formato de respuesta (JSON puro):
{{
  "nivel": "amarillo",
  "calificaciones": {{
    "animo": 2.5,
    "ansiedad": 3.2,
    "estres": 3.5,
    "apoyo": 1.0
  }},
  "descripcion": "Descripción empática del estado emocional del usuario...",
  "recomendaciones": [
    "Primera recomendación práctica",
    "Segunda recomendación práctica", 
    "Tercera recomendación práctica"
  ]
}}

Respuestas del usuario:
{respuestas_texto}
"""
    logger.info("Prompt construido exitosamente")
    return prompt.strip()

# ------------------ HELPER FUNCTIONS ------------------
def extraer_json_de_respuesta(content: str) -> dict:
    """
    Extrae el JSON válido de la respuesta de DeepSeek que puede contener markdown y texto adicional
    """
    logger.info("Extrayendo JSON de la respuesta de DeepSeek")
    
    # Buscar JSON dentro de bloques de código markdown
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
        logger.info(f"JSON encontrado en bloque markdown: {json_str[:100]}...")
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON del bloque markdown: {e}")
    
    # Si no hay bloque markdown, buscar JSON directamente
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        logger.info(f"JSON encontrado directamente: {json_str[:100]}...")
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON directo: {e}")
    
    # Si todo falla, intentar con eval (método anterior)
    logger.warning("No se pudo extraer JSON válido, intentando con eval")
    try:
        return eval(content)
    except Exception as e:
        logger.error(f"Error con eval: {e}")
        raise ValueError(f"No se pudo procesar la respuesta de DeepSeek: {content[:200]}...")

# ------------------ RUTA PRINCIPAL ------------------
@router.post("/evaluar-estado-emocional")
async def evaluar_estado_emocional(data: RespuestaFormulario, db: Session = Depends(get_db)):
    logger.info(f"Evaluación de estado emocional iniciada para usuario: {data.usuario_id}")
    logger.info(f"Número de respuestas recibidas: {len(data.respuestas)}")
    
    try:
        prompt = construir_prompt(data.respuestas)
        logger.info("Prompt construido, enviando a DeepSeek")

        response = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Eres un psicólogo clínico experto en salud mental."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 800
            }
        )
        
        logger.info(f"Respuesta de DeepSeek recibida. Status: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Error en DeepSeek API: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"Error en DeepSeek API: {response.text}")

        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        logger.info(f"Contenido recibido de DeepSeek: {content[:100]}...")
        
        resultado = extraer_json_de_respuesta(content)
        logger.info(f"Resultado procesado: nivel={resultado.get('nivel')}")

        estado = EstadoPsicologico(
            id=str(uuid.uuid4()),
            usuario_id=data.usuario_id,
            nivel=resultado.get("nivel", "amarillo"),
            descripcion=resultado.get("descripcion", ""),
            fecha=datetime.utcnow()
        )

        db.add(estado)
        db.commit()
        logger.info(f"Estado psicológico guardado en BD. ID: {estado.id}")

        return {
            "mensaje": "Evaluación completada exitosamente.",
            "estado": {
                "nivel": estado.nivel,
                "descripcion": estado.descripcion
            }
        }

    except Exception as e:
        logger.error(f"Error en evaluación de estado emocional: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/activar-evaluacion-inicial")
async def activar_evaluacion_inicial(data: ActivarEvaluacionRequest, db: Session = Depends(get_db)):
    logger.info(f"Verificando evaluación inicial para usuario: {data.usuario_id}")
    
    estado_existente = db.query(EstadoPsicologico)\
        .filter_by(usuario_id=data.usuario_id)\
        .first()

    if estado_existente:
        logger.info(f"Usuario {data.usuario_id} ya tiene evaluación registrada")
        return {
            "estado": "ya_registrado",
            "mensaje": "El perfil psicológico ya fue evaluado previamente.",
        }

    logger.info(f"Usuario {data.usuario_id} necesita evaluación inicial")
    return {
        "estado": "pendiente",
        "mensaje": "Perfil psicológico aún no evaluado. El formulario puede ser mostrado.",
    }
    