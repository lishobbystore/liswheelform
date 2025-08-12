import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
import json
import math
import streamlit.components.v1 as components  # for smooth scroll

# --- Google Sheets API setup ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
service_account_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)
sheet_key = st.secrets["sheets"]["sheet_key"]

# ----- Cached loader for Inventory (anti-429) -----
@st.cache_data(ttl=60)  # cache for 60 seconds
def load_inventory(_sheet_key: str) -> pd.DataFrame:
    ws = client.open_by_key(_sheet_key).worksheet("Inventory")
    data = ws.get_all_records()
    return pd.DataFrame(data)

def _clear_inventory_cache():
    load_inventory.clear()

# Open Orders sheet (write only on submit)
orders_sheet = client.open_by_key(sheet_key).worksheet("Orders")

# Load inventory data (cached)
df = load_inventory(sheet_key)

# --- Style ---
st.markdown(
    """
    <style>
    .price { font-size: 24px; font-weight: bold; }

    .footer-desktop { display: block; text-align: center; }
    .footer-mobile { display: none; }

    @media (max-width: 768px) {
        .footer-desktop { display: none; }
        .footer-mobile { display: block; text-align: left; }
    }

    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #f0f6ff; color: #222; padding: 10px;
        font-size: 12px; border-top: 1px solid #cce0ff;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ----- Column safety -----
if "Category" not in df.columns:
    df["Category"] = "Uncategorized"
if "ImageURL" not in df.columns:
    df["ImageURL"] = ""

# ----- Session state defaults -----
if "selected_item" not in st.session_state:
    st.session_state.selected_item = None
if "page" not in st.session_state:
    st.session_state.page = 1
if "jump_to_price" not in st.session_state:
    st.session_state.jump_to_price = False
if "sort_option" not in st.session_state:
    st.session_state.sort_option = "Tanpa urutan"

with st.container():
    # Header
    st.image("banner.jpg", use_container_width=True)
    st.title(" Lis Live Discount Form")
    st.markdown(
        '<div>Udah gacha di live? Saatnya kamu kunci diskonnya — isi ini semua and we’ll handle the rest!</div><br/>',
        unsafe_allow_html=True
    )

    # Optional: manual refresh inventory cache
    st.button("Reload Data", on_click=_clear_inventory_cache, help="Paksa refresh inventory dari Google Sheets")

    # =========================================================
    # FILTERS (Category + Search)
    # =========================================================
    # Category (keep original order from sheet)
    raw_categories = df["Category"].dropna().tolist()
    seen = set(); categories = []
    for c in raw_categories:
        if c not in seen:
            categories.append(c); seen.add(c)
    categories = ["Semua Kategori"] + categories

    selected_category = st.selectbox("Pilih Kategori", categories, index=0)
    search_query = st.text_input("Cari item (nama mengandung kata ini)", placeholder="Contoh: nendoroid, klee, figma ...")

    # =========================================================
    # FILTERING + SORTING
    # =========================================================
    if selected_category == "Semua Kategori":
        df_filtered = df.copy()
    else:
        df_filtered = df[df["Category"] == selected_category].copy()

    if search_query.strip():
        q = search_query.strip().lower()
        df_filtered = df_filtered[df_filtered["ItemName"].str.lower().str.contains(q, na=False)]

    # Sorting (applied before pagination)
    df_filtered["_PriceNum"] = pd.to_numeric(df_filtered["Price"], errors="coerce")
    if st.session_state.sort_option == "Harga Terendah":
        df_filtered = df_filtered.sort_values(by="_PriceNum", ascending=True, kind="stable")
    elif st.session_state.sort_option == "Harga Tertinggi":
        df_filtered = df_filtered.sort_values(by="_PriceNum", ascending=False, kind="stable")
    elif st.session_state.sort_option == "Nama A-Z":
        df_filtered = df_filtered.sort_values(by="ItemName", key=lambda s: s.str.lower(), kind="stable")
    # "Tanpa urutan" -> keep original order

    # Jika tidak ada hasil
    if df_filtered.empty:
        st.info("Tidak ada item yang cocok dengan filter saat ini.")
        st.stop()

    # =========================================================
    # PAGINATION (fixed page size = 6)
    # =========================================================
    page_size = 6
    total_items = len(df_filtered)
    total_pages = max(1, math.ceil(total_items / page_size))
    st.session_state.page = min(max(1, st.session_state.page), total_pages)

    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⟵ Prev", disabled=(st.session_state.page <= 1)):
            st.session_state.page -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center'>Halaman {st.session_state.page} dari {total_pages} &middot; {total_items} item</di_
