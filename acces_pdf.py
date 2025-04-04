import os
import fitz  # PyMuPDF
import time
import logging
from tqdm import tqdm
import tempfile
import subprocess
import sys
import shutil
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='pdf_scanned_accessibility.log'
)

def setup_directories(input_dir, output_dir, temp_dir):
    """Verifica y crea los directorios necesarios."""
    for directory in [input_dir, output_dir, temp_dir]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logging.info(f"Directorio creado: {directory}")

def check_tesseract_installed():
    """Comprueba si Tesseract OCR está instalado."""
    try:
        subprocess.run(["tesseract", "--version"], 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE, 
                       check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def apply_ocr_to_page(page, language="spa", dpi=300):
    """Aplica OCR a una página y devuelve el texto reconocido."""
    try:
        # Renderizar la página como imagen con mayor resolución para mejor OCR
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img_path = tempfile.mktemp(suffix='.png')
        pix.save(img_path)
        
        # Aplicar OCR con Tesseract con configuración mejorada
        output_base = tempfile.mktemp()
        subprocess.run([
            "tesseract",
            img_path,
            output_base,
            "-l", language,
            "--psm", "1",  # Modo de segmentación de página automático
            "--oem", "3",  # Motor de OCR: LSTM neural net
            "-c", "preserve_interword_spaces=1",
            "-c", "textord_min_linesize=2.5"
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Leer el texto resultante
        text_file = f"{output_base}.txt"
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Limpiar archivos temporales
        os.unlink(img_path)
        os.unlink(text_file)
        
        logging.debug(f"OCR completado. Cantidad de texto detectado: {len(text)} caracteres")
        return text
    except Exception as e:
        logging.error(f"Error en OCR: {str(e)}")
        return ""

def create_structure_tree(doc, page, text):
    """Crea un árbol de estructura completo para el PDF."""
    try:
        # Verificar si el documento soporta etiquetado estructural
        if not hasattr(doc, "is_tagged") or not doc.is_tagged:
            # Inicializar estructura si es posible
            if hasattr(doc, "init_doc_structure"):
                try:
                    doc.init_doc_structure()
                except Exception as e:
                    logging.warning(f"Error inicializando estructura: {str(e)}")
                    return False
            else:
                logging.warning("Versión de PyMuPDF no soporta etiquetado estructural completo")
                return False
        
        # Si no hay métodos para crear estructura, abandonar
        if not hasattr(doc, "add_struct_element") or not hasattr(doc, "append_struct_element"):
            logging.warning("La versión de PyMuPDF no tiene los métodos necesarios para etiquetado estructural")
            return False

        # Intentar crear estructura jerárquica completa
        try:
            # Verificar si ya existe un nodo raíz Document
            root_node = None
            
            # Comprobar si hay un nodo raíz
            try:
                if hasattr(doc, "get_struct_tree_root"):
                    root_info = doc.get_struct_tree_root()
                    if root_info:
                        # Ya existe un nodo raíz
                        root_node = 0  # Convención para nodo raíz
            except Exception as e:
                logging.debug(f"Error al verificar nodo raíz: {str(e)}")
            
            # Crear nodo raíz si no existe
            if root_node is None and hasattr(doc, "add_struct_element"):
                try:
                    root_node = doc.add_struct_element("Document", parent=-1)
                except Exception as e:
                    logging.warning(f"Error al crear nodo Document: {str(e)}")
                    root_node = -1  # Usar nodo predeterminado
            
            # Crear un nodo Div para contener el contenido de la página
            div_node = None
            try:
                if hasattr(doc, "add_struct_element") and root_node is not None:
                    div_node = doc.add_struct_element("Div", parent=root_node, page=page)
            except Exception as e:
                logging.warning(f"Error al crear nodo Div: {str(e)}")
                div_node = root_node if root_node is not None else -1
                
            # Procesar el texto para identificar estructura
            paragraphs = []
            
            # Intentar identificar párrafos con diferentes patrones
            if '\n\n' in text:
                paragraphs = [p for p in text.split('\n\n') if p.strip()]
            elif '\n' in text:
                # Si no hay párrafos claros, usar líneas como párrafos
                paragraphs = [p for p in text.split('\n') if p.strip()]
            else:
                # Si no hay separadores, tratar todo como un párrafo
                paragraphs = [text] if text.strip() else []
            
            # Para cada párrafo, crear un nodo P
            for i, para in enumerate(paragraphs):
                if not para.strip():
                    continue
                    
                try:
                    # Crear elemento de párrafo
                    parent = div_node if div_node is not None else -1
                    p_node = doc.add_struct_element("P", parent=parent, page=page)
                    
                    # Calcular posición aproximada para este párrafo
                    total_paragraphs = max(len(paragraphs), 1)
                    top = (i * page.rect.height) / total_paragraphs
                    height = page.rect.height / total_paragraphs
                    p_rect = fitz.Rect(0, top, page.rect.width, top + height)
                    
                    # Añadir contenido al nodo
                    doc.append_struct_element(p_node, 0, p_rect, para)
                    
                    logging.debug(f"Párrafo {i+1} etiquetado correctamente")
                except Exception as e:
                    logging.warning(f"Error al etiquetar párrafo {i+1}: {str(e)}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error al crear estructura jerárquica: {str(e)}")
            
            # Plan B: Intentar un enfoque más simple si el jerárquico falla
            try:
                # Añadir todas las líneas de texto como elementos etiquetados directamente
                lines = [line for line in text.split('\n') if line.strip()]
                
                # Si hay texto, pero no se identifica como líneas, tratar como un solo párrafo
                if text.strip() and not lines:
                    lines = [text.strip()]
                
                # Altura aproximada para cada línea de texto
                line_height = page.rect.height / max(len(lines), 1)
                
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                        
                    try:
                        # Crear elemento de párrafo
                        p_node = doc.add_struct_element("P", parent=-1, page=page)
                        
                        # Calcular una posición aproximada para esta línea de texto
                        y_pos = i * line_height
                        text_rect = fitz.Rect(0, y_pos, page.rect.width, y_pos + line_height)
                        
                        # Añadir contenido al párrafo
                        doc.append_struct_element(p_node, 0, text_rect, line)
                    except Exception as e:
                        logging.warning(f"Error al etiquetar línea de texto: {str(e)}")
                
                return True
            except Exception as e:
                logging.error(f"Error en plan B de etiquetado: {str(e)}")
                return False
    except Exception as e:
        logging.error(f"Error general creando estructura: {str(e)}")
        return False

def optimize_pdf(doc, compress_level=1):
    """Optimiza el PDF para reducir tamaño."""
    try:
        # Eliminar objetos no utilizados si existe el método
        if hasattr(doc, "garbage_collect"):
            doc.garbage_collect()
        
        # Optimizar streams si existe el método
        if hasattr(doc, "clean_contents"):
            for page in doc:
                try:
                    page.clean_contents()
                except:
                    pass
        
        # Configuración de compresión
        params = {
            "deflate": True,         # Comprimir streams
            "garbage": 4,            # Máxima recolección de basura
            "clean": True,           # Limpiar el documento
            "linear": True,          # Optimización para web
            "ascii": False           # Permitir binario para mejor compresión
        }
        
        # Ajustar nivel de compresión si la versión lo soporta
        if compress_level > 0:
            try:
                # Verificamos si la versión soporta el parámetro 'compress'
                import inspect
                sig = inspect.signature(doc.save)
                if 'compress' in sig.parameters:
                    params["compress"] = compress_level
            except:
                pass
        
        return params
    except Exception as e:
        logging.error(f"Error optimizando PDF: {str(e)}")
        return {}

def process_scanned_pdf(input_path, output_path, config):
    """Procesa un PDF escaneado para hacerlo accesible."""
    try:
        # Abrir el documento
        doc = fitz.open(input_path)
        
        # Establecer metadatos de accesibilidad
        doc.set_metadata({
            "title": os.path.basename(input_path).replace(".pdf", ""),
            "subject": "Documento accesible",
            "keywords": "accesibilidad, PDF, escaneado",
            "creator": "Script de Accesibilidad para PDFs Escaneados",
            "producer": "PyMuPDF con etiquetado estructural"
        })
        
        # Establecer el idioma del documento y etiquetado
        try:
            doc.set_xml_metadata(f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
            <x:xmpmeta xmlns:x="adobe:ns:meta/">
            <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" dc:language="{config['language']}"/>
            <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
                <pdf:Tagged>true</pdf:Tagged>
            </rdf:Description>
            </rdf:RDF>
            </x:xmpmeta>
            <?xpacket end="w"?>""")
        except Exception as e:
            logging.warning(f"No se pudo establecer metadatos XML: {str(e)}")
        
        # Intento seguro de habilitar etiquetado del PDF
        try:
            if hasattr(doc, "init_doc_structure"):
                doc.init_doc_structure()
        except Exception as e:
            logging.warning(f"No se pudo inicializar la estructura del documento: {str(e)}")
        
        # Determinar si el PDF parece ser escaneado
        is_scanned = True
        text_length = 0
        
        for page in doc:
            page_text = page.get_text().strip()
            text_length += len(page_text)
            if len(page_text) > 50:  # Si hay texto sustancial, no es solo escaneado
                is_scanned = False
                break
        
        logging.debug(f"Documento '{input_path}': es_escaneado={is_scanned}, longitud_texto={text_length}")
        
        if is_scanned:
            logging.info(f"El documento '{input_path}' parece ser un PDF escaneado. Aplicando OCR.")
            
            # Crear un nuevo documento para el resultado
            new_doc = fitz.open()
            
            # Procesar cada página
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Aplicar OCR
                text = apply_ocr_to_page(page, language=config['language'], dpi=config['dpi'])
                
                # Crear nueva página con la imagen original
                pix = page.get_pixmap()
                new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(page.rect, pixmap=pix)
                
                # Añadir capa de texto invisible encima
                if text:
                    # Método seguro para añadir texto
                    try:
                        text_rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
                        new_page.insert_textbox(text_rect, text, fontname="helv", fontsize=12, color=(0,0,0,0))  # Color transparente
                    except AttributeError:
                        # Alternativa para versiones antiguas
                        text_rect = fitz.Rect(0, 0, page.rect.width, page.rect.height)
                        new_page.insert_text(text_rect.tl, text, fontname="helv", fontsize=12, color=(0,0,0,0))
                    
                    # Asegurar que el texto se ha insertado antes de crear la estructura
                    if hasattr(new_doc, "reload_page"):
                        new_doc.reload_page(new_page)
                    
                    # Intentar crear estructura etiquetada para la accesibilidad
                    success = create_structure_tree(new_doc, new_page, text)
                    if success:
                        logging.info(f"Estructura etiquetada creada para la página {page_num+1}")
                    
                    logging.info(f"Texto OCR añadido a la página {page_num+1}")
            
            # Optimización del PDF
            save_params = optimize_pdf(new_doc, config['compress_level'])
            
            # Guardar el nuevo documento
            new_doc.save(output_path, **save_params)
            new_doc.close()
        else:
            # Si no es escaneado, añadir etiquetas estructurales al documento original
            logging.info(f"El documento '{input_path}' parece tener texto. Añadiendo etiquetas estructurales.")
            
            # Intentar inicializar estructura etiquetada de forma segura
            try:
                if hasattr(doc, "is_tagged") and not doc.is_tagged and hasattr(doc, "init_doc_structure"):
                    doc.init_doc_structure()
            except Exception as e:
                logging.warning(f"No se pudo inicializar la estructura: {str(e)}")
            
            # Procesar cada página del documento original
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Extraer el texto existente
                text = page.get_text()
                
                # Intentar crear estructura etiquetada para la página original
                if text.strip():
                    success = create_structure_tree(doc, page, text)
                    if success:
                        logging.info(f"Estructura etiquetada creada para la página {page_num+1}")
                
                # Etiquetar imágenes con texto alternativo
                try:
                    image_list = page.get_images(full=True)
                    
                    for img_index, img in enumerate(image_list):
                        alt_text = f"Imagen {img_index+1}"
                        # Añadir imagen como figura etiquetada
                        try:
                            if hasattr(doc, "add_struct_element") and hasattr(doc, "set_struct_alt"):
                                # Obtener coordenadas de la imagen
                                xref = img[0]  # xref del objeto imagen
                                img_rect = None
                                
                                # Buscar la imagen en el contenido de la página
                                for item in page.get_drawings():
                                    if item.get("type") == "image" and item.get("xref") == xref:
                                        img_rect = item.get("rect")
                                        break
                                
                                if img_rect:
                                    # Añadir como figura etiquetada
                                    fig_node = doc.add_struct_element("Figure", parent=-1, page=page)
                                    doc.set_struct_alt(fig_node, alt_text)
                                    doc.append_struct_element(fig_node, 0, img_rect, "")
                                    logging.debug(f"Imagen {img_index+1} etiquetada en página {page_num+1}")
                        except Exception as e:
                            logging.warning(f"No se pudo etiquetar imagen: {str(e)}")
                except Exception as e:
                    logging.warning(f"Error al procesar imágenes: {str(e)}")
            
            # Optimización del PDF original
            save_params = optimize_pdf(doc, config['compress_level'])
            
            # Guardar el documento original con optimización
            doc.save(output_path, **save_params)
        
        doc.close()
        logging.info(f"Procesado completado: {input_path} -> {output_path}")
        
        # Verificación post-procesamiento
        try:
            # Abrir el documento generado para verificar etiquetado
            check_doc = fitz.open(output_path)
            is_tagged = False
            
            if hasattr(check_doc, "is_tagged"):
                is_tagged = check_doc.is_tagged
            
            # Intentar obtener información sobre el árbol de estructura
            struct_info = "No disponible"
            try:
                if hasattr(check_doc, "get_struct_tree_root"):
                    root_info = check_doc.get_struct_tree_root()
                    struct_info = "Disponible" if root_info else "No disponible"
            except:
                pass
            
            logging.info(f"Verificación del documento generado: Etiquetado={is_tagged}, Estructura={struct_info}")
            check_doc.close()
        except Exception as e:
            logging.warning(f"Error en verificación post-procesamiento: {str(e)}")
        
        return True
    
    except Exception as e:
        logging.error(f"Error procesando {input_path}: {str(e)}")
        return False

def process_single_pdf(args):
    """Función para procesar un solo PDF (usada para paralelización)."""
    input_path, output_path, config = args
    return process_scanned_pdf(input_path, output_path, config), input_path

def process_directory(input_dir, output_dir, temp_dir, config):
    """Procesa todos los PDFs en un directorio usando paralelización."""
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        logging.warning(f"No se encontraron PDFs en {input_dir}")
        return 0
    
    success_count = 0
    total_files = len(pdf_files)
    
    # Preparar argumentos para procesamiento en paralelo
    process_args = []
    for pdf_file in pdf_files:
        input_path = os.path.join(input_dir, pdf_file)
        output_path = os.path.join(output_dir, pdf_file)
        process_args.append((input_path, output_path, config))
    
    # Determinar el número óptimo de workers (dejando algunos núcleos libres)
    max_workers = max(1, multiprocessing.cpu_count() - 1)
    
    # Procesar archivos en paralelo con una barra de progreso
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_pdf, arg) for arg in process_args]
        
        with tqdm(total=total_files, desc="Procesando PDFs") as progress_bar:
            for future in as_completed(futures):
                try:
                    result, input_path = future.result()
                    if result:
                        success_count += 1
                    else:
                        logging.warning(f"Procesamiento fallido para: {input_path}")
                except Exception as e:
                    logging.error(f"Error en proceso paralelo: {str(e)}")
                progress_bar.update(1)
    
    return success_count

def post_process_pdf(input_path, output_path=None):
    """Intenta corregir problemas comunes de accesibilidad usando QPDF si está disponible."""
    if output_path is None:
        output_path = input_path
    
    try:
        # Verificar si QPDF está instalado
        subprocess.run(["qpdf", "--version"], 
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE, 
                     check=True)
        
        # Crear un archivo temporal para la salida
        temp_output = tempfile.mktemp(suffix='.pdf')
        
        # Ejecutar qpdf para linearizar y reparar el PDF
        subprocess.run([
            "qpdf", 
            "--linearize",
            "--object-streams=generate",
            "--compress-streams=y",
            "--recompress-flate",
            "--replace-input",
            input_path,
            temp_output
        ], check=True)
        
        # Reemplazar el archivo original con el procesado
        shutil.move(temp_output, output_path)
        logging.info(f"Post-procesamiento con QPDF completado: {output_path}")
        return True
    except FileNotFoundError:
        logging.info("QPDF no está instalado. Omitiendo post-procesamiento.")
        return False
    except subprocess.CalledProcessError as e:
        logging.warning(f"Error en post-procesamiento con QPDF: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Error general en post-procesamiento: {str(e)}")
        return False

def check_pymupdf_version():
    """Verifica la versión de PyMuPDF y sus capacidades."""
    try:
        version = fitz.version
        logging.info(f"Versión de PyMuPDF: {version}")
        
        # Verificar capacidades de etiquetado
        capabilities = []
        
        # Verificar métodos importantes para etiquetado
        sample_doc = fitz.open()
        sample_doc.new_page()
        
        if hasattr(sample_doc, "init_doc_structure"):
            capabilities.append("init_doc_structure")
        if hasattr(sample_doc, "set_xml_metadata"):
            capabilities.append("set_xml_metadata")
        if hasattr(sample_doc, "add_struct_element"):
            capabilities.append("add_struct_element")
        if hasattr(sample_doc, "is_tagged"):
            capabilities.append("is_tagged")
        
        sample_doc.close()
        
        if capabilities:
            logging.info(f"Capacidades de etiquetado disponibles: {', '.join(capabilities)}")
        else:
            logging.warning("No se detectaron capacidades de etiquetado estructural en PyMuPDF")
            
        return version, capabilities
    except Exception as e:
        logging.error(f"Error verificando versión de PyMuPDF: {str(e)}")
        return "desconocida", []

def main():
    """Función principal."""
    print("=== Script de Accesibilidad para PDFs Escaneados - Versión Mejorada ===")
    
    # Verificar versión de PyMuPDF
    pymupdf_version, capabilities = check_pymupdf_version()
    
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(description='Procesa PDFs escaneados para hacerlos accesibles.')
    parser.add_argument('--input', default='pdfs', help='Directorio de entrada con PDFs originales')
    parser.add_argument('--output', default='pdfs_accesibles', help='Directorio de salida para PDFs accesibles')
    parser.add_argument('--temp', default='temp_ocr', help='Directorio temporal para archivos de OCR')
    parser.add_argument('--language', default='spa', help='Idioma para OCR (códigos ISO 639-2)')
    parser.add_argument('--dpi', type=int, default=300, help='Resolución DPI para OCR')
    parser.add_argument('--compress', type=int, choices=[0, 1, 2, 3], default=1, 
                        help='Nivel de compresión (0=ninguna, 3=máxima)')
    parser.add_argument('--post-process', action='store_true', 
                        help='Aplicar post-procesamiento con QPDF si está disponible')
    parser.add_argument('--debug', action='store_true', 
                        help='Habilitar mensajes de depuración detallados')
    
    args = parser.parse_args()
    
    # Ajustar nivel de logging si se solicita depuración
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.info("Modo de depuración activado")
    
    # Verificar que Tesseract esté instalado
    if not check_tesseract_installed():
        print("ERROR: Tesseract OCR no está instalado o no se encuentra en el PATH.")
        print("Por favor, instálalo antes de continuar:")
        print("- Windows: https://github.com/UB-Mannheim/tesseract/wiki")
        print("- Linux: sudo apt-get install tesseract-ocr tesseract-ocr-spa")
        print("- macOS: brew install tesseract tesseract-lang")
        sys.exit(1)
    
    # Configurar directorios
    input_dir = args.input
    output_dir = args.output
    temp_dir = args.temp
    
    # Configuración para el procesamiento
    config = {
        'language': args.language,
        'dpi': args.dpi,
        'compress_level': args.compress
    }
    
    setup_directories(input_dir, output_dir, temp_dir)
    
    print(f"\nDirectorio de entrada: {input_dir}")
    print(f"Directorio de salida: {output_dir}")
    print(f"Directorio temporal: {temp_dir}")
    print(f"Idioma OCR: {config['language']}")
    print(f"Resolución OCR: {config['dpi']} DPI")
    print(f"Nivel de compresión: {config['compress_level']}")
    print(f"Post-procesamiento: {'Activado' if args.post_process else 'Desactivado'}")
    print(f"Versión de PyMuPDF: {pymupdf_version}")
    
    # Advertencia si las capacidades de etiquetado no están disponibles
    if not any(cap in capabilities for cap in ["add_struct_element", "init_doc_structure"]):
        print("\n⚠️ ADVERTENCIA: Tu versión de PyMuPDF puede no soportar etiquetado estructural completo.")
        print("Para mejor accesibilidad, considera actualizar PyMuPDF a la versión 1.18.0 o superior.")
    
    print("\nEste script procesa PDFs escaneados, añade OCR y características de accesibilidad básicas.")
    print("Presiona Enter para comenzar el procesamiento...")
    input()
    
    start_time = time.time()
    
    # Procesar los PDFs
    processed_count = process_directory(input_dir, output_dir, temp_dir, config)
    
    # Aplicar post-procesamiento si se solicita
    if args.post_process and processed_count > 0:
        print("\nAplicando post-procesamiento para mejorar la accesibilidad...")
        post_processed = 0
        
        for pdf_file in os.listdir(output_dir):
            if pdf_file.lower().endswith('.pdf'):
                pdf_path = os.path.join(output_dir, pdf_file)
                if post_process_pdf(pdf_path):
                    post_processed += 1
        
        print(f"Post-procesamiento completado: {post_processed} de {processed_count} archivos")
    
    # Mostrar resultados
    elapsed_time = time.time() - start_time
    print(f"\nProcesamiento completado en {elapsed_time:.2f} segundos.")
    print(f"PDFs procesados con éxito: {processed_count}")
    print(f"Los PDFs accesibles se han guardado en: {output_dir}")
    print("\nRecomendaciones para mejor accesibilidad:")
    print("1. Verifica los PDFs con herramientas como PAC (PDF Accessibility Checker)")
    print("2. Para un etiquetado estructural completo, considera usar Adobe Acrobat Pro")
    print("3. Revisa manualmente que el texto OCR sea correcto")
    print("\nRevisa el archivo 'pdf_scanned_accessibility.log' para más detalles.")

    # Limpiar directorio temporal
    try:
        shutil.rmtree(temp_dir)
        logging.info(f"Directorio temporal eliminado: {temp_dir}")
    except:
        logging.warning(f"No se pudo eliminar el directorio temporal: {temp_dir}")

if __name__ == "__main__":
    main()