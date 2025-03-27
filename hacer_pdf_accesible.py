import os
import sys
import importlib.util

def check_and_install_dependencies():
    """
    Verificar e instalar dependencias necesarias.
    """
    dependencies = ['pytesseract', 'Pillow']
    for dep in dependencies:
        try:
            importlib.import_module(dep)
        except ImportError:
            print(f"{dep} no encontrado. Instalando...")
            try:
                import pip
                pip.main(['install', dep])
            except Exception as e:
                print(f"Error instalando {dep}: {e}")
                sys.exit(1)

class TesseractLanguageManager:
    def __init__(self, tesseract_path: str = None):
        """
        Inicializar el manejador de configuración de Tesseract.
        
        Args:
            tesseract_path: Ruta personalizada a Tesseract OCR
        """
        # Importar dinámicamente para manejar dependencias
        global pytesseract
        import pytesseract
        
        self._configurar_rutas(tesseract_path)
        self._verificar_instalacion()
    
    def _configurar_rutas(self, tesseract_path: str = None):
        """
        Configurar rutas de Tesseract de manera inteligente.
        
        Args:
            tesseract_path: Ruta opcional al ejecutable de Tesseract
        """
        # Rutas predeterminadas de Tesseract para diferentes sistemas operativos
        rutas_tesseract = [
            # Rutas para Windows
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            os.path.expanduser('~/AppData/Local/Tesseract-OCR/tesseract.exe'),
            
            # Rutas para macOS
            '/usr/local/bin/tesseract',
            '/opt/homebrew/bin/tesseract',
            
            # Rutas para Linux
            '/usr/bin/tesseract',
            '/usr/local/bin/tesseract'
        ]
        
        # Buscar ruta de Tesseract
        if tesseract_path and os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            return
        
        for ruta in rutas_tesseract:
            if os.path.exists(ruta):
                pytesseract.pytesseract.tesseract_cmd = ruta
                return
        
        raise FileNotFoundError("""
        Tesseract no encontrado. 
        Por favor instala Tesseract OCR:
        - Windows: Descarga desde https://github.com/UB-Mannheim/tesseract/wiki
        - macOS: Usa 'brew install tesseract'
        - Linux: Usa 'sudo apt-get install tesseract-ocr'
        """)
    
    def _verificar_instalacion(self):
        """
        Verificar la instalación de Tesseract y los datos de idioma.
        """
        try:
            # Verificar ejecutable
            version = pytesseract.get_tesseract_version()
            print(f"Tesseract versión detectada: {version}")
        except Exception as e:
            raise RuntimeError(f"Error al verificar Tesseract: {e}")
    
    def configurar_datos_idioma(self, ruta_tessdata: str = None):
        """
        Configurar la ruta de los datos de idioma de Tesseract.
        
        Args:
            ruta_tessdata: Ruta personalizada al directorio tessdata
        """
        # Rutas predeterminadas de tessdata para diferentes sistemas
        rutas_tessdata = [
            # Rutas para Windows
            r'C:\Program Files\Tesseract-OCR\tessdata',
            r'C:\Program Files (x86)\Tesseract-OCR\tessdata',
            os.path.expanduser('~/AppData/Local/Tesseract-OCR/tessdata'),
            
            # Rutas para macOS
            '/usr/local/share/tessdata',
            '/opt/homebrew/share/tessdata',
            
            # Rutas para Linux
            '/usr/share/tesseract-ocr/4.00/tessdata',
            '/usr/local/share/tessdata'
        ]
        
        # Si se proporciona ruta personalizada
        if ruta_tessdata and os.path.exists(ruta_tessdata):
            os.environ['TESSDATA_PREFIX'] = ruta_tessdata
            return
        
        # Buscar ruta de tessdata
        for ruta in rutas_tessdata:
            if os.path.exists(ruta):
                os.environ['TESSDATA_PREFIX'] = ruta
                return
        
        raise FileNotFoundError("""
        No se encontró el directorio tessdata. 
        Necesitas descargarlo de: https://github.com/tesseract-ocr/tessdata
        """)
    
    def verificar_idiomas_disponibles(self):
        """
        Verificar idiomas disponibles en Tesseract.
        
        Returns:
            Lista de códigos de idioma disponibles
        """
        try:
            idiomas = pytesseract.get_languages()
            print("Idiomas disponibles:", idiomas)
            return idiomas
        except Exception as e:
            print(f"Error al obtener idiomas: {e}")
            return []

def configurar_tesseract(
    ruta_tesseract: str = None, 
    ruta_tessdata: str = None
) -> TesseractLanguageManager:
    """
    Función de configuración principal para Tesseract.
    
    Args:
        ruta_tesseract: Ruta al ejecutable de Tesseract
        ruta_tessdata: Ruta al directorio de datos de idioma
    
    Returns:
        Instancia de TesseractLanguageManager
    """
    # Verificar e instalar dependencias
    check_and_install_dependencies()
    
    # Crear instancia y configurar
    manager = TesseractLanguageManager(ruta_tesseract)
    manager.configurar_datos_idioma(ruta_tessdata)
    
    # Verificar idiomas disponibles
    manager.verificar_idiomas_disponibles()
    
    return manager

# Ejemplo de uso
if __name__ == "__main__":
    try:
        # Intentar configurar Tesseract
        configurar_tesseract()
        
        # Ejemplo de configuración con rutas personalizadas
        # configurar_tesseract(
        #     ruta_tesseract=r'C:\ruta\personalizada\tesseract.exe',
        #     ruta_tessdata=r'C:\ruta\personalizada\tessdata'
        # )
    
    except Exception as e:
        print(f"Error en configuración de Tesseract: {e}")
        print("\nPasos de resolución:")
        print("1. Asegúrate de tener Tesseract OCR instalado")
        print("2. Descarga archivos de idioma desde: https://github.com/tesseract-ocr/tessdata")
        print("3. Configura las variables de entorno TESSDATA_PREFIX")
        print("4. Verifica que las rutas de instalación sean correctas")