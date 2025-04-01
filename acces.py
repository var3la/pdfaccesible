from borb.pdf.document.document import Document
from borb.pdf.pdf import PDF
from borb.pdf.canvas.layout.image.image import Image as BImage
from borb.pdf.canvas.layout.page_layout.multi_column_layout import SingleColumnLayout
from borb.pdf.canvas.layout.page_layout.page_layout import PageLayout
from borb.pdf.page.page import Page
from borb.pdf.canvas.layout.text.paragraph import Paragraph
import typing


def add_alt_tags_to_pdf(input_pdf_path: str, output_pdf_path: str):
    """
    Añade etiquetas alt a las imágenes del PDF usando borb.
    """
    try:
        # Leer el PDF original
        with open(input_pdf_path, "rb") as pdf_file:
            doc: typing.Optional[Document] = PDF.loads(pdf_file)

        if doc is None:
            print(f"No se pudo leer el PDF: {input_pdf_path}")
            return

        # Crear un nuevo PDF accesible
        new_doc: Document = Document()

        # Iterar sobre las páginas del PDF original
        for page_num, page in enumerate(doc.get("XRef").get("Trailer").get("Root").get("Pages").get("Kids"), start=1):
            new_page = Page()
            new_doc.add_page(new_page)

            layout: PageLayout = SingleColumnLayout(new_page)

            # Extraer contenido de la página original
            for element in page:
                if isinstance(element, BImage):
                    # Añadir etiqueta alt a la imagen
                    alt_text = f"Descripción de la imagen en la página {page_num}."
                    element.set_alt_text(alt_text)
                    layout.add(element)
                elif isinstance(element, Paragraph):
                    # Añadir texto
                    layout.add(element)

        # Guardar el PDF accesible
        with open(output_pdf_path, "wb") as pdf_file:
            PDF.dumps(pdf_file, new_doc)

        print(f"PDF accesible generado: {output_pdf_path}")

    except Exception as e:
        print(f"Error al procesar el PDF '{input_pdf_path}': {e}")



# Ejemplo de uso
input_pdf = "./pdfs/399.pdf"
output_pdf = "./acc/399as.pdf"
add_alt_tags_to_pdf(input_pdf, output_pdf)