import streamlit as st
import websocket
import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import threading
import time
import numpy as np
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📊 Mapa de Calor - Order Book BTC/USDT")

# Parámetros
symbol = "BTCUSDT"
step = 10
orderbook = pd.DataFrame(columns=["price", "quantity", "side"])
depth_lock = threading.Lock()

# Inputs de usuario para definir eje Y
col1, col2 = st.columns(2)
min_y = col1.number_input("📉 Precio mínimo en el eje Y", min_value=0.0, value=25000.0, step=100.0)
max_y = col2.number_input("📈 Precio máximo en el eje Y", min_value=0.0, value=35000.0, step=100.0)

# Cargar snapshot inicial
@st.cache_data(ttl=60)
def cargar_snapshot():
    url = "https://api.binance.com/api/v3/depth"
    params = {"symbol": symbol, "limit": 5000}
    response = requests.get(url, params=params)
    data = response.json()

    if "bids" not in data or "asks" not in data:
        st.error("Error cargando snapshot")
        return pd.DataFrame()

    bids = pd.DataFrame(data["bids"], columns=["price", "quantity"], dtype=float)
    asks = pd.DataFrame(data["asks"], columns=["price", "quantity"], dtype=float)
    bids["side"] = "bid"
    asks["side"] = "ask"
    snapshot = pd.concat([bids, asks])
    return snapshot

# Aplicar updates desde WebSocket
def aplicar_update(data):
    global orderbook
    updates = []

    if "b" in data and "a" in data:
        for price_str, qty_str in data["b"]:
            updates.append({"price": float(price_str), "quantity": float(qty_str), "side": "bid"})
        for price_str, qty_str in data["a"]:
            updates.append({"price": float(price_str), "quantity": float(qty_str), "side": "ask"})

    update_df = pd.DataFrame(updates)
    with depth_lock:
        for _, row in update_df.iterrows():
            orderbook.drop(orderbook[(orderbook["price"] == row["price"]) & (orderbook["side"] == row["side"])].index, inplace=True)
        update_df = update_df[update_df["quantity"] > 0]
        orderbook = pd.concat([orderbook, update_df], ignore_index=True)

# WebSocket
def iniciar_websocket():
    def on_message(ws, message):
        msg = json.loads(message)
        aplicar_update(msg)

    def on_error(ws, error): print("WebSocket error:", error)
    def on_close(ws, *args): print("WebSocket cerrado")
    def on_open(ws): print("WebSocket conectado")

    ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth@100ms"
    ws = websocket.WebSocketApp(ws_url,
        on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
    ws.run_forever()

# Arranca WebSocket en hilo aparte
@st.cache_resource
def start_ws():
    thread = threading.Thread(target=iniciar_websocket)
    thread.daemon = True
    thread.start()

# Iniciar el WebSocket una vez
start_ws()

# Cargar snapshot inicial
if orderbook.empty:
    orderbook = cargar_snapshot()

# Mostrar mapa de calor
placeholder = st.empty()

while True:
    with depth_lock:
        ob = orderbook.copy()

    if ob.empty:
        time.sleep(0.5)
        continue

    best_bid = ob[ob['side'] == 'bid']['price'].max()
    best_ask = ob[ob['side'] == 'ask']['price'].min()
    mid_price = (best_bid + best_ask) / 2

    min_price = int(min_y // step * step)
    max_price = int(max_y // step * step)
    precios = np.arange(min_price, max_price + step, step)

    ob['price'] = (ob['price'] // step * step).astype(int)
    grouped = ob.groupby(['price', 'side'])['quantity'].sum().unstack(fill_value=0)
    heatmap_data = pd.DataFrame(index=precios).join(grouped).fillna(0).sort_index(ascending=False)

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(heatmap_data, cmap="YlGnBu", ax=ax, cbar=True)

    # Línea roja para el precio actual
    if min_price <= mid_price <= max_price:
        y_pos = len(precios) - int((mid_price - min_price) // step) - 1
        ax.hlines(y=y_pos + 0.5, xmin=0, xmax=2, colors="red", linestyles="--", linewidth=2)

    hora_actual = datetime.now().strftime("%H:%M:%S")
    ax.set_title(f"📉 Order Book BTC/USDT – Precio medio: {mid_price:.2f} – {hora_actual}")
    ax.set_xlabel("Tipo de orden")
    ax.set_ylabel("Precio")
    ax.tick_params(right=True, labelright=True)

    placeholder.pyplot(fig)
    time.sleep(1)
