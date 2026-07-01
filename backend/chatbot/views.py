from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication

from .services.chatbot_service import TecnoCareChatbot
from .services.context_builder import ContextBuilder

_chatbot: TecnoCareChatbot | None = None


def _get_chatbot() -> TecnoCareChatbot:
    global _chatbot
    if _chatbot is None:
        _chatbot = TecnoCareChatbot()
    return _chatbot


class ChatRateThrottle(UserRateThrottle):
    scope = 'chat'


class ChatbotView(APIView):
    """
    POST /api/chat/
    body: {"pregunta": "...", "historial": [{"role": "user"|"assistant", "content": "..."}]}

    Disponible para cualquier usuario autenticado (ADMIN, SUPERVISOR o
    TECNICO); el nivel de detalle de la respuesta depende del rol, ya que
    ContextBuilder limita qué información en tiempo real se le entrega al LLM.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    def post(self, request):
        pregunta = request.data.get('pregunta', '').strip()
        historial = request.data.get('historial', [])

        if not pregunta:
            return Response(
                {'error': 'La pregunta no puede estar vacía.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(pregunta) > 1000:
            return Response(
                {'error': 'Pregunta demasiado larga (máx. 1000 caracteres).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            contexto_rol = ContextBuilder.build(request.user)
            respuesta = _get_chatbot().responder(
                pregunta=pregunta,
                historial=historial,
                contexto_rol=contexto_rol,
            )
            return Response({
                'respuesta': respuesta,
                'rol': request.user.rol,
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
