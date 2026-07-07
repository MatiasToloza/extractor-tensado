import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="Prueba", layout="wide")

st.title(".")
st.write(".")

def is_number(s):
    """Verifica si un string es un número válido (incluso si tiene decimales)"""
    try:
        float(s.replace(',', '.'))
        return True
    except ValueError:
        return False

def procesar_reporte(archivos_pdf):
    datos_consolidados = []

    for archivo in archivos_pdf:
        with pdfplumber.open(archivo) as pdf:
            tramo_actual = None
            estado = "BUSCANDO_TRAMO"
            
            estructuras_tramo = []
            tension_final_15 = "No encontrado"

            progress_bar = st.progress(0, text=f"Procesando archivo: {archivo.name}")
            total_pages = len(pdf.pages)

            for num_pag, page in enumerate(pdf.pages):
                texto = page.extract_text(layout=True)
                if not texto: continue

                lineas = texto.split('\n')

                for linea in lineas:
                    linea_limpia = linea.strip()
                    if not linea_limpia: continue

                    # 1. Buscar Subtítulo de Tramo
                    match_tramo = re.search(r'Tramo\s+([A-Za-z0-9\-]+)', linea_limpia, re.IGNORECASE)
                    if match_tramo:
                        nuevo_tramo = match_tramo.group(1).upper()
                        if tramo_actual != nuevo_tramo:
                            if tramo_actual and estructuras_tramo:
                                for est in estructuras_tramo:
                                    datos_consolidados.append({
                                        'Structure Name': est['struct'],
                                        'Span Ahead': est['span'],
                                        'Columna C Vacia': '',
                                        'Hor. Tension in Sheaves (N)': est['tension'],
                                        'Unloaded AAT (15 Degree) Final Tension (N)': tension_final_15,
                                        'Columna F Vacia': ''
                                    })
                            
                            tramo_actual = nuevo_tramo
                            estructuras_tramo = []
                            tension_final_15 = "No encontrado"
                            estado = "BUSCANDO_INICIAL"

                    # 2. MAQUINA DE ESTADOS
                    
                    if estado == "BUSCANDO_INICIAL":
                        if "INICIAL" in linea_limpia.upper() and "15" in linea_limpia:
                            estado = "LEYENDO_INICIAL"
                            continue
                            
                    elif estado == "LEYENDO_INICIAL":
                        if "INICIAL" in linea_limpia.upper() and "15" not in linea_limpia:
                            estado = "BUSCANDO_FINAL"
                            continue
                            
                        tokens = linea_limpia.split()
                        
                        if len(tokens) >= 5 and is_number(tokens[1]) and is_number(tokens[4]):
                            struct_str = tokens[0]
                            span_str = tokens[1].replace(',', '.')
                            tension_str = tokens[4].replace(',', '.')
                            
                            val_n = round(float(tension_str), 2)
                            
                            if not any(e['struct'] == struct_str for e in estructuras_tramo):
                                estructuras_tramo.append({
                                    'struct': struct_str,
                                    'span': span_str,
                                    'tension': val_n
                                })
                                
                    elif estado == "BUSCANDO_FINAL" or estado == "LEYENDO_INICIAL":
                        if "FINAL" in linea_limpia.upper():
                            # En vez de buscar "Horiz Tension", buscamos las unidades
                            estado = "BUSCANDO_UNIDADES_N"
                            continue

                    elif estado == "BUSCANDO_UNIDADES_N":
                        # Buscamos la fila que tiene múltiples "(N)"
                        if "(N)" in linea_limpia and linea_limpia.count("(N)") >= 5:
                            estado = "LEYENDO_TENSION_FINAL"
                            continue

                    elif estado == "LEYENDO_TENSION_FINAL":
                        tokens = linea_limpia.split()
                        # Buscamos la fila de números (debe tener 12 columnas para las 12 temperaturas)
                        if len(tokens) >= 12 and all(is_number(t) for t in tokens[:6]):
                            # El 15°C está en la 5ta columna (índice 4)
                            val_15 = float(tokens[4].replace(',', '.'))
                            tension_final_15 = round(val_15, 2)
                            
                            estado = "BUSCANDO_TRAMO"

                progress_bar.progress((num_pag + 1) / total_pages, text=f"Procesando archivo: {archivo.name} (Página {num_pag + 1} de {total_pages})")
            
            progress_bar.empty()

            if tramo_actual and estructuras_tramo:
                for est in estructuras_tramo:
                    datos_consolidados.append({
                        'Structure Name': est['struct'],
                        'Span Ahead': est['span'],
                        'Columna C Vacia': '',
                        'Hor. Tension in Sheaves (N)': est['tension'],
                        'Unloaded AAT (15 Degree) Final Tension (N)': tension_final_15,
                        'Columna F Vacia': ''
                    })

    return pd.DataFrame(datos_consolidados)

# --- INTERFAZ DE USUARIO ---
archivos_subidos = st.file_uploader("Sube tus archivos PDF (OPGW, ACAR, etc.)", type="pdf", accept_multiple_files=True)

if archivos_subidos:
    if st.button("Ejecutar Extracción", type="primary"):
        with st.spinner("Buscando bloques INICIAL y detectando unidades (N) en tabla FINAL..."):
            df_final = procesar_reporte(archivos_subidos)
            
            if not df_final.empty:
                df_final.rename(columns={'Columna C Vacia': '', 'Columna F Vacia': ' '}, inplace=True)
                
                st.success(f"¡Extracción exitosa! Se encontraron {len(df_final)} estructuras con sus vanos y tensiones.")
                st.dataframe(df_final) 
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Datos de Tensado')
                
                st.download_button(
                    label="⬇️ Descargar Excel",
                    data=buffer.getvalue(),
                    file_name="Reporte_Tensado_Newtons_Final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No se encontraron datos que coincidan. Revisa si el documento está en formato imagen.")
