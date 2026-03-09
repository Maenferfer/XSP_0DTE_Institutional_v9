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
    token = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
    chat_id = "7121107501"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
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
    hoy = str(date.today())
    url = f"https://finnhub.io/api/v1/calendar/economic?from={hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "eventos": []}
    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
            if ev.get('country') == 'US' and str(ev.get('impact', '')).lower() in ['high', '3', '4']:
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    h_utc = datetime.strptime(ev['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    h_es = h_utc.astimezone(ZONA_HORARIA).time()
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if time(14, 0) <= h_es <= time(21, 0):
                        estado["bloqueo"] = True
    except:
        pass
    return estado

# ================================================================
# FUNCIONES DE CÁLCULO
# ================================================================
def calcular_streak_dias(df_diario):
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2: return 0
    streak = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i - 1]) * direction > 0:
            streak += direction
        else:
            break
    return streak

def evaluar_ventana_horaria(ahora_time):
    """Evalúa la calidad de la ventana horaria para operar 0DTE (hora Madrid)"""
    if time(15, 30) <= ahora_time <= time(15, 45):
        return "EVITAR", "🔴", "Apertura NY caótica"
    elif time(15, 45) <= ahora_time <= time(17, 30):
        return "ÓPTIMA", "🟢", "Apertura NY asentada"
    elif time(17, 30) <= ahora_time <= time(19, 0):
        return "NORMAL", "🟡", "Tramo intermedio"
    elif time(19, 0) <= ahora_time <= time(20, 30):
        return "ÓPTIMA", "🟢", "Tramo final tranquilo"
    elif time(20, 30) <= ahora_time <= time(21, 0):
        return "EVITAR", "🔴", "Cierre errático"
    elif ahora_time < time(15, 30):
        return "PREMERCADO", "⚪", "Mercado cerrado"
    else:
        return "CERRADO", "⚪", "Mercado cerrado"

def obtener_datos_maestros():
    try:
        tickers = {
            "XSP": "^XSP", "SPY": "SPY", "RSP": "RSP",
            "VIX": "^VIX", "VIX1D": "^VIX1D", "VIX9D": "^VIX9D", "VIX3M": "^VIX3M",
            "VVIX": "^VVIX", "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"
        }
        raw_data = {}
        for k, v in tickers.items():
            t = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty:
                df = t.history(period="7d", interval="1d")
            raw_data[k] = df

        df_x = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if raw_data["XSP"].empty else 1
        actual = float(df_x['Close'].iloc[-1]) * factor

        # apertura y prev_close desde datos diarios
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

        # ── VWAP + Opening Range (SPY = volumen real) ──────────────────
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
                    typical  = (df_hoy['High'] + df_hoy['Low'] + df_hoy['Close']) / 3
                    cum_vol  = df_hoy['Volume'].cumsum().replace(0, np.nan)
                    vwap_s   = (typical * df_hoy['Volume']).cumsum() / cum_vol
                    vwap_actual = float(vwap_s.dropna().iloc[-1]) * factor

                    ap_ts  = df_hoy.index[0]
                    df_or  = df_hoy[df_hoy.index <= ap_ts + pd.Timedelta(minutes=30)]
                    if not df_or.empty:
                        or_high = float(df_or['High'].max()) * factor
                        or_low  = float(df_or['Low'].min())  * factor
        except Exception as e_vwap:
            st.warning(f"⚠️ VWAP/OR fallback: {e_vwap}")

        # ── IV Rank 52 semanas ──────────────────────────────────────────
        ivr = 50.0
        try:
            vix_hist = yf.Ticker("^VIX").history(period="252d", interval="1d")['Close']
            if len(vix_hist) > 20:
                ivr = (float(raw_data["VIX"]['Close'].iloc[-1]) - vix_hist.min()) / \
                      (vix_hist.max() - vix_hist.min()) * 100
        except:
            pass

        # ── Bollinger %B ────────────────────────────────────────────────
        pct_b = 0.5
        try:
            ma20     = cierre_diario.tail(20).mean()
            std20    = cierre_diario.tail(20).std()
            bb_upper = ma20 + 2 * std20
            bb_lower = ma20 - 2 * std20
            if (bb_upper - bb_lower) > 0:
                pct_b = (cierre_diario.iloc[-1] - bb_lower) / (bb_upper - bb_lower)
        except:
            pass

        # ── VVIX ────────────────────────────────────────────────────────
        vvix = 90.0
        try:
            if not raw_data["VVIX"].empty:
                vvix = float(raw_data["VVIX"]['Close'].iloc[-1])
        except:
            pass

        # ── VIX1D ───────────────────────────────────────────────────────
        vix1d = float(raw_data["VIX"]['Close'].iloc[-1])  # fallback al VIX normal
        try:
            if not raw_data["VIX1D"].empty:
                vix1d = float(raw_data["VIX1D"]['Close'].iloc[-1])
        except:
            pass

        # ── TNX Momentum ────────────────────────────────────────────────
        tnx_val      = float(raw_data["TNX"]['Close'].iloc[-1])  if not raw_data["TNX"].empty else 4.0
        tnx_prev_val = float(raw_data["TNX"]['Close'].iloc[-2])  if len(raw_data["TNX"]) > 1 else tnx_val
        tnx_cambio   = ((tnx_val - tnx_prev_val) / tnx_prev_val) * 100 if tnx_prev_val > 0 else 0

        # ── Term Structure Slope VIX/VIX3M ──────────────────────────────
        vix3m     = float(raw_data["VIX3M"]['Close'].iloc[-1]) if not raw_data["VIX3M"].empty else 20.0
        ts_slope  = float(raw_data["VIX"]['Close'].iloc[-1]) / vix3m if vix3m > 0 else 1.0

        # ── Amplitud de mercado SPY vs RSP ──────────────────────────────
        spy_up = (not raw_data["SPY"].empty and
                  float(raw_data["SPY"]['Close'].iloc[-1]) > float(raw_data["SPY"]['Open'].iloc[-1]))
        rsp_up = (not raw_data["RSP"].empty and
                  float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]))
        amplitud_ok = spy_up and rsp_up

        # ── VIX1D Spike ratio ───────────────────────────────────────────
        vix_ref       = float(raw_data["VIX"]['Close'].iloc[-1])
        vix1d_ratio   = vix1d / vix_ref if vix_ref > 0 else 1.0

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
            "amplitud_ok" : amplitud_ok,
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

def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    T     = dias_exp / 252
    sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    return round(norm.cdf(-d1), 4)

# ================================================================
# MAIN STREAMLIT
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v9.0")

    cap         = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia     = st.sidebar.number_input("P&L del día (€)",    value=250.0)
    MAX_LOSS_DIA = -300.0
    enviar_auto = st.sidebar.checkbox("Enviar Telegram automáticamente", value=False)

    if st.button('EJECUTAR ANÁLISIS'):
        with st.spinner('Obteniendo datos maestros...'):
            noticias = check_noticias_pro(FINNHUB_API_KEY)
            d        = obtener_datos_maestros()

            if not d:
                st.error("No se pudieron obtener los datos.")
                return

            ahora      = datetime.now(ZONA_HORARIA)
            ahora_time = ahora.time()

            # ── Ventana horaria ────────────────────────────────────────
            ventana, ventana_icon, ventana_desc = evaluar_ventana_horaria(ahora_time)

            # ── Filtros ────────────────────────────────────────────────
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

            # ── VIX1D: spike de volatilidad intradía ───────────────────
            # ratio >1.2 = mercado espera movimiento grande HOY
            vix1d_spike         = d["vix1d_ratio"] > 1.2

            # ── Term Structure Slope ───────────────────────────────────
            # <0.85 contango normal | 0.85-0.95 tensión | >0.95 peligro
            ts_tension          = d["ts_slope"] > 0.95

            # ── Amplitud: rally falso si SPY sube pero RSP no acompaña ─
            rally_falso         = not d["amplitud_ok"] and d["actual"] > d["prev"]

            # ── BIAS ───────────────────────────────────────────────────
            bias = (
                d["actual"] > d["prev"] and
                d["votos_tech"] >= 2 and
                d["rsp_bull"] and
                d["amplitud_ok"] and
                not vix_peligro and
                not noticias["bloqueo"] and
                precio_sobre_vwap
            )

            if d["z_score"] > 2.2  or sobreextendido_arr:              bias = False
            if d["z_score"] < -2.2 or sobreextendido_abj:              bias = True
            if gap_grande_arr:                                           bias = False
            if gap_grande_abj:                                           bias = True
            if tnx_presion_bajista and bias:                             bias = False
            if rally_falso and bias:                                     bias = False
            if vix1d_spike:                                              bias = False  # no apostar dirección si vol intradía alta

            # ── Iron Condor ────────────────────────────────────────────
            iron_condor = (
                d["vix"] < 18 and
                d["inside_day"] and
                abs(d["streak"]) < 2 and
                1 <= d["votos_tech"] <= 2 and
                d["skew"] < 125
            ) or precio_en_or

            # ── Strike y lotes ─────────────────────────────────────────
            # Usar VIX1D para distancia si hay spike, es más preciso para hoy
            vix_para_dist = d["vix1d"] if vix1d_spike else d["vix"]
            m_seg  = 0.85 if d["vix"] < 15 else (1.05 if d["vix"] < 22 else 1.35)
            dist   = max(d["atr14"] * 0.90, d["actual"] * ((vix_para_dist / 100) / (252**0.5)) * m_seg)
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
            if vender % 5 == 0: vender = vender - 1 if bias else vender + 1

            prob_itm            = calcular_delta_prob(d["actual"], vender, vix_para_dist)
            distancia_seguridad = abs(d["actual"] - vender)

            lotes_base = max(1, int((cap / 25000) * 10))

            # ── Motivo de bloqueo y lotes finales ─────────────────────
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
                if prima_barata:  lotes = max(1, lotes - 1)  # prima barata → reducir
                if vix1d_spike:   lotes = max(1, lotes - 1)  # vol intradía alta → reducir

            # ── DISPLAY ────────────────────────────────────────────────
            st.header(f"Dashboard | {ahora.strftime('%H:%M:%S')}")

            # Ventana horaria — banner destacado
            if ventana == "ÓPTIMA":
                st.success(f"{ventana_icon} Ventana horaria: **{ventana}** — {ventana_desc}")
            elif ventana == "EVITAR":
                st.error(f"{ventana_icon} Ventana horaria: **{ventana}** — {ventana_desc}")
            else:
                st.info(f"{ventana_icon} Ventana horaria: **{ventana}** — {ventana_desc}")

            # Fila 1 — Precios y VIX
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("XSP Precio",  f"{d['actual']:.2f}")
            col2.metric("VWAP",        f"{d['vwap']:.2f}",   "SOBRE" if precio_sobre_vwap else "BAJO")
            col3.metric("VIX",         f"{d['vix']:.2f}")
            col4.metric("VIX1D",       f"{d['vix1d']:.2f}",  f"ratio {d['vix1d_ratio']:.2f} 🔴" if vix1d_spike else f"ratio {d['vix1d_ratio']:.2f} ✅")
            col5.metric("Z-Score",     f"{d['z_score']:.2f}")

            # Fila 2 — Volatilidad estructural
            col6, col7, col8, col9, col10 = st.columns(5)
            col6.metric("IV Rank",     f"{d['ivr']:.1f}%",   "Prima rica ✅" if d['ivr'] >= 50 else "Prima barata ⚠️")
            col7.metric("VVIX",        f"{d['vvix']:.1f}",   "Peligro 🔴" if vvix_extremo else "Normal ✅")
            col8.metric("TS Slope",    f"{d['ts_slope']:.3f}","Tensión 🔴" if ts_tension else ("Alerta
