import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
import json
import time
from typing import Callable, Any

# ================================
# ANTI-429 UTILITIES
# ================================

# Cache the authorized client + worksheets for the whole app session
@st.cache_resource(show_spinner=False)
def get_worksheets(_svc_info: dict, _sheet_key: str):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",  # add spreadsheets scope for reliability
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(_svc_info, scope)
    _client = gspread.authorize(creds)
    sh = _client.open_by_key(_sheet_key)
    inv_ws = sh.worksheet("Inventory")
    ord_ws = sh.worksheet("Orders")
    return inv_ws, ord_ws

def with_backoff(fn: Callable[[], Any], *, retries: int = 6, base: float = 0.5):
    """
    Run a gspread call with exponential backoff on 429/5xx.
    Sleeps: base * 2^i  (0.5s, 1s, 2s, 4s, 8s, 16s)
    """
    last_exc = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e).lower()
            if ("429" in msg) or ("rate limit" in msg) or ("quota" in msg) or ("internal error" in msg) or ("503" in msg) or ("500" in msg):
                time.sleep(base * (2 ** i))
                last_exc = e
                continue
            raise
    raise last_exc if last_exc else RuntimeError("Unknown error in with_backoff")

# ================================
# GOOGLE SHEETS HANDLES (CACHED)
# ================================
service_account_info = st.secrets["gcp_service_account"]
sheet_key = st.secrets["sheets"]["sheet_key"]
inventory_sheet, orders_sheet = get_worksheets(service_account_info, sheet_key)

# ================================
# DATA LOAD (CACHED + BACKOFF)
# ================================
@st.cache_data(ttl=120, show_spinner=False)  # cache reads for 5 minutes
def load_inventory_df() -> pd.DataFrame:
    data = with_backoff(lambda: inventory_sheet.get_all_records())
    df_local = pd.DataFrame(data)
    if "Category" not in df_local.columns:
        df_local["Category"] = "Uncategorized"
    return df_local

df = load_inventory_df()

# ================================
# STYLE
# ================================
st.markdown(
    """
    <style>
    .price {
        font-size: 24px;
        font-weight: bold; 
    }

    .footer-desktop {
        display: block;
        text-align: center;
    }
    .footer-mobile {
        display: none;
    }

    @media (max-width: 768px) {
        .footer-desktop {
            display: none;
        }
        .footer-mobile {
            display: block;
            text-align: left;
        }
    }

    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #f0f6ff;
        color: #222;
        padding: 10px;
        font-size: 12px;
        border-top: 1px solid #cce0ff;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ================================
# UI
# ================================
with st.container():
    st.image("banner.jpg", use_container_width=True)
    st.title(" Lis Live Discount Form")
    st.markdown(
        '<div>Udah gacha di live? Saatnya kamu kunci diskonnya — isi ini semua and we’ll handle the rest!</div><br/>',
        unsafe_allow_html=True
    )

    name = st.text_input("Nama Kamu")
    wa_number = st.text_input("Nomor WhatsApp", placeholder="0891234567788")
    address = st.text_area(
        "Alamat Lengkap", 
        placeholder="Contoh: Jl. Medan Merdeka Utara No. 3, Kel. Gambir, Kec. Gambir, Kota Jakarta Pusat, DKI Jakarta 10110"
    )
    st.caption("Harap isi lengkap: nama jalan, kelurahan, kecamatan, kota/kabupaten, provinsi, dan kode pos.")
    
    # ====== CATEGORY FILTER
    categories = sorted([c for c in df["Category"].dropna().unique().tolist()])
    categories = ["Semua Kategori"] + categories
    selected_category = st.selectbox("Pilih Kategori", categories, index=0)

    if selected_category == "Semua Kategori":
        df_filtered = df.copy()
    else:
        df_filtered = df[df["Category"] == selected_category].copy()

    if df_filtered.empty:
        st.warning("Belum ada item untuk kategori ini.")
        st.stop()

    st.caption("Tips: Kamu bisa mulai mengetik untuk mencari item lebih cepat.")
    item_names = df_filtered["ItemName"].tolist()
    selected_item = st.selectbox("Pilih Item", item_names)

    # Ambil baris item terpilih
    row = df_filtered.loc[df_filtered["ItemName"] == selected_item].iloc[0]
    price = float(row["Price"])
    item_category = row["Category"]
    
    st.markdown(f'<div class="price">Harga: Rp {price:,.0f}</div>', unsafe_allow_html=True)

    discount = st.selectbox("Dapet Discount Berapa % di Live?", [20, 25, 30, 39.9999999])
    final_price = price * (1 - discount / 100)
    st.markdown(
        f'<div class="price">Harga Final Setelah {discount}% Discount: Rp {final_price:,.0f}</div><br/>',
        unsafe_allow_html=True
    )

    # --- simple double-submit throttle to avoid burst appends (helps with rate limits)
    if "last_write_ts" not in st.session_state:
        st.session_state.last_write_ts = 0.0

    if st.button("Submit Order"):
        if not name.strip() or not wa_number.strip() or not address.strip():
            st.error("Tolong isi Nama Kamu, Nomor WhatsApp, dan Alamat Lengkap.")
        elif not wa_number.strip().isdigit():
            st.error("Nomor WhatsApp harus berupa angka saja (tanpa spasi atau simbol).")
        else:
            now_ts = time.time()
            if now_ts - st.session_state.last_write_ts < 1.0:
                st.warning("Sebentar ya… (mencegah kirim ganda).")
            else:
                tz = pytz.timezone("Asia/Jakarta")
                current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

                # WRITE with backoff
                try:
                    with_backoff(lambda: orders_sheet.append_row([
                        current_time,
                        name,
                        wa_number,
                        address,
                        selected_item,
                        price,
                        discount,
                        final_price
                    ]))
                    st.session_state.last_write_ts = now_ts

                    st.success("Order submitted! Please follow the instructions below to pay.")

                    st.markdown("""
                    ## Instruski Pembayaran 
                    Transfer ke: **BCA 2530244574 a/n PT. Licht Cahaya Abadi**  
                    Mohon cantumkan note:
                    - `"Pembayaran atas nama {0}"` 

                    Setelah transfer, harap konfirmasi via WhatsApp: **+62 819-5255-5657**
                    """.format(name))

                    st.write("---")
                    st.subheader("Order Summary")
                    st.write(f"**Name:** {name}")
                    st.write(f"**WhatsApp:** {wa_number}")
                    st.write(f"**Alamat:** {address}")
                    st.write(f"**Item:** {selected_item}")
                    st.write(f"**Original Price:** Rp {price:,.0f}")
                    st.write(f"**Discount:** {discount}%")
                    st.write(f"**Final Price:** Rp {final_price:,.0f}")

                except Exception as e:
                    st.error(f"Gagal submit order. Coba lagi sebentar ya. (Detail: {e})")

st.markdown(
    """
    <div class="footer footer-desktop">
        &copy; 2025 Lichtschein Hobby Store | Follow @lishobbystore on Instagram for more promos! 🚀
    </div>
    <div class="footer footer-mobile">
        Follow @lishobbystore on Instagram for more promos!
    </div>
    """,
    unsafe_allow_html=True
)
