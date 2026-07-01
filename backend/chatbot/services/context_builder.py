"""
Construye el contexto en tiempo real que se inyecta al LLM, según el rol
del usuario autenticado. Replica la misma lógica de
chatbot/services/context_builder.py (proyecto académico) pero adaptada
al dominio de TecnoCare: equipos, mantenimientos e intervenciones.
"""
from datetime import date

from django.db.models import Count, Sum

from usuarios.models import Usuario


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _hoy_label() -> str:
    return date.today().strftime('%A %d/%m/%Y')


def _resumen_equipos(lines: list):
    try:
        from equipos.models import Equipo

        totales = (
            Equipo.objects
            .values('estado')
            .annotate(total=Count('id'))
            .order_by('estado')
        )
        lines.append("\n── EQUIPOS POR ESTADO ──")
        if totales:
            for t in totales:
                estado_label = dict(Equipo.Estado.choices).get(t['estado'], t['estado'])
                lines.append(f"  • {estado_label}: {t['total']}")
        else:
            lines.append("  No hay equipos registrados.")
    except Exception as e:
        lines.append(f"  (Error resumen equipos: {e})")


def _equipos_en_alerta(lines: list, queryset=None, titulo='EQUIPOS EN ALERTA DE MANTENIMIENTO'):
    """alerta_vencida / alerta_proxima son @property en Python, no se pueden
    filtrar directamente en la BD, así que se evalúan en memoria."""
    try:
        from equipos.models import Equipo

        qs = queryset if queryset is not None else Equipo.objects.exclude(
            estado=Equipo.Estado.DADO_DE_BAJA
        )
        qs = qs.select_related('categoria', 'responsable')

        vencidos, proximos = [], []
        for eq in qs:
            if eq.alerta_vencida:
                vencidos.append(eq)
            elif eq.alerta_proxima:
                proximos.append(eq)

        lines.append(f"\n── {titulo} ──")
        if not vencidos and not proximos:
            lines.append("  Sin alertas de mantenimiento pendientes.")
            return

        if vencidos:
            lines.append("  Mantenimiento VENCIDO:")
            for eq in vencidos[:30]:
                dias = eq.dias_para_proximo_mantenimiento
                lines.append(
                    f"    ⚠ {eq.codigo_interno} — {eq.nombre} | "
                    f"{eq.ubicacion} | vencido hace {abs(dias)} día(s)"
                )
        if proximos:
            lines.append("  Mantenimiento PRÓXIMO (≤30 días):")
            for eq in proximos[:30]:
                dias = eq.dias_para_proximo_mantenimiento
                lines.append(
                    f"    • {eq.codigo_interno} — {eq.nombre} | "
                    f"{eq.ubicacion} | en {dias} día(s)"
                )
    except Exception as e:
        lines.append(f"\n(Error equipos en alerta: {e})")


def _mantenimientos_hoy(lines: list, tecnico=None):
    try:
        from mantenimientos.models import Mantenimiento

        qs = (
            Mantenimiento.objects
            .filter(fecha_programada=date.today())
            .select_related('equipo', 'tecnico_asignado')
        )
        if tecnico is not None:
            qs = qs.filter(tecnico_asignado=tecnico)
        qs = qs.order_by('prioridad')

        lines.append(f"\n── MANTENIMIENTOS PROGRAMADOS HOY ({_hoy_label()}) ──")
        if qs.exists():
            for m in qs:
                tec = m.tecnico_asignado.nombre_completo if m.tecnico_asignado else 'sin asignar'
                lines.append(
                    f"  • [{m.get_tipo_display()}/{m.get_prioridad_display()}] "
                    f"{m.titulo} | Equipo: {m.equipo.codigo_interno} | "
                    f"Técnico: {tec} | Estado: {m.get_estado_display()}"
                )
        else:
            lines.append("  No hay mantenimientos programados para hoy.")
    except Exception as e:
        lines.append(f"  (Error mantenimientos de hoy: {e})")


def _mantenimientos_pendientes(lines: list, tecnico):
    try:
        from mantenimientos.models import Mantenimiento

        pendientes = (
            Mantenimiento.objects
            .filter(
                tecnico_asignado=tecnico,
                estado__in=[Mantenimiento.Estado.PROGRAMADO, Mantenimiento.Estado.EN_PROCESO],
            )
            .select_related('equipo')
            .order_by('fecha_programada')
        )
        lines.append("\n── MIS MANTENIMIENTOS PENDIENTES / EN PROCESO ──")
        if pendientes.exists():
            for m in pendientes[:30]:
                lines.append(
                    f"  • [{m.get_estado_display()}] {m.titulo} | "
                    f"Equipo: {m.equipo.codigo_interno} — {m.equipo.nombre} | "
                    f"Prioridad: {m.get_prioridad_display()} | "
                    f"Programado: {m.fecha_programada.strftime('%d/%m/%Y')}"
                )
        else:
            lines.append("  No tienes mantenimientos pendientes asignados.")
    except Exception as e:
        lines.append(f"\n(Error mantenimientos pendientes: {e})")


def _equipos_a_cargo(lines: list, user):
    try:
        from equipos.models import Equipo

        equipos = (
            Equipo.objects
            .filter(responsable=user)
            .select_related('categoria')
            .order_by('codigo_interno')
        )
        lines.append("\n── EQUIPOS A MI CARGO ──")
        if equipos.exists():
            for eq in equipos[:30]:
                lines.append(
                    f"  • {eq.codigo_interno} — {eq.nombre} ({eq.categoria.nombre}) | "
                    f"{eq.ubicacion} | Estado: {eq.get_estado_display()}"
                )
            _equipos_en_alerta(lines, queryset=equipos, titulo='ALERTAS DE MIS EQUIPOS')
        else:
            lines.append("  No tienes equipos asignados como responsable.")
    except Exception as e:
        lines.append(f"\n(Error equipos a cargo: {e})")


def _carga_tecnicos(lines: list):
    try:
        from mantenimientos.models import Mantenimiento

        carga = (
            Mantenimiento.objects
            .filter(
                tecnico_asignado__isnull=False,
                estado__in=[Mantenimiento.Estado.PROGRAMADO, Mantenimiento.Estado.EN_PROCESO],
            )
            .values(
                'tecnico_asignado__id',
                'tecnico_asignado__first_name',
                'tecnico_asignado__last_name',
                'tecnico_asignado__username',
            )
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        lines.append("\n── CARGA DE TRABAJO POR TÉCNICO (pendiente/en proceso) ──")
        if carga:
            for c in carga:
                nombre = (
                    f"{c['tecnico_asignado__first_name']} {c['tecnico_asignado__last_name']}".strip()
                    or c['tecnico_asignado__username']
                )
                lines.append(f"  • {nombre}: {c['total']} mantenimiento(s)")
        else:
            lines.append("  No hay mantenimientos asignados actualmente.")
    except Exception as e:
        lines.append(f"\n(Error carga de técnicos: {e})")


def _costos_mes_actual(lines: list):
    try:
        from mantenimientos.models import Mantenimiento

        hoy = date.today()
        finalizados = Mantenimiento.objects.filter(
            estado=Mantenimiento.Estado.FINALIZADO,
            fecha_finalizacion__year=hoy.year,
            fecha_finalizacion__month=hoy.month,
        )
        agregados = finalizados.aggregate(
            repuestos=Sum('costo_repuestos'), mano_obra=Sum('costo_mano_obra')
        )
        repuestos = agregados['repuestos'] or 0
        mano_obra = agregados['mano_obra'] or 0
        lines.append("\n── COSTOS DEL MES ACTUAL (mantenimientos finalizados) ──")
        lines.append(f"  • Repuestos   : ${repuestos:,.2f}")
        lines.append(f"  • Mano de obra: ${mano_obra:,.2f}")
        lines.append(f"  • Total       : ${(repuestos + mano_obra):,.2f}")
    except Exception as e:
        lines.append(f"\n(Error costos del mes: {e})")


def _mantenimientos_por_estado(lines: list):
    try:
        from mantenimientos.models import Mantenimiento

        totales = (
            Mantenimiento.objects
            .values('estado')
            .annotate(total=Count('id'))
            .order_by('estado')
        )
        lines.append("\n── MANTENIMIENTOS POR ESTADO ──")
        if totales:
            for t in totales:
                estado_label = dict(Mantenimiento.Estado.choices).get(t['estado'], t['estado'])
                lines.append(f"  • {estado_label}: {t['total']}")
        else:
            lines.append("  No hay mantenimientos registrados.")
    except Exception as e:
        lines.append(f"  (Error mantenimientos por estado: {e})")


def _usuarios_activos_por_rol(lines: list):
    try:
        totales = (
            Usuario.objects
            .filter(is_active=True)
            .values('rol')
            .annotate(total=Count('id'))
            .order_by('rol')
        )
        lines.append("\n── USUARIOS ACTIVOS POR ROL ──")
        for t in totales:
            rol_label = dict(Usuario.Rol.choices).get(t['rol'], t['rol'])
            lines.append(f"  • {rol_label}: {t['total']}")
    except Exception as e:
        lines.append(f"\n(Error usuarios activos: {e})")


# ─────────────────────────────────────────────────────────────────────────────
# TÉCNICO
# ─────────────────────────────────────────────────────────────────────────────

def _contexto_tecnico(user) -> str:
    lines = [
        f"El usuario es TÉCNICO: {user.nombre_completo} ({user.email}).",
        "Solo responde con información de los equipos y mantenimientos que le "
        "corresponden. No reveles datos sensibles de otros técnicos ni costos "
        "globales del sistema.",
    ]
    if user.cargo:
        lines.append(f"Cargo: {user.cargo}")

    _mantenimientos_pendientes(lines, user)
    _mantenimientos_hoy(lines, tecnico=user)
    _equipos_a_cargo(lines, user)

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SUPERVISOR / ADMINISTRADOR
# ─────────────────────────────────────────────────────────────────────────────

def _contexto_admin(user) -> str:
    lines = [
        f"El usuario es {user.get_rol_display().upper()}: "
        f"{user.nombre_completo} ({user.email}).",
        "Tiene acceso completo al sistema de gestión de mantenimiento. "
        "Puede consultar cualquier dato de equipos, mantenimientos, técnicos y costos.",
    ]

    _resumen_equipos(lines)
    _equipos_en_alerta(lines)
    _mantenimientos_por_estado(lines)
    _mantenimientos_hoy(lines)
    _carga_tecnicos(lines)
    _costos_mes_actual(lines)
    _usuarios_activos_por_rol(lines)

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SELECTOR PÚBLICO
# ─────────────────────────────────────────────────────────────────────────────

class ContextBuilder:

    @classmethod
    def build(cls, user) -> str:
        rol = user.rol
        if rol == Usuario.Rol.TECNICO:
            return _contexto_tecnico(user)
        elif rol in (Usuario.Rol.SUPERVISOR, Usuario.Rol.ADMINISTRADOR):
            return _contexto_admin(user)
        return f"Usuario: {user.nombre_completo} | Rol: {user.get_rol_display()}"
