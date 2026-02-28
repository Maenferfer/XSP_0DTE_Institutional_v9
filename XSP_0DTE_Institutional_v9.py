### Page 1 ### import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz
import os
import warnings
import time as sleep_timer
import winsound
import logging
# --- CONFIGURACIÓN ---
warnings.filterwarnings("ignore")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
ZONA_HORARIA = pytz.timezone('Europe/Madrid')
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
#
================================================================
# TELEGRAM — BUG #4 CORREGIDO: faltaba /bot antes del token
#
================================================================
def enviar_telegram(mensaje):
 token = "8730360984:AAGJCvvnQKbZJFnAIQnfnC4bmrq1lCk9MEo"
 chat_id = "7121107501"
 url = f"https://api.telegram.org{token}/sendMessage"
 try:
 requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=5)
 except:
 pass
#
================================================================
# NOTICIAS — BUG #1 CORREGIDO: URL de Finnhub completa
#
================================================================
def check_noticias_pro(api_key):
 eventos_prohibidos = [
 "CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE",
 "JOBLESS", "TARIFF", "TRADE WAR", "RETAIL SALES", "EARNINGS"
 ]
 hoy = str(date.today())
 # URL corregida — antes faltaba el endpoint completo
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
### Page 2 ###  return estado
#
================================================================
# STREAK DE DÍAS CONSECUTIVOS
#
================================================================
def calcular_streak_dias(df_diario):
 closes = df_diario['Close'].tail(10).values
 if len(closes) < 2:
 return 0
 streak = 0
 direction = 1 if closes[-1] > closes[-2] else -1
 for i in range(len(closes) - 1, 0, -1):
 if (closes[i] - closes[i - 1]) * direction > 0:
 streak += direction
 else:
 break
 return streak
#
================================================================
# DATOS MAESTROS — MEJORA: VIX3M añadido
#
================================================================
def obtener_datos_maestros():
 vals = {}
 try:
 tickers = {
 "XSP": "^XSP", "SPY": "SPY", "RSP": "RSP", "VIX": "^VIX",
 "VIX9D": "^VIX9D", "VIX3M": "^VIX3M", "SKEW": "^SKEW",
 "TNX": "^TNX", "PCCE": "PCCE"
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
 apertura = float(df_x['Open'].iloc[-1]) * factor
 prev_close= float(df_x['Close'].iloc[-2]) * factor
 def calc_rsi(series, p):
 delta = series.diff()
 g = delta.where(delta > 0, 0).rolling(window=p).mean()
 l = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
 return 100 - (100 / (1 + (g / l.replace(0, np.nan)))).iloc[-1]
 vol_actual = df_x['Volume'].iloc[-1]
 vol_avg = df_x['Volume'].tail(30).mean()
 vol_rel = vol_actual / vol_avg if vol_avg > 0 else 1.0
 # Datos diarios para ATR, streak, z-score e inside_day
 df_diario = yf.Ticker("^XSP").history(period="30d", interval="1d")
 if df_diario.empty:
 df_diario = yf.Ticker("SPY").history(period="30d", interval="1d")
### Page 3 ###  df_diario = df_diario * factor if raw_data["XSP"].empty else df_diario
 atr14 = (df_diario['High'] - df_diario['Low']).tail(14).mean()
 streak = calcular_streak_dias(df_diario)
 cierre_diario = df_diario['Close']
 std_20 = cierre_diario.tail(20).std()
 z_score = (cierre_diario.iloc[-1] - cierre_diario.tail(20).mean()) / std_20 if std_20 > 0 else 0
 # BUG #2 CORREGIDO: inside_day con guard robusto de longitud
 inside_day = (
 len(df_diario) >= 2 and
 df_diario['High'].iloc[-1] < df_diario['High'].iloc[-2] and
 df_diario['Low'].iloc[-1] > df_diario['Low'].iloc[-2]
 )
 # NUEVO v9.0: VWAP intradiario
 if len(df_x) > 30:
 typical = (df_x['High'] + df_x['Low'] + df_x['Close']) / 3
 vwap = (typical * df_x['Volume']).cumsum() / df_x['Volume'].cumsum()
 vwap_actual = float(vwap.iloc[-1]) * factor
 else:
 vwap_actual = actual # sin datos suficientes → neutral
 # NUEVO v9.0: VIX3M para detectar backwardation (pánico real)
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
 "vix_speed": (float(raw_data["VIX"]['Close'].iloc[-1]) / float(raw_data["VIX"]['Close'].iloc[-5]) -
1) * 100
 if len(raw_data["VIX"]) > 5 else 0,
 # BUG caida_flash corregido: usar .tail() para evitar IndexError
 "caida_flash": (actual / (float(df_x['Close'].tail(6).iloc[0]) * factor) - 1) * 100
 if len(df_x) > 5 else 0,
 }
 # Votos tech
 votos = 0
 for tk in ["AAPL", "MSFT", "NVDA"]:
### Page 4 ###  d = yf.Ticker(tk).history(period="1d", interval="1m")
 if not d.empty and d['Close'].iloc[-1] > d['Open'].iloc[-1]:
 votos += 1
 vals["votos_tech"] = votos
 except Exception as e:
 print(f"[ERROR datos]: {e}")
 return None
 return vals
#
================================================================
# FUNCIÓN AUXILIAR: Delta teórico del strike (prob. de quedar ITM)
#
================================================================
def calcular_delta_prob(precio, strike, vix, dias_exp=1):
 T = dias_exp / 252
 sigma = vix / 100
 if T <= 0 or sigma <= 0 or precio <= 0:
 return 0.5
 d1 = (np.log(precio / strike) + 0.5 * sigma**2 * T) / (sigma * T**0.5)
 # Bull Put: queremos prob de que precio quede > strike → 1 - N(-d1)
 prob_itm = norm.cdf(-d1)
 return round(prob_itm, 4)
#
================================================================
# MAIN
#
================================================================
def main():
 os.system('cls' if os.name == 'nt' else 'clear')
 print(" XSP 0DTE Institutional v9.0 — Definitivo")
 print("=" * 65)
 cap = float(input("Capital Cuenta (€): ") or 25000.0)
 # P&L del día (nuevo: límite diario de pérdidas)
 pnl_dia = 0.0
 MAX_LOSS_DIA = -300.0 # Si pierdes 300€ en el día → no volver a operar
 while True:
 noticias = check_noticias_pro(FINNHUB_API_KEY)
 d = obtener_datos_maestros()
 if not d:
 sleep_timer.sleep(5)
 continue
 os.system('cls' if os.name == 'nt' else 'clear')
 ahora = datetime.now(ZONA_HORARIA)
 ahora_time = ahora.time()
 mercado_asentado = ahora_time >= time(16, 45)
 hora_limite = time(20, 45)
 minutos_al_limite = max(0, (
 datetime.combine(date.today(), hora_limite) -
 datetime.combine(date.today(), ahora_time)
 ).total_seconds() / 60)
### Page 5 ###  #
============================================================
 # FILTROS DE RÉGIMEN
 #
============================================================
 vix_extremo = d["vix"] > 35
 backwardation = d["vix"] > d["vix3m"] # NUEVO v9.0: pánico real
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
 # NUEVO v9.0: VWAP confirma sesgo
 precio_sobre_vwap = d["actual"] > d["vwap"]
 # NUEVO v9.0: Iron Condor si mercado es lateral
 skew_ok_ic = d["skew"] < 125
 iron_condor = (
 d["vix"] < 18 and
 d["inside_day"] and
 abs(d["streak"]) < 2 and
 1 <= d["votos_tech"] <= 2 and
 skew_ok_ic
 )
 #
============================================================
 # BIAS v9.0
 #
============================================================
 bias = (
 (d["actual"] > d["prev"]) and
 (d["votos_tech"] >= 2) and
 d["rsp_bull"] and
 not vix_peligro and
 not noticias["bloqueo"] and
 not divergencia_bonos and
 precio_sobre_vwap # NUEVO: confirmación VWAP
 )
 # Forzar sesgo por Z-Score extremo
 if d["z_score"] > 2.2:
 bias = False
 print(" PATRÓN: Agotamiento alcista extremo (Z > 2.2) → Bear Call forzado")
 if d["z_score"] < -2.2:
 bias = True
 print(" PATRÓN: Pánico excesivo (Z < -2.2) → Bull Put forzado")
 # Ajuste por gaps de apertura
 if gap_grande_arr and not iron_condor:
 bias = False
 if gap_grande_abj and not iron_condor:
 bias = True
### Page 6 ###  #
============================================================
 # CÁLCULO DE STRIKE v9.0
 #
============================================================
 if d["vix"] < 15:
 m_seg = 0.85
 elif d["vix"] < 22:
 m_seg = 1.05
 else:
 m_seg = 1.35
 m_horario = 0.92 if ahora_time >= time(16, 45) else 1.0
 dist_atr = d["atr14"] * 0.90 * m_horario
 dist_sigma = d["actual"] * ((d["vix"] / 100) / (252**0.5)) * m_seg
 dist = max(dist_atr, dist_sigma)
 vender = round(d["actual"] - dist) if bias else round(d["actual"] + dist)
 if vender % 5 == 0:
 vender = vender - 1 if bias else vender + 1
 # NUEVO v9.0: Delta/probabilidad del strike elegido
 prob_itm = calcular_delta_prob(d["actual"], vender, d["vix"])
 if prob_itm > 0.20:
 # Strike demasiado cercano → alejar 1 punto más
 vender = vender - 2 if bias else vender + 2
 prob_itm = calcular_delta_prob(d["actual"], vender, d["vix"])
 distancia_seguridad = abs(d["actual"] - vender)
 #
============================================================
 # GESTIÓN DE LOTES v9.0
 # BUG #3 CORREGIDO: lotes_base calculado primero, inside_day al final
 #
============================================================
 lotes_base = max(1, int((cap / 25000) * 10))
 if vix_extremo or backwardation or pico_bonos or vix_panico:
 lotes = 0
 if vix_extremo: motivo_bloqueo = "VIX EXTREMO (>35)"
 elif backwardation: motivo_bloqueo = "BACKWARDATION VIX (pánico real)"
 elif pico_bonos: motivo_bloqueo = "SALTO BONOS +2%"
 else: motivo_bloqueo = "PÁNICO VIX SPEED"
 else:
 if d["vix"] < 18:
 lotes = int(lotes_base * 1.5)
 elif d["vix"] < 25:
 lotes = lotes_base
 else:
 lotes = max(1, lotes_base // 2)
 if distancia_seguridad > 5 and d["vix"] < 20:
 lotes = max(lotes, 15)
 # Inside Day bonus — AHORA al final, sobre lotes ya calculados
 if d["inside_day"] and not vix_peligro and lotes > 0:
 lotes = int(lotes * 1.2)
 print(" OPORTUNIDAD: Inside Day detectado. Lotes +20%.")
 # NUEVO v9.0: Límite diario de pérdidas
### Page 7 ###  if pnl_dia <= MAX_LOSS_DIA:
 lotes = 0
 print(f" LÍMITE DIARIO ALCANZADO: P&L día = {pnl_dia:.0f}€. No operar más hoy.")
 #
============================================================
 # SPREAD DINÁMICO
 #
============================================================
 if iron_condor:
 ancho = 2
 vender_call = round(d["actual"] + dist)
 comprar_call = vender_call + ancho
 comprar_put = vender - ancho
 else:
 if d["vix"] < 18: ancho = 2
 elif d["vix"] < 25: ancho = 3
 else: ancho = 5
 comprar = vender - ancho if bias else vender + ancho
 #
============================================================
 # ALERTAS SONORAS
 #
============================================================
 if ahora_time >= hora_limite:
 winsound.Beep(1500, 1000)
 if abs(d["actual"] - vender) < 0.8:
 winsound.Beep(2000, 800)
 if vix_extremo:
 winsound.Beep(800, 1500)
 #
============================================================
 # DISPLAY
 #
============================================================
 print(f" XSP 0DTE v9.0 | {ahora.strftime('%H:%M:%S')} | CAPITAL: {cap:,.0f}€ | P&L HOY:
{pnl_dia:+.0f}€")
 print(f"XSP: {d['actual']:.2f} | VWAP: {d['vwap']:.2f} {'▲ SOBRE' if precio_sobre_vwap else '▼
BAJO'} | MA5: {d['ma5']:.1f}")
 print(f"RSI14: {d['rsi_14']:.1f} | Z-Score: {d['z_score']:.2f} | ATR14: {d['atr14']:.2f} | VOL:
{d['vol_rel']:.2f}x")
 print("-" * 65)
 print(f"VIX: {d['vix']:.2f}{' EXTREMO' if vix_extremo else ''} | VIX9D: {d['vix9d']:.2f} | VIX3M:
{d['vix3m']:.2f}{' BACKW.' if backwardation else ''}")
 print(f"SKEW: {d['skew']:.2f} | P/C: {d['pc_ratio']:.2f} | TNX: {d['tnx']:.2f} | TECH:
{d['votos_tech']}/3 | RSP: {' ' if d['rsp_bull'] else ' '}")
 print(f"GAP: {d['gap_pct']:+.2f}% | STREAK: {d['streak']:+d}d | INSIDE DAY: {' ' if d['inside_day']
else ' '} | IRON CONDOR: {' ' if iron_condor else ' '}")
 print("=" * 65)
 if noticias["bloqueo"]:
 print(f" BLOQUEO NOTICIAS: {noticias['eventos']}")
 elif vix_extremo or backwardation:
 msg = f" {'VIX EXTREMO' if vix_extremo else 'BACKWARDATION'} — NO OPERAR HOY"
 print(msg)
 elif lotes == 0:
 print(f" NO OPERAR: {motivo_bloqueo if 'motivo_bloqueo' in dir() else 'Condiciones
insuficientes'}")
 else:
### Page 8 ###  if ahora_time >= hora_limite:
 print(" HORA LÍMITE ALCANZADA (20:45h). LIQUIDAR POSICIÓN AHORA.")
 elif minutos_al_limite <= 60:
 print(f"⏳ Cierre automático en {int(minutos_al_limite)} min (20:45h)")
 if not mercado_asentado:
 print("\n⏳ MODO PRE-CHECK — Esperando 16:45h para ejecutar")
 print(f" Pre-estrategia: {'IRON CONDOR' if iron_condor else ('BULL PUT' if bias else 'BEAR
CALL')}")
 print(f" Vender estimado: {vender} | Prob ITM: {prob_itm*100:.1f}%")
 else:
 alerta_flash = d["caida_flash"] < -0.40 if bias else d["caida_flash"] > 0.40
 if alerta_flash:
 msg = " ALERTA FLASH: Movimiento violento en XSP. ¡EVALUAR CIERRE!"
 enviar_telegram(msg)
 print(msg)
 print()
 if iron_condor:
 print(" ESTRATEGIA: IRON CONDOR (mercado lateral, VIX bajo)")
 print(f" BULL PUT → VENDER {vender} / COMPRAR {comprar_put} (ancho {ancho}
pts)")
 print(f" BEAR CALL → VENDER {vender_call} / COMPRAR {comprar_call} (ancho {ancho}
pts)")
 print(f" LOTES: {lotes} por pata | Prima doble estimada")
 else:
 print(f" ESTRATEGIA: {'BULL PUT' if bias else 'BEAR CALL'}")
 print(f" VENDER: {vender} | COMPRAR: {comprar} (spread {ancho} pts)")
 print(f" DISTANCIA: {distancia_seguridad:.2f} pts | PROB ITM: {prob_itm*100:.1f}% |
LOTES: {lotes}")
 print(f" SL: si precio toca {vender} | TP: 65% prima recibida")
 print("=" * 65)
 # Notificación Telegram a las 16:45h
 if ahora.hour == 16 and ahora.minute == 45 and ahora.second <= 30:
 estrategia_txt = "IRON CONDOR" if iron_condor else ("BULL PUT" if bias else "BEAR CALL")
 msg_tel = (
 f" XSP v9.0 — {estrategia_txt}\n"
 f" VENDER: {vender} | PROB ITM: {prob_itm*100:.1f}%\n"
 f" LOTES: {lotes} | SPREAD: {ancho} pts\n"
 f" VIX: {d['vix']:.1f} | Z: {d['z_score']:.2f} | GAP: {d['gap_pct']:+.2f}%"
 )
 enviar_telegram(msg_tel)
 print("=" * 65)
 for i in range(30, 0, -1):
 print(f"Actualizando en: {i}s... ", end="\r", flush=True)
 sleep_timer.sleep(1)
if __name__ == "__main__":
 main()
