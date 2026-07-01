from django.conf import settings
from django.core.management.base import BaseCommand

from chatbot.services.indexer import Indexer


class Command(BaseCommand):
    help = 'Reindexa equipos, categorías y mantenimientos en Chroma para el chatbot (RAG).'

    def handle(self, *args, **options):
        chroma_dir = getattr(settings, 'CHROMA_DIR', './chroma_db')
        total = Indexer(persist_directory=str(chroma_dir)).indexar()
        self.stdout.write(self.style.SUCCESS(f'{total} documentos indexados.'))
