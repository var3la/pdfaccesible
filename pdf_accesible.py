import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
import os


def extract_and_make_accessible(input_pdf_path, output_pdf_path):
    """
    Extrae texto e imágenes del PDF original y genera un PDF accesible.
    """
    try:
        # Leer el PDF original con PyMuPDF
        doc = fitz.open(input_pdf_path)
        num_pages = len(doc)

        # Crear un nuevo PDF accesible con ReportLab
        c = canvas.Canvas(output_pdf_path, pagesize=letter)
        width, height = letter

        for page_num in range(num_pages):
            page = doc.load_page(page_num)  # Cargar página
            text_blocks = page.get_text("blocks")  # Obtener bloques de texto
            images = page.get_images(full=True)  # Obtener imágenes

            # Procesar bloques de texto
            for block in text_blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                if block_type == 0:  # Solo procesar bloques de texto
                    c.drawString(x0 * inch, height - y0 * inch, text.strip())

            # Procesar imágenes
            for img_index, img in enumerate(images):
                xref = img[0]  # Referencia de la imagen
                base_image = doc.extract_image(xref)
                image_data = base_image["image"]
                ext = base_image["ext"]  # Extensión de la imagen (png, jpg, etc.)

                # Guardar la imagen temporalmente
                temp_image_path = f"temp_image_{img_index}.{ext}"
                with open(temp_image_path, "wb") as img_file:
                    img_file.write(image_data)

                # Obtener posición de la imagen
                bbox = page.get_image_rects(xref)[0]
                x0, y0, x1, y1 = bbox

                # Añadir la imagen al PDF accesible
                img_width = (x1 - x0) * inch
                img_height = (y1 - y0) * inch
                c.drawImage(temp_image_path, x0 * inch, height - y1 * inch, width=img_width, height=img_height)

                # Eliminar la imagen temporal
                os.remove(temp_image_path)

            # Finalizar la página
            c.showPage()

        # Guardar el PDF accesible
        c.save()
        print(f"PDF accesible generado: {output_pdf_path}")

    except Exception as e:
        print(f"Error al procesar el PDF '{input_pdf_path}': {e}")


def process_pdf_list(pdf_list, output_folder):
    """
    Procesa una lista de PDFs y genera versiones accesibles en la carpeta de salida.
    :param pdf_list: Lista de rutas de los PDFs originales.
    :param output_folder: Carpeta donde se guardarán los PDFs accesibles.
    """
    # Crear la carpeta de salida si no existe
    os.makedirs(output_folder, exist_ok=True)

    for pdf_path in pdf_list:
        if not os.path.exists(pdf_path):
            print(f"El archivo '{pdf_path}' no existe. Saltando...")
            continue

        pdf_filename = os.path.basename(pdf_path)
        output_pdf_path = os.path.join(output_folder, f"accesible_{pdf_filename}")
        extract_and_make_accessible(pdf_path, output_pdf_path)

# Ejemplo de uso
pdf_list = [
    "./pdfs/carta.pdf",
    "./pdfs/399.pdf",
    "./pdfs/205.pdf"
]
output_folder = "./acc"
process_pdf_list(pdf_list, output_folder)