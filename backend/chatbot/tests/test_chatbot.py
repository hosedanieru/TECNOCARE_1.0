import sys
import types
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from usuarios.models import Usuario
from equipos.models import CategoriaEquipo, Equipo
from mantenimientos.models import Mantenimiento

from chatbot.services.context_builder import ContextBuilder
from chatbot.services.chatbot_service import TecnoCareChatbot
from chatbot.services.indexer import Indexer


def _fake_langchain_modules(llm_response='Respuesta generada por el LLM.',
                             retriever_docs=None):
    """
    TecnoCareChatbot e Indexer importan langchain_groq / langchain_chroma /
    langchain_huggingface de forma diferida (dentro de los métodos) para no
    obligar a instalar PyTorch/transformers solo para correr el proyecto
    Django. Para testear sin esas dependencias pesadas, registramos módulos
    falsos en sys.modules con dobles de prueba.
    """
    retriever_docs = retriever_docs if retriever_docs is not None else []

    groq_mod = types.ModuleType('langchain_groq')
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.return_value = MagicMock(content=llm_response)
    groq_mod.ChatGroq = MagicMock(return_value=mock_llm_instance)

    chroma_mod = types.ModuleType('langchain_chroma')
    mock_vectorstore = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = retriever_docs
    mock_vectorstore.as_retriever.return_value = mock_retriever
    chroma_cls = MagicMock(return_value=mock_vectorstore)
    chroma_cls.from_documents = MagicMock()
    chroma_mod.Chroma = chroma_cls

    hf_mod = types.ModuleType('langchain_huggingface')
    hf_mod.HuggingFaceEmbeddings = MagicMock()

    modules = {
        'langchain_groq': groq_mod,
        'langchain_chroma': chroma_mod,
        'langchain_huggingface': hf_mod,
    }
    return modules, mock_llm_instance, chroma_cls


def _crear_usuario(rol, username):
    return Usuario.objects.create_user(
        username=username,
        email=f'{username}@tecnocare.com',
        password='Clave12345!',
        rol=rol,
        first_name=username.capitalize(),
    )


def _crear_equipo(responsable=None, dias_frecuencia=30, ultimo=None):
    categoria = CategoriaEquipo.objects.create(nombre=f'Cat-{Equipo.objects.count()}')
    return Equipo.objects.create(
        codigo_interno=f'EQ-{Equipo.objects.count() + 1:04d}',
        nombre='Servidor de pruebas',
        categoria=categoria,
        ubicacion='Sala de cómputo',
        responsable=responsable,
        frecuencia_mantenimiento_dias=dias_frecuencia,
        fecha_ultimo_mantenimiento=ultimo,
        fecha_adquisicion=ultimo or date.today() - timedelta(days=400),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ContextBuilder
# ─────────────────────────────────────────────────────────────────────────────

class ContextBuilderTest(TestCase):

    def test_tecnico_ve_solo_su_informacion(self):
        tecnico = _crear_usuario(Usuario.Rol.TECNICO, 'tecnico1')
        otro_tecnico = _crear_usuario(Usuario.Rol.TECNICO, 'tecnico2')
        equipo = _crear_equipo(responsable=tecnico)
        Mantenimiento.objects.create(
            equipo=equipo,
            tipo=Mantenimiento.Tipo.PREVENTIVO,
            tecnico_asignado=tecnico,
            creado_por=tecnico,
            titulo='Revisión preventiva',
            descripcion='Chequeo general',
            fecha_programada=date.today(),
        )

        contexto = ContextBuilder.build(tecnico)

        self.assertIn('TÉCNICO', contexto)
        self.assertIn('EQ-', contexto)
        self.assertIn('Revisión preventiva', contexto)

    def test_administrador_ve_resumen_global(self):
        admin = _crear_usuario(Usuario.Rol.ADMINISTRADOR, 'admin1')
        tecnico = _crear_usuario(Usuario.Rol.TECNICO, 'tecnico3')
        _crear_equipo(responsable=tecnico)

        contexto = ContextBuilder.build(admin)

        self.assertIn('ADMINISTRADOR', contexto)
        self.assertIn('EQUIPOS POR ESTADO', contexto)
        self.assertIn('USUARIOS ACTIVOS POR ROL', contexto)

    def test_supervisor_tiene_acceso_tipo_admin(self):
        supervisor = _crear_usuario(Usuario.Rol.SUPERVISOR, 'super1')
        contexto = ContextBuilder.build(supervisor)
        self.assertIn('SUPERVISOR', contexto)
        self.assertIn('MANTENIMIENTOS POR ESTADO', contexto)

    def test_equipo_vencido_genera_alerta(self):
        admin = _crear_usuario(Usuario.Rol.ADMINISTRADOR, 'admin2')
        _crear_equipo(
            dias_frecuencia=10,
            ultimo=date.today() - timedelta(days=40),
        )
        contexto = ContextBuilder.build(admin)
        self.assertIn('VENCIDO', contexto)


# ─────────────────────────────────────────────────────────────────────────────
# TecnoCareChatbot (servicio LLM) — todo lo pesado va mockeado
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(GROQ_API_KEY='dummy-key', CHROMA_DIR='/tmp/chroma_test')
class TecnoCareChatbotTest(TestCase):

    def test_responder_devuelve_texto_del_llm(self):
        modules, mock_llm, _ = _fake_langchain_modules(
            llm_response='Respuesta generada por el LLM.'
        )
        with patch.dict(sys.modules, modules):
            chatbot = TecnoCareChatbot()
            respuesta = chatbot.responder(
                pregunta='¿Qué equipos tienen mantenimiento vencido?',
                historial=[{'role': 'user', 'content': 'Hola'}],
                contexto_rol='El usuario es ADMINISTRADOR.',
            )

        self.assertEqual(respuesta, 'Respuesta generada por el LLM.')
        mock_llm.invoke.assert_called_once()
        # El prompt enviado debe incluir el contexto del rol y la pregunta.
        prompt_enviado = mock_llm.invoke.call_args[0][0]
        self.assertIn('El usuario es ADMINISTRADOR.', prompt_enviado)
        self.assertIn('¿Qué equipos tienen mantenimiento vencido?', prompt_enviado)

    def test_responder_funciona_si_falla_el_rag(self):
        modules, mock_llm, _ = _fake_langchain_modules(llm_response='Igual respondo.')
        # Forzamos que el retriever falle para validar el fallback.
        with patch.dict(sys.modules, modules):
            chatbot = TecnoCareChatbot()
            chatbot.vectorstore.as_retriever.side_effect = Exception('chroma caído')
            respuesta = chatbot.responder(pregunta='Hola', historial=[], contexto_rol='')

        self.assertEqual(respuesta, 'Igual respondo.')


# ─────────────────────────────────────────────────────────────────────────────
# Indexer
# ─────────────────────────────────────────────────────────────────────────────

class IndexerTest(TestCase):

    def test_build_documents_incluye_equipos_y_categorias(self):
        _crear_equipo()
        indexer = Indexer(persist_directory='/tmp/chroma_test')
        docs = indexer._build_documents()

        tipos = {d.metadata['tipo'] for d in docs}
        self.assertIn('equipo', tipos)
        self.assertIn('categoria', tipos)

    def test_indexar_sin_documentos_no_falla(self):
        modules, _, chroma_cls = _fake_langchain_modules()
        with patch.dict(sys.modules, modules):
            indexer = Indexer(persist_directory='/tmp/chroma_test')
            total = indexer.indexar()

        self.assertEqual(total, 0)
        chroma_cls.from_documents.assert_not_called()

    def test_indexar_con_documentos_llama_chroma(self):
        _crear_equipo()
        modules, _, chroma_cls = _fake_langchain_modules()
        with patch.dict(sys.modules, modules):
            indexer = Indexer(persist_directory='/tmp/chroma_test')
            total = indexer.indexar()

        self.assertGreater(total, 0)
        chroma_cls.from_documents.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# ChatbotView (endpoint /api/chat/)
# ─────────────────────────────────────────────────────────────────────────────

class ChatbotViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.tecnico = _crear_usuario(Usuario.Rol.TECNICO, 'tecview')

    def test_requiere_autenticacion(self):
        response = self.client.post('/api/chat/', {'pregunta': 'Hola'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_pregunta_vacia_devuelve_400(self):
        self.client.force_authenticate(user=self.tecnico)
        response = self.client.post('/api/chat/', {'pregunta': '   '}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_pregunta_demasiado_larga_devuelve_400(self):
        self.client.force_authenticate(user=self.tecnico)
        response = self.client.post(
            '/api/chat/', {'pregunta': 'x' * 1001}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    @patch('chatbot.views._get_chatbot')
    def test_pregunta_valida_devuelve_respuesta(self, mock_get_chatbot):
        mock_service = MagicMock()
        mock_service.responder.return_value = 'Esta es la respuesta de TECNOCARE-IA.'
        mock_get_chatbot.return_value = mock_service

        self.client.force_authenticate(user=self.tecnico)
        response = self.client.post(
            '/api/chat/',
            {'pregunta': '¿Cuáles son mis mantenimientos pendientes?', 'historial': []},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['respuesta'], 'Esta es la respuesta de TECNOCARE-IA.')
        self.assertEqual(response.data['rol'], Usuario.Rol.TECNICO)
        mock_service.responder.assert_called_once()
