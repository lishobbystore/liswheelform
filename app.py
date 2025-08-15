import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
import math
import streamlit.components.v1 as components  # for smooth scroll
from urllib.parse import quote

# --- Google Sheets API setup ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
service_account_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)
sheet_key = st.secrets["sheets"]["sheet_key"]

# Ultra-light inline placeholder (no file I/O, instant render)
PLACEHOLDER_SVG = "data:image/svg+xml;utf8," + quote("""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'>
  <rect width='100%' height='100%' fill='#0f1116'/>
  <text x='50%' y='52%' fill='#9aa4b2' font-size='32' text-anchor='middle' font-family='sans-serif'>NO IMAGE</text>
</svg>
""")

# ----- Cached loader for Inventory (anti-429) -----
@st.cache_data(ttl=120)  # cache for 120 seconds
def load_inventory(_sheet_key: str) -> pd.DataFrame:
    ws = client.open_by_key(_sheet_key).worksheet("Inventory")
    data = ws.get_all_records()
    df_local = pd.DataFrame(data)
    # Column safety & normalization
    if "Category" not in df_local.columns:
        df_local["Category"] = "Uncategorized"
    if "ImageURL" not in df_local.columns:
        df_local["ImageURL"] = ""
    else:
        df_local["ImageURL"] = df_local["ImageURL"].fillna("").astype(str).str.strip()
    return df_local

# Orders sheet (write only on submit)
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
    @media (max-width: 768px) { .footer-desktop { display: none; } .footer-mobile { display: block; text-align: left; } }
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #f0f6ff; color: #222; padding: 10px;
        font-size: 12px; border-top: 1px solid #cce0ff;
    }

    /* Product card */
    .p-card{
      border:1px solid rgba(255,255,255,0.12); border-radius:12px; padding:12px;
      height:100%; display:flex; flex-direction:column; gap:10px;
      background:rgba(255,255,255,0.03);
      margin-bottom:16px; /* space for the button below */
    }
    .p-card .imgwrap{
      width:100%; aspect-ratio:1/1; border-radius:10px; overflow:hidden;
      background:#0f1116; display:flex; align-items:center; justify-content:center;
    }
    .p-card .imgwrap img{ width:100%; height:100%; object-fit:cover; } /* crop to fill */
    .p-card .name{
      font-weight:600; font-size:14px; line-height:1.3;
      display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
      overflow:hidden; min-height: calc(1.3em * 2); /* lock to 2 lines */
    }
    .p-card .price-row{ margin-top:auto; }
    .p-card .price-tag{ font-size:16px; font-weight:700; }

    /* Make Streamlit button match card width */
    .stButton > button{
      width:100%; border-radius:10px; padding:6px 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ----- Session state defaults -----
if "selected_item" not in st.session_state:
    st.session_state.selected_item = None
if "page" not in st.session_state:
    st.session_state.page = 1
if "jump_to_price" not in st.session_state:
    st.session_state.jump_to_price = False
if "sort_option" not in st.session_state:
    st.session_state.sort_option = "Tanpa urutan"
if "selected_category" not in st.session_state:
    st.session_state.selected_category = "Semua Kategori"
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
# Only for forcing the scroll component to re-render
if "scroll_seq" not in st.session_state:
    st.session_state.scroll_seq = 0

# Helper: reset page to 1 on filter changes
def reset_page():
    st.session_state.page = 1

with st.container():
    # Header
    st.image("banner.jpg", use_container_width=True)
    st.title(" Lis Live Discount Form")
    st.markdown(
        '<div>Udah gacha di live? Saatnya kamu kunci diskonnya — isi ini semua and we’ll handle the rest!</div><br/>',
        unsafe_allow_html=True
    )

    # =========================================================
    # FILTERS (Category + Search)
    # =========================================================
    raw_categories = df["Category"].dropna().tolist()
    seen = set(); categories = []
    for c in raw_categories:
        if c not in seen:
            categories.append(c); seen.add(c)
    categories = ["Semua Kategori"] + categories

    selected_category = st.selectbox(
        "Pilih Kategori",
        categories,
        index=categories.index(st.session_state.selected_category) if st.session_state.selected_category in categories else 0,
        key="selected_category",
        on_change=reset_page
    )
    search_query = st.text_input(
        "Cari item (nama mengandung kata ini)",
        value=st.session_state.search_query,
        placeholder="Contoh: nendoroid, klee, figma ...",
        key="search_query",
        on_change=reset_page
    )

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
    # "Tanpa urutan" -> original order

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

    # TOP pagination
    col_prev, col_info, col_next = st.columns([1, 2, 1])
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
    # PRODUCT GRID (3 columns)
    # =========================================================
    num_cols = 3
    records = page_df.to_dict("records")
    rows = math.ceil(len(records) / num_cols)

    for r in range(rows):
        cols = st.columns(num_cols)
        for c in range(num_cols):
            idx = r * num_cols + c
            if idx >= len(records):
                continue
            rec = records[idx]

            # Use URL if http(s)/data, else inline SVG placeholder
            raw = str(rec.get("ImageURL", "") or "").strip()
            low = raw.lower()
            img_src = raw if (low.startswith("http://") or low.startswith("https://") or low.startswith("data:")) else PLACEHOLDER_SVG

            with cols[c]:
                st.markdown(
                    f"""
                    <div class="p-card">
                      <div class="imgwrap">
                        <img src="{img_src}" alt="product" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
                      </div>
                      <div class="name">{rec['ItemName']}</div>
                      <div class="price-row"><div class="price-tag">Rp {float(rec['Price']):,.0f}</div></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if st.button("Pilih", key=f"choose_{start+idx}"):
                    st.session_state.selected_item = rec["ItemName"]
                    st.session_state.jump_to_price = True
                    st.session_state.scroll_seq += 1  # force scroll JS to re-render
                    st.toast(f"Item dipilih: {st.session_state.selected_item}")

    # =========================================================
    # SORT + BOTTOM pagination (no auto scroll)
    # =========================================================
    st.selectbox(
        "Urutkan",
        ["Tanpa urutan", "Harga Terendah", "Harga Tertinggi", "Nama A-Z"],
        key="sort_option",
        index=["Tanpa urutan", "Harga Terendah", "Harga Tertinggi", "Nama A-Z"].index(st.session_state.sort_option),
        on_change=reset_page,
        help="Pilih cara mengurutkan katalog."
    )

    col_prev_b, col_info_b, col_next_b = st.columns([1, 2, 1])
    with col_prev_b:
        if st.button("⟵ Prev", key="prev_bottom", disabled=(st.session_state.page <= 1)):
            st.session_state.page -= 1
            st.rerun()
    with col_info_b:
        st.markdown(
            f"<div style='text-align:center'>Halaman {st.session_state.page} dari {total_pages} · {total_items} item</div>",
            unsafe_allow_html=True
        )
    with col_next_b:
        if st.button("Next ⟶", key="next_bottom", disabled=(st.session_state.page >= total_pages)):
            st.session_state.page += 1
            st.rerun()

    # =========================================================
    # PRICE + DISCOUNT  (anchor is HERE, right above the section)
    # =========================================================
    st.markdown('<div id="price-section"></div>', unsafe_allow_html=True)

    if not st.session_state.selected_item:
        st.session_state.selected_item = page_df.iloc[0]["ItemName"]

    sel_row = df[df["ItemName"] == st.session_state.selected_item].iloc[0]
    selected_item = sel_row["ItemName"]
    price = float(sel_row["Price"])

    st.write("---")
    st.subheader("Detail Harga")
    st.caption("Item yang dipilih akan muncul di sini. Kamu bisa ganti pilihan dari katalog di atas.")
    st.write(f"**Item:** {selected_item}")
    st.markdown(f'<div class="price">Harga: Rp {price:,.0f}</div>', unsafe_allow_html=True)

    discount = st.selectbox("Dapet Discount Berapa % di Live?", [20, 25, 30, 35, 39.9999999])
    final_price = price * (1 - discount / 100)
    st.markdown(
        f'<div class="price">Harga Final Setelah {discount}% Discount: Rp {final_price:,.0f}</div><br/>',
        unsafe_allow_html=True
    )

    # ---- Smooth scroll to price (run AFTER the section exists) ----
    if st.session_state.get("jump_to_price"):
        nonce = st.session_state.get("scroll_seq", 0)
        components.html(
            f"""
            <script>
            (function() {{
              try {{
                const el = window.parent.document.getElementById("price-section");
                if (!el) return;
                el.scrollIntoView({{behavior:"auto", block:"start"}});
                setTimeout(() => el.scrollIntoView({{behavior:"smooth", block:"start"}}), 50);
                // nonce to force rerender: {nonce}
              }} catch(e) {{}}
            }})();
            </script>
            """,
            height=0
        )
        st.session_state.jump_to_price = False

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

# Footer
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
