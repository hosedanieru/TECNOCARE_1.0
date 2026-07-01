# Chatbot TecnoCare-IA — integración en `back_t`

Esta es la misma lógica del chatbot RAG que tenías en el proyecto académico
(`chatbot.zip`), adaptada al dominio de **TecnoCare** (equipos, mantenimientos,
usuarios) y verificada con tests automatizados (13/13 OK).

## 1. Qué cambia respecto al chatbot original

| Original (PLANIFY)                          | TecnoCare                                         |
|----------------------------------------------|----------------------------------------------------|
| Roles: ESTUDIANTE / DOCENTE / COORDINADOR / ADMINISTRATIVO | Roles: TÉCNICO / SUPERVISOR / ADMINISTRADOR |
| Contexto: fichas, horarios, docentes, aulas   | Contexto: equipos, mantenimientos, alertas, costos |
| `CHRONOSIAChatbot`                            | `TecnoCareChatbot`                                  |
| Colección Chroma `planify`                    | Colección Chroma `tecnocare`                        |
| `indexer.py` (faltaba el código fuente)       | Reescrito como clase `Indexer` reutilizable + management command |

Arquitectura idéntica: **Groq (LLM) + Chroma (vectorstore) + HuggingFace
embeddings multilenguaje**, con un `ContextBuilder` que arma el contexto en
tiempo real según el rol antes de llamar al LLM (RAG + contexto de rol).

### Lógica de contexto por rol (`chatbot/services/context_builder.py`)
- **TÉCNICO**: solo ve sus mantenimientos pendientes/en proceso, los
  programados para hoy y los equipos donde es responsable (con sus alertas).
- **SUPERVISOR / ADMINISTRADOR**: ven todo el sistema — equipos por estado,
  alertas de mantenimiento vencido/próximo, mantenimientos por estado, carga
  de trabajo por técnico, costos del mes y usuarios activos por rol.

## 2. Archivos nuevos

```
chatbot/
├── apps.py
├── urls.py                      # POST /api/chat/
├── views.py                     # ChatbotView (JWT + throttle 'chat')
├── services/
│   ├── chatbot_service.py       # TecnoCareChatbot (Groq + Chroma + HF embeddings)
│   ├── context_builder.py       # Contexto en tiempo real por rol
│   └── indexer.py               # Indexador RAG (equipos/categorías/mantenimientos)
├── tasks/
│   └── indexer_task.py          # Tarea Celery opcional (si más adelante agregas Celery)
├── management/commands/
│   └── reindexar_chatbot.py     # Alternativa SIN Celery: `python manage.py reindexar_chatbot`
└── tests/
    └── test_chatbot.py          # 13 tests (ContextBuilder, servicio LLM, Indexer, endpoint)
```

`config/settings.py` y `config/urls.py` ya quedaron actualizados:
- `'chatbot'` agregado a `INSTALLED_APPS`.
- `path('api/', include('chatbot.urls'))` agregado.
- `DEFAULT_THROTTLE_RATES = {'chat': '30/minute'}` (configurable con `CHAT_THROTTLE_RATE`).
- `GROQ_API_KEY` y `CHROMA_DIR` leídos desde `.env`.

Si ya tienes tu propio `manage.py`, ignora el que viene en este zip (es el
estándar de Django, solo está por si te sirve de referencia).

## 3. Pasos para dejarlo funcionando

1. **Copia la carpeta `chatbot/`** a la raíz de tu proyecto `back_t`
   (al mismo nivel que `usuarios/`, `equipos/`, etc.).
2. **Aplica los mismos cambios** a tu `config/settings.py` y `config/urls.py`
   reales (o reemplázalos por los de este zip si no los has tocado).
3. **Agrega a tu `.env`:**
   ```
   GROQ_API_KEY=tu_api_key_de_groq
   CHROMA_DIR=./chroma_db
   CHAT_THROTTLE_RATE=30/minute
   ```
4. **Instala las dependencias del chatbot** (no estaban en `back_t`):
   ```bash
   pip install langchain-groq langchain-chroma langchain-huggingface langchain-core sentence-transformers
   ```
5. **Indexa los datos** (equipos, categorías y mantenimientos finalizados)
   para que el RAG tenga información que recuperar:
   ```bash
   python manage.py reindexar_chatbot
   ```
   (o usa la tarea Celery `chatbot.reindexar` si ya tienes Celery corriendo).
6. **Prueba el endpoint:**
   ```bash
   curl -X POST http://localhost:8000/api/chat/ \
     -H "Authorization: Bearer <tu_access_token>" \
     -H "Content-Type: application/json" \
     -d '{"pregunta": "¿Qué equipos tienen mantenimiento vencido?", "historial": []}'
   ```

## 4. Tests

Los tests mockean las librerías de IA (no necesitas Groq ni modelos
descargados para correrlos) y validan: el contexto por rol, el servicio del
LLM, el indexador y el endpoint completo.

```bash
python manage.py test chatbot --settings=config.settings_test
```

`config/settings_test.py` es un settings auxiliar con SQLite en memoria, útil
si no quieres levantar PostgreSQL solo para correr tests. Es opcional: si ya
tienes tu propia config de test, ignóralo.

**Resultado verificado en este entorno: 13/13 tests OK.**
