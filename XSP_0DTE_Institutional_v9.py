import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import os
import warnings
import time as sleep_timer
import logging

# --- CONFIGURACIÓN ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

# Configuración de interfaz Streamlit
st.set_page_config(page_title="XSP 0DTE Institutional v9.0", layout="wide")

# ================================================================
# TELEGRAM — BUG #4 CORREGIDO
# ================================================================
def enviar_telegram(mensaje):
    token = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
    chat_id = "7121107501"
    url = f"https://api.telegram.org{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=5)
    except:
        pass

# ================================================================
# NOTICIAS — BUG #1 CORREGIDO
# ================================================================
def check_noticias_pro(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS", "TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}"
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
# STREAK DE DÍAS CONSECUTIVOS
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

# ================================================================
# DATOS MAESTROS — MEJORA: VIX3M añadido
# ================================================================
def obtener_datos_maestros():
    vals = {}
    try:
        tickers = {"XSP": "^XSP", "SPY": "SPY", "RSP": "RSP", "VIX": "^VIX", "VIX9D": "^VIX9D", "VIX3M": "^VIX3M", "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"}
        raw_data = {}
        for k, v in tickers.items():
            t = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            raw_data[k] = df
        
        df_x = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if raw_data["XSP"].empty else 1
        actual = float(df_x['Close'].iloc[-1]) * factor
        apertura = float(df_x['Open'].iloc[-1]) * factor
        prev_close = float(df_x['Close'].iloc[-2]) * factor

        def calc_rsi(series, p):
            delta = series.diff()
            g = delta.where(delta > 0, 0).rolling(window=p).mean()
            l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]

        vol_actual = df_x['Volume'].iloc[-1]
        vol_avg = df_x['Volume'].tail(30).mean()
        vol_rel = vol_actual / vol_avg if vol_avg > 0 else 1.0

        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty: df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
        df_diario = df_diario * factor if raw_data["XSP"].empty else df_diario
        
        atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        streak = calcular_streak_dias(df_diario)
        cierre_diario = df_diario['Close']
        std_20 = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0
        
        inside_day = (len(df_diario) >= 2 and df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2])

        if len(df_x) > 30:
            typical = (df_x['High'] + df_x['Low'] + df_x['Close']) / 3
            vwap = (typical * df_x['Volume']).cumsum() / df_x['Volume'].cumsum()
            vwap_actual = float(vwap.iloc[-1]) * factor
        else: vwap_actual = actual

        vix3m = float(raw_data["VIX3M"]['Close'].iloc[-1]) if not raw_data["VIX3M"].empty else 20.0
        
        vals = {
            "actual": actual, "apertura": apertura, "prev": prev_close,
            "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14), "rsi_5m": calc_rsi(df_x['Close'], 5),
            "cambio_15m": (actual - float(df_x['Close'].iloc[-15]) * factor) if len(df_x) > 15 else 0,
            "std_dev": df_x['Close'].std() * factor, "vol_rel": vol_rel,
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]), "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]), "vix3m": vix3m,
            "skew": float(raw_data["SKEW"]['Close'].iloc[-1]), "tnx": float(raw_data["TNX"]['Close'].iloc[-1]),
            "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]),
            "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),
            "atr14": atr14, "streak": streak, "z_score": z_score, "inside_day": inside_day,
            "gap_pct": (apertura - prev_close) / prev_close * 100, "vwap": vwap_actual,
            "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash": (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100 if len(df_x) > 5 else 0,
        }

        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d_tk = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d_tk.empty and d_tk['Close'].iloc[-1] > d_tk['Open'].iloc[-1]: votos += 1
        vals["votos_tech"] = votos

    except Exception as e:
        st.error(f"[ERROR datos]: {e}")
        return None
    return vals

# ================================================================
# FUNCIÓN AUXILIAR: Delta teórico
# ================================================================
def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    T = dias_exp / 252
    sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    prob_itm = norm.cdf(-d1)
    return round(prob_itm, 4)

# ================================================================
# MAIN STREAMLIT
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v9.0 — Definitivo")
    st.markdown("---")
    
    # Sidebar para inputs que antes eran consola
    cap = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia = st.sidebar.number_input("P&L del día (€)", value=0.0)
    MAX_LOSS_DIA = -300.0

    if st.button('EJECUTAR ANÁLISIS'):
        with st.spinner('Obteniendo datos maestros...'):
            noticias = check_noticias_pro(FINNHUB_API_KEY)
            d = obtener_datos_maestros()
            
            if not d:
                st.error("No se pudieron obtener los datos.")
                return

            ahora = datetime.now(ZONA_HORARIA)
            ahora_time = ahora.time()
            mercado_asentado = ahora_time >= time(16, 45)
            hora_limite = time(20, 45)
            minutos_al_limite = max(0, (datetime.combine(date.today(), hora_limite) - datetime.combine(date.today(), ahora_time)).total_seconds() / 60)

            # --- FILTROS DE RÉGIMEN ---
            vix_extremo = d["vix"] > 35
            backwardation = d["vix"] > d["vix3m"]
            vix_inv = d["vix"] < d["vix9d"]
            vix_peligro = d["vix"] > d["vix9d"]
            pico_bonos = d["tnx"] > d["tnx_prev"] * 1.02
            vix_panico = d["vix_speed"] > 3.5
            agotamiento = (d["actual"] > d["apertura"]) and (d["vol_rel"] < 0.6)
            extendido = abs(d["actual"] - d["apertura"]) > d["std_dev"] * 2.5
            gap_grande_arr = d["gap_pct"] > 0.5
            gap_grande_abj = d["gap_pct"] < -0.5
            streak_bajista = d["streak"] <= -3
            streak_alcista = d["streak"] >= 3
            divergencia_bonos = (d["tnx"] > d["tnx_prev"]) and (d["actual"] > d["apertura"])
            precio_sobre_vwap = d["actual"] > d["vwap"]
            skew_ok_ic = d["skew"] < 125
            iron_condor = (d["vix"] < 18 and d["inside_day"] and abs(d["streak"]) < 2 and 1 <= d["votos_tech"] <= 2 and skew_ok_ic)

            # --- BIAS ---
            bias = (d["actual"] > d["prev"] and d["votos_tech"] >= 2 and d["rsp_bull"] and not vix_peligro and not noticias["bloqueo"] and not divergencia_bonos and precio_sobre_vwap)
            
            if d["z_score"] > 2.2:
                bias = False
                st.warning("PATRÓN: Agotamiento alcista extremo (Z > 2.2) → Bear Call forzado")
            if d["z_score"] < -2.2:
                bias = True
                st.warning("PATRÓN: Pánico excesivo (Z < -2.2) → Bull Put forzado")
            if gap_grande_arr and not iron_condor: bias = False
            if gap_grande_abj and not iron_condor: bias = True

            # --- CÁLCULO STRIKE ---
            m_seg = 0.85 if d["vix"] < 15 else (1.05 if d["vix"] < 22 else 1.35)
            m_horario = 0.92 if ahora_time >= time(16, 45) else 1.0
            dist_atr = d["atr14"] * 0.90 * m_horario
            dist_sigma = d["actual"] * ((d["vix"] / 100) / (252**0.5)) * m_seg
            dist = max(dist_atr, dist_sigma)
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
            if vender % 5 == 0: vender = vender - 1 if bias else vender + 1
            
            prob_itm = calcular_delta_prob(d["actual"], vender, d["vix"])
            if prob_itm > 0.20:
                vender = vender - 2 if bias else vender + 2
                prob_itm = calcular_delta_prob(d["actual"], vender, d["vix"])
            distancia_seguridad = abs(d["actual"] - vender)

            # --- GESTIÓN LOTES ---
            lotes_base = max(1, int((cap / 25000) * 10))
            if vix_extremo or backwardation or pico_bonos or vix_panico:
                lotes = 0
                motivo_bloqueo = "VIX EXTREMO / BACKWARDATION / BONOS"
            else:
                if d["vix"] < 18: lotes = int(lotes_base * 1.5)
                elif d["vix"] < 25: lotes = lotes_base
                else: lotes = max(1, lotes_base // 2)
                if distancia_seguridad > 5 and d["vix"] < 20: lotes = max(lotes, 15)
                if d["inside_day"] and not vix_peligro and lotes > 0:
                    lotes = int(lotes * 1.2)
                    st.info("OPORTUNIDAD: Inside Day detectado. Lotes +20%.")
            
            if pnl_dia <= MAX_LOSS_DIA:
                lotes = 0
                st.error(f"LÍMITE DIARIO ALCANZADO: P&L día = {pnl_dia:.0f}€. No operar.")

            # --- SPREAD ---
            if iron_condor:
                ancho = 2
                vender_call = round(d["actual"] + dist)
                comprar_call = vender_call + ancho
                comprar_put = vender - ancho
            else:
                ancho = 2 if d["vix"] < 18 else (3 if d["vix"] < 25 else 5)
                comprar = vender - ancho if bias else vender + ancho

            # --- DISPLAY DASHBOARD ---
            st.header(f"XSP 0DTE v9.0 | {ahora.strftime('%H:%M:%S')}")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("XSP Precio", f"{d['actual']:.2f}")
            col2.metric("VWAP", f"{d['vwap']:.2f}", "SOBRE" if precio_sobre_vwap else "BAJO")
            col3.metric("VIX", f"{d['vix']:.2f}", "¡PELIGRO!" if vix_extremo else "")
            col4.metric("Z-Score", f"{d['z_score']:.2f}")

            st.write("---")
            if lotes == 0:
                st.error(f"🚫 NO OPERAR: {motivo_bloqueo if 'motivo_bloqueo' in locals() else 'Condiciones insuficientes'}")
            else:
                if iron_condor:
                    st.success(f"💎 ESTRATEGIA: IRON CONDOR | LOTES: {lotes}")
                    st.write(f"**BULL PUT:** Vender {vender} / Comprar {comprar_put}")
                    st.write(f"**BEAR CALL:** Vender {vender_call} / Comprar {comprar_call}")
                else:
                    st.success(f"🔥 ESTRATEGIA: {'BULL PUT' if bias else 'BEAR CALL'}")
                    st.write(f"**VENDER:** {vender} | **COMPRAR:** {comprar} | **LOTES:** {lotes}")
                    st.write(f"Distancia: {distancia_seguridad:.2f} | Prob ITM: {prob_itm*100:.1f}%")

            # Notificación Telegram (simulada al dar click o programada)
            if st.button("Enviar alerta a Telegram ahora"):
                estrategia_txt = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias else "BEAR CALL")
                msg_tel = f"XSP v9.0 — {estrategia_txt}\nVENDER: {vender} | PROB ITM: {prob_itm*100:.1f}%\nLOTES: {lotes} | VIX: {d['vix']:.1f}"
                enviar_telegram(msg_tel)
                st.toast("Enviado!")

if __name__ == "__main__":
    main()
