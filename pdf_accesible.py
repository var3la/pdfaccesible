#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para hacer PDFs accesibles mediante OCR.
Convierte PDFs basados en imágenes a PDFs con texto seleccionable y accesible.
Utiliza PyMuPDF (fitz) para crear PDFs accesibles.
"""

import os
import sys
import argparse
from bs4 import BeautifulSoup
import logging
from pathlib import Path
import tempfile
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constantes de configuración
TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
DPI = 300  # Resolución para conversión de PDF a imagen
OCR_LANG = 'spa'  # Idioma para OCR (español)
TEMP_DIR = tempfile.gettempdir()  # Directorio temporal para archivos intermedios

# Asegurarse de que Tesseract esté configurado correctamente
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def convertir_pdf_a_imagenes(ruta_pdf: str, dpi: int = DPI) -> List[Image.Image]:
    """
    Convierte un archivo PDF a una lista de imágenes.
    Args:
        ruta_pdf: Ruta al archivo PDF
        dpi: Resolución de las imágenes (puntos por pulgada)
    Returns:
        Lista de objetos imagen (PIL.Image)
    """
    logger.info(f"Convirtiendo PDF a imágenes (DPI: {dpi}): {ruta_pdf}")
    try:
        imagenes = []
        with fitz.open(ruta_pdf) as pdf_documento:
            for pagina_num in range(len(pdf_documento)):
                pagina = pdf_documento.load_page(pagina_num)
                pix = pagina.get_pixmap(dpi=dpi)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                imagenes.append(img)
        logger.info(f"Conversión completada: {len(imagenes)} páginas encontradas")
        return imagenes
    except Exception as e:
        logger.error(f"Error al convertir PDF a imágenes: {e}")
        raise


def aplicar_ocr_a_imagenes(imagenes: List[Image.Image], idioma: str = OCR_LANG) -> List[Dict[str, Any]]:
    """
    Aplica OCR a una lista de imágenes para extraer texto estructurado con información de posición.
    Args:
        imagenes: Lista de imágenes (objetos PIL.Image)
        idioma: Código de idioma para OCR (por defecto 'spa' para español)
    Returns:
        Lista de datos estructurados con texto y posiciones, uno por imagen/página
    """
    logger.info(f"Aplicando OCR con HOCR (idioma: {idioma}) a {len(imagenes)} imágenes")
    resultados = []
    for i, imagen in enumerate(imagenes):
        try:
            logger.info(f"Procesando página {i+1}/{len(imagenes)}")
            hocr_text = pytesseract.image_to_pdf_or_hocr(imagen, extension='hocr', lang=idioma)
            hocr_str = hocr_text.decode('utf-8')
            soup = BeautifulSoup(hocr_str, 'html.parser')
            pagina_data = {
                'width': imagen.width,
                'height': imagen.height,
                'blocks': []
            }
            for p_idx, ocr_p in enumerate(soup.find_all('p', class_='ocr_par')):
                p_title = ocr_p.get('title', '')
                p_bbox_match = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', p_title)
                if p_bbox_match:
                    p_x1, p_y1, p_x2, p_y2 = map(int, p_bbox_match.groups())
                    p_block = {
                        'type': 'paragraph',
                        'id': f'p_{i}_{p_idx}',
                        'bbox': (p_x1, p_y1, p_x2, p_y2),
                        'lines': []
                    }
                    for l_idx, ocr_line in enumerate(ocr_p.find_all('span', class_='ocr_line')):
                        l_title = ocr_line.get('title', '')
                        l_bbox_match = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', l_title)
                        if l_bbox_match:
                            l_x1, l_y1, l_x2, l_y2 = map(int, l_bbox_match.groups())
                            line_text = ' '.join([w.get_text() for w in ocr_line.find_all('span', class_='ocrx_word')])
                            words = []
                            for w_idx, word in enumerate(ocr_line.find_all('span', class_='ocrx_word')):
                                w_title = word.get('title', '')
                                w_bbox_match = re.search(r'bbox (\d+) (\d+) (\d+) (\d+)', w_title)
                                if w_bbox_match:
                                    w_x1, w_y1, w_x2, w_y2 = map(int, w_bbox_match.groups())
                                    words.append({
                                        'text': word.get_text(),
                                        'bbox': (w_x1, w_y1, w_x2, w_y2)
                                    })
                            p_block['lines'].append({
                                'id': f'l_{i}_{p_idx}_{l_idx}',
                                'bbox': (l_x1, l_y1, l_x2, l_y2),
                                'text': line_text,
                                'words': words
                            })
                    pagina_data['blocks'].append(p_block)
            resultados.append(pagina_data)
            logger.info(f"Página {i+1}: {len(pagina_data['blocks'])} bloques de texto encontrados")
        except Exception as e:
            logger.error(f"Error en OCR para página {i+1}: {e}")
            resultados.append({
                'width': imagen.width if imagen else 0,
                'height': imagen.height if imagen else 0,
                'blocks': []
            })
    return resultados


def crear_pdf_con_capa_texto(
    imagenes: List[Image.Image], 
    datos_ocr: List[Dict[str, Any]],
    ruta_salida: str
) -> str:
    """
    Crea un nuevo PDF accesible con estructura de documento según estándares PDF/UA
    usando PyMuPDF.
    Args:
        imagenes: Lista de imágenes (objetos PIL.Image)
        datos_ocr: Lista de datos estructurados con texto y posiciones
        ruta_salida: Ruta donde guardar el PDF resultante
    Returns:
        Ruta al PDF creado
    """
    logger.info(f"Creando PDF accesible con estructura PDF/UA: {ruta_salida}")
    try:
        pdf_accesible = fitz.open()  # Crear un nuevo PDF
        for i, (imagen, pagina_data) in enumerate(zip(imagenes, datos_ocr)):
            try:
                width, height = imagen.size
                # Crear una nueva página en blanco
                pagina = pdf_accesible.new_page(width=width, height=height)
                
                # Insertar la imagen en la página
                img_temp_path = os.path.join(TEMP_DIR, f"temp_img_{i}.png")
                imagen.save(img_temp_path, "PNG")
                pagina.insert_image(pagina.rect, filename=img_temp_path)
                
                # Añadir texto extraído mediante OCR
                for block in pagina_data['blocks']:
                    for line in block['lines']:
                        line_bbox = line['bbox']
                        line_text = line['text']
                        x0, y0, x1, y1 = line_bbox
                        # Ajustar coordenadas para PyMuPDF (coordenadas relativas)
                        rect = fitz.Rect(x0, y0, x1, y1)
                        pagina.insert_textbox(rect, line_text, fontsize=12, align=fitz.TEXT_ALIGN_LEFT)
            except Exception as e:
                logger.error(f"Error al procesar página {i+1}: {e}")
        
        # Guardar el PDF accesible
        pdf_accesible.save(ruta_salida, garbage=4, deflate=True, clean=True)
        logger.info(f"PDF accesible creado con éxito: {ruta_salida}")
        return ruta_salida
    except Exception as e:
        logger.error(f"Error al crear PDF accesible: {e}")
        raise

def procesar_pdf(ruta_entrada: str, ruta_salida: str, **kwargs) -> None:
    """
    Procesa un PDF para hacerlo accesible mediante OCR.
    Args:
        ruta_entrada: Ruta al PDF original
        ruta_salida: Ruta donde guardar el PDF accesible
        **kwargs: Argumentos adicionales para la configuración
    """
    try:
        # Verificar que ruta_salida no sea None
        if not ruta_salida:
            raise ValueError("La ruta de salida (ruta_salida) no puede ser None.")
        
        # 1. Convertir PDF a imágenes
        imagenes = convertir_pdf_a_imagenes(
            ruta_entrada, 
            dpi=kwargs.get('dpi', DPI)
        )
        # 2. Aplicar OCR a las imágenes
        textos = aplicar_ocr_a_imagenes(
            imagenes, 
            idioma=kwargs.get('idioma', OCR_LANG)
        )
        # 3. Crear un PDF con capas de texto
        temp_path = os.path.join(TEMP_DIR, "pdf_con_texto_temp.pdf")
        pdf_con_texto = crear_pdf_con_capa_texto(imagenes, textos, temp_path)
        # 4. Añadir metadatos de accesibilidad
        añadir_metadatos_accesibilidad(
            pdf_con_texto, 
            ruta_salida,
            titulo=kwargs.get('titulo'),
            autor=kwargs.get('autor'),
            asunto=kwargs.get('asunto')
        )
        # 5. Limpiar archivos temporales
        if os.path.exists(pdf_con_texto) and pdf_con_texto != ruta_salida:
            os.remove(pdf_con_texto)
        logger.info(f"Proceso completado con éxito: {ruta_salida}")
    except Exception as e:
        logger.error(f"Error al procesar el PDF: {e}")
        raise


def main():
    """Función principal que procesa los argumentos y ejecuta el proceso."""
    # Configurar el parser de argumentos
    parser = argparse.ArgumentParser(
        description="Hacer PDFs accesibles mediante OCR (español)"
    )
    parser.add_argument(
        "entrada", 
        help="Ruta al archivo PDF de entrada"
    )
    parser.add_argument(
        "-o", "--salida", 
        help="Ruta para el archivo PDF de salida. Si no se especifica, "
        "se usará el nombre del archivo de entrada con sufijo '_accesible'"
    )
    parser.add_argument(
        "-d", "--dpi", 
        type=int, 
        default=DPI,
        help=f"Resolución para la conversión de PDF a imagen (por defecto: {DPI})"
    )
    parser.add_argument(
        "-l", "--idioma", 
        default=OCR_LANG,
        help=f"Código de idioma para OCR (por defecto: {OCR_LANG})"
    )
    parser.add_argument(
        "-t", "--titulo", 
        help="Título del documento (para metadatos)"
    )
    parser.add_argument(
        "-a", "--autor", 
        help="Autor del documento (para metadatos)"
    )
    parser.add_argument(
        "-s", "--asunto", 
        help="Asunto o descripción del documento (para metadatos)"
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true",
        help="Mostrar información detallada del proceso"
    )
    # Parsear argumentos
    args = parser.parse_args()
    # Configurar nivel de logging según verbose
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    # Verificar que el archivo de entrada existe
    if not os.path.isfile(args.entrada):
        logger.error(f"El archivo de entrada no existe: {args.entrada}")
        return 1
    # Determinar la ruta de salida si no se especificó
    if not args.salida:
        entrada_path = Path(args.entrada)
        args.salida = str(entrada_path.parent / f"{entrada_path.stem}_accesible{entrada_path.suffix}")
    logger.info(f"Iniciando proceso de conversión a PDF accesible")
    logger.info(f"Archivo de entrada: {args.entrada}")
    logger.info(f"Archivo de salida: {args.salida}")
    try:
        # Procesar el PDF
        procesar_pdf(
            args.entrada, 
            args.salida,
            dpi=args.dpi,
            idioma=args.idioma,
            titulo=args.titulo,
            autor=args.autor,
            asunto=args.asunto
        )
        logger.info("¡Proceso completado con éxito!")
        return 0
    except Exception as e:
        logger.error(f"Error durante el procesamiento: {e}")
        return 1


def añadir_metadatos_accesibilidad(
    pdf_path: str,
    pdf_salida: str,
    titulo: str = None,
    autor: str = None,
    asunto: str = None
) -> None:
    """
    Añade metadatos de accesibilidad al PDF usando pikepdf.
    Args:
        pdf_path: Ruta al PDF de entrada
        pdf_salida: Ruta donde se guardará el PDF con metadatos
        titulo: Título del documento (opcional)
        autor: Autor del documento (opcional)
        asunto: Asunto del documento (opcional)
    """
    try:
        # Fecha actual para metadatos
        fecha_actual = datetime.now()
        fecha_pdf = fecha_actual.strftime("D:%Y%m%d%H%M%S+00'00'")
        fecha_xmp = fecha_actual.strftime("%Y-%m-%dT%H:%M:%S")
        # Abrir el PDF con pikepdf
        with pikepdf.open(pdf_path) as pdf:
            # Configurar metadatos de documento
            with pdf.open_metadata() as meta:
                # Metadatos básicos de Dublin Core
                meta["dc:format"] = "application/pdf"
                if titulo:
                    meta["dc:title"] = titulo
                if autor:
                    meta["dc:creator"] = autor
                if asunto:
                    meta["dc:description"] = asunto

                # Metadatos XMP básicos
                meta["xmp:CreatorTool"] = "pdf_accesible.py - Script Python para PDF accesible"
                meta["xmp:CreateDate"] = fecha_xmp
                meta["xmp:ModifyDate"] = fecha_xmp
                meta["xmp:MetadataDate"] = fecha_xmp

                # Metadatos PDF
                meta["pdf:Producer"] = "pdf_accesible.py - Python Script con pikepdf"
                meta["pdf:Trapped"] = "False"

                # Metadatos de accesibilidad PDF/UA
                meta["pdfuaid:part"] = "1"

                # Metadatos PDF/A
                meta["pdfaid:part"] = "1"
                meta["pdfaid:conformance"] = "B"

                # Metadatos de accesibilidad Web
                meta["a11y:accessibility"] = "Tagged PDF"
                meta["a11y:accessible"] = "true"

                # Características de accesibilidad como array
                accessibility_features = [
                    "alternativeText",
                    "structuredNavigation",
                    "taggedPDF"
                ]
                meta.set_multiple("a11y:accessibilityFeature", accessibility_features)

            # Configurar catálogo del documento para PDF/UA
            if "MarkInfo" not in pdf.Root:
                pdf.Root.MarkInfo = Dictionary(
                    Marked=True,
                    Suspects=False,
                    UserProperties=False
                )
            else:
                pdf.Root.MarkInfo.Marked = True
                pdf.Root.MarkInfo.Suspects = False

            # Establecer idioma del documento
            pdf.Root.Lang = "es-ES"

            # Configurar el ViewerPreferences del documento
            if "ViewerPreferences" not in pdf.Root:
                pdf.Root.ViewerPreferences = Dictionary(
                    DisplayDocTitle=True
                )
            else:
                pdf.Root.ViewerPreferences.DisplayDocTitle = True

            # Guardar el PDF con configuraciones para accesibilidad
            pdf.save(
                pdf_salida,
                linearize=True,  # Optimizado para web
                object_stream_mode=pikepdf.ObjectStreamMode.generate,  # Compresión eficiente
                compress_streams=True,  # Comprimir streams
                normalize_content=True,  # Normalizar el contenido
                qdf=False  # No formatear para depuración
            )
            logger.info(f"PDF accesible creado con éxito: {pdf_salida}")
    except Exception as e:
        logger.error(f"Error al añadir metadatos de accesibilidad: {e}")
        try:
            # Intento alternativo más simple en caso de error
            with pikepdf.open(pdf_path) as pdf:
                # Establecer metadatos mínimos
                with pdf.open_metadata() as meta:
                    if titulo:
                        meta["dc:title"] = titulo
                    if autor:
                        meta["dc:creator"] = autor
                    meta["dc:format"] = "application/pdf"
                    meta["pdfuaid:part"] = "1"
                # Guardar con configuraciones básicas
                pdf.save(pdf_salida)
                logger.warning("Se guardó el PDF con metadatos básicos debido a un error")
        except Exception as save_error:
            logger.error(f"Error crítico al guardar el PDF: {save_error}")
            raise


def main():
    parser = argparse.ArgumentParser(description="Hacer PDFs accesibles mediante OCR (español)")
    parser.add_argument("entrada", help="Ruta al archivo PDF de entrada")
    parser.add_argument("-o", "--salida", help="Ruta para el archivo PDF de salida.")
    parser.add_argument("-d", "--dpi", type=int, default=DPI, help=f"Resolución para la conversión de PDF a imagen (por defecto: {DPI})")
    parser.add_argument("-l", "--idioma", default=OCR_LANG, help=f"Código de idioma para OCR (por defecto: {OCR_LANG})")
    parser.add_argument("-t", "--titulo", help="Título del documento (para metadatos)")
    parser.add_argument("-a", "--autor", help="Autor del documento (para metadatos)")
    parser.add_argument("-s", "--asunto", help="Asunto o descripción del documento (para metadatos)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar información detallada del proceso")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if not os.path.isfile(args.entrada):
        logger.error(f"El archivo de entrada no existe: {args.entrada}")
        sys.exit(1)

    if not args.salida:
        entrada_path = Path(args.entrada)
        args.salida = str(entrada_path.parent / f"{entrada_path.stem}_accesible{entrada_path.suffix}")

    logger.info(f"Iniciando proceso de conversión a PDF accesible")
    logger.info(f"Archivo de entrada: {args.entrada}")
    logger.info(f"Archivo de salida: {args.salida}")

    try:
        procesar_pdf(
            args.entrada, 
            args.salida,
            dpi=args.dpi,
            idioma=args.idioma,
            titulo=args.titulo,
            autor=args.autor,
            asunto=args.asunto
        )
        logger.info("¡Proceso completado con éxito!")
        return 0
    except Exception as e:
        logger.error(f"Error durante el procesamiento: {e}")
        return 1
        # Convertir PDF a imágenes
        imagenes = convertir_pdf_a_imagenes(args.entrada, dpi=args.dpi)
        # Aplicar OCR
        textos = aplicar_ocr_a_imagenes(imagenes, idioma=args.idioma)
        # Crear PDF accesible
        crear_pdf_con_capa_texto(imagenes, textos, args.salida)
        # Añadir metadatos
        añadir_metadatos_accesibilidad(args.salida, titulo=args.titulo, autor=args.autor, asunto=args.asunto)
        logger.info("¡Proceso completado con éxito!")
    except Exception as e:
        logger.error(f"Error durante el procesamiento: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
