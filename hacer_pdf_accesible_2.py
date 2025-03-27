import os
from pypdf import PdfReader, PdfWriter

# Rutas del PDF original y el accesible
original_pdf = "carta.pdf"
temp_pdf = "temp.pdf"

# Abrir el PDF
reader = PdfReader(original_pdf)
writer = PdfWriter()

# 1️⃣ Copiar todas las páginas
for page in reader.pages:
    writer.add_page(page)

# 2️⃣ Agregar metadatos accesibles
writer.add_metadata({
    "/Title": "Documento Accesible",
    "/Author": "Hotusa",
    "/Subject": "Optimizado para accesibilidad",
    "/Keywords": "PDF, Accesibilidad, Lector de pantalla",
    "/Lang": "es-ES",  # Idioma en español
})

# 3️⃣ Guardar en un archivo temporal
with open(temp_pdf, "wb") as f:
    writer.write(f)

# 4️⃣ Reemplazar el original
os.replace(temp_pdf, original_pdf)  # 🔥 Sobrescribe el original

print(f"✅ PDF accesible guardado en '{original_pdf}'")
