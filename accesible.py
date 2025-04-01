# estructura el documento pero no añade etiquetas a las imagenes
from pdfixsdk import *

def hacer_pdf_pac_compliant(pdf_path, output_path):
    pdfix = GetPdfix()  
    if pdfix is None:
        print("Error al inicializar PDFix")
        return
    
    doc = pdfix.OpenDoc(pdf_path, "")
    if doc is None:
        print("No se pudo abrir el PDF")
        return
    
    # 1️⃣ Verificar si el PDF ya tiene estructura de etiquetas
    struct_tree = doc.GetStructTree()
    if struct_tree is None:
        print("El PDF no tiene etiquetas. Agregando estructura de etiquetas...")
        doc.AddTags(None)  # 🔹 Corregido: solo un argumento

    # 2️⃣ Guardar el PDF accesible
    if not doc.Save(output_path, kSaveFull):
        print("Error al guardar PDF")
    
    doc.Close()
    print(f"PDF accesible compatible con PAC guardado en: {output_path}")

# Uso
hacer_pdf_pac_compliant("carta.pdf", "./acc/carta_accesible.pdf")
