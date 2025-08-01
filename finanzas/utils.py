# finanzas/utils.py
from decimal import Decimal
from calendar import monthrange
from .models import inversiones
from datetime import datetime, date
from collections import defaultdict


def parse_date_safely(date_str: str | None) -> date:
    """
    Convierte y valida de forma segura una cadena de texto a un objeto de fecha.
    Si la fecha parseada es de hace más de un año, la considera inválida.
    Si falla, devuelve la fecha actual.
    """
    parsed_date = None
    
    if date_str and isinstance(date_str, str):
        formats_to_try = [
            "%Y-%m-%d",  # Formato ideal (ISO)
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d/%m/%y",
        ]
        for fmt in formats_to_try:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                break  # Si tiene éxito, salimos del bucle
            except (ValueError, TypeError):
                continue

    # --- LÓGICA DE VALIDACIÓN MEJORADA ---
    if parsed_date:
        # Si la fecha extraída es de hace más de 365 días, es muy probable que
        # sea un error de la IA. Es más seguro usar la fecha actual.
        if (datetime.now().date() - parsed_date).days > 365:
            print(f"ADVERTENCIA: La fecha extraída '{parsed_date}' es muy antigua y fue descartada. Se usará la fecha actual.")
            return datetime.now().date()
        else:
            # La fecha es razonable y se devuelve
            return parsed_date

    # Fallback final si no se pudo parsear o la cadena era inválida
    if date_str:
        print(f"ADVERTENCIA: La cadena de fecha '{date_str}' no pudo ser procesada. Se usará la fecha actual.")
    return datetime.now().date()

def calculate_monthly_profit(user, price_service=None):
    from .services import StockPriceService
    """Calcula la ganancia mensual no realizada de las inversiones de un usuario."""
    servicio_precios = price_service or StockPriceService()
    #servicio_precios = StockPriceService()
    ganancias_mensuales = defaultdict(Decimal)
    
    # Obtenemos todas las inversiones del usuario de una vez
    inversiones_usuario = inversiones.objects.filter(propietario=user)
    
    if not inversiones_usuario:
        return {}

    # Obtenemos el mes y año actual para saber hasta dónde calcular
    hoy = datetime.now().date()
    
    # Creamos un diccionario para cachear los precios que ya consultamos y evitar llamadas duplicadas
    #cache_precios = {}
    inversiones_por_ticker = defaultdict(list)
    inicio_por_ticker = {}
    # Iteramos por cada una de las inversiones del usuario
    for inv in inversiones_usuario:
        '''
        # Iteramos por cada mes desde la fecha de compra hasta el día de hoy
        fecha_iter = inv.fecha_compra
        while fecha_iter <= hoy:
            mes_str = fecha_iter.strftime('%Y-%m')
            
            # Buscamos el precio de cierre para el final de ese mes
            ultimo_dia_mes = monthrange(fecha_iter.year, fecha_iter.month)[1]
            fecha_cierre_mes = date(fecha_iter.year, fecha_iter.month, ultimo_dia_mes)
        '''
        inversiones_por_ticker[inv.emisora_ticker].append(inv)
        inicio = inv.fecha_compra.replace(day=1)
        '''
            # Usamos nuestro caché para no volver a pedir el mismo precio
            cache_key = f"{inv.emisora_ticker}-{fecha_cierre_mes}"
            precio_cierre = cache_precios.get(cache_key)
        
            if precio_cierre is None:
                precio_cierre_float = servicio_precios.get_closing_price_for_date(inv.emisora_ticker, fecha_cierre_mes)
                
                # Guardamos en el caché, incluso si es None, para no volver a preguntar
                cache_precios[cache_key] = precio_cierre_float
                precio_cierre = Decimal(str(precio_cierre_float)) if precio_cierre_float is not None else None
        '''
        if inv.emisora_ticker not in inicio_por_ticker or inicio < inicio_por_ticker[inv.emisora_ticker]:
            inicio_por_ticker[inv.emisora_ticker] = inicio

            # Consultamos la serie mensual solo una vez por ticker
    series_cache = {}
    for ticker, inicio in inicio_por_ticker.items():
        series = servicio_precios.get_monthly_series(ticker, inicio, hoy)
        series_cache[ticker] = {p["datetime"][:7]: Decimal(str(p["close"])) for p in series}

    # Calculamos las ganancias iterando sobre cada inversión pero reutilizando el caché
    for ticker, inversiones_list in inversiones_por_ticker.items():
        precios_por_mes = series_cache.get(ticker, {})
        for inv in inversiones_list:
            fecha_iter = inv.fecha_compra.replace(day=1)
            while fecha_iter <= hoy:
                mes_str = fecha_iter.strftime("%Y-%m")
                precio_cierre = precios_por_mes.get(mes_str)
                if precio_cierre is not None:
                    costo_total_adquisicion = inv.cantidad_titulos * inv.precio_compra_titulo
                    valor_actual_mercado = inv.cantidad_titulos * precio_cierre
                    ganancia_perdida_no_realizada = valor_actual_mercado - costo_total_adquisicion
                    ganancias_mensuales[mes_str] += ganancia_perdida_no_realizada
                    #ganancia = (precio_cierre - inv.precio_compra_titulo) * inv.cantidad_titulos
                    #print(f"Ganancia para {inv.nombre_activo} en {mes_str}: {ganancias_mensuales[mes_str]}")
                # Avanzamos al siguiente mes
                if fecha_iter.month == 12:
                    fecha_iter = date(fecha_iter.year + 1, 1, 1)
                else:
                    fecha_iter = date(fecha_iter.year, fecha_iter.month + 1, 1)

    # Ordenamos por fecha para devolver un diccionario coherente
    return dict(sorted(ganancias_mensuales.items()))