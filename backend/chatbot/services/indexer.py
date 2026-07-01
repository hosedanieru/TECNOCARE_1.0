"""
Indexador de documentos del sistema TecnoCare para búsqueda semántica (RAG).

Recorre equipos, categorías y mantenimientos relevantes y los convierte en
Documents de LangChain que se guardan en Chroma, para que el chatbot pueda
recuperarlos por similitud semántica además del contexto en tiempo real
que entrega ContextBuilder.
"""
from .chatbot_service import CHROMA_COLLECTION


class Indexer:

    def __init__(self, persist_directory: str = './chroma_db'):
        self.persist_directory = persist_directory

    def _build_documents(self):
        from langchain_core.documents import Document

        docs = []

        # ── Equipos ──────────────────────────────────────────────────────
        try:
            from equipos.models import Equipo

            for eq in Equipo.objects.exclude(estado=Equipo.Estado.DADO_DE_BAJA).select_related('categoria', 'responsable'):
                responsable = eq.responsable.nombre_completo if eq.responsable else 'sin asignar'
                docs.append(Document(
                    page_content=(
                        f"Equipo {eq.codigo_interno} — {eq.nombre} ({eq.categoria.nombre}). "
                        f"Marca: {eq.marca or 'N/D'}, modelo: {eq.modelo or 'N/D'}. "
                        f"Ubicación: {eq.ubicacion}. Estado: {eq.get_estado_display()}. "
                        f"Responsable: {responsable}. "
                        f"Frecuencia de mantenimiento: cada {eq.frecuencia_mantenimiento_dias} días."
                    ),
                    metadata={'tipo': 'equipo', 'id': eq.pk},
                ))
        except Exception as e:
            print(f'[indexer] Error equipos: {e}')

        # ── Categorías de equipo ────────────────────────────────────────
        try:
            from equipos.models import CategoriaEquipo

            for c in CategoriaEquipo.objects.all():
                docs.append(Document(
                    page_content=f"Categoría de equipo {c.nombre}: {c.descripcion or 'sin descripción'}.",
                    metadata={'tipo': 'categoria', 'id': c.pk},
                ))
        except Exception as e:
            print(f'[indexer] Error categorías: {e}')

        # ── Mantenimientos (últimos finalizados, útil como histórico) ──────
        try:
            from mantenimientos.models import Mantenimiento

            recientes = (
                Mantenimiento.objects
                .filter(estado=Mantenimiento.Estado.FINALIZADO)
                .select_related('equipo', 'tecnico_asignado')
                .order_by('-fecha_finalizacion')[:200]
            )
            for m in recientes:
                tecnico = m.tecnico_asignado.nombre_completo if m.tecnico_asignado else 'sin asignar'
                docs.append(Document(
                    page_content=(
                        f"Mantenimiento {m.get_tipo_display()} del equipo {m.equipo.codigo_interno} "
                        f"({m.equipo.nombre}): {m.titulo}. Diagnóstico: {m.diagnostico or 'N/D'}. "
                        f"Solución aplicada: {m.solucion_aplicada or 'N/D'}. "
                        f"Técnico: {tecnico}. Costo total: ${m.costo_total}."
                    ),
                    metadata={'tipo': 'mantenimiento', 'id': m.pk},
                ))
        except Exception as e:
            print(f'[indexer] Error mantenimientos: {e}')

        return docs

    def indexar(self) -> int:
        """Reconstruye la colección de Chroma con el estado actual del sistema."""
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        docs = self._build_documents()
        if not docs:
            print('[indexer] Sin documentos para indexar.')
            return 0

        embeddings = HuggingFaceEmbeddings(
            model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
            model_kwargs={'device': 'cpu'},
        )

        Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            persist_directory=self.persist_directory,
            collection_name=CHROMA_COLLECTION,
        )
        print(f'[indexer] {len(docs)} documentos indexados correctamente.')
        return len(docs)
