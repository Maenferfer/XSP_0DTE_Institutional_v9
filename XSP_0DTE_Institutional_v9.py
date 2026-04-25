
import pytz
import warnings
import logging
import os
import hashlib

try:
    from streamlit_autorefresh import st_autorefresh

warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA    = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
APP_VERSION = "10.2"
MAX_LOSS_DIA = -300.0

st.set_page_config(page_title=f"XSP 0DTE Institutional v{APP_VERSION}", layout="wide")


st.set_page_config(page_title="XSP 0DTE Institutional v10.1", layout="wide")
def leer_config(nombre, default=""):
    try:
        valor = st.secrets.get(nombre, "")
    except Exception:
        valor = ""
    return os.getenv(nombre, valor or default)

# ================================================================
# TELEGRAM
# ================================================================
def enviar_telegram(msg_tel):
    token   = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
    chat_id = "7121107501"
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    token = leer_config("TELEGRAM_BOT_TOKEN")
    chat_id = leer_config("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        st.sidebar.warning("Telegram no configurado: define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": msg_tel}, timeout=10)
        if r.status_code == 200:
            st.sidebar.success("✅ Alerta enviada a Telegram")
            return True
        else:
            st.sidebar.error(f"❌ Error API Telegram: {r.text}")
            return False
    except Exception as e:
        st.sidebar.error(f"❌ Error de conexión Telegram: {e}")
        return False

# ================================================================
# NOTICIAS
                          "JOBLESS", "TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"]
    hoy   = str(date.today())
    url   = f"https://finnhub.io/api/v1/calendar/economic?from={hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "eventos": []}
    estado = {"bloqueo": False, "eventos": [], "error": ""}
    if not api_key:
        estado["error"] = "Finnhub no configurado: define FINNHUB_API_KEY."
        return estado

    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
        respuesta = requests.get(url, timeout=5)
        respuesta.raise_for_status()
        eventos = respuesta.json().get('economicCalendar', [])
        for ev in eventos:
            if ev.get('country') == 'US' and str(ev.get('impact', '')).lower() in ['high', '3', '4']:
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if time(14, 0) <= h_es <= time(21, 0):
                        estado["bloqueo"] = True
    except:
        pass
    except Exception as e:
        estado["error"] = f"No se pudo consultar Finnhub: {e}"
    return estado

# ================================================================
        "max_pain": None,  "gex_neto": 0,    "gex_positivo": True,
        "en_rango_gamma": False, "exp_usada": "N/A",
        "call_wall_redondo": False, "put_wall_redondo": False,
        "expected_move": None,
        "expected_move": None, "error": "",
    }
    try:
        t    = yf.Ticker("SPY")
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
            atm_call = calls.loc[(calls['strike'] - precio_spy).abs().idxmin()]
            atm_put  = puts.loc[(puts['strike'] - precio_spy).abs().idxmin()]
            resultado["expected_move"] = round(
                (float(atm_call['lastPrice']) + float(atm_put['lastPrice'])) * factor, 2)
        except Exception as e:
            resultado["error"] = f"Expected move no disponible: {e}"
        if resultado["put_wall"] and resultado["call_wall"]:
            resultado["en_rango_gamma"] = resultado["put_wall"] <= precio_actual <= resultado["call_wall"]
    except Exception as e:
        resultado["error"] = str(e)
        st.warning(f"⚠️ Gamma levels fallback: {e}")
    return resultado

        }
        raw_data = {}
        for k, v in tickers.items():
            t  = yf.Ticker(v)
            df = t.history(period="7d", interval="1m")
            if df.empty: df = t.history(period="7d", interval="1d")
            try:
                t  = yf.Ticker(v)
                df = t.history(period="7d", interval="1m")
                if df.empty:
                    df = t.history(period="7d", interval="1d")
            except Exception:
                df = pd.DataFrame()
            raw_data[k] = df

        df_x   = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        factor = 10 if raw_data["XSP"].empty else 1
        df_x = raw_data["XSP"] if not raw_data["XSP"].empty else raw_data["SPY"]
        fuente_precio = "XSP" if not raw_data["XSP"].empty else "SPY fallback"
        factor = 1
        if df_x.empty:
            raise ValueError("Sin datos de precio para XSP ni SPY.")
        actual = float(df_x['Close'].iloc[-1]) * factor

        df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
        if df_diario.empty:
            df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
            for col in ['Open', 'High', 'Low', 'Close']:
                df_diario[col] = df_diario[col] * factor
        if df_diario.empty or len(df_diario) < 2:
            raise ValueError("Sin histórico diario suficiente para XSP/SPY.")

        apertura   = float(df_diario['Open'].iloc[-1])
        prev_close = float(df_diario['Close'].iloc[-2])

        def calc_rsi(series, p):
            if len(series) < p + 1:
                return 50.0
            delta = series.diff()
            g = delta.where(delta > 0, 0).rolling(window=p).mean()
            l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]
            rsi = 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]
            return float(rsi) if pd.notna(rsi) else 50.0

        vol_rel = (df_x['Volume'].iloc[-1] / df_x['Volume'].tail(30).mean()) \
                  if df_x['Volume'].tail(30).mean() > 0 else 1.0
        vol_media = df_x['Volume'].tail(30).mean() if 'Volume' in df_x else 0
        vol_rel = (df_x['Volume'].iloc[-1] / vol_media) if vol_media and vol_media > 0 else 1.0
        atr14   = (df_diario['High'] - df_diario['Low']).tail(14).mean()
        streak  = calcular_streak_dias(df_diario)

        )

        hv20    = cierre_diario.pct_change().tail(20).std() * np.sqrt(252) * 100
        hv20    = float(hv20) if pd.notna(hv20) else 0.0
        if raw_data["VIX"].empty:
            raise ValueError("Sin datos de VIX.")
        vix_ref = float(raw_data["VIX"]['Close'].iloc[-1])
        hv_iv   = hv20 / vix_ref if vix_ref > 0 else 1.0

                    if not df_or.empty:
                        or_high = float(df_or['High'].max()) * factor
                        or_low  = float(df_or['Low'].min())  * factor
        except: pass
        except Exception:
            pass

        ivr = 50.0
        try:
            vix_hist = yf.Ticker("^VIX").history(period="252d", interval="1d")['Close']
            if len(vix_hist) > 20:
                ivr = (vix_ref - vix_hist.min()) / (vix_hist.max() - vix_hist.min()) * 100
        except: pass
                rango_vix = vix_hist.max() - vix_hist.min()
                if rango_vix > 0:
                    ivr = (vix_ref - vix_hist.min()) / rango_vix * 100
        except Exception:
            pass

        pct_b = 0.5
        try:
            ma20 = cierre_diario.tail(20).mean(); std20 = cierre_diario.tail(20).std()
            bb_u = ma20 + 2*std20; bb_l = ma20 - 2*std20
            if (bb_u - bb_l) > 0: pct_b = (cierre_diario.iloc[-1] - bb_l) / (bb_u - bb_l)
        except: pass
        except Exception:
            pass

        vvix = 90.0
        try:
            if not raw_data["VVIX"].empty: vvix = float(raw_data["VVIX"]['Close'].iloc[-1])
        except: pass
        except Exception:
            pass

        vix1d = vix_ref
        try:
            if not raw_data["VIX1D"].empty: vix1d = float(raw_data["VIX1D"]['Close'].iloc[-1])
        except: pass
        except Exception:
            pass
        vix1d_ratio = vix1d / vix_ref if vix_ref > 0 else 1.0

        tnx_val      = float(raw_data["TNX"]['Close'].iloc[-1]) if not raw_data["TNX"].empty else 4.0
                                   (qqq_ret < 0 and spy_ret_val > 0) or
                                   abs(qqq_ret - spy_ret_val) > 0.4)
                qqq_lidera = qqq_ret > spy_ret_val + 0.3
        except: pass
        except Exception:
            pass

        spy_up = (not raw_data["SPY"].empty and
                  float(raw_data["SPY"]['Close'].iloc[-1]) > float(raw_data["SPY"]['Open'].iloc[-1]))

        return {
            "actual": actual, "apertura": apertura, "prev": prev_close,
            "factor": factor, "fuente_precio": fuente_precio,
            "ma5": df_x['Close'].tail(5).mean() * factor,
            "rsi_14": calc_rsi(df_x['Close'], 14), "rsi_5m": calc_rsi(df_x['Close'], 5),
            "cambio_15m": (actual - float(df_x['Close'].iloc[-15]) * factor) if len(df_x) > 15 else 0,
            "ivr": ivr, "pct_b": pct_b, "hv20": hv20, "hv_iv": hv_iv,
            "qqq_ret": qqq_ret, "spy_ret": spy_ret_val,
            "qqq_alcista": qqq_alcista, "qqq_lidera": qqq_lidera, "divergencia_qqq": divergencia_qqq,
            "vix_speed": (vix_ref / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100 if len(raw_data["VIX"]) > 5 else 0,
            "vix_speed": (
                (vix_ref / float(raw_data["VIX"]['Close'].iloc[-5]) - 1) * 100
                if len(raw_data["VIX"]) > 5 and float(raw_data["VIX"]['Close'].iloc[-5]) > 0 else 0
            ),
            "caida_flash": (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100 if len(df_x) > 5 else 0,
            "votos_tech": votos,
        }
        return None

# ================================================================
# DELTA / PROB ITM
# PROB ITM
# ================================================================
def calcular_delta_prob(precio, strike, vix, dias_exp=1):
def calcular_prob_itm(precio, strike, vix, tipo_opcion, dias_exp=1):
    T = dias_exp / 252; sigma = vix / 100
    if T <= 0 or sigma <= 0 or precio <= 0: return 0.5
    d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
    return round(norm.cdf(-d1), 4)
    if T <= 0 or sigma <= 0 or precio <= 0 or strike <= 0:
        return 0.5
    d2 = (np.log(precio / strike) - 0.5 * sigma**2 * T) / (sigma * T**0.5)
    tipo = tipo_opcion.lower()
    if tipo == "call":
        prob = norm.cdf(d2)
    elif tipo == "put":
        prob = norm.cdf(-d2)
    else:
        raise ValueError("tipo_opcion debe ser 'call' o 'put'.")
    return round(float(np.clip(prob, 0, 1)), 4)

def calcular_delta_prob(precio, strike, vix, dias_exp=1):
    return calcular_prob_itm(precio, strike, vix, "put", dias_exp)

# ================================================================
# JOURNAL
# ================================================================
def inicializar_journal():
    if "journal"         not in st.session_state: st.session_state.journal         = []
    if "analisis_activo" not in st.session_state: st.session_state.analisis_activo = False
    if "ultimo_telegram_signal_id" not in st.session_state: st.session_state.ultimo_telegram_signal_id = None

def crear_signal_id(fecha_sesion, estrategia, strike, lotes):
    payload = f"{fecha_sesion}|{estrategia}|{strike}|{lotes}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

def guardar_en_journal(entrada):
    signal_id = entrada.get("signal_id")
    if signal_id and any(e.get("signal_id") == signal_id for e in st.session_state.journal):
        return False
    st.session_state.journal.append(entrada)
    return True

def mostrar_journal():
    if not st.session_state.journal:
        st.info("Sin operaciones registradas en esta sesión.")
        return
    df_j = pd.DataFrame(st.session_state.journal)
    st.dataframe(df_j, hide_index=True, use_container_width=True)
    st.dataframe(df_j.drop(columns=["signal_id"], errors="ignore"), hide_index=True, use_container_width=True)
    con_resultado = df_j[df_j['resultado'].notna() & (df_j['resultado'] != "")].copy()
    if not con_resultado.empty:
        try:
            c2.metric("Win Rate",         f"{win_rate:.0f}%")
            c3.metric("Ganadoras",        ganadoras)
            c4.metric("Perdedoras",       perdedoras)
        except: pass
        except Exception:
            st.warning("No se pudieron calcular métricas del journal.")

def formulario_resultado_journal():
    if st.session_state.journal:
# EJECUTAR ANÁLISIS
# ================================================================
def ejecutar_analisis(cap, pnl_dia, enviar_auto):
    MAX_LOSS_DIA = -300.0

    with st.spinner("Obteniendo datos maestros..."):
        noticias = check_noticias_pro(FINNHUB_API_KEY)
        noticias = check_noticias_pro(leer_config("FINNHUB_API_KEY"))
        d        = obtener_datos_maestros()
        if not d:
            st.error("No se pudieron obtener los datos.")
            return

    with st.spinner("Calculando niveles gamma..."):
        g = calcular_niveles_gamma(d["actual"], factor=1)
        g = calcular_niveles_gamma(d["actual"], factor=d.get("factor", 1))

    ahora      = datetime.now(ZONA_HORARIA)
    ahora_time = ahora.time()
        if bias     and g["max_pain"] < d["actual"] and vender > g["max_pain"]: vender = int(g["max_pain"]) - 2
        elif not bias and g["max_pain"] > d["actual"] and vender < g["max_pain"]: vender = int(g["max_pain"]) + 2

    prob_itm            = calcular_delta_prob(d["actual"], vender, vix_para_dist)
    tipo_opcion         = "put" if bias else "call"
    prob_itm            = calcular_prob_itm(d["actual"], vender, vix_para_dist, tipo_opcion)
    distancia_seguridad = abs(d["actual"] - vender)

    # ── LOTES ─────────────────────────────────────────────────────
    # DISPLAY
    # ══════════════════════════════════════════════════════════════
    st.header(f"Dashboard | {ahora.strftime('%H:%M:%S')}")
    st.caption(f"Fuente precio: {d.get('fuente_precio', 'N/A')} | Exp gamma: {g.get('exp_usada', 'N/A')}")

    # 1️⃣ Ventana horaria
    if   ventana == "ÓPTIMA": st.success(f"{ventana_icon} **{ventana}** — {ventana_desc}")
    # Ala dinámica: 40% de la distancia al strike corto, mínimo 3 pts, máximo 20 pts
    # Escala automáticamente con VIX y ATR — más vol = más distancia = ala más ancha
    ala = max(3, min(20, round(dist_base * 0.40)))
    strike_journal = str(vender)
    orden_msg = f"VENDER {vender}"
    prob_linea_msg = f"{prob_itm*100:.1f}%"
    prob_itm_metric = prob_itm
    st.divider()
    if lotes > 0:
        if estrategia_txt == "IRON CONDOR":
            vender_call, _ = ajustar_strike_redondo(vender_call, False)
            comprar_put  = vender_put  - ala
            comprar_call = vender_call + ala
            prob_put  = calcular_delta_prob(d["actual"], vender_put,  vix_para_dist)
            prob_call = calcular_delta_prob(d["actual"], vender_call, vix_para_dist)
            prob_put  = calcular_prob_itm(d["actual"], vender_put,  vix_para_dist, "put")
            prob_call = calcular_prob_itm(d["actual"], vender_call, vix_para_dist, "call")
            prob_itm_metric = max(prob_put, prob_call)
            strike_journal = f"P {vender_put}/{comprar_put} | C {vender_call}/{comprar_call}"
            orden_msg = f"PUT {vender_put}/{comprar_put} | CALL {vender_call}/{comprar_call}"
            prob_linea_msg = f"PUT {prob_put*100:.1f}% | CALL {prob_call*100:.1f}%"
            st.success(
                f"🔥 **IRON CONDOR** | "
                f"VENDER PUT {vender_put} / COMPRAR PUT {comprar_put} | "
            )
        else:
            comprar = vender - ala if estrategia_txt == "BULL PUT" else vender + ala
            strike_journal = f"{vender}/{comprar}"
            orden_msg = f"{estrategia_txt} {vender}/{comprar}"
            prob_linea_msg = f"{prob_itm*100:.1f}%"
            st.success(
                f"🔥 **{estrategia_txt}** | "
                f"VENDER: **{vender}** / COMPRAR: **{comprar}** | "
        st.error(f"🚫 **NO OPERAR** — {motivo_display}")
        vender_teorico     = round(d["actual"] - dist_base) if bias_teorico else round(d["actual"] + dist_base)
        vender_teorico, _  = ajustar_strike_redondo(vender_teorico, bias_teorico)
        prob_teorica       = calcular_delta_prob(d["actual"], vender_teorico, vix_para_dist)
        tipo_teorico       = "put" if bias_teorico else "call"
        prob_teorica       = calcular_prob_itm(d["actual"], vender_teorico, vix_para_dist, tipo_teorico)
        dist_teorica       = abs(d["actual"] - vender_teorico)
        lotes_teoricos     = max(1, int(lotes_base * 1.5) if d["vix"] < 18 else (lotes_base if d["vix"] < 25 else lotes_base // 2))
        if señal_teorica == "IRON CONDOR":
            vender_call_teo, _ = ajustar_strike_redondo(vender_call_teo, False)
            comprar_put_teo  = vender_put_teo  - ala
            comprar_call_teo = vender_call_teo + ala
            prob_put_teo  = calcular_delta_prob(d["actual"], vender_put_teo,  vix_para_dist)
            prob_call_teo = calcular_delta_prob(d["actual"], vender_call_teo, vix_para_dist)
            prob_put_teo  = calcular_prob_itm(d["actual"], vender_put_teo,  vix_para_dist, "put")
            prob_call_teo = calcular_prob_itm(d["actual"], vender_call_teo, vix_para_dist, "call")
            st.caption(
                f"* Si se operara ahora: **{señal_teorica}** | "
                f"VENDER PUT {vender_put_teo} / COMPRAR PUT {comprar_put_teo} | "
    c22.metric("Gap %",     f"{d['gap_pct']:.2f}%")
    c23.metric("Streak",    f"{d['streak']} días")
    c24.metric("Distancia", f"{distancia_seguridad:.1f} pts")
    c25.metric("Prob ITM",  f"{prob_itm*100:.1f}%")
    c25.metric("Prob ITM",  f"{prob_itm_metric*100:.1f}%")

    st.info(
        f"📊 OR: {d['or_low']:.2f} — {d['or_high']:.2f} | "
        st.dataframe(df_niv, hide_index=True)

    # Alertas
    if noticias.get("error"):      st.warning(f"⚠️ Noticias: {noticias['error']}")
    if g.get("error"):             st.info(f"Gamma/EM: {g['error']}")
    if noticias["eventos"]:       st.warning(f"📅 Noticias: {', '.join(noticias['eventos'])}")
    if fue_ajustado:              st.info("📐 Strike ajustado — evitando strike redondo contestado")
    if cerca_redondo:             st.info(f"🧲 Strike {vender} cerca del nivel {redondo_cercano} — posible imán")

    # Telegram y journal solo si hay operación
    if lotes > 0:
        guardar_en_journal({
        signal_id = crear_signal_id(ahora.strftime('%Y-%m-%d'), estrategia_txt, strike_journal, lotes)
        guardado = guardar_en_journal({
            "signal_id": signal_id,
            "hora": ahora.strftime('%H:%M'), "estrategia": estrategia_txt,
            "strike": vender, "prob_itm": f"{prob_itm*100:.1f}%",
            "strike": strike_journal, "prob_itm": f"{prob_itm_metric*100:.1f}%",
            "distancia": f"{distancia_seguridad:.1f}", "lotes": lotes,
            "vix": f"{d['vix']:.1f}", "ivr": f"{d['ivr']:.1f}%",
            "hv_iv": f"{d['hv_iv']:.2f}", "gex": "+" if g['gex_positivo'] else "-",
            "em": f"±{g['expected_move']:.1f}" if g['expected_move'] else "N/A",
            "resultado": "", "notas": "",
        })
        if enviar_auto:
        if guardado:
            st.sidebar.success("Señal registrada en journal.")
        if enviar_auto and st.session_state.ultimo_telegram_signal_id != signal_id:
            mp_l = f"🔹 Max Pain: {g['max_pain']:.1f} (sesgo {sesgo_max_pain})\n" if g['max_pain'] else ""
            gf_l = f"🔹 Gamma Flip: {g['gamma_flip']:.1f} {'⚠️' if precio_bajo_flip else '✅'}\n" if g['gamma_flip'] else ""
            em_l = f"🔹 Exp Move: ±{g['expected_move']:.1f} pts\n" if g['expected_move'] else ""
            msg_tel = (
                f"🚀 XSP v10.1 — {estrategia_txt}\n"
                f"🔹 VENDER: {vender}{' (ajustado redondo)' if fue_ajustado else ''}\n"
                f"🔹 PROB ITM: {prob_itm*100:.1f}% | DIST: {distancia_seguridad:.1f} pts\n"
                f"🚀 XSP v{APP_VERSION} — {estrategia_txt}\n"
                f"🔹 ORDEN: {orden_msg}{' (ajustado redondo)' if fue_ajustado else ''}\n"
                f"🔹 PROB ITM: {prob_linea_msg} | DIST: {distancia_seguridad:.1f} pts\n"
                f"🔹 LOTES: {lotes}\n─────────────────\n"
                f"🔹 CW: {g['call_wall'] if g['call_wall'] else 'N/A'} {'🔴' if call_wall_confirmado else ''} | "
                f"PW: {g['put_wall'] if g['put_wall'] else 'N/A'} {'🔴' if put_wall_confirmado else ''}\n"
                f"🔹 TNX: {d['tnx_cambio']:+.2f}% | VIX9D: {'⚠️' if vix_peligro_leve else '✅'}\n"
                f"🔹 Amplitud: {'✅' if d['amplitud_ok'] else '⚠️'} | Ventana: {ventana_icon} {ventana}"
            )
            enviar_telegram(msg_tel)
            if enviar_telegram(msg_tel):
                st.session_state.ultimo_telegram_signal_id = signal_id

# ================================================================
# MAIN
# ================================================================
def main():
    st.title("🛡️ XSP 0DTE Institutional v10.1")
    st.title(f"🛡️ XSP 0DTE Institutional v{APP_VERSION}")
    inicializar_journal()

    cap         = st.sidebar.number_input("Capital Cuenta (€)", value=25000.0)
    pnl_dia     = st.sidebar.number_input("P&L del día (€)",    value=250.0)
    enviar_auto = st.sidebar.checkbox("Enviar Telegram automáticamente", value=False)

    with st.sidebar.expander("🔐 Configuración"):
        st.caption("Usa .streamlit/secrets.toml o variables de entorno.")
        st.write("Finnhub:", "✅" if leer_config("FINNHUB_API_KEY") else "⚠️ pendiente")
        st.write("Telegram:", "✅" if leer_config("TELEGRAM_BOT_TOKEN") and leer_config("TELEGRAM_CHAT_ID") else "⚠️ pendiente")

    if AUTOREFRESH_DISPONIBLE:
        refresh_min = st.sidebar.selectbox("Auto-refresh cada", [0, 2, 5, 10], index=2)
        if refresh_min > 0:
