import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
import websocket
import threading
import json
import time
import requests

symbol = "BTCUSDT"
step = 10
rango_usd = 2000
orderbook = pd.DataFrame(columns=["price", "quantity", "side"])
depth_lock = threading.Lock()

def cargar_snapshot():
    url = "https://api.binance.com/api/v3/depth"
    params = {"symbol": symbol, "limit": 5000}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        bids = pd.DataFrame(data["bids"], columns=["price", "quantity"], dtype=float)
        asks = pd.DataFrame(data["asks"], columns=["price", "quantity"], dtype=float)
        bids["side"] = "bid"
        asks["side"] = "ask"
        return pd.concat([bids, asks])
    except Exception as e:
        st.error(f"Error al cargar snapshot: {e}")
        return pd.DataFrame()

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
            orderbook.drop(orderbook[(orderbook["price"] == row["price"]) &
                                     (orderbook["side"] == row["side"])].index, inplace=True)
        update_df = update_df[update_df["quantity"] > 0]
        orderbook = pd.concat([orderbook, update_df], ignore_index=True)

def on_message(ws, message):
    aplicar_update(json.loads(message))

def iniciar_websocket():
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth@100ms"
    ws = websocket.WebSocketApp(url,
                                 on_message=on_message)
    ws.run_forever()

# Iniciar WebSocket
if "websocket_started" not in st.session_state:
    orderbook = cargar_snapshot()
    ws_thread = threading.Thread(target=iniciar_websocket)
    ws_thread.daemon = True
    ws_thread.start()
    st.session_state.websocket_started = True

st.title("📊 BTC/USDT Order Book Heatmap (Binance)")
plot_area = st.empty()

while True:
    with depth_lock:
        ob = orderbook.copy()

    if ob.empty:
        time.sleep(1)
        continue

    best_bid = ob[ob['side'] == 'bid']['price'].max()
    best_ask = ob[ob['side'] == 'ask']['price'].min()
    mid_price = (best_bid + best_ask) / 2
    min_price = int((mid_price - rango_usd) // step * step)
    max_price = int((mid_price + rango_usd) // step * step)
    precios = np.arange(min_price, max_price + step, step)

    ob['price'] = (ob['price'] // step * step).astype(int)
    grouped = ob.groupby(['price', 'side'])['quantity'].sum().unstack(fill_value=0)
    heatmap_data = pd.DataFrame(index=precios).join(grouped).fillna(0).sort_index(ascending=False)

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(heatmap_data, cmap="YlGnBu", ax=ax, cbar=False)
    ax.set_title(f"📈 BTC/USDT Order Book\nPrecio medio: {mid_price:.2f} | Actualizado: {datetime.now().strftime('%H:%M:%S')}")
    ax.set_xlabel("Tipo de orden")
    ax.set_ylabel("Precio")
    ax.tick_params(right=True, labelright=True)

    plot_area.pyplot(fig)
    time.sleep(2)
