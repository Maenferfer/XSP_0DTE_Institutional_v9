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

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_DISPONIBLE = True
except ImportError:
    AUTOREFRESH_DISPONIBLE = False

warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA    = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'

st.set_page_config(page_title="XSP 0DTE Institutional v10.1", layout="wide")

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
    if   time(15, 30) <= ahora_time <= time(15, 45): return "EVITAR",     "🔴", "Apertura NY caótica"
    elif time(15, 45) <= ahora_time <= time(17, 30): return "ÓPTIMA",     "🟢", "Apertura NY asentada"
    elif time(17, 30) <= ahora_time <= time(19,  0): return "NORMAL",     "🟡", "Tramo intermedio"
    elif time(19,  0) <= ahora_time <= time(20, 30): return "ÓPTIMA",     "🟢", "Tramo final tranquilo"
    elif time(20, 30) <= ahora_time <= time(21,  0): return "EVITAR",     "🔴", "Cierre errático"
    elif ahora_time < time(15, 30):                  return "PREMERCADO", "⚪", "Mercado cerrado"
    else:                                             return "CERRADO",    "⚪", "Mercado cerrado"

# ================================================================
# STRIKES REDONDOS
# ================================================================
def analizar_strikes_redondos(precio, rango_pts=25):
    niveles = []
    base = int(precio // 5) * 5
    for i in range(-rango_pts // 5 - 2, rango_pts // 5 + 3):
        s    = base + i * 5
        dist = round(s - precio, 2)
        if abs(dist) <= rango_pts:
            fuerza = "FUERTE 🔴" if s % 10 == 0 else "MEDIO 🟡"
            niveles.append({"strike": s, "fuerza": fuerza, "distancia": dist})
    return sorted(niveles, key=lambda x: abs(x["distancia"]))

def es_strike_redondo(strike):
    return int(strike) % 5 == 0

def ajustar_strike_redondo(strike, bias):
    if not es_strike_redondo(strike):
        return strike, False
    return (strike - 1 if bias else strike + 1), True

def strike_cerca_redondo_clave(strike, umbral=3):
    multiplo = round(strike / 10) * 10
    return abs(strike - multiplo) <= umbral, multiplo

# ================================================================
# GEX — GAMMA FLIP — CALL WALL — PUT WALL — MAX PAIN — EXPECTED MOVE
# ================================================================
def calcular_niveles_gamma(precio_actual, factor=1):
    resultado = {
        "call_wall": None, "put_wall": None, "gamma_flip": None,
        "max_pain": None,  "gex_neto": 0,    "gex_positivo": True,
        "en_rango_gamma": False, "exp_usada": "N/A",
        "call_wall_redondo": False, "put_wall_redondo": False,
        "expected_move": None,
    }
    try:
        t    = yf.Ticker("SPY")
        exps = t.options
        if not exps: return resultado
        hoy_d   = date.today()
        exp_hoy = min(exps, key=lambda x: abs((datetime.strptime(x, "%Y-%m-%d").date() - hoy_d).days))
        resultado["exp_usada"] = exp_hoy
        chain = t.option_chain(exp_hoy)
        calls = chain.calls[['strike', 'openInterest', 'volume', 'lastPrice']].copy().fillna(0)
        puts  = chain.puts[['strike',  'openInterest', 'volume', 'lastPrice']].copy().fillna(0)
        precio_spy = precio_actual / factor
        calls_otm = calls[calls['strike'] > precio_spy]
        if not calls_otm.empty:
            cw = float(calls_otm.loc[calls_otm['openInterest'].idxmax(), 'strike'])
            resultado["call_wall"]         = round(cw * factor, 2)
            resultado["call_wall_redondo"] = es_strike_redondo(int(cw * factor))
        puts_otm = puts[puts['strike'] < precio_spy]
        if not puts_otm.empty:
            pw = float(puts_otm.loc[puts_otm['openInterest'].idxmax(), 'strike'])
            resultado["put_wall"]         = round(pw * factor, 2)
            resultado["put_wall_redondo"] = es_strike_redondo(int(pw * factor))
        calls_g = calls[['strike', 'openInterest']].copy(); calls_g['gex'] =  calls_g['openInterest']
        puts_g  = puts[['strike',  'openInterest']].copy(); puts_g['gex']  = -puts_g['openInterest']
        gex_by_s = pd.concat([calls_g[['strike','gex']], puts_g[['strike','gex']]]) \
                     .groupby('strike')['gex'].sum().sort_index()
        rango_m = (gex_by_s.index >= precio_spy * 0.95) & (gex_by_s.index <= precio_spy * 1.05)
        resultado["gex_neto"]     = float(gex_by_s[rango_m].sum())
        resultado["gex_positivo"] = resultado["gex_neto"] >= 0
        gex_cum = gex_by_s.cumsum()
        cruces  = np.where(np.diff(np.sign(gex_cum.values)))[0]
        resultado["gamma_flip"] = round(float(gex_by_s.index[cruces[0]]) * factor, 2) \
                                  if len(cruces) > 0 else precio_actual
        strikes_all = np.union1d(calls['strike'].values, puts['strike'].values)
        pains = []
        for s in strikes_all:
            pc = float(((s - calls.loc[calls['strike'] < s, 'strike']) *
                         calls.loc[calls['strike'] < s, 'openInterest']).sum())
            pp = float(((puts.loc[puts['strike'] > s, 'strike'] - s) *
                         puts.loc[puts['strike'] > s, 'openInterest']).sum())
            pains.append(pc + pp)
        if pains:
            resultado["max_pain"] = round(float(strikes_all[int(np.argmin(pains))]) * factor, 2)
        try:
            atm_calls = calls[abs(calls['strike'] - precio_spy) <= 2].nsmallest(1, 'strike')
            atm_puts  = puts[abs(puts['strike']   - precio_spy) <= 2].nlargest(1,  'strike')
            if not atm_calls.empty and not atm_puts.empty:
                resultado["expected_move"] = round(
                    (float(atm_calls['lastPrice'].iloc[0]) +
                     float(atm_puts['lastPrice'].iloc[0])) * factor, 2)
        except: pass
        if resultado["put_wall"] and resultado["call_wall"]:
            resultado["en_rango_gamma"] = resultado["put_wall"] <= precio_actual <= resultado["call_wall"]
    except Exception as e:
        st.warning(f"⚠️ Gamma levels fallback: {e}")
    return resultado

# ================================================================
# STREAK
# ================================================================
def calcular_streak_dias(df_diario):
    closes = df_diario['Close'].tail(10).values
    if len(closes) < 2: return 0
    streak    = 0
    direction = 1 if closes[-1] > closes[-2] else -1
    for i in range(len(closes) - 1, 0, -1):
        if (closes[i] - closes[i-1]) * direction > 0: streak += direction
        else: break
    return streak

# ================================================================
# DATOS MAESTROS
# ================================================================
def obtener_datos_maestros():
    try:
        tickers = {
            "XSP": "^XSP", "SPY": "SPY", "QQQ": "QQQ", "RSP": "RSP",
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

        vol_rel = (df_x['Volume'].iloc[-1] / df_x['Volume'].tail(30).mean()) \
                  if df_x['Volume'].tail(30).mean() > 0 else 1.0
        atr14   = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        streak  = calcular_streak_dias(df_diario)

        cierre_diario = df_diario['Close']
        std_20  = cierre_diario.tail(20).std()
        z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0

        inside_day = (
            len(df_diario) >= 2 and
            df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and
            df_diario['Low'].iloc[-1]  > df_diario['Low'].iloc[-2]
        )

        hv20    = cierre_diario.pct_change().tail(20).std() * np.sqrt(252) * 100
        vix_ref = float(raw_data["VIX"]['Close'].iloc[-1])
        hv_iv   = hv20 / vix_ref if vix_ref > 0 else 1.0

        vwap_actual = actual; or_high = actual + 1; or_low = actual - 1
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
        except: pass

        ivr = 50.0
        try:
            vix_hist = yf.Ticker("^VIX").history(period="252d", interval="1d")['Close']
            if len(vix_hist) > 20:
                ivr = (vix_ref - vix_hist.min()) / (vix_hist.max() - vix_hist.min()) * 100
        except: pass

        pct_b = 0.5
        try:
            ma20 = cierre_diario.tail(20).mean(); std20 = cierre_diario.tail(20).std()
            bb_u = ma20 + 2*std20; bb_l = ma20 - 2*std20
            if (bb_u - bb_l) > 0: pct_b = (cierre_diario.iloc[-1] - bb_l) / (bb_u - bb_l)
        except: pass

        vvix = 90.0
        try:
            if not raw_data["VVIX"].empty: vvix = float(raw_data["VVIX"]['Close'].iloc[-1])
        except: pass

        vix1d = vix_ref
        try:
            if not raw_data["VIX1D"].empty: vix1d = float(raw_data["VIX1D"]['Close'].iloc[-1])
        except: pass
        vix1d_ratio = vix1d / vix_ref if vix_ref > 0 else 1.0

        tnx_val      = float(raw_data["TNX"]['Close'].iloc[-1]) if not raw_data["TNX"].empty else 4.0
        tnx_prev_val = float(raw_data["TNX"]['Close'].iloc[-2]) if len(raw_data["TNX"]) > 1 else tnx_val
        tnx_cambio   = ((tnx_val - tnx_prev_val) / tnx_prev_val) * 100 if tnx_prev_val > 0 else 0
        vix3m        = float(raw_data["VIX3M"]['Close'].iloc[-1]) if not raw_data["VIX3M"].empty else 20.0
        ts_slope     = vix_ref / vix3m if vix3m > 0 else 1.0

        qqq_ret = 0.0; spy_ret_val = 0.0
        qqq_lidera = False; divergencia_qqq = False; qqq_alcista = False
        try:
            qqq_d = raw_data["QQQ"]; spy_d = raw_data["SPY"]
            if not qqq_d.empty and not spy_d.empty:
                qqq_ret     = (float(qqq_d['Close'].iloc[-1]) - float(qqq_d['Open'].iloc[-1])) / float(qqq_d['Open'].iloc[-1]) * 100
                spy_ret_val = (float(spy_d['Close'].iloc[-1]) - float(spy_d['Open'].iloc[-1])) / float(spy_d['Open'].iloc[-1]) * 100
                qqq_alcista     = float(qqq_d['Close'].iloc[-1]) > float(qqq_d['Open'].iloc[-1])
                divergencia_qqq = ((qqq_ret > 0 and spy_ret_val < 0) or
                                   (qqq_ret < 0 and spy_ret_val > 0) or
                                   abs(qqq_ret - spy_ret_val) > 0.4)
                qqq_lidera = qqq_ret > spy_ret_val + 0.3
        except: pass

        spy_up = (not raw_data["SPY"].empty and
                  float(raw_data["SPY"]['Close'].iloc[-1]) > float(raw_data["SPY"]['Open'].iloc[-1]))
        rsp_up = (not raw_data["RSP"].empty and
                  float(raw_data["RSP"]['Close'].iloc[-1]) > float(raw_data["RSP"]['Open'].iloc[-1]))

        votos = 0
        for tk in ["AAPL", "MSFT", "NVDA"]:
            d_tk = yf.Ticker(tk).history(period="1d", interval="1m")
            if not d_tk.empty and d_tk['Close'].iloc[-1] > d_tk['Open'].iloc[-1]: votos += 1

        return {
            "actual": actual, "apertura": apertura, "prev": prev_close,
            "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14), "rsi_5m": calc_rsi(df_x['Close'], 5),
            "cambio_15m": (actual - float(df_x['Close'].iloc[-15]) * factor) if len(df_x) > 15 else 0,
            "std_dev": df_x['Close'].std() * factor, "vol_rel": vol_rel,
            "vix": vix_ref, "vix1d": vix1d, "vix1d_ratio": vix1d_ratio,
            "vix9d": float(raw_data["VIX9D"]['Close'].iloc[-1]) if not raw_data["VIX9D"].empty else vix_ref,
            "vix3m": vix3m, "ts_slope": ts_slope, "vvix": vvix,
            "skew": float(raw_data["SKEW"]['Close'].iloc[-1]) if not raw_data["SKEW"].empty else 120.0,
            "tnx": tnx_val, "tnx_prev": tnx_prev_val, "tnx_cambio": tnx_cambio,
            "pc_ratio": float(raw_data["PCCE"]['Close'].iloc[-1]) if not raw_data["PCCE"].empty else 0.8,
            "rsp_bull": rsp_up, "amplitud_ok": spy_up and rsp_up,
            "atr14": atr14, "streak": streak, "z_score": z_score, "inside_day": inside_day,
            "gap_pct": (apertura - prev_close) / prev_close * 100,
            "vwap": vwap_actual, "or_high": or_high, "or_low": or_low,
            "ivr": ivr, "pct_b": pct_b, "hv20": hv20, "hv_iv": hv_iv,
            "qqq_ret": qqq_ret, "spy_ret": spy_ret_val,
            "qqq_alcista": qqq_alcista, "qqq_lidera": qqq_lidera, "divergencia_qqq": divergencia_qqq,
            "vix_speed": (vix_ref / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "caida_flash": (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100 if len(df_x) > 5 else 0,
            "votos_tech": votos,
        }
    except Exception as e:
        st.error(f"[ERROR datos]: {e}")
        return None

# ================================================================
# DELTA / PROB ITM
# ================================================================
def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    T = dias_exp / 252; sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    return round(norm.cdf(-d1), 4)

# ================================================================
# JOURNAL
# ================================================================
def inicializar_journal():
    if "journal"         not in st.session_state: st.session_state.journal         = []
    if "analisis_activo" not in st.session_state: st.session_state.analisis_activo = False

def guardar_en_journal(entrada):
    st.session_state.journal.append(entrada)

def mostrar_journal():
    if not st.session_state.journal:
        st.info("Sin operaciones registradas en esta sesión.")
        return
    df_j = pd.DataFrame(st.session_state.journal)
    st.dataframe(df_j, hide_index=True, use_container_width=True)
    con_resultado = df_j[df_j['resultado'].notna() & (df_j['resultado'] != "")].copy()
    if not con_resultado.empty:
        try:
            con_resultado['pnl_num'] = pd.to_numeric(con_resultado['resultado'], errors='coerce')
            pnl_total  = con_resultado['pnl_num'].sum()
            ganadoras  = (con_resultado['pnl_num'] > 0).sum()
            perdedoras = (con_resultado['pnl_num'] < 0).sum()
            win_rate   = ganadoras / len(con_resultado) * 100 if len(con_resultado) > 0 else 0
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("P&L Total sesión", f"{pnl_total:.0f}€")
            c2.metric("Win Rate",         f"{win_rate:.0f}%")
            c3.metric("Ganadoras",        ganadoras)
            c4.metric("Perdedoras",       perdedoras)
        except: pass

def formulario_resultado_journal():
    if st.session_state.journal:
        with st.form("resultado_form"):
            st.caption("📝 Registrar resultado de la última señal")
            resultado = st.text_input("P&L (€) de la operación (ej: 150 o -80)")
            notas     = st.text_input("Notas opcionales")
            if st.form_submit_button("Guardar resultado") and resultado:
                st.session_state.journal[-1]["resultado"] = resultado
                st.session_state.journal[-1]["notas"]     = notas
                st.success("✅ Resultado guardado")

# ================================================================
# EJECUTAR ANÁLISIS
# ================================================================
def ejecutar_analisis(cap, pnl_dia, enviar_auto):
    MAX_LOSS_DIA = -300.0

    with st.spinner("Obteniendo datos maestros..."):
        noticias = check_noticias_pro(FINNHUB_API_KEY)
        d        = obtener_datos_maestros()
        if not d:
            st.error("No se pudieron obtener los datos.")
            return

    with st.spinner("Calculando niveles gamma..."):
        g = calcular_niveles_gamma(d["actual"], factor=1)

    ahora      = datetime.now(ZONA_HORARIA)
    ahora_time = ahora.time()
    ventana, ventana_icon, ventana_desc = evaluar_ventana_horaria(ahora_time)
    niveles_redondos = analizar_strikes_redondos(d["actual"], rango_pts=25)

    # ================================================================
    # FILTROS — UMBRALES CALIBRADOS ESTADÍSTICAMENTE (desde abr-2023)
    # ================================================================
    vix_extremo         = d["vix"] > 35
    backwardation       = d["vix"] > d["vix3m"]
    vix_peligro_leve    = d["vix"] > d["vix9d"]
    vix_peligro_bloqueo = d["vix"] > d["vix9d"] and d["vix"] > 25
    vvix_extremo        = d["vvix"] > 115
    vix1d_spike         = d["vix1d_ratio"] > 1.35
    ts_tension          = d["ts_slope"] > 0.93
    ts_critico          = d["ts_slope"] > 0.97
    tnx_presion_bajista = d["tnx_cambio"] > 0.8
    precio_sobre_vwap   = d["actual"] > d["vwap"]
    gap_grande_arr      = d["gap_pct"] > 0.5
    gap_grande_abj      = d["gap_pct"] < -0.5
    prima_barata        = d["ivr"] < 25
    sobreextendido_arr  = d["pct_b"] > 0.95
    sobreextendido_abj  = d["pct_b"] < 0.05
    precio_en_or        = d["or_low"] <= d["actual"] <= d["or_high"]
    ventana_evitar      = ventana == "EVITAR"
    rally_falso         = not d["amplitud_ok"] and d["actual"] > d["prev"]
    gex_negativo        = not g["gex_positivo"]
    precio_bajo_flip    = g["gamma_flip"] and d["actual"] < g["gamma_flip"]
    hv_iv_peligroso     = d["hv_iv"] > 1.0
    hv_iv_ideal         = d["hv_iv"] < 0.7
    max_pain_dist       = (d["actual"] - g["max_pain"]) if g["max_pain"] else 0
    sesgo_max_pain      = "bajista" if max_pain_dist > 5 else ("alcista" if max_pain_dist < -5 else "neutro")
    call_wall_confirmado = g["call_wall"] and g["call_wall_redondo"]
    put_wall_confirmado  = g["put_wall"]  and g["put_wall_redondo"]

    # ── BIAS REAL (con bloqueos incluidos) ────────────────────────
    bias = (
        d["actual"] > d["prev"] and d["votos_tech"] >= 2 and d["rsp_bull"] and
        d["amplitud_ok"] and d["qqq_alcista"] and not vix_peligro_bloqueo and
        not noticias["bloqueo"] and precio_sobre_vwap
    )
    if d["z_score"] > 2.0  or sobreextendido_arr:  bias = False
    if d["z_score"] < -2.0 or sobreextendido_abj:  bias = True
    if gap_grande_arr:                               bias = False
    if gap_grande_abj:                               bias = True
    if tnx_presion_bajista and bias:                 bias = False
    if rally_falso and bias:                         bias = False
    if vix1d_spike:                                  bias = False
    if precio_bajo_flip:                             bias = False
    if d["divergencia_qqq"] and bias:                bias = False
    if d["qqq_lidera"] and not bias:                 bias = True
    if sesgo_max_pain == "bajista" and bias:         bias = False
    if sesgo_max_pain == "alcista" and not bias:     bias = True
    if hv_iv_peligroso:                              bias = False

    # ── BIAS TEÓRICO (sin contaminar por bloqueos — solo para señal teórica) ──
    bias_teorico = (
        d["actual"] > d["prev"] and d["votos_tech"] >= 2 and d["rsp_bull"] and
        d["amplitud_ok"] and d["qqq_alcista"] and precio_sobre_vwap
    )
    if d["z_score"] > 2.0  or sobreextendido_arr:  bias_teorico = False
    if d["z_score"] < -2.0 or sobreextendido_abj:  bias_teorico = True
    if gap_grande_arr:                               bias_teorico = False
    if gap_grande_abj:                               bias_teorico = True
    if d["qqq_lidera"] and not bias_teorico:         bias_teorico = True
    if d["divergencia_qqq"] and bias_teorico:        bias_teorico = False

    # ── IRON CONDOR ───────────────────────────────────────────────
    iron_condor = (
        (d["vix"] < 20 and d["inside_day"] and abs(d["streak"]) < 2 and
         1 <= d["votos_tech"] <= 2 and d["skew"] < 135)
        or precio_en_or or g["en_rango_gamma"] or d["divergencia_qqq"]
    )

    # ── STRIKE — multiplicador VIX>22 corregido a 1.60 ───────────
    vix_para_dist = d["vix1d"] if vix1d_spike else d["vix"]
    dist_base = max(
        d["atr14"] * 0.90,
        d["actual"] * ((vix_para_dist / 100) / (252**0.5)) *
        (0.85 if d["vix"] < 15 else (1.05 if d["vix"] < 22 else 1.60))
    )
    if g["expected_move"]:
        dist_base = max(dist_base, g["expected_move"] * 0.9)

    vender = round(d["actual"] - dist_base) if bias else round(d["actual"] + dist_base)
    vender, fue_ajustado = ajustar_strike_redondo(vender, bias)
    cerca_redondo, redondo_cercano = strike_cerca_redondo_clave(vender, umbral=3)

    if g["call_wall"] and bias and vender >= g["call_wall"]:
        vender, _ = ajustar_strike_redondo(int(g["call_wall"]) - 1, bias)
    if g["put_wall"] and not bias and vender <= g["put_wall"]:
        vender, _ = ajustar_strike_redondo(int(g["put_wall"]) + 1, bias)
    if g["max_pain"]:
        if bias     and g["max_pain"] < d["actual"] and vender > g["max_pain"]: vender = int(g["max_pain"]) - 2
        elif not bias and g["max_pain"] > d["actual"] and vender < g["max_pain"]: vender = int(g["max_pain"]) + 2

    prob_itm            = calcular_delta_prob(d["actual"], vender, vix_para_dist)
    distancia_seguridad = abs(d["actual"] - vender)

    # ── LOTES ─────────────────────────────────────────────────────
    lotes_base     = max(1, int((cap / 25000) * 10))
    motivo_bloqueo = ""

    if vix_extremo:
        motivo_bloqueo = "VIX Extremo (>35)";                                lotes = 0
    elif vvix_extremo:
        motivo_bloqueo = "VVIX Extremo (>115)";                              lotes = 0
    elif backwardation:
        motivo_bloqueo = "Backwardation VIX/VIX3M";                          lotes = 0
    elif ts_critico:
        motivo_bloqueo = f"Term Structure crítica ({d['ts_slope']:.3f})";    lotes = 0
    elif d["vix_speed"] > 3.5:
        motivo_bloqueo = f"Velocidad VIX ({d['vix_speed']:.1f}%)";           lotes = 0
    elif ventana_evitar:
        motivo_bloqueo = f"Ventana peligrosa — {ventana_desc}";              lotes = 0
    elif noticias["bloqueo"]:
        motivo_bloqueo = f"Noticias: {', '.join(noticias['eventos'])}";      lotes = 0
    elif pnl_dia <= MAX_LOSS_DIA:
        motivo_bloqueo = f"Límite pérdida diaria ({pnl_dia}€)";              lotes = 0
    else:
        lotes = int(lotes_base * 1.5) if d["vix"] < 18 else (lotes_base if d["vix"] < 25 else lotes_base // 2)
        if prima_barata:                              lotes = max(1, lotes - 1)
        if vix1d_spike:                               lotes = max(1, lotes - 1)
        if gex_negativo:                              lotes = max(1, lotes - 1)
        if hv_iv_peligroso:                           lotes = max(1, lotes - 1)
        if vix_peligro_leve:                          lotes = max(1, lotes - 1)
        if ts_tension:                                lotes = max(1, lotes - 1)
        if d["divergencia_qqq"] and not iron_condor:  lotes = max(1, lotes - 1)
        if tnx_presion_bajista:                       lotes = max(1, lotes - 1)

    # ── Textos de decisión ────────────────────────────────────────
    if lotes > 0:
        estrategia_txt = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias else "BEAR CALL")
        motivo_display = ""
        señal_teorica  = ""
    else:
        estrategia_txt = None
        motivo_display = motivo_bloqueo if motivo_bloqueo else "Condiciones de riesgo detectadas"
        señal_teorica  = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias_teorico else "BEAR CALL")

    # ══════════════════════════════════════════════════════════════
    # DISPLAY
    # ══════════════════════════════════════════════════════════════
    st.header(f"Dashboard | {ahora.strftime('%H:%M:%S')}")

    # 1️⃣ Ventana horaria
    if   ventana == "ÓPTIMA": st.success(f"{ventana_icon} **{ventana}** — {ventana_desc}")
    elif ventana == "EVITAR": st.error(  f"{ventana_icon} **{ventana}** — {ventana_desc}")
    else:                     st.info(   f"{ventana_icon} **{ventana}** — {ventana_desc}")

    # 2️⃣ RESULTADO — visible sin scroll
    st.divider()
    if lotes > 0:
        st.success(
            f"🔥 **{estrategia_txt}** | "
            f"VENDER: **{vender}** | "
            f"LOTES: **{lotes}** | "
            f"PROB ITM: {prob_itm*100:.1f}% | "
            f"DIST: {distancia_seguridad:.1f} pts | "
            f"VIX usado: {vix_para_dist:.1f}"
        )
    else:
        st.error(f"🚫 **NO OPERAR** — {motivo_display}")
        vender_teorico     = round(d["actual"] - dist_base) if bias_teorico else round(d["actual"] + dist_base)
        vender_teorico, _  = ajustar_strike_redondo(vender_teorico, bias_teorico)
        prob_teorica       = calcular_delta_prob(d["actual"], vender_teorico, vix_para_dist)
        dist_teorica       = abs(d["actual"] - vender_teorico)
        lotes_teoricos     = max(1, int(lotes_base * 1.5) if d["vix"] < 18 else (lotes_base if d["vix"] < 25 else lotes_base // 2))
        if señal_teorica == "IRON CONDOR":
            vender_put_teo  = round(d["actual"] - dist_base)
            vender_call_teo = round(d["actual"] + dist_base)
            vender_put_teo,  _ = ajustar_strike_redondo(vender_put_teo,  True)
            vender_call_teo, _ = ajustar_strike_redondo(vender_call_teo, False)
            prob_put_teo  = calcular_delta_prob(d["actual"], vender_put_teo,  vix_para_dist)
            prob_call_teo = calcular_delta_prob(d["actual"], vender_call_teo, vix_para_dist)
            st.caption(
                f"* Si se operara ahora: **{señal_teorica}** | "
                f"PUT: **{vender_put_teo}** (ITM {prob_put_teo*100:.1f}%) | "
                f"CALL: **{vender_call_teo}** (ITM {prob_call_teo*100:.1f}%) | "
                f"Dist: ±{dist_teorica:.1f} pts | "
                f"Lotes: **{lotes_teoricos}** — ⚠️ el riesgo no justifica la operación"
            )
        else:
            st.caption(
                f"* Si se operara ahora: **{señal_teorica}** | "
                f"Strike: **{vender_teorico}** | "
                f"Prob ITM: {prob_teorica*100:.1f}% | "
                f"Dist: {dist_teorica:.1f} pts | "
                f"Lotes: **{lotes_teoricos}** — ⚠️ el riesgo no justifica la operación"
            )
    st.divider()

    # 3️⃣ Métricas
    st.subheader("📈 Precio y Volatilidad")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("XSP Precio",  f"{d['actual']:.2f}")
    c2.metric("VWAP",        f"{d['vwap']:.2f}",      "SOBRE" if precio_sobre_vwap else "BAJO")
    c3.metric("VIX",         f"{d['vix']:.2f}")
    c4.metric("VIX1D",       f"{d['vix1d']:.2f}",     f"x{d['vix1d_ratio']:.2f} 🔴" if vix1d_spike else f"x{d['vix1d_ratio']:.2f} ✅")
    c5.metric("Z-Score",     f"{d['z_score']:.2f}",   "Extremo ⚠️" if abs(d['z_score']) > 2.0 else "Normal ✅")

    st.subheader("🌡️ Estructura de Volatilidad")
    c6,c7,c8,c9,c10 = st.columns(5)
    c6.metric("IV Rank",      f"{d['ivr']:.1f}%",     "Rica ✅" if d['ivr'] >= 50 else "Barata ⚠️")
    c7.metric("HV20/IV",      f"{d['hv_iv']:.2f}",    "Peligroso 🔴" if hv_iv_peligroso else ("Ideal ✅" if hv_iv_ideal else "Normal 🟡"))
    c8.metric("VVIX",         f"{d['vvix']:.1f}",     "Extremo 🔴" if vvix_extremo else ("Alerta ⚠️" if d['vvix'] > 100 else "Normal ✅"))
    c9.metric("TS Slope",     f"{d['ts_slope']:.3f}", "Crítico 🔴" if ts_critico else ("Tensión ⚠️" if ts_tension else ("Alerta 🟡" if d['ts_slope'] > 0.85 else "Contango ✅")))
    c10.metric("Bollinger %B",f"{d['pct_b']:.2f}",    "Sobreext ⚠️" if (sobreextendido_arr or sobreextendido_abj) else "Normal ✅")

    st.subheader("📡 Flujo de Mercado")
    c11,c12,c13,c14,c15 = st.columns(5)
    c11.metric("QQQ Ret",    f"{d['qqq_ret']:+.2f}%", "Alcista ✅" if d['qqq_alcista'] else "Bajista 🔴")
    c12.metric("SPY Ret",    f"{d['spy_ret']:+.2f}%")
    c13.metric("QQQ vs SPY", f"{d['qqq_ret']-d['spy_ret']:+.2f}%",
               "Lidera ✅" if d['qqq_lidera'] else ("Diverge ⚠️" if d['divergencia_qqq'] else "Alineado ✅"))
    c14.metric("Amplitud",   "Confirmada ✅" if d['amplitud_ok'] else "Falso ⚠️")
    c15.metric("TNX Cambio", f"{d['tnx_cambio']:+.2f}%", "Presión 🔴" if tnx_presion_bajista else "Normal ✅")

    st.subheader("⚡ Niveles Gamma")
    c16,c17,c18,c19,c20 = st.columns(5)
    cw_txt = f"{g['call_wall']:.1f} {'🔴' if call_wall_confirmado else ''}" if g['call_wall'] else "N/A"
    pw_txt = f"{g['put_wall']:.1f}  {'🔴' if put_wall_confirmado  else ''}" if g['put_wall']  else "N/A"
    c16.metric("Call Wall",    cw_txt)
    c17.metric("Put Wall",     pw_txt)
    c18.metric("Gamma Flip",   f"{g['gamma_flip']:.1f}" if g['gamma_flip'] else "N/A",
               "Bajo flip ⚠️" if precio_bajo_flip else "Sobre flip ✅")
    c19.metric("Max Pain",     f"{g['max_pain']:.1f}"   if g['max_pain']   else "N/A",
               f"Sesgo {sesgo_max_pain}")
    c20.metric("Expected Move",f"±{g['expected_move']:.1f} pts" if g['expected_move'] else "N/A")

    st.subheader("🎯 Operativa")
    c21,c22,c23,c24,c25 = st.columns(5)
    c21.metric("GEX Neto",  f"{g['gex_neto']:,.0f}", "Anclaje ✅" if g['gex_positivo'] else "Volátil 🔴")
    c22.metric("Gap %",     f"{d['gap_pct']:.2f}%")
    c23.metric("Streak",    f"{d['streak']} días")
    c24.metric("Distancia", f"{distancia_seguridad:.1f} pts")
    c25.metric("Prob ITM",  f"{prob_itm*100:.1f}%")

    st.info(
        f"📊 OR: {d['or_low']:.2f} — {d['or_high']:.2f} | "
        f"Precio {'DENTRO ⚠️ (indecisión)' if precio_en_or else 'FUERA ✅ (hay dirección)'} | "
        f"VIX9D: {'⚠️ lotes reducidos' if vix_peligro_leve else '✅ normal'}"
    )

    with st.expander("📐 Strikes redondos clave"):
        df_niv = pd.DataFrame(niveles_redondos[:12])
        df_niv['Call Wall'] = df_niv['strike'].apply(lambda s: "✅" if g['call_wall'] and abs(s - g['call_wall']) < 2 else "")
        df_niv['Put Wall']  = df_niv['strike'].apply(lambda s: "✅" if g['put_wall']  and abs(s - g['put_wall'])  < 2 else "")
        df_niv['Max Pain']  = df_niv['strike'].apply(lambda s: "✅" if g['max_pain']  and abs(s - g['max_pain'])  < 2 else "")
        df_niv['Exp Move']  = df_niv['strike'].apply(
            lambda s: "✅" if g['expected_move'] and abs(abs(d['actual'] - s) - g['expected_move']) < 2 else "")
        st.dataframe(df_niv, hide_index=True)

    # Alertas
    if noticias["eventos"]:       st.warning(f"📅 Noticias: {', '.join(noticias['eventos'])}")
    if fue_ajustado:              st.info("📐 Strike ajustado — evitando strike redondo contestado")
    if cerca_redondo:             st.info(f"🧲 Strike {vender} cerca del nivel {redondo_cercano} — posible imán")
    if put_wall_confirmado:       st.success(f"🔴 Put Wall {g['put_wall']:.1f} = redondo — soporte DOBLEMENTE confirmado")
    if call_wall_confirmado:      st.success(f"🔴 Call Wall {g['call_wall']:.1f} = redondo — resistencia DOBLEMENTE confirmada")
    if g["en_rango_gamma"]:       st.success(f"✅ Precio en rango gamma [{g['put_wall']:.1f} — {g['call_wall']:.1f}] — Iron Condor ideal")
    if d["divergencia_qqq"]:      st.warning(f"⚠️ QQQ ({d['qqq_ret']:+.2f}%) diverge de SPY ({d['spy_ret']:+.2f}%)")
    if d["qqq_lidera"] and not d["divergencia_qqq"]: st.success("✅ QQQ lidera — apetito de riesgo confirmado")
    if hv_iv_peligroso:           st.warning(f"⚠️ HV20/IV = {d['hv_iv']:.2f} — mercado subestima la vol, lotes reducidos")
    if hv_iv_ideal and not prima_barata: st.success(f"✅ HV20/IV = {d['hv_iv']:.2f} — prima cara, condiciones ideales")
    if prima_barata:              st.warning(f"⚠️ IVR bajo ({d['ivr']:.1f}%) — prima barata, lotes reducidos")
    if vix1d_spike:               st.warning(f"⚠️ VIX1D spike (x{d['vix1d_ratio']:.2f} > 1.35) — lotes reducidos")
    if d['vvix'] > 100 and not vvix_extremo: st.warning(f"⚠️ VVIX elevado ({d['vvix']:.1f}) — atención")
    if vvix_extremo:              st.error(f"🔴 VVIX Extremo ({d['vvix']:.1f} > 115) — bloqueo total")
    if gex_negativo:              st.warning("⚠️ GEX negativo — MM cubriendo, lotes reducidos")
    if precio_bajo_flip:          st.warning(f"⚠️ Precio bajo Gamma Flip ({g['gamma_flip']:.1f}) — zona bajista")
    if rally_falso:               st.warning("⚠️ Rally falso — SPY sube pero RSP no confirma")
    if tnx_presion_bajista:       st.warning(f"⚠️ TNX +{d['tnx_cambio']:.2f}% — presión bajista bonos, lotes reducidos")
    if vix_peligro_leve:          st.warning(f"⚠️ VIX ({d['vix']:.1f}) > VIX9D ({d['vix9d']:.1f}) — lotes reducidos")
    if ts_tension:                st.warning(f"⚠️ TS Slope {d['ts_slope']:.3f} > 0.93 — tensión en curva, lotes reducidos")
    if g["expected_move"]:        st.info(
        f"📏 Expected Move hoy: ±{g['expected_move']:.1f} pts "
        f"[{d['actual']-g['expected_move']:.1f} — {d['actual']+g['expected_move']:.1f}]"
    )

    # Telegram y journal solo si hay operación
    if lotes > 0:
        guardar_en_journal({
            "hora": ahora.strftime('%H:%M'), "estrategia": estrategia_txt,
            "strike": vender, "prob_itm": f"{prob_itm*100:.1f}%",
            "distancia": f"{distancia_seguridad:.1f}", "lotes": lotes,
            "vix": f"{d['vix']:.1f}", "ivr": f"{d['ivr']:.1f}%",
            "hv_iv": f"{d['hv_iv']:.2f}", "gex": "+" if g['gex_positivo'] else "-",
            "qqq_spy": f"{d['qqq_ret']-d['spy_ret']:+.2f}%",
            "em": f"±{g['expected_move']:.1f}" if g['expected_move'] else "N/A",
            "resultado": "", "notas": "",
        })
        if enviar_auto:
            mp_l = f"🔹 Max Pain: {g['max_pain']:.1f} (sesgo {sesgo_max_pain})\n" if g['max_pain'] else ""
            gf_l = f"🔹 Gamma Flip: {g['gamma_flip']:.1f} {'⚠️' if precio_bajo_flip else '✅'}\n" if g['gamma_flip'] else ""
            em_l = f"🔹 Exp Move: ±{g['expected_move']:.1f} pts\n" if g['expected_move'] else ""
            msg_tel = (
                f"🚀 XSP v10.1 — {estrategia_txt}\n"
                f"🔹 VENDER: {vender}{' (ajustado redondo)' if fue_ajustado else ''}\n"
                f"🔹 PROB ITM: {prob_itm*100:.1f}% | DIST: {distancia_seguridad:.1f} pts\n"
                f"🔹 LOTES: {lotes}\n─────────────────\n"
                f"🔹 CW: {g['call_wall'] if g['call_wall'] else 'N/A'} {'🔴' if call_wall_confirmado else ''} | "
                f"PW: {g['put_wall'] if g['put_wall'] else 'N/A'} {'🔴' if put_wall_confirmado else ''}\n"
                f"{gf_l}{mp_l}{em_l}"
                f"🔹 GEX: {'Anclaje ✅' if g['gex_positivo'] else 'Volátil 🔴'}\n─────────────────\n"
                f"🔹 VIX: {d['vix']:.1f} | VIX1D: {d['vix1d']:.1f} (x{d['vix1d_ratio']:.2f})\n"
                f"🔹 VVIX: {d['vvix']:.1f} | TS: {d['ts_slope']:.3f}\n"
                f"🔹 IVR: {d['ivr']:.1f}% | HV/IV: {d['hv_iv']:.2f}\n"
                f"🔹 %B: {d['pct_b']:.2f} | Z: {d['z_score']:.2f}\n"
                f"🔹 QQQ: {d['qqq_ret']:+.2f}% | SPY: {d['spy_ret']:+.2f}% "
                f"{'⚠️ diverge' if d['divergencia_qqq'] else '✅'}\n"
                f"🔹 TNX: {d['tnx_cambio']:+.2f}% | VIX9D: {'⚠️' if vix_peligro_leve else '✅'}\n"
                f"🔹 Amplitud: {'✅' if d['amplitud_ok'] else '⚠️'} | Ventana: {ventana_icon} {ventana}"
            )
            enviar_telegram(msg_tel)

# ================================================================
# MAIN
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v10.1")
    inicializar_journal()

    cap         = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia     = st.sidebar.number_input("P&L del día (€)",    value=250.0)
    enviar_auto = st.sidebar.checkbox("Enviar Telegram automáticamente", value=False)

    if AUTOREFRESH_DISPONIBLE:
        refresh_min = st.sidebar.selectbox("Auto-refresh cada", [0, 2, 5, 10], index=2)
        if refresh_min > 0:
            st_autorefresh(interval=refresh_min * 60 * 1000, key="autorefresh")
            st.sidebar.info(f"🔄 Refresh cada {refresh_min} min")
    else:
        st.sidebar.warning("💡 pip install streamlit-autorefresh")

    if st.session_state.analisis_activo:
        st.sidebar.success("🟢 Auto-análisis ACTIVO")
    else:
        st.sidebar.info("⚪ Auto-análisis INACTIVO")

    tab_dashboard, tab_journal = st.tabs(["📊 Dashboard", "📓 Journal"])

    with tab_dashboard:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("▶️ EJECUTAR ANÁLISIS", use_container_width=True):
                st.session_state.analisis_activo = True
        with col_btn2:
            if st.button("⏹️ DETENER AUTO-ANÁLISIS", use_container_width=True):
                st.session_state.analisis_activo = False
                st.info("Auto-análisis detenido.")
        if st.session_state.analisis_activo:
            ejecutar_analisis(cap, pnl_dia, enviar_auto)

    with tab_journal:
        st.subheader("📓 Journal de Operaciones")
        formulario_resultado_journal()
        st.divider()
        mostrar_journal()
        if st.button("🗑️ Limpiar journal"):
            st.session_state.journal = []
            st.success("Journal limpiado")

if __name__ == "__main__":
    main()
