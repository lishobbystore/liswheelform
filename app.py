import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
import json

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
        background-color: #f0f6ff;  /* same light blue as form box */
        color: #222;
        padding: 10px;
        font-size: 12px;
        border-top: 1px solid #cce0ff;
    }
    </style>
    """,
    unsafe_allow_html=True
)

with st.container():
    st.image("banner.jpg", use_container_width=True)
    st.title(" Lis Live Discount Form")
    st.markdown(f'<div>Udah gacha di live? Saatnya kamu kunci diskonnya — isi ini semua and we’ll handle the rest!</div><br/>', unsafe_allow_html=True)

    name = st.text_input("Nama Kamu")
    wa_number = st.text_input("Nomor WhatsApp", placeholder = "0891234567788")
    address = st.text_area(
        "Alamat Lengkap", 
        placeholder="Contoh: Jl. Medan Merdeka Utara No. 3, Kel. Gambir, Kec. Gambir, Kota Jakarta Pusat, DKI Jakarta 10110"
    )
    
    st.caption("Harap isi lengkap: nama jalan, kelurahan, kecamatan, kota/kabupaten, provinsi, dan kode pos.")

    item_names = df["ItemName"].tolist()
    
    st.caption("Tips: Kamu bisa mulai mengetik untuk mencari item lebih cepat.")
    selected_item = st.selectbox("Pilih Item", item_names)

    price = float(df.loc[df["ItemName"] == selected_item, "Price"].values[0])
    
    st.markdown(f'<div class="price">Harga: Rp {price:,.0f}</div>', unsafe_allow_html=True)

    discount = st.selectbox("Dapet Discount Berapa % di Live?", [10, 15, 20, 25, 30, 35, 50])
    final_price = price * (1 - discount / 100)
    
    st.markdown(f'<div class="price">Harga Final Setelah {discount}% Discount: Rp {final_price:,.0f}</div><br/>', unsafe_allow_html=True)

    if st.button("Submit Order"):
        if not name.strip() or not wa_number.strip() or not address.strip():
            st.error("Tolong isi Nama Kamu, Nomor WhatsApp, dan Alamat Lengkap.")
        elif not wa_number.strip().isdigit():
            st.error("Nomor WhatsApp harus berupa angka saja (tanpa spasi atau simbol).")
        else:
            tz = pytz.timezone("Asia/Jakarta")
            current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

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
