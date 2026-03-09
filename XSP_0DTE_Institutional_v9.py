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

def obtener_datos_maestros():
    vals = {}
    try:
        tickers = {
            "XSP": "^XSP", "SPY": "SPY", "RSP": "RSP",
            "VIX": "^VIX", "VIX9D": "^VIX9D", "VIX3M": "^VIX3M",
            "SKEW": "^SKEW", "TNX": "^TNX", "PCCE": "PCCE"
        }
        raw_data = {}
        for k, v in tickers.items():
            t = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            raw_data[k] = df

        df_x = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if raw_data["XSP"].empty else 1
        actual = float(df_x['Close'].iloc[-1]) * factor

        # ✅ FIX 1: apertura y prev_close desde datos diarios, no minutos
        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty:
            df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
            # ✅ FIX 2: solo escalar columnas de precio, no volumen
            for col in ['Open', 'High', 'Low', 'Close']:
                df_diario[col] = df_diario[col] * factor

        apertura = float(df_diario['Open'].iloc[-1]) * (1 if raw_data["XSP"].empty == False else 1)
        prev_close = float(df_diario['Close'].iloc[-2])

        def calc_rsi(series, p):
            delta = series.diff()
            g = delta.where(delta > 0, 0).rolling(window=p).mean()
            l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]

        vol_actual = df_x['Volume'].iloc[-1]
        vol_avg = df_x['Volume'].tail(30).mean()
        vol_rel = vol_actual / vol_avg if vol_avg > 0 else 1.0

        atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        streak = calcular_streak_dias(df_diario)
        cierre_diario = df_diario['Close']
        std_20 = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0

        inside_day = (
            len(df_diario) >= 2 and
            df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and
            df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2]
        )

        # ✅ FIX 3: VWAP usando SPY (volumen real) — ^XSP es índice sin volumen
        vwap_actual = actual
        try:
            df_spy_vwap = yf.Ticker("SPY").history(period="2d", interval="1m")
            if not df_spy_vwap.empty:
                tz_df = df_spy_vwap.index.tz
                hoy_date = pd.Timestamp.now(tz=tz_df).date()
                df_hoy_spy = df_spy_vwap[df_spy_vwap.index.date == hoy_date]
                if len(df_hoy_spy) > 5:
                    typical = (df_hoy_spy['High'] + df_hoy_spy['Low'] + df_hoy_spy['Close']) / 3
                    cum_vol = df_hoy_spy['Volume'].cumsum().replace(0, np.nan)
                    vwap_series = (typical * df_hoy_spy['Volume']).cumsum() / cum_vol
                    vwap_val = vwap_series.dropna().iloc[-1]
                    vwap_actual = float(vwap_val) * factor
        except Exception as e_vwap:
            st.warning(f"⚠️ VWAP fallback al precio: {e_vwap}")
            vwap_actual = actual

        vix3m = float(raw_data["VIX3M"]['Close'].iloc[-1]) if not raw_data["VIX3M"].empty else 20.0

        vals = {
            "actual": actual,
            "apertura": apertura,
            "prev": prev_close,
            "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14),
            "rsi_5m": calc_rsi(df_x['Close'], 5),
            "cambio_15m": (actual - float(df_x['Close'].iloc[-15]) * factor) if len(df_x) > 15 else 0,
            "std_dev": df_x['Close'].std() * factor,
            "vol_rel": vol_rel,
            "vix": float(raw_data["VIX"]['Close'].iloc[-1]),
            "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]),
            "vix3m": vix3m,
            "skew": float(raw_data["SKEW"]['Close'].iloc[-1]),
            "tnx": float(raw_data["TNX"]['Close'].iloc[-1]),
            "tnx_prev": float(raw_data["TNX"]['Close'].iloc[-2]),
            "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull": float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]),
            "atr14": atr14,
            "streak": streak,
            "z_score": z_score,
            "inside_day": inside_day,
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "vwap": vwap_actual,
            "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash": (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100 if len(df_x) > 5 else 0,
        }

        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d_tk = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d_tk.empty and d_tk['Close'].iloc[-1] > d_tk['Open'].iloc[-1]:
                votos += 1
        vals["votos_tech"] = votos

    except Exception as e:
        st.error(f"[ERROR datos]: {e}")
        return None
    return vals

def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    T = dias_exp / 252
    sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    return round(norm.cdf(-d1), 4)

# ================================================================
# MAIN STREAMLIT
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v9.0")

    cap = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia = st.sidebar.number_input("P&L del día (€)", value=250.0)
    MAX_LOSS_DIA = -300.0
    enviar_auto = st.sidebar.checkbox("Enviar Telegram automáticamente", value=False)

    if st.button('EJECUTAR ANÁLISIS'):
        with st.spinner('Obteniendo datos maestros...'):
            noticias = check_noticias_pro(FINNHUB_API_KEY)
            d = obtener_datos_maestros()

            if not d:
                st.error("No se pudieron obtener los datos.")
                return

            ahora = datetime.now(ZONA_HORARIA)
            ahora_time = ahora.time()

            # --- FILTROS Y BIAS ---
            vix_extremo = d["vix"] > 35
            backwardation = d["vix"] > d["vix3m"]
            vix_peligro = d["vix"] > d["vix9d"]
            precio_sobre_vwap = d["actual"] > d["vwap"]
            gap_grande_arr = d["gap_pct"] > 0.5
            gap_grande_abj = d["gap_pct"] < -0.5
            iron_condor = (
                d["vix"] < 18 and d["inside_day"] and
                abs(d["streak"]) < 2 and
                1 <= d["votos_tech"] <= 2 and
                d["skew"] < 125
            )

            bias = (
                d["actual"] > d["prev"] and
                d["votos_tech"] >= 2 and
                d["rsp_bull"] and
                not vix_peligro and
                not noticias["bloqueo"] and
                precio_sobre_vwap
            )

            if d["z_score"] > 2.2: bias = False
            elif d["z_score"] < -2.2: bias = True
            if gap_grande_arr and not iron_condor: bias = False
            if gap_grande_abj and not iron_condor: bias = True

            # --- STRIKE Y LOTES ---
            m_seg = 0.85 if d["vix"] < 15 else (1.05 if d["vix"] < 22 else 1.35)
            dist = max(d["atr14"] * 0.90, d["actual"] * ((d["vix"] / 100) / (252**0.5)) * m_seg)
            vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
            if vender % 5 == 0: vender = vender - 1 if bias else vender + 1

            prob_itm = calcular_delta_prob(d["actual"], vender, d["vix"])
            distancia_seguridad = abs(d["actual"] - vender)

            lotes_base = max(1, int((cap / 25000) * 10))

            # ✅ FIX 4: motivo_bloqueo siempre definido antes de usarse
            motivo_bloqueo = ""
            if vix_extremo:
                motivo_bloqueo = "VIX Extremo (>35)"
            elif backwardation:
                motivo_bloqueo = "Backwardation VIX/VIX3M"
            elif d["vix_speed"] > 3.5:
                motivo_bloqueo = "Velocidad VIX elevada"
            elif pnl_dia <= MAX_LOSS_DIA:
                motivo_bloqueo = f"Límite pérdida diaria alcanzado ({pnl_dia}€)"
            elif noticias["bloqueo"]:
                motivo_bloqueo = f"Noticias de alto impacto: {', '.join(noticias['eventos'])}"

            if vix_extremo or backwardation or d["vix_speed"] > 3.5:
                lotes = 0
            else:
                lotes = int(lotes_base * 1.5) if d["vix"] < 18 else (lotes_base if d["vix"] < 25 else lotes_base // 2)

            if pnl_dia <= MAX_LOSS_DIA:
                lotes = 0

            # --- DISPLAY DASHBOARD ---
            st.header(f"Dashboard | {ahora.strftime('%H:%M:%S')}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("XSP Precio", f"{d['actual']:.2f}")
            col2.metric("VWAP", f"{d['vwap']:.2f}", "SOBRE" if precio_sobre_vwap else "BAJO")
            col3.metric("VIX", f"{d['vix']:.2f}")
            col4.metric("Z-Score", f"{d['z_score']:.2f}")

            # Info adicional
            col5, col6, col7, col8 = st.columns(4)
            col5.metric("Gap %", f"{d['gap_pct']:.2f}%")
            col6.metric("Streak", f"{d['streak']} días")
            col7.metric("Distancia Strike", f"{distancia_seguridad:.1f} pts")
            col8.metric("Prob ITM", f"{prob_itm*100:.1f}%")

            if noticias["eventos"]:
                st.warning(f"📅 Noticias hoy: {', '.join(noticias['eventos'])}")

            if lotes > 0:
                estrategia_txt = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias else "BEAR CALL")
                st.success(f"🔥 ESTRATEGIA: {estrategia_txt} | VENDER: {vender} | LOTES: {lotes}")

                if enviar_auto:
                    msg_tel = (
                        f"🚀 XSP v9.0 — {estrategia_txt}\n"
                        f"🔹 VENDER: {vender}\n"
                        f"🔹 PROB ITM: {prob_itm*100:.1f}%\n"
                        f"🔹 DISTANCIA: {distancia_seguridad:.1f} pts\n"
                        f"🔹 LOTES: {lotes}\n"
                        f"🔹 VIX: {d['vix']:.1f} | Z: {d['z_score']:.2f}"
                    )
                    enviar_telegram(msg_tel)
            else:
                # ✅ FIX 4: muestra el motivo real del bloqueo
                motivo_display = motivo_bloqueo if motivo_bloqueo else "Condiciones de riesgo detectadas"
                st.error(f"🚫 NO OPERAR: {motivo_display}")

if __name__ == "__main__":
    main()
