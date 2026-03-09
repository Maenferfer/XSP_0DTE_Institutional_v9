import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import warnings
import logging

# --- CONFIGURACIÓN ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

st.set_page_config(page_title="XSP 0DTE Institutional v9.0", layout="wide")

# ================================================================
# TELEGRAM
# ================================================================
def enviar_telegram(msg_tel):
    token   = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
    chat_id = "7121107501"
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": msg_tel}, timeout=10)
        if r.status_code == 200:
            st.sidebar.success("✅ Alerta enviada a Telegram")
        else:
            st.sidebar.error(f"❌ Error API Telegram: {r.text}")
    except Exception as e:
        st.sidebar.error(f"❌ Error de conexión Telegram: {e}")

# ================================================================
# NOTICIAS
# ================================================================
def check_noticias_pro(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE",
                          "JOBLESS", "TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
    hoy   = str(date.today())
    url   = f"https://finnhub.io/api/v1/calendar/economic?from={hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "eventos": []}
    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
            if ev.get('country') == 'US' and str(ev.get('impact', '')).lower() in ['high', '3', '4']:
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    h_utc = datetime.strptime(ev['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    h_es  = h_utc.astimezone(ZONA_HORARIA).time()
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if time(14, 0) <= h_es <= time(21, 0):
                        estado["bloqueo"] = True
    except:
        pass
    return estado

# ================================================================
# VENTANA HORARIA
# ================================================================
def evaluar_ventana_horaria(ahora_time):
    if   time(15, 30) <= ahora_time <= time(15, 45): return "EVITAR",    "🔴", "Apertura NY caótica"
    elif time(15, 45) <= ahora_time <= time(17, 30): return "ÓPTIMA",    "🟢", "Apertura NY asentada"
    elif time(17, 30) <= ahora_time <= time(19,  0): return "NORMAL",    "🟡", "Tramo intermedio"
    elif time(19,  0) <= ahora_time <= time(20, 30): return "ÓPTIMA",    "🟢", "Tramo final tranquilo"
    elif time(20, 30) <= ahora_time <= time(21,  0): return "EVITAR",    "🔴", "Cierre errático"
    elif ahora_time < time(15, 30):                  return "PREMERCADO","⚪", "Mercado cerrado"
    else:                                             return "CERRADO",   "⚪", "Mercado cerrado"

# ================================================================
# STRIKES REDONDOS — niveles psicológicos clave (múltiplos de 5 y 10)
# ================================================================
def analizar_strikes_redondos(precio, rango_pts=20):
    """
    Devuelve los strikes redondos más cercanos al precio actual.
    - Múltiplos de 10: niveles psicológicos FUERTES
    - Múltiplos de 5:  niveles psicológicos MEDIOS
    Los market makers acumulan OI en estos strikes → actúan como
    imán de precio y zonas de rebote/rechazo muy fiables.
    """
    niveles = []
    base = int(precio // 5) * 5
    for i in range(-rango_pts // 5 - 2, rango_pts // 5 + 3):
        s = base + i * 5
        if abs(s - precio) <= rango_pts:
            fuerza = "FUERTE 🔴" if s % 10 == 0 else "MEDIO 🟡"
            dist   = round(s - precio, 2)
            niveles.append({"strike": s, "fuerza": fuerza, "distancia": dist})
    niveles.sort(key=lambda x: abs(x["distancia"]))
    return niveles

def es_strike_redondo(strike):
    """True si el strike acaba en 0 o 5 — zona contestada, evitar vender justo ahí"""
    return int(strike) % 5 == 0

def ajustar_strike_redondo(strike, bias):
    """
    Si el strike propuesto cae en múltiplo de 5/10, lo aleja un tick.
    En Bull Put queremos el strike un poco más abajo del nivel redondo.
    En Bear Call queremos el strike un poco más arriba.
    Así no vendemos justo en la zona de mayor concentración de OI.
    """
    if not es_strike_redondo(strike):
        return strike, False
    ajustado = strike - 1 if bias else strike + 1
    return ajustado, True

def strike_cerca_redondo_clave(strike, umbral=3):
    """
    Detecta si el strike está muy cerca de un múltiplo de 10.
    Si está dentro de 'umbral' puntos de un nivel fuerte,
    el precio tiene alta probabilidad de ser atraído hacia él.
    """
    multiplo_10_mas_cercano = round(strike / 10) * 10
    return abs(strike - multiplo_10_mas_cercano) <= umbral, multiplo_10_mas_cercano

# ================================================================
# GEX, GAMMA FLIP, CALL WALL, PUT WALL, MAX PAIN
# ================================================================
def calcular_niveles_gamma(precio_actual, factor=1):
    """
    Calcula niveles gamma usando la chain de opciones de SPY (yFinance).
    Se usa SPY siempre porque XSP no tiene liquidez suficiente en options.
    factor: escala los strikes al universo XSP si factor=10.

    Retorna:
      call_wall   — strike call con mayor OI por encima del precio (resistencia gamma)
      put_wall    — strike put  con mayor OI por debajo del precio (soporte gamma)
      gamma_flip  — nivel donde GEX cambia de positivo a negativo
      max_pain    — strike donde expiran con menor valor total las opciones
      gex_neto    — GEX total en rango ±5%: >0 anclaje, <0 volatilidad
      gex_positivo— bool: True = MM venden vol (bueno IC), False = MM cubren (malo)
      en_rango_gamma — precio entre put_wall y call_wall (ideal Iron Condor)
    """
    resultado = {
        "call_wall": None, "put_wall": None, "gamma_flip": None,
        "max_pain": None,  "gex_neto": 0,    "gex_positivo": True,
        "en_rango_gamma": False, "exp_usada": "N/A",
        "call_wall_redondo": False, "put_wall_redondo": False,
    }
    try:
        t    = yf.Ticker("SPY")
        exps = t.options
        if not exps:
            return resultado

        # Vencimiento más cercano a hoy (0DTE o el siguiente disponible)
        hoy_d   = date.today()
        exp_hoy = min(exps, key=lambda x: abs(
            (datetime.strptime(x, "%Y-%m-%d").date() - hoy_d).days
        ))
        resultado["exp_usada"] = exp_hoy

        chain = t.option_chain(exp_hoy)
        calls = chain.calls[['strike', 'openInterest', 'volume']].copy().fillna(0)
        puts  = chain.puts[['strike',  'openInterest', 'volume']].copy().fillna(0)

        # Precio SPY sin factor (chain está en SPY)
        precio_spy = precio_actual / factor

        # ── CALL WALL ────────────────────────────────────────────────
        calls_otm = calls[calls['strike'] > precio_spy]
        if not calls_otm.empty:
            cw = float(calls_otm.loc[calls_otm['openInterest'].idxmax(), 'strike'])
            resultado["call_wall"] = round(cw * factor, 2)
            resultado["call_wall_redondo"] = es_strike_redondo(int(cw * factor))

        # ── PUT WALL ─────────────────────────────────────────────────
        puts_otm = puts[puts['strike'] < precio_spy]
        if not puts_otm.empty:
            pw = float(puts_otm.loc[puts_otm['openInterest'].idxmax(), 'strike'])
            resultado["put_wall"] = round(pw * factor, 2)
            resultado["put_wall_redondo"] = es_strike_redondo(int(pw * factor))

        # ── GEX APROXIMADO ───────────────────────────────────────────
        # GEX = OI_calls - OI_puts por strike
        # Positivo: MM delta-hedging vende cuando sube → precio anclado
        # Negativo: MM delta-hedging compra cuando sube → precio se acelera
        calls_g = calls[['strike', 'openInterest']].copy()
        puts_g  = puts[['strike',  'openInterest']].copy()
        calls_g['gex'] =  calls_g['openInterest']
        puts_g['gex']  = -puts_g['openInterest']
        all_gex  = pd.concat([calls_g[['strike','gex']], puts_g[['strike','gex']]])
        gex_by_s = all_gex.groupby('strike')['gex'].sum().sort_index()

        rango_mask = (gex_by_s.index >= precio_spy * 0.95) & (gex_by_s.index <= precio_spy * 1.05)
        resultado["gex_neto"]     = float(gex_by_s[rango_mask].sum())
        resultado["gex_positivo"] = resultado["gex_neto"] >= 0

        # ── GAMMA FLIP ───────────────────────────────────────────────
        # El strike más cercano donde el GEX acumulado cruza de + a -
        gex_cum = gex_by_s.cumsum()
        # Buscar cruce: zona donde cambia de signo
        signos = np.sign(gex_cum.values)
        cruces = np.where(np.diff(signos))[0]
        if len(cruces) > 0:
            idx_flip = cruces[0]
            flip_spy = float(gex_by_s.index[idx_flip])
            resultado["gamma_flip"] = round(flip_spy * factor, 2)
        else:
            resultado["gamma_flip"] = precio_actual  # sin flip claro

        # ── MAX PAIN ─────────────────────────────────────────────────
        # Strike donde el valor total de opciones en expiración es mínimo
        # El precio tiende a gravitar hacia este nivel en las últimas horas
        strikes_all = np.union1d(calls['strike'].values, puts['strike'].values)
        pains = []
        for s in strikes_all:
            # Dolor calls ITM (precio > strike): calls_itm.sum = calls con strike < s
            pain_c = float(((s - calls.loc[calls['strike'] < s, 'strike'])
                             * calls.loc[calls['strike'] < s, 'openInterest']).sum())
            # Dolor puts ITM (precio < strike): puts_itm.sum = puts con strike > s
            pain_p = float(((puts.loc[puts['strike'] > s, 'strike'] - s)
                             * puts.loc[puts['strike'] > s, 'openInterest']).sum())
            pains.append(pain_c + pain_p)

        if pains:
            mp_spy = float(strikes_all[int(np.argmin(pains))])
            resultado["max_pain"] = round(mp_spy * factor, 2)

        # ── EN RANGO GAMMA ───────────────────────────────────────────
        if resultado["put_wall"] and resultado["call_wall"]:
            resultado["en_rango_gamma"] = (
                resultado["put_wall"] <= precio_actual <= resultado["call_wall"]
            )

    except Exception as e:
        st.warning(f"⚠️ Gamma levels fallback: {e}")

    return resultado

# ================================================================
# STREAK DÍAS
# ================================================================
def calcular_streak_dias(df_diario):
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2: return 0
    streak    = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i - 1]) * direction > 0: streak += direction
        else: break
    return streak

# ================================================================
# DATOS MAESTROS
# ================================================================
def obtener_datos_maestros():
    try:
        tickers = {
            "XSP": "^XSP", "SPY": "SPY", "RSP": "RSP",
            "VIX": "^VIX", "VIX1D": "^VIX1D", "VIX9D": "^VIX9D", "VIX3M": "^VIX3M",
            "VVIX": "^VVIX", "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"
        }
        raw_data = {}
        for k, v in tickers.items():
            t  = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            raw_data[k] = df

        df_x   = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if raw_data["XSP"].empty else 1
        actual = float(df_x['Close'].iloc[-1]) * factor

        # ── Datos diarios para apertura/prev_close ────────────────────
        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty:
            df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
            for col in ['Open', 'High', 'Low', 'Close']:
                df_diario[col] = df_diario[col] * factor

        apertura   = float(df_diario['Open'].iloc[-1])
        prev_close = float(df_diario['Close'].iloc[-2])

        def calc_rsi(series, p):
            delta = series.diff()
            g = delta.where(delta > 0, 0).rolling(window=p).mean()
            l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]

        vol_actual = df_x['Volume'].iloc[-1]
        vol_avg    = df_x['Volume'].tail(30).mean()
        vol_rel    = vol_actual / vol_avg if vol_avg > 0 else 1.0

        atr14  = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        streak = calcular_streak_dias(df_diario)

        cierre_diario = df_diario['Close']
        std_20  = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0

        inside_day = (
            len(df_diario) >= 2 and
            df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and
            df_diario['Low'].iloc[-1]  > df_diario['Low'].iloc[-2]
        )

        # ── VWAP + Opening Range (SPY = volumen real) ─────────────────
        vwap_actual = actual
        or_high     = actual + 1
        or_low      = actual - 1
        try:
            df_spy_vwap = yf.Ticker("SPY").history(period="2d", interval="1m")
            if not df_spy_vwap.empty:
                tz_df    = df_spy_vwap.index.tz
                hoy_date = pd.Timestamp.now(tz=tz_df).date()
                df_hoy   = df_spy_vwap[df_spy_vwap.index.date == hoy_date]
                if len(df_hoy) > 5:
                    typical = (df_hoy['High'] + df_hoy['Low'] + df_hoy['Close']) / 3
                    cum_vol = df_hoy['Volume'].cumsum().replace(0, np.nan)
                    vwap_s  = (typical * df_hoy['Volume']).cumsum() / cum_vol
                    vwap_actual = float(vwap_s.dropna().iloc[-1]) * factor
                    ap_ts  = df_hoy.index[0]
                    df_or  = df_hoy[df_hoy.index <= ap_ts + pd.Timedelta(minutes=30)]
                    if not df_or.empty:
                        or_high = float(df_or['High'].max()) * factor
                        or_low  = float(df_or['Low'].min())  * factor
        except Exception as e_vwap:
            st.warning(f"⚠️ VWAP/OR fallback: {e_vwap}")

        # ── IV Rank 52 semanas ────────────────────────────────────────
        ivr = 50.0
        try:
            vix_hist = yf.Ticker("^VIX").history(period="252d", interval="1d")['Close']
            if len(vix_hist) > 20:
                ivr = (float(raw_data["VIX"]['Close'].iloc[-1]) - vix_hist.min()) / \
                      (vix_hist.max() - vix_hist.min()) * 100
        except: pass

        # ── Bollinger %B ──────────────────────────────────────────────
        pct_b = 0.5
        try:
            ma20     = cierre_diario.tail(20).mean()
            std20    = cierre_diario.tail(20).std()
            bb_upper = ma20 + 2 * std20
            bb_lower = ma20 - 2 * std20
            if (bb_upper - bb_lower) > 0:
                pct_b = (cierre_diario.iloc[-1] - bb_lower) / (bb_upper - bb_lower)
        except: pass

        # ── VVIX ──────────────────────────────────────────────────────
        vvix = 90.0
        try:
            if not raw_data["VVIX"].empty:
                vvix = float(raw_data["VVIX"]['Close'].iloc[-1])
        except: pass

        # ── VIX1D ─────────────────────────────────────────────────────
        vix_ref = float(raw_data["VIX"]['Close'].iloc[-1])
        vix1d   = vix_ref
        try:
            if not raw_data["VIX1D"].empty:
                vix1d = float(raw_data["VIX1D"]['Close'].iloc[-1])
        except: pass
        vix1d_ratio = vix1d / vix_ref if vix_ref > 0 else 1.0

        # ── TNX Momentum ──────────────────────────────────────────────
        tnx_val      = float(raw_data["TNX"]['Close'].iloc[-1]) if not raw_data["TNX"].empty else 4.0
        tnx_prev_val = float(raw_data["TNX"]['Close'].iloc[-2]) if len(raw_data["TNX"]) > 1 else tnx_val
        tnx_cambio   = ((tnx_val - tnx_prev_val) / tnx_prev_val) * 100 if tnx_prev_val > 0 else 0

        # ── Term Structure Slope VIX/VIX3M ───────────────────────────
        vix3m    = float(raw_data["VIX3M"]['Close'].iloc[-1]) if not raw_data["VIX3M"].empty else 20.0
        ts_slope = vix_ref / vix3m if vix3m > 0 else 1.0

        # ── Amplitud SPY vs RSP ───────────────────────────────────────
        spy_up = (not raw_data["SPY"].empty and
                  float(raw_data["SPY"]['Close'].iloc[-1]) > float(raw_data["SPY"]['Open'].iloc[-1]))
        rsp_up = (not raw_data["RSP"].empty and
                  float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]))

        # ── Tech votes ───────────────────────────────────────────────
        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d_tk = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d_tk.empty and d_tk['Close'].iloc[-1] > d_tk['Open'].iloc[-1]:
                votos += 1

        vals = {
            "actual"      : actual,
            "apertura"    : apertura,
            "prev"        : prev_close,
            "ma5"         : df_x['Close'].tail(5).mean() * factor,
            "rsi_14"      : calc_rsi(df_x['Close'], 14),
            "rsi_5m"      : calc_rsi(df_x['Close'], 5),
            "cambio_15m"  : (actual - float(df_x['Close'].iloc[-15]) * factor) if len(df_x) > 15 else 0,
            "std_dev"     : df_x['Close'].std() * factor,
            "vol_rel"     : vol_rel,
            "vix"         : vix_ref,
            "vix1d"       : vix1d,
            "vix1d_ratio" : vix1d_ratio,
            "vix9d"       : float(raw_data["VIX9D"]['Close'].iloc[-1]) if not raw_data["VIX9D"].empty else vix_ref,
            "vix3m"       : vix3m,
            "ts_slope"    : ts_slope,
            "vvix"        : vvix,
            "skew"        : float(raw_data["SKEW"]['Close'].iloc[-1]) if not raw_data["SKEW"].empty else 120.0,
            "tnx"         : tnx_val,
            "tnx_prev"    : tnx_prev_val,
            "tnx_cambio"  : tnx_cambio,
            "pc_ratio"    : float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull"    : rsp_up,
            "amplitud_ok" : spy_up and rsp_up,
            "atr14"       : atr14,
            "streak"      : streak,
            "z_score"     : z_score,
            "inside_day"  : inside_day,
            "gap_pct"     : (apertura - prev_close) / prev_close * 100,
            "vwap"        : vwap_actual,
            "or_high"     : or_high,
            "or_low"      : or_low,
            "ivr"         : ivr,
            "pct_b"       : pct_b,
            "vix_speed"   : (vix_ref / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash" : (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100 if len(df_x) > 5 else 0,
            "votos_tech"  : votos,
        }

    except Exception as e:
        st.error(f"[ERROR datos]: {e}")
        return None
    return vals

# ================================================================
# DELTA / PROB ITM
# ================================================================
def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    T     = dias_exp / 252
    sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    return round(norm.cdf(-d1), 4)

# ================================================================
# MAIN
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v9.0")

    cap          = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia      = st.sidebar.number_input("P&L del día (€)",    value=250.0)
    MAX_LOSS_DIA = -300.0
    enviar_auto  = st.sidebar.checkbox("Enviar Telegram automáticamente", value=False)

    if st.button("EJECUTAR ANÁLISIS"):
        with st.spinner("Obteniendo datos maestros..."):
            noticias = check_noticias_pro(FINNHUB_API_KEY)
            d        = obtener_datos_maestros()

            if not d:
                st.error("No se pudieron obtener los datos.")
                return

            ahora      = datetime.now(ZONA_HORARIA)
            ahora_time = ahora.time()
            factor     = 1  # XSP

        with st.spinner("Calculando niveles gamma..."):
            g = calcular_niveles_gamma(d["actual"], factor=factor)

        # ── Ventana horaria ────────────────────────────────────────────
        ventana, ventana_icon, ventana_desc = evaluar_ventana_horaria(ahora_time)

        # ── Strikes redondos cercanos ──────────────────────────────────
        niveles_redondos = analizar_strikes_redondos(d["actual"], rango_pts=25)

        # ── FILTROS BASE ───────────────────────────────────────────────
        vix_extremo         = d["vix"] > 35
        backwardation       = d["vix"] > d["vix3m"]
        vix_peligro         = d["vix"] > d["vix9d"]
        precio_sobre_vwap   = d["actual"] > d["vwap"]
        gap_grande_arr      = d["gap_pct"] > 0.5
        gap_grande_abj      = d["gap_pct"] < -0.5
        vvix_extremo        = d["vvix"] > 100
        prima_barata        = d["ivr"] < 25
        sobreextendido_arr  = d["pct_b"] > 0.95
        sobreextendido_abj  = d["pct_b"] < 0.05
        tnx_presion_bajista = d["tnx_cambio"] > 1.5
        precio_en_or        = d["or_low"] <= d["actual"] <= d["or_high"]
        ventana_evitar      = ventana == "EVITAR"
        vix1d_spike         = d["vix1d_ratio"] > 1.2
        ts_tension          = d["ts_slope"] > 0.95
        rally_falso         = not d["amplitud_ok"] and d["actual"] > d["prev"]

        # ── FILTROS GAMMA ──────────────────────────────────────────────
        gex_negativo        = not g["gex_positivo"]
        precio_bajo_flip    = g["gamma_flip"] and d["actual"] < g["gamma_flip"]

        # Max Pain: si el precio está lejos del max pain, tiende a acercarse
        max_pain_dist = None
        sesgo_max_pain = None
        if g["max_pain"]:
            max_pain_dist  = d["actual"] - g["max_pain"]
            # Si precio > max_pain → tiende a bajar → favor Bear Call / IC
            # Si precio < max_pain → tiende a subir → favor Bull Put / IC
            sesgo_max_pain = "bajista" if max_pain_dist > 5 else ("alcista" if max_pain_dist < -5 else "neutro")

        # Call Wall / Put Wall como resistencia/soporte gamma
        # Si put_wall coincide con un redondo → nivel DOBLEMENTE confirmado
        put_wall_confirmado  = g["put_wall"]  and g["put_wall_redondo"]
        call_wall_confirmado = g["call_wall"] and g["call_wall_redondo"]

        # ── BIAS ───────────────────────────────────────────────────────
        bias = (
            d["actual"] > d["prev"] and
            d["votos_tech"] >= 2 and
            d["rsp_bull"] and
            d["amplitud_ok"] and
            not vix_peligro and
            not noticias["bloqueo"] and
            precio_sobre_vwap
        )

        if d["z_score"] > 2.2  or sobreextendido_arr: bias = False
        if d["z_score"] < -2.2 or sobreextendido_abj: bias = True
        if gap_grande_arr:                              bias = False
        if gap_grande_abj:                              bias = True
        if tnx_presion_bajista and bias:                bias = False
        if rally_falso and bias:                        bias = False
        if vix1d_spike:                                 bias = False
        if precio_bajo_flip:                            bias = False  # debajo del flip → no apostar al alza
        # Ajuste por Max Pain
        if sesgo_max_pain == "bajista" and bias:        bias = False
        if sesgo_max_pain == "alcista" and not bias:    bias = True

        # ── IRON CONDOR ────────────────────────────────────────────────
        iron_condor = (
            (d["vix"] < 18 and d["inside_day"] and
             abs(d["streak"]) < 2 and 1 <= d["votos_tech"] <= 2 and d["skew"] < 125)
            or precio_en_or
            or g["en_rango_gamma"]   # precio dentro de put_wall / call_wall → IC ideal
        )

        # ── CÁLCULO STRIKE BASE ────────────────────────────────────────
        vix_para_dist = d["vix1d"] if vix1d_spike else d["vix"]
        m_seg  = 0.85 if d["vix"] < 15 else (1.05 if d["vix"] < 22 else 1.35)
        dist   = max(d["atr14"] * 0.90, d["actual"] * ((vix_para_dist / 100) / (252**0.5)) * m_seg)
        vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)

        # ── AJUSTE POR STRIKES REDONDOS ────────────────────────────────
        # 1. Si el strike cae en múltiplo de 5/10, alejarlo un tick
        vender, fue_ajustado = ajustar_strike_redondo(vender, bias)

        # 2. Si el strike está muy cerca de un nivel redondo fuerte (múltiplo de 10),
        #    ese nivel actuará como imán — lo tenemos en cuenta para la prob ITM
        cerca_redondo, redondo_cercano = strike_cerca_redondo_clave(vender, umbral=3)

        # 3. No cruzar Call Wall / Put Wall con el strike vendido
        if g["call_wall"] and bias and vender >= g["call_wall"]:
            vender = int(g["call_wall"]) - 1
            vender, _ = ajustar_strike_redondo(vender, bias)

        if g["put_wall"] and not bias and vender <= g["put_wall"]:
            vender = int(g["put_wall"]) + 1
            vender, _ = ajustar_strike_redondo(vender, bias)

        # 4. Alineación con Max Pain: si el strike propuesto está entre
        #    precio y max_pain, lo alejamos un poco más (zona de atracción)
        if g["max_pain"]:
            if bias and g["max_pain"] < d["actual"] and vender > g["max_pain"]:
                vender = int(g["max_pain"]) - 2
            elif not bias and g["max_pain"] > d["actual"] and vender < g["max_pain"]:
                vender = int(g["max_pain"]) + 2

        prob_itm            = calcular_delta_prob(d["actual"], vender, vix_para_dist)
        distancia_seguridad = abs(d["actual"] - vender)

        # ── LOTES ──────────────────────────────────────────────────────
        lotes_base     = max(1, int((cap / 25000) * 10))
        motivo_bloqueo = ""

        if vix_extremo:
            motivo_bloqueo = "VIX Extremo (>35)"
            lotes = 0
        elif vvix_extremo:
            motivo_bloqueo = "VVIX Extremo (>100) — volatilidad impredecible"
            lotes = 0
        elif backwardation:
            motivo_bloqueo = "Backwardation VIX/VIX3M"
            lotes = 0
        elif ts_tension:
            motivo_bloqueo = f"Term Structure en tensión (slope {d['ts_slope']:.2f})"
            lotes = 0
        elif d["vix_speed"] > 3.5:
            motivo_bloqueo = f"Velocidad VIX elevada ({d['vix_speed']:.1f}%)"
            lotes = 0
        elif ventana_evitar:
            motivo_bloqueo = f"Ventana horaria peligrosa — {ventana_desc}"
            lotes = 0
        elif noticias["bloqueo"]:
            motivo_bloqueo = f"Noticias alto impacto: {', '.join(noticias['eventos'])}"
            lotes = 0
        elif pnl_dia <= MAX_LOSS_DIA:
            motivo_bloqueo = f"Límite pérdida diaria ({pnl_dia}€)"
            lotes = 0
        else:
            lotes = int(lotes_base * 1.5) if d["vix"] < 18 else (lotes_base if d["vix"] < 25 else lotes_base // 2)
            if prima_barata:   lotes = max(1, lotes - 1)  # prima barata → reducir
            if vix1d_spike:    lotes = max(1, lotes - 1)  # vol intradía alta → reducir
            if gex_negativo:   lotes = max(1, lotes - 1)  # GEX negativo → MM en modo volátil

        # ══════════════════════════════════════════════════════════════
        # DISPLAY
        # ══════════════════════════════════════════════════════════════
        st.header(f"Dashboard | {ahora.strftime('%H:%M:%S')}")

        # Banner ventana horaria
        if   ventana == "ÓPTIMA":   st.success(f"{ventana_icon} Ventana: **{ventana}** — {ventana_desc}")
        elif ventana == "EVITAR":   st.error(  f"{ventana_icon} Ventana: **{ventana}** — {ventana_desc}")
        else:                       st.info(   f"{ventana_icon} Ventana: **{ventana}** — {ventana_desc}")

        # ── Fila 1: Precios ───────────────────────────────────────────
        st.subheader("📈 Precio y Volatilidad")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("XSP Precio",  f"{d['actual']:.2f}")
        c2.metric("VWAP",        f"{d['vwap']:.2f}",        "SOBRE" if precio_sobre_vwap else "BAJO")
        c3.metric("VIX",         f"{d['vix']:.2f}")
        c4.metric("VIX1D",       f"{d['vix1d']:.2f}",       f"ratio {d['vix1d_ratio']:.2f} 🔴" if vix1d_spike else f"ratio {d['vix1d_ratio']:.2f} ✅")
        c5.metric("Z-Score",     f"{d['z_score']:.2f}")

        # ── Fila 2: Estructura volatilidad ────────────────────────────
        st.subheader("🌡️ Estructura de Volatilidad")
        c6, c7, c8, c9, c10 = st.columns(5)
        c6.metric("IV Rank",      f"{d['ivr']:.1f}%",        "Prima rica ✅" if d['ivr'] >= 50 else "Prima barata ⚠️")
        c7.metric("VVIX",         f"{d['vvix']:.1f}",        "Peligro 🔴"   if vvix_extremo  else "Normal ✅")
        c8.metric("TS Slope",     f"{d['ts_slope']:.3f}",    "Tensión 🔴"   if ts_tension    else ("Alerta ⚠️" if d['ts_slope'] > 0.85 else "Contango ✅"))
        c9.metric("Bollinger %B", f"{d['pct_b']:.2f}",       "Sobreext ⚠️"  if (sobreextendido_arr or sobreextendido_abj) else "Normal ✅")
        c10.metric("TNX Cambio",  f"{d['tnx_cambio']:+.2f}%","Presión 🔴"   if tnx_presion_bajista else "Normal ✅")

        # ── Fila 3: Niveles Gamma ─────────────────────────────────────
        st.subheader("⚡ Niveles Gamma (Options Flow)")
        c11, c12, c13, c14, c15 = st.columns(5)
        cw_txt = f"{g['call_wall']:.1f} {'🔴 REDONDO' if call_wall_confirmado else ''}" if g['call_wall'] else "N/A"
        pw_txt = f"{g['put_wall']:.1f} {'🔴 REDONDO' if put_wall_confirmado  else ''}" if g['put_wall']  else "N/A"
        gf_txt = f"{g['gamma_flip']:.1f}" if g['gamma_flip'] else "N/A"
        mp_txt = f"{g['max_pain']:.1f}"   if g['max_pain']   else "N/A"
        c11.metric("Call Wall",   cw_txt)
        c12.metric("Put Wall",    pw_txt)
        c13.metric("Gamma Flip",  gf_txt, "Precio BAJO flip ⚠️" if precio_bajo_flip else "Precio SOBRE flip ✅")
        c14.metric("Max Pain",    mp_txt, f"Sesgo {sesgo_max_pain}" if sesgo_max_pain else "")
        c15.metric("GEX Neto",    f"{g['gex_neto']:,.0f}", "Anclaje ✅" if g['gex_positivo'] else "Volátil 🔴")

        # ── Fila 4: Operativa ─────────────────────────────────────────
        st.subheader("🎯 Operativa")
        c16, c17, c18, c19, c20 = st.columns(5)
        c16.metric("Gap %",       f"{d['gap_pct']:.2f}%")
        c17.metric("Streak",      f"{d['streak']} días")
        c18.metric("Amplitud",    "Confirmada ✅" if d['amplitud_ok'] else "Rally falso ⚠️")
        c19.metric("Distancia",   f"{distancia_seguridad:.1f} pts")
        c20.metric("Prob ITM",    f"{prob_itm*100:.1f}%")

        # ── Opening Range ─────────────────────────────────────────────
        st.info(
            f"📊 Opening Range: {d['or_low']:.2f} — {d['or_high']:.2f} | "
            f"Precio {'DENTRO ⚠️ (indecisión)' if precio_en_or else 'FUERA ✅ (hay dirección)'}"
        )

        # ── Tabla de strikes redondos cercanos ────────────────────────
        with st.expander("📐 Strikes redondos clave cercanos al precio"):
            st.caption("Los múltiplos de 10 son niveles FUERTES — mayor concentración de OI y actividad MM")
            df_niveles = pd.DataFrame(niveles_redondos[:10])
            df_niveles['coincide_call_wall'] = df_niveles['strike'].apply(
                lambda s: "✅" if g['call_wall'] and abs(s - g['call_wall']) < 2 else "")
            df_niveles['coincide_put_wall']  = df_niveles['strike'].apply(
                lambda s: "✅" if g['put_wall']  and abs(s - g['put_wall'])  < 2 else "")
            df_niveles['coincide_max_pain']  = df_niveles['strike'].apply(
                lambda s: "✅" if g['max_pain']  and abs(s - g['max_pain'])  < 2 else "")
            st.dataframe(df_niveles, hide_index=True)

        # ── Alertas ───────────────────────────────────────────────────
        if noticias["eventos"]:
            st.warning(f"📅 Noticias hoy: {', '.join(noticias['eventos'])}")
        if fue_ajustado:
            st.info(f"📐 Strike ajustado por nivel redondo — evitando vender en zona contestada")
        if cerca_redondo:
            st.info(f"🧲 Strike {vender} cerca del nivel redondo {redondo_cercano} — posible imán de precio")
        if put_wall_confirmado:
            st.success(f"🔴 Put Wall {g['put_wall']:.1f} coincide con strike redondo — soporte DOBLEMENTE confirmado")
        if call_wall_confirmado:
            st.success(f"🔴 Call Wall {g['call_wall']:.1f} coincide con strike redondo — resistencia DOBLEMENTE confirmada")
        if prima_barata and lotes > 0:
            st.warning(f"⚠️ IVR bajo ({d['ivr']:.1f}%) — prima barata, lotes reducidos a {lotes}")
        if vix1d_spike and lotes > 0:
            st.warning(f"⚠️ VIX1D spike (ratio {d['vix1d_ratio']:.2f}) — volatilidad intradía alta, lotes reducidos a {lotes}")
        if gex_negativo and lotes > 0:
            st.warning(f"⚠️ GEX negativo — MM en modo cobertura, lotes reducidos a {lotes}")
        if rally_falso:
            st.warning("⚠️ Rally falso — SPY sube pero RSP no confirma amplitud")
        if precio_bajo_flip:
            st.warning(f"⚠️ Precio bajo Gamma Flip ({g['gamma_flip']:.1f}) — zona de aceleración bajista")
        if g["en_rango_gamma"]:
            st.success(f"✅ Precio dentro del rango gamma [{g['put_wall']:.1f} — {g['call_wall']:.1f}] — Iron Condor ideal")

        # ── Resultado final ───────────────────────────────────────────
        if lotes > 0:
            estrategia_txt = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias else "BEAR CALL")
            st.success(
                f"🔥 ESTRATEGIA: {estrategia_txt} | "
                f"VENDER: {vender} | "
                f"LOTES: {lotes} | "
                f"VIX usado: {vix_para_dist:.1f}"
            )

            if enviar_auto:
                mp_line = f"🔹 Max Pain: {g['max_pain']:.1f} (sesgo {sesgo_max_pain})\n" if g['max_pain'] else ""
                gf_line = f"🔹 Gamma Flip: {g['gamma_flip']:.1f} {'⚠️ bajo flip' if precio_bajo_flip else '✅'}\n" if g['gamma_flip'] else ""
                msg_tel = (
                    f"🚀 XSP v9.0 — {estrategia_txt}\n"
                    f"🔹 VENDER: {vender}{' (ajustado por redondo)' if fue_ajustado else ''}\n"
                    f"🔹 PROB ITM: {prob_itm*100:.1f}%\n"
                    f"🔹 DISTANCIA: {distancia_seguridad:.1f} pts\n"
                    f"🔹 LOTES: {lotes}\n"
                    f"─────────────────\n"
                    f"🔹 Call Wall: {g['call_wall']:.1f if g['call_wall'] else 'N/A'} {'🔴' if call_wall_confirmado else ''}\n"
                    f"🔹 Put Wall:  {g['put_wall']:.1f  if g['put_wall']  else 'N/A'} {'🔴' if put_wall_confirmado  else ''}\n"
                    f"{gf_line}"
                    f"{mp_line}"
                    f"🔹 GEX: {'Anclaje ✅' if g['gex_positivo'] else 'Volátil 🔴'} ({g['gex_neto']:,.0f})\n"
                    f"─────────────────\n"
                    f"🔹 VIX: {d['vix']:.1f} | VIX1D: {d['vix1d']:.1f} (x{d['vix1d_ratio']:.2f})\n"
                    f"🔹 VVIX: {d['vvix']:.1f} | TS: {d['ts_slope']:.3f}\n"
                    f"🔹 IVR: {d['ivr']:.1f}% | %B: {d['pct_b']:.2f}\n"
                    f"🔹 Z: {d['z_score']:.2f} | TNX: {d['tnx_cambio']:+.2f}%\n"
                    f"🔹 Amplitud: {'✅' if d['amplitud_ok'] else '⚠️ falso'} | "
                    f"Ventana: {ventana_icon} {ventana}"
                )
                enviar_telegram(msg_tel)
        else:
            motivo_display = motivo_bloqueo if motivo_bloqueo else "Condiciones de riesgo detectadas"
            st.error(f"🚫 NO OPERAR: {motivo_display}")

if __name__ == "__main__":
    main()
