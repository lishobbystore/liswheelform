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

# Get creds from secrets
service_account_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)

# Get sheet key from secrets
sheet_key = st.secrets["sheets"]["sheet_key"]

# Open your Google Sheets
inventory_sheet = client.open_by_key(sheet_key).worksheet("Inventory")
orders_sheet = client.open_by_key(sheet_key).worksheet("Orders")

# Load inventory data
data = inventory_sheet.get_all_records()
df = pd.DataFrame(data)

# --- Style ---
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

    /* sticky filter bar */
    .filter-bar { position: sticky; top: 0; z-index: 999; background: white; padding: 8px 0 6px; border-bottom: 1px solid #eee; }
    </style>
    """,
    unsafe_allow_html=True
)

# ----- Column safety: ensure Category & ImageURL exist -----
if "Category" not in df.columns:
    df["Category"] = "Uncategorized"
if "ImageURL" not in df.columns:
    df["ImageURL"] = ""

with st.container():
    # Header
    st.image("banner.jpg", use_container_width=True)
    st.title(" Lis Live Discount Form")
    st.markdown(
        '<div>Udah gacha di live? Saatnya kamu kunci diskonnya — isi ini semua and we’ll handle the rest!</div><br/>',
        unsafe_allow_html=True
    )

    # =========================================================
    # FILTER BAR: Category + Search (sticky)
    # =========================================================
    #st.markdown('<div class="filter-bar">', unsafe_allow_html=True)

    # Category (maintain original order from sheet)
    raw_categories = df["Category"].dropna().tolist()
    seen = set()
    categories = []
    for c in raw_categories:
        if c not in seen:
            categories.append(c)
            seen.add(c)
    categories = ["Semua Kategori"] + categories

    selected_category = st.selectbox("Pilih Kategori", categories, index=0)

    # Search (case-insensitive)
    search_query = st.text_input("Cari item (nama mengandung kata ini)", placeholder="Contoh: nendoroid, klee, figma ...")

    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # FILTERING
    # =========================================================
    if selected_category == "Semua Kategori":
        df_filtered = df.copy()
    else:
        df_filtered = df[df["Category"] == selected_category].copy()

    if search_query.strip():
        q = search_query.strip().lower()
        df_filtered = df_filtered[df_filtered["ItemName"].str.lower().str.contains(q, na=False)]

    # Jika tidak ada hasil
    if df_filtered.empty:
        st.info("Tidak ada item yang cocok dengan filter saat ini.")
        st.stop()

    # =========================================================
    # PAGINATION STATE (page size fixed = 6)
    # =========================================================
    if "selected_item" not in st.session_state:
        st.session_state.selected_item = None
    if "page" not in st.session_state:
        st.session_state.page = 1
    if "jump_to_price" not in st.session_state:
        st.session_state.jump_to_price = False

    page_size = 6  # << fixed
    total_items = len(df_filtered)
    total_pages = max(1, math.ceil(total_items / page_size))
    st.session_state.page = min(max(1, st.session_state.page), total_pages)

    # Pagination controls
    col_prev, col_info, col_next = st.columns([1, 2, 1], vertical_alignment="center")
    with col_prev:
        if st.button("⟵ Prev", disabled=(st.session_state.page <= 1)):
            st.session_state.page -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center'>Halaman {st.session_state.page} dari {total_pages} &middot; {total_items} item</div>",
            unsafe_allow_html=True
        )
    with col_next:
        if st.button("Next ⟶", disabled=(st.session_state.page >= total_pages)):
            st.session_state.page += 1
            st.rerun()

    start = (st.session_state.page - 1) * page_size
    end = start + page_size
    page_df = df_filtered.iloc[start:end].reset_index(drop=True)

    # =========================================================
    # PRODUCT GRID (3 columns desktop-ish)
    # =========================================================
   # =========================================================
# PRODUCT GRID (3 columns desktop-ish)
# =========================================================
num_cols = 3
rows = math.ceil(len(page_df) / num_cols)

for r in range(rows):
    cols = st.columns(num_cols, vertical_alignment="top")
    for c in range(num_cols):
        idx = r * num_cols + c
        if idx >= len(page_df):
            continue
        rec = page_df.iloc[idx]

        with cols[c]:
            # Image (placeholder file if empty)
            img_url = str(rec.get("ImageURL", "") or "").strip()
            if img_url:
                st.image(img_url, use_container_width=True)
            else:
                st.image("no_image.jpg", use_container_width=True)  # <<-- local placeholder image

            st.markdown(f"**{rec['ItemName']}**")
            st.markdown(f"<div class='price' style='font-size:16px;'>Rp {float(rec['Price']):,.0f}</div>", unsafe_allow_html=True)

            if st.button("Pilih", key=f"choose_{start+idx}"):
                st.session_state.selected_item = rec["ItemName"]
                st.session_state.jump_to_price = True  # trigger smooth scroll
                st.toast(f"Item dipilih: {st.session_state.selected_item}")

    # =========================================================
    # Smooth scroll to price after pick
    # =========================================================
    if st.session_state.jump_to_price:
        components.html(
            """
            <script>
            const el = window.parent.document.getElementById("price-section");
            if (el) { el.scrollIntoView({behavior:"smooth", block:"start"}); }
            </script>
            """,
            height=0,
        )
        st.session_state.jump_to_price = False

    # =========================================================
    # PRICE + DISCOUNT (after selection)
    # =========================================================
    # anchor for scrolling
    st.markdown('<div id="price-section"></div>', unsafe_allow_html=True)

    # fallback ke item pertama di halaman jika belum ada pilihan
    if not st.session_state.selected_item:
        st.session_state.selected_item = page_df.iloc[0]["ItemName"]

    sel_row = df[df["ItemName"] == st.session_state.selected_item].iloc[0]
    selected_item = sel_row["ItemName"]
    price = float(sel_row["Price"])

    st.write("---")
    st.caption("Item yang dipilih akan muncul di sini. Kamu bisa ganti pilihan dari katalog di atas.")
    st.write(f"**Item:** {selected_item}")
    st.markdown(f'<div class="price">Harga: Rp {price:,.0f}</div>', unsafe_allow_html=True)

    discount = st.selectbox("Dapet Discount Berapa % di Live?", [20, 25, 30, 35, 40])
    final_price = price * (1 - discount / 100)
    st.markdown(
        f'<div class="price">Harga Final Setelah {discount}% Discount: Rp {final_price:,.0f}</div><br/>',
        unsafe_allow_html=True
    )

    # =========================================================
    # BUYER FORM
    # =========================================================
    st.subheader("Data Pembeli")
    name = st.text_input("Nama Kamu")
    wa_number = st.text_input("Nomor WhatsApp", placeholder="0891234567788")
    address = st.text_area(
        "Alamat Lengkap",
        placeholder="Contoh: Jl. Medan Merdeka Utara No. 3, Kel. Gambir, Kec. Gambir, Kota Jakarta Pusat, DKI Jakarta 10110"
    )
    st.caption("Harap isi lengkap: nama jalan, kelurahan, kecamatan, kota/kabupaten, provinsi, dan kode pos.")

    # =========================================================
    # SUBMIT
    # =========================================================
    if st.button("Submit Order"):
        if not name.strip() or not wa_number.strip() or not address.strip():
            st.error("Tolong isi Nama Kamu, Nomor WhatsApp, dan Alamat Lengkap.")
        elif not wa_number.strip().isdigit():
            st.error("Nomor WhatsApp harus berupa angka saja (tanpa spasi atau simbol).")
        else:
            tz = pytz.timezone("Asia/Jakarta")
            current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

            # Orders header expected:
            # Time | Name | WhatsApp | Address | Item | Price | Discount | FinalPrice
            orders_sheet.append_row([
                current_time,
                name,
                wa_number,
                address,
                selected_item,
                price,
                discount,
                final_price
            ])

            st.success("Order submitted! Please follow the instructions below to pay.")

            st.markdown(f"""
            ## Instruksi Pembayaran
            Transfer ke: **BCA 2530244574 a/n PT. Licht Cahaya Abadi**  
            Mohon cantumkan note:
            - `"Pembayaran atas nama {name}"`

            Setelah transfer, harap konfirmasi via WhatsApp: **+62 819-5255-5657**
            """)

            st.write("---")
            st.subheader("Order Summary")
            st.write(f"**Name:** {name}")
            st.write(f"**WhatsApp:** {wa_number}")
            st.write(f"**Alamat:** {address}")
            st.write(f"**Item:** {selected_item}")
            st.write(f"**Original Price:** Rp {price:,.0f}")
            st.write(f"**Discount:** {discount}%")
            st.write(f"**Final Price:** Rp {final_price:,.0f}")

    st.markdown('</div>', unsafe_allow_html=True)
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
