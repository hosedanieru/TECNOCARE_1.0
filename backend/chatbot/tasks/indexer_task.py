"""
Tarea Celery opcional para reindexar el contenido del sistema en Chroma.

TecnoCare (back_t) no trae Celery configurado en este momento. Esta tarea
queda lista para usarse en cuanto se agregue 'celery' a settings; mientras
tanto, usa el management command equivalente:

    python manage.py reindexar_chatbot
"""
try:
    from celery import shared_task
except ImportError:  # Celery aún no está instalado en el proyecto
    shared_task = None


def _reindexar():
    from django.conf import settings
    from chatbot.services.indexer import Indexer

    chroma_dir = getattr(settings, 'CHROMA_DIR', './chroma_db')
    Indexer(persist_directory=str(chroma_dir)).indexar()


if shared_task is not None:
    @shared_task(name='chatbot.reindexar')
    def reindexar_datos_sistema():
        _reindexar()
