"""
Servicio principal del asistente IA de TecnoCare.

Replica exactamente la misma arquitectura del chatbot académico
(CHRONOSIAChatbot): LLM vía Groq + recuperación semántica con Chroma +
embeddings locales multilenguaje, combinando el contexto en tiempo real
del rol del usuario (ContextBuilder) con la información indexada del
sistema (RAG).

Los imports de librerías pesadas (langchain, chromadb, etc.) se hacen de
forma diferida dentro de __init__, para no acoplar el arranque de Django
a la disponibilidad de esas dependencias.
"""
import os

from django.conf import settings

CHROMA_COLLECTION = 'tecnocare'


class TecnoCareChatbot:

    def __init__(self):
        # Imports diferidos: solo se cargan cuando realmente se instancia
        # el chatbot (primera petición), no al arrancar Django.
        from langchain_groq import ChatGroq
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        api_key = getattr(settings, 'GROQ_API_KEY', None) or os.getenv('GROQ_API_KEY')
        chroma_dir = getattr(settings, 'CHROMA_DIR', './chroma_db')

        self.llm = ChatGroq(
            model='llama-3.1-8b-instant',
            api_key=api_key,
            temperature=0.5,
        )

        # Embeddings locales livianos — no necesitan GPU ni servicios externos.
        self.embeddings = HuggingFaceEmbeddings(
            model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
            model_kwargs={'device': 'cpu'},
        )

        self.vectorstore = Chroma(
            embedding_function=self.embeddings,
            persist_directory=str(chroma_dir),
            collection_name=CHROMA_COLLECTION,
        )

    def responder(
        self,
        pregunta: str,
        historial: list,
        contexto_rol: str = '',
    ) -> str:
        # ── RAG: documentos indexados relevantes ───────────────────────────
        try:
            retriever = self.vectorstore.as_retriever(
                search_type='similarity',
                search_kwargs={'k': 5},
            )
            docs = retriever.invoke(pregunta)
            contexto_docs = '\n\n'.join(d.page_content for d in docs)
        except Exception:
            contexto_docs = ''

        # ── Historial de conversación (últimos 6 mensajes) ─────────────────
        historial_txt = ''
        for msg in historial[-6:]:
            rol_label = 'Usuario' if msg.get('role') == 'user' else 'Asistente'
            historial_txt += f"{rol_label}: {msg.get('content', '')}\n"

        # ── Prompt ───────────────────────────────────────────────────────
        prompt = f"""Eres TECNOCARE-IA, el asistente inteligente del sistema de gestión
de mantenimiento de equipos tecnológicos TecnoCare.
Responde siempre en español, de forma clara, precisa y directa.
No inventes información; si no la tienes, dilo explícitamente.
No reveles datos de equipos, mantenimientos o usuarios que no correspondan
al rol del solicitante.

══════════════════════════════
CONTEXTO DEL USUARIO (datos en tiempo real)
══════════════════════════════
{contexto_rol}

══════════════════════════════
INFORMACIÓN ADICIONAL DEL SISTEMA
══════════════════════════════
{contexto_docs if contexto_docs else 'Sin documentos adicionales relevantes.'}

══════════════════════════════
HISTORIAL DE CONVERSACIÓN
══════════════════════════════
{historial_txt if historial_txt else 'Inicio de conversación.'}

══════════════════════════════
PREGUNTA ACTUAL
══════════════════════════════
{pregunta}

RESPUESTA:"""

        # ChatGroq devuelve un AIMessage; extraemos el texto.
        response = self.llm.invoke(prompt)
        return response.content
