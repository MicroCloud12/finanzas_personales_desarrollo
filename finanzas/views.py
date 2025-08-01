import json
import logging
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import login
from .tasks import process_drive_tickets
from datetime import datetime, timedelta
from .utils import calculate_monthly_profit
from django.contrib.auth.models import User
from django.utils.dateformat import DateFormat
from django.db.models.functions import TruncMonth
from celery.result import AsyncResult, GroupResult
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .services import TransactionService, MercadoPagoService, StockPriceService
from .forms import TransaccionesForm, FormularioRegistroPersonalizado, InversionForm
from .models import registro_transacciones, Suscripcion, TransaccionPendiente, inversiones, GananciaMensual,GananciaMensual

logger = logging.getLogger(__name__)


def home(request):
    return render(request, 'index.html')

@login_required
def iniciar_procesamiento_drive(request):
    """
    Inicia el proceso de descubrimiento y procesamiento paralelo de tickets.
    """
    try:
        # La lógica de token ahora está dentro del servicio, pero la vista
        # debe asegurarse de que la tarea se inicie.
        task = process_drive_tickets.delay(request.user.id)
        return JsonResponse({"task_id": task.id}, status=202)
    except Exception as e:
        # Captura errores generales durante el inicio de la tarea
        return JsonResponse({"error": f"No se pudo iniciar la tarea: {str(e)}"}, status=400)

@login_required
def aprobar_ticket(request, ticket_id):
    if request.method == 'POST':
        cuenta_seleccionada = request.POST.get('cuenta_origen')
        categoria_seleccionada = request.POST.get('categoria')
        tipo_seleccionado = request.POST.get('tipo', 'GASTO') # Valor por defecto 'GASTO'
        # Usamos el servicio para manejar la aprobación
        TransactionService.approve_pending_transaction(
            ticket_id=ticket_id,
            user=request.user,
            cuenta=cuenta_seleccionada,
            categoria=categoria_seleccionada,
            tipo_transaccion=tipo_seleccionado
        )
        
    return redirect('revisar_tickets')

def iniciosesion(request):
    return render(request, 'dashboard.html')

def registro(request):
    if request.method == 'POST':
        form = FormularioRegistroPersonalizado(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = FormularioRegistroPersonalizado()
    
    context = {'form': form}
    return render(request, 'registro.html', context)

@login_required
def vista_dashboard(request):
    suscripcion, created = Suscripcion.objects.get_or_create(usuario=request.user)
    # --- LÓGICA PARA LA GRÁFICA DE LÍNEAS ---
    # Obtenemos todas las compras de inversiones del usuario, ordenadas por fecha
    compras = inversiones.objects.filter(propietario=request.user).order_by('fecha_compra')

    chart_labels = []
    chart_data = []
    capital_acumulado = Decimal('0.0')

    # Agrupamos las compras por día y calculamos el capital acumulado
    compras_por_dia = {}
    for compra in compras:
        fecha_str = compra.fecha_compra.strftime('%Y-%m-%d')
        if fecha_str not in compras_por_dia:
            compras_por_dia[fecha_str] = Decimal('0.0')
        compras_por_dia[fecha_str] += compra.costo_total_adquisicion

    # Ordenamos las fechas y construimos los datos del gráfico
    fechas_ordenadas = sorted(compras_por_dia.keys())
    for fecha in fechas_ordenadas:
        capital_acumulado += compras_por_dia[fecha]
        chart_labels.append(fecha)
        chart_data.append(str(capital_acumulado))
    # ----------------------------------------------
    # Verificamos si la suscripción está activa con nuestro método del modelo.
    es_usuario_premium = suscripcion.is_active()
    current_year = datetime.now().year
    current_month = datetime.now().month
    year = int(request.GET.get('year', current_year))
    month = int(request.GET.get('month', current_month))
    transacciones = registro_transacciones.objects.filter(
        propietario=request.user, 
        fecha__year=year, 
        fecha__month=month
    )
    ingresos = transacciones.filter(tipo='INGRESO').exclude(categoria='Ahorro').filter(cuenta_origen = 'Efectivo Quincena').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    gastos = transacciones.filter(tipo='GASTO').exclude(categoria='Ahorro').filter(cuenta_origen = 'Efectivo Quincena').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    ahorro_total = transacciones.filter(tipo='INGRESO').filter(categoria='Ahorro').filter(cuenta_origen = 'Cuenta Ahorro').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    proviciones = transacciones.filter(tipo='GASTO').exclude(categoria='Ahorro').filter(cuenta_origen = 'Cuenta Ahorro').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    transferencias = transacciones.filter(tipo='TRANSFERENCIA').exclude(categoria='Ahorro').exclude(categoria='Ahorro').filter(cuenta_origen = 'Efectivo Quincena').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    inversion_inicial_usd = inversiones.objects.filter(propietario=request.user).aggregate(total=Sum('costo_total_adquisicion'))['total'] or Decimal('0.00')
    inversion_actual = inversiones.objects.filter(propietario=request.user).aggregate(total=Sum('valor_actual_mercado'))['total'] or Decimal('0.00')

    balance = ingresos - gastos
    disponible_banco = ingresos - gastos - transferencias
    ahorro = ahorro_total - proviciones

    context = {
        'ingresos': ingresos,
        'gastos': gastos,
        'balance': balance,
        'transferencias':transferencias,
        'disponible_banco':disponible_banco,
        'ahorro': ahorro,
        'selected_year': year,
        'selected_month': month,
        'years': range(current_year, current_year - 5, -1),
        'months': range(1, 13),
        'es_usuario_premium': es_usuario_premium,
        'inversion_inicial': inversion_inicial_usd,
        'inversion_actual': inversion_actual,
        # --- Pasamos los datos del nuevo gráfico ---
        'investment_chart_labels': json.dumps(chart_labels),
        'investment_chart_data': json.dumps(chart_data),
    }
    return render(request, 'dashboard.html', context)

@login_required
def crear_transacciones(request):
    if request.method == 'POST':
        form = TransaccionesForm(request.POST)
        if form.is_valid():
            nueva_transaccion = form.save(commit=False)
            nueva_transaccion.propietario = request.user
            nueva_transaccion.save()
            return redirect('dashboard')
    else: 
        form = TransaccionesForm()
    context = {'form': form}
    return render(request, 'transacciones.html', context)

@login_required
def lista_transacciones(request):
    suscripcion, created = Suscripcion.objects.get_or_create(usuario=request.user)
    es_usuario_premium = suscripcion.is_active()
    current_year = datetime.now().year
    current_month = datetime.now().month
    year = int(request.GET.get('year', current_year))
    month = int(request.GET.get('month', current_month))
    transacciones_del_mes = registro_transacciones.objects.filter(
        propietario=request.user,
        fecha__year=year,
        fecha__month=month
    ).order_by('-fecha')
    
    context = {
        'transacciones': transacciones_del_mes,
        'es_usuario_premium': es_usuario_premium, # <-- Añadir la variable al contexto
    }
    return render(request, 'lista_transacciones.html', context)

@login_required
def editar_transaccion(request, transaccion_id):
    transaccion = get_object_or_404(registro_transacciones, id=transaccion_id, propietario=request.user)
    if request.method == 'POST':
        form = TransaccionesForm(request.POST, instance=transaccion)
        if form.is_valid():
            form.save()
            return redirect('lista_transacciones')
    else:
        form = TransaccionesForm(instance=transaccion)
    return render(request, 'editar_transaccion.html', {'form': form})

@login_required
def eliminar_transaccion(request, transaccion_id):
    transaccion = get_object_or_404(registro_transacciones, id=transaccion_id, propietario=request.user)
    if request.method == 'POST':
        transaccion.delete()
        return redirect('lista_transacciones')
    return render(request, 'confirmar_eliminar_transaccion.html', {'transaccion': transaccion})

@login_required
def datos_gastos_categoria(request):
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    gastos_por_categoria = registro_transacciones.objects.filter(
        propietario=request.user,
        tipo='GASTO',
        fecha__year=year,
        fecha__month=month
    ).values('categoria').annotate(total=Sum('monto')).order_by('-total')
    data = {
        'labels': [item['categoria'] for item in gastos_por_categoria],
        'data': [item['total'] for item in gastos_por_categoria],
    }
    return JsonResponse(data)

@login_required
def datos_flujo_dinero(request):
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    transacciones_del_mes = registro_transacciones.objects.filter(
        propietario=request.user,
        fecha__year=year,
        fecha__month=month
    )
    ingresos = transacciones_del_mes.filter(tipo='INGRESO').exclude(categoria='Ahorro').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    gastos = transacciones_del_mes.filter(tipo='GASTO').exclude(categoria='Ahorro').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    data = {
        'labels': ['Ingresos del Mes', 'Gastos del Mes'],
        'data': [ingresos, gastos],
    }
    return JsonResponse(data)

@login_required
def vista_procesamiento_automatico(request):
    return render(request, 'procesamiento_automatico.html')

@login_required
def revisar_tickets(request):
    tickets_pendientes = TransaccionPendiente.objects.filter(propietario=request.user, estado='pendiente')
    return render(request, 'revisar_tickets.html', {'tickets': tickets_pendientes})

@login_required
def get_initial_task_result(request, task_id):
    """
    Consulta el resultado de la tarea "lanzadora". Su único trabajo es
    esperar a que esta tarea termine para devolver el ID del grupo.
    """
    try:
        task_result = AsyncResult(task_id)
        if task_result.ready():
            return JsonResponse({"status": "SUCCESS", "result": task_result.result})
        else:
            return JsonResponse({"status": "PENDING"})
    except Exception as e:
        logger.error(f"Error en get_initial_task_result: {e}")
        return JsonResponse({"status": "FAILURE", "info": str(e)}, status=500)

@login_required
def get_group_status(request, group_id):
    """
    Consulta el estado de un GroupResult para reportar el progreso.
    """
    try:
        group_result = GroupResult.restore(group_id)
        if not group_result:
             return JsonResponse({"status": "PENDING"})

        if group_result.ready():
            return JsonResponse({"status": "COMPLETED"})
        else:
            total = len(group_result)
            completed = group_result.completed_count()
            return JsonResponse({
                "status": "PROGRESS",
                "total": total,
                "completed": completed,
                "progress": int((completed / total) * 100) if total > 0 else 0
            })
    except Exception as e:
        logger.error(f"Error en get_group_status: {e}")
        return JsonResponse({"status": "FAILURE", "info": str(e)}, status=500)
     
@login_required
def rechazar_ticket(request, ticket_id):
    ticket = TransaccionPendiente.objects.get(id=ticket_id, propietario=request.user)
    ticket.estado = 'rechazada'
    ticket.save()
    return redirect('revisar_tickets')

@login_required
def lista_inversiones(request):
    """
    Muestra todas las inversiones del usuario logueado.
    """
    lista = inversiones.objects.filter(propietario=request.user).order_by('-fecha_compra')
    context = {'inversiones': lista}
    return render(request, 'lista_inversiones.html', context)

@login_required
def crear_inversion(request):
    """
    Maneja la creación de una nueva inversión, obteniendo el precio actual de una API.
    """
    if request.method == 'POST':
        form = InversionForm(request.POST)
        if form.is_valid():
            nueva_inversion = form.save(commit=False)
            nueva_inversion.propietario = request.user
            price_service = StockPriceService()
            ticker = form.cleaned_data.get('emisora_ticker').upper()

            # Obtenemos el precio como float desde el servicio
            precio_actual_float = price_service.get_current_price(ticker)
            
            # --- PASO 2: AQUÍ ESTÁ LA CORRECCIÓN ---
            if precio_actual_float is not None:
                # Convertimos el float a un Decimal antes de asignarlo al modelo
                # Usamos str() en el medio, es la forma más segura de evitar errores de precisión.
                nueva_inversion.precio_actual_titulo = Decimal(str(precio_actual_float))
            else:
                # Si la API falla, usamos el precio de compra como respaldo
                nueva_inversion.precio_actual_titulo = nueva_inversion.precio_compra_titulo
            
            nueva_inversion.save() # Ahora la multiplicación será entre dos Decimales
            messages.success(request, f"Inversión en {ticker} guardada con éxito.")
            return redirect('lista_inversiones')
    else:
        form = InversionForm()
    
    context = {'form': form}
    # Asegúrate de que el path a tu template es correcto
    return render(request, 'crear_inversion.html', context)

@login_required
def datos_inversiones(request):
    
    qs = (
        inversiones.objects
        .filter(propietario=request.user)
        .annotate(month=TruncMonth('fecha_compra'))
        .values('month')
        .annotate(total=Sum('ganancia_perdida_no_realizada'))
        .order_by('month')
    )
    labels = [DateFormat(item['month']).format('Y-m') for item in qs]
    values = [item['total'] for item in qs]
    return JsonResponse({'labels': labels, 'data': values})

@login_required
def gestionar_suscripcion(request):
    """
    Muestra el estado de la suscripción y genera el link de pago si es necesario.
    """
    suscripcion, created = Suscripcion.objects.get_or_create(usuario=request.user)
    
    link_pago = None
    if not suscripcion.is_active():
        try:
            mp_service = MercadoPagoService()
            # La vista construye la URL absoluta y se la pasa al servicio
            success_url = request.build_absolute_uri(reverse('suscripcion_exitosa'))
            link_pago = mp_service.crear_link_suscripcion(request.user, success_url)
        except Exception as e:
            messages.error(request, f"Error al generar link de pago: {e}")

    context = {
        'suscripcion': suscripcion,
        'link_pago': link_pago
    }
    return render(request, 'gestionar_suscripcion.html', context)

@login_required
def suscripcion_exitosa(request):
    messages.success(request, "¡Tu pago se está procesando! La activación puede tardar unos minutos.")
    return redirect('gestionar_suscripcion')

@login_required
def suscripcion_fallida(request):
    messages.error(request, "Hubo un problema con tu pago. Por favor, intenta de nuevo.")
    return redirect('gestionar_suscripcion')

@csrf_exempt
def mercadopago_webhook(request):
    """
    Recibe notificaciones de MercadoPago para actualizar el estado de las suscripciones.
    """
    if request.method != 'POST':
        return HttpResponse(status=405) # Method Not Allowed

    try:
        data = json.loads(request.body)
        topic = data.get("type")

        if topic == "subscription_preapproval":
            subscription_id = data.get("data", {}).get("id")
            if not subscription_id:
                return HttpResponse(status=400) # Bad Request, no ID provided

            mp_service = MercadoPagoService()
            # Obtenemos los detalles de la suscripción desde la API de Mercado Pago
            subscription_details = mp_service.sdk.preapproval().get(subscription_id)
            
            if subscription_details["status"] == 200:
                sub_data = subscription_details["response"]
                payer_email = sub_data.get("payer_email")
                status = sub_data.get("status")

                # Buscamos al usuario por su email
                user = User.objects.filter(email=payer_email).first()
                if not user:
                    return HttpResponse(status=404) # User not found

                suscripcion_obj = Suscripcion.objects.get(usuario=user)

                # ¡La magia! Actualizamos nuestro modelo según el estado de Mercado Pago
                if status == 'authorized':
                    suscripcion_obj.estado = 'activa'
                    suscripcion_obj.id_suscripcion_mercadopago = subscription_id
                    suscripcion_obj.fecha_inicio = timezone.now()
                    suscripcion_obj.fecha_fin = timezone.now() + timedelta(days=31)
                elif status in ['paused', 'cancelled']:
                    suscripcion_obj.estado = 'cancelada'
                
                suscripcion_obj.save()

    except (json.JSONDecodeError, KeyError, Suscripcion.DoesNotExist) as e:
        # Log del error sería ideal aquí en un sistema de producción
        print(f"Error procesando webhook: {e}")
        return HttpResponse(status=400)

    # Devolvemos un 200 OK para que Mercado Pago sepa que recibimos la notificación
    return HttpResponse(status=200)

@login_required
def datos_ganancias_mensuales(request):
    """Retorna las ganancias mensuales acumuladas de las inversiones del usuario.
    profits = calculate_monthly_profit(request.user)
    labels = list(profits.keys())
    data = [profits[month] for month in labels]
    return JsonResponse({'labels': labels, 'data': data})
    """
    
    ganancias = GananciaMensual.objects.filter(
        propietario=request.user
    ).order_by('mes')
    labels = [g.mes for g in ganancias]
    data = [g.total for g in ganancias]
    return JsonResponse({'labels': labels, 'data': data})

def lista_deudas(request):
    return render(request, 'deudas.html')

@login_required
def crear_deuda(request):
    return render(request, 'crear_deuda.html')