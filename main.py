import firebase_admin
from firebase_admin import firestore
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from firebase_functions import https_fn
import logging
import random
import sys

# --- 1. Configuración de Logs ---
# Configuración básica de logging para un mejor seguimiento de la aplicación.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 2. Aplicación Flask ---
flask_app = Flask(__name__)

# Permite CORS solo desde el dominio de tu app de React.
# Es más seguro que permitir todos los orígenes.
# Asegúrate de que esta URL coincida con el frontend de tu aplicación.
CORS(flask_app, resources={r"/api/*": {
    "origins": ["http://localhost:3000", "https://stock-manager-app-v2.web.app"],
    "supports_credentials": True
}})

# --- 3. Inicialización de Firebase ---
# Variable global para la instancia de la base de datos de Firestore.
db = None

def initialize_firebase_once():
    """
    Inicializa el SDK de Firebase Admin solo una vez.
    Cuando se despliega en Google Cloud (Cloud Run/Functions),
    el SDK usa las credenciales del entorno automáticamente.
    """
    global db
    if not firebase_admin._apps:
        try:
            firebase_admin.initialize_app()
            db = firestore.client()
            logging.info("Firebase Admin SDK inicializado exitosamente.")
        except Exception as e:
            logging.error(f"Error al inicializar Firebase Admin SDK: {e}", exc_info=True)
            # Podrías querer levantar una excepción o manejar este error de forma más robusta
            # si la inicialización es crítica para la operación de la app.
            raise RuntimeError(f"Fallo crítico al inicializar Firebase: {e}")

# Llama a la inicialización al inicio de la aplicación o asegúrate de que se llame
# antes de cualquier operación de base de datos.
# Para Cloud Functions/Run, se inicializará la primera vez que se ejecute la función.

# --- 4. Funciones Auxiliares para Interacción con Firestore ---

def _get_firestore_db():
    """
    Retorna la instancia de Firestore. Asegura que Firebase esté inicializado.
    """
    if db is None:
        initialize_firebase_once()
    if db is None: # Si la inicialización falló, aún podría ser None
        logging.error("La instancia de Firestore no está disponible.")
        return None
    return db

def buscar_producto(codigo: str) -> dict | None:
    """
    Busca un producto por su código en Firestore.
    Retorna los datos del producto como un diccionario si se encuentra, de lo contrario None.
    """
    firestore_db = _get_firestore_db()
    if not firestore_db:
        return None
    try:
        doc_ref = firestore_db.collection('productos').document(codigo)
        doc = doc_ref.get()
        if doc.exists:
            product_data = doc.to_dict()
            product_data['codigo'] = doc.id # Añadir el código (ID del documento) a los datos
            return product_data
        else:
            return None
    except Exception as e:
        logging.error(f"Error al buscar producto {codigo}: {e}", exc_info=True)
        return None

def buscar_productos_por_linea(linea_nombre: str) -> list:
    """
    Busca productos por línea en Firestore.
    Maneja el caso especial de 'sensoriales' mapeando a 'manualidades'.
    Retorna una lista de diccionarios de productos.
    """
    firestore_db = _get_firestore_db()
    if not firestore_db:
        return []

    # Normalizar el nombre de la línea para la búsqueda.
    search_linea = linea_nombre.lower()
    if search_linea == 'sensoriales':
        search_linea = 'manualidades'

    try:
        productos = []
        # Utiliza la sintaxis de consulta correcta para Firestore
        docs = firestore_db.collection('productos').where('linea', '==', search_linea).stream()
        for doc in docs:
            producto_data = doc.to_dict()
            producto_data['codigo'] = doc.id # Añadir el código (ID del documento) a los datos
            productos.append(producto_data)
        return productos
    except Exception as e:
        logging.error(f"Error al buscar productos por línea {linea_nombre}: {e}", exc_info=True)
        return []

def buscar_productos_por_nombre_flexible(nombre_producto: str) -> list:
    """
    Busca productos de forma flexible siguiendo una estrategia de precisión:
    1. Intenta buscar una coincidencia exacta por código de producto.
    2. Si no, intenta buscar una coincidencia exacta por código EAN.
    3. Como último recurso, busca por palabras clave ('keywords') en el nombre.
    """
    firestore_db = _get_firestore_db()
    if not firestore_db:
        return []

    # --- 1. Búsqueda por Código de Producto Exacto ---
    # Asumimos que los códigos pueden estar en mayúsculas
    producto_por_codigo = buscar_producto(nombre_producto.upper())
    if producto_por_codigo:
        logging.info(f"Búsqueda flexible: Encontrado producto por código exacto '{nombre_producto}'.")
        return [producto_por_codigo]

    # --- 2. Búsqueda por Código EAN Exacto ---
    try:
        docs_ean = firestore_db.collection('productos').where('cod_ean', '==', nombre_producto).limit(1).stream()
        productos_por_ean = []
        for doc in docs_ean:
            producto_data = doc.to_dict()
            producto_data['codigo'] = doc.id
            productos_por_ean.append(producto_data)
        if productos_por_ean:
            logging.info(f"Búsqueda flexible: Encontrado producto por EAN exacto '{nombre_producto}'.")
            return productos_por_ean
    except Exception as e:
        logging.error(f"Error al buscar por EAN '{nombre_producto}': {e}", exc_info=True)

    # --- 3. Búsqueda por Palabras Clave (Fallback) ---
    logging.info(f"Búsqueda flexible: No se encontró por código/EAN, buscando por nombre '{nombre_producto}'.")
    # Normalizar y dividir la consulta de búsqueda en palabras clave
    search_keywords = [kw.lower() for kw in nombre_producto.split() if kw]
    if not search_keywords:
        return []

    try:
        query = firestore_db.collection('productos').where('keywords', 'array_contains', search_keywords[0])
        docs = query.limit(20).stream() # Limitar para no sobrecargar y dar una respuesta rápida

        productos_encontrados = []
        for doc in docs:
            product_data = doc.to_dict()
            product_keywords = product_data.get('keywords', [])
            
            # Filtrado secundario: verificar que TODOS los keywords de búsqueda estén en los keywords del producto.
            if all(search_kw in product_keywords for search_kw in search_keywords):
                product_data['codigo'] = doc.id
                productos_encontrados.append(product_data)
        
        return productos_encontrados[:5] # Devolver un máximo de 5 para una respuesta concisa

    except Exception as e:
        logging.error(f"Error al buscar productos por nombre '{nombre_producto}': {e}", exc_info=True)
        return []

def get_all_products_from_firestore() -> list:
    """
    Obtiene todos los productos de la colección 'productos' en Firestore.
    Retorna una lista de diccionarios de productos.
    """
    firestore_db = _get_firestore_db()
    if not firestore_db:
        return []
    try:
        all_products = []
        docs = firestore_db.collection('productos').stream()
        for doc in docs:
            product_data = doc.to_dict()
            product_data['codigo'] = doc.id # Añadir el código (ID del documento) a los datos
            all_products.append(product_data)
        return all_products
    except Exception as e:
        logging.error(f"Error al obtener todos los productos: {e}", exc_info=True)
        return []

# --- 5. Rutas de la API ---

@flask_app.route('/api/producto/<string:codigo>', methods=['GET'])
def get_product(codigo: str):
    """
    Endpoint para obtener los detalles de un producto por su código.
    """
    if not codigo:
        logging.warning("Solicitud de producto sin código.")
        return jsonify({"error": "El código del producto no puede estar vacío"}), 400
    
    product_data = buscar_producto(codigo)
    if product_data:
        return jsonify(product_data)
    else:
        logging.info(f"Producto con código '{codigo}' no encontrado.")
        return jsonify({"error": f"Producto con código '{codigo}' no encontrado"}), 404

@flask_app.route('/api/productos_por_linea/<string:linea_nombre>', methods=['GET'])
def get_products_by_line(linea_nombre: str):
    """
    Endpoint para obtener productos filtrados por línea.
    """
    if not linea_nombre:
        logging.warning("Solicitud de productos por línea sin nombre de línea.")
        return jsonify({"error": "El nombre de la línea no puede estar vacío"}), 400
    
    productos = buscar_productos_por_linea(linea_nombre)
    if productos:
        return jsonify(productos)
    else:
        logging.info(f"No se encontraron productos para la línea '{linea_nombre}'.")
        return jsonify({"message": f"No se encontraron productos para la línea '{linea_nombre}'"}), 200

@flask_app.route('/api/all-products', methods=['GET'])
def get_all_products_endpoint():
    """
    Endpoint para obtener todos los productos.
    """
    products = get_all_products_from_firestore()
    return jsonify(products) # Retorna una lista vacía si no hay productos o hay un error

# --- 6. Plantillas y Generadores de Respuestas ---
# Centralizar las respuestas aquí hace que el bot sea más fácil de mantener y personalizar.

RESPONSE_TEMPLATES = {
    "PRODUCT_NOT_FOUND": [
        "Lo siento, no pude encontrar un producto con ese código. ¿Podrías verificarlo?",
        "Mmm, no encontré ese producto. ¿Quizás el código es incorrecto? También puedes buscar por nombre.",
        "No hay resultados para ese código. Intenta con otro o busca por nombre."
    ],
    "PROVIDE_CODE": [
        "Por favor, indícame el código del producto que te interesa.",
        "Claro, ¿cuál es el código del producto que buscas?",
    ],
    "PROVIDE_NAME": [
        "Por favor, dime el nombre del producto que buscas.",
        "Ok, ¿qué producto te gustaría encontrar?",
    ],
    "GENERIC_ERROR": [
        "Lo siento, algo salió mal y no pude procesar tu solicitud. Inténtalo de nuevo.",
        "Uups, tuve un problema técnico. ¿Podemos intentarlo de nuevo?",
    ],
    "UNHANDLED_INTENT": [
        "No estoy seguro de cómo ayudarte con eso. Puedo buscar productos por código o nombre, y darte su stock.",
        "No entendí muy bien. Recuerda que puedo darte detalles y stock de productos si me das su código o nombre.",
    ]
}

def _get_random_response(key: str) -> str:
    """Obtiene una respuesta aleatoria de las plantillas."""
    # Si la clave no existe, devuelve una respuesta genérica para evitar errores.
    return random.choice(RESPONSE_TEMPLATES.get(key, ["No sé qué decir a eso."]))

# --- 6. Webhook de Dialogflow ---

def _get_product_details_text(product_data: dict | None) -> str:
    """
    Formatea los detalles de un producto para la respuesta de Dialogflow.
    """
    if not product_data:
        return _get_random_response("PRODUCT_NOT_FOUND")

    # Usar .get() con un valor por defecto para evitar KeyError
    codigo = product_data.get('codigo', 'N/A')
    descripcion = product_data.get('nombre', 'N/A')
    linea = product_data.get('linea', 'N/A')
    master = product_data.get('master', 'N/A')
    precio = product_data.get('precio', 'N/A')
    cod_ean = product_data.get('cod_ean', 'N/A')
    peso = product_data.get('can_kg_um', 'N/A')

    response_text = (
        f"¡Aquí tienes los detalles de {descripcion} (Código: {codigo})!\n"
        f"Línea: {linea}\n"
        f"Unidades Master: {master}\n"
        f"Precio: {precio}\n"
        f"Código EAN: {cod_ean}\n"
        f"Peso: {peso} kg"
    )
    return response_text

def _get_stock_by_warehouse_text(product_data: dict | None) -> str:
    """
    Formatea la información de stock por almacén para la respuesta de Dialogflow.
    """
    if not product_data:
        return _get_random_response("PRODUCT_NOT_FOUND")

    codigo = product_data.get('codigo', 'N/A')
    descripcion = product_data.get('nombre', 'N/A')
    
    stock_info = []
    # Asegúrate de que 'almacenes' sea una lista antes de iterar
    if isinstance(product_data.get('almacenes'), list):
        for almacen in product_data['almacenes']:
            almacen_nombre = almacen.get('nombre', 'N/A')
            disponible = int(almacen.get('disponible', 0))
            if disponible > 0: # Mostrar si hay stock
                stock_info.append(f"   - {almacen_nombre}: {disponible} unidades")
    
    response_text = f"Este es el stock para {descripcion} (Código: {codigo}):\n"
    if stock_info:
        response_text += "\n".join(stock_info)
    else:
        response_text += "Actualmente no hay stock disponible en ningún almacén."

    return response_text

@flask_app.route('/', methods=['POST'])
def dialogflow_webhook():
    """
    Endpoint principal para el webhook de Dialogflow.
    Procesa las intenciones y parámetros para generar la respuesta adecuada.
    """
    request_json = request.get_json(silent=True)
    logging.info(f"Solicitud de Dialogflow recibida: {request_json}")
    # sys.stdout.write(f"Dialogflow Request: {request_json}\n") # Solo para depuración extrema en algunos entornos

    intent_display_name = request_json.get('queryResult', {}).get('intent', {}).get('displayName')
    parameters = request_json.get('queryResult', {}).get('parameters', {})
    fulfillment_text = _get_random_response("GENERIC_ERROR")

    # Asegura que product_codes sea siempre una lista para facilitar la iteración
    product_codes = parameters.get('product_code')
    if isinstance(product_codes, str):
        product_codes = [product_codes]
    elif not isinstance(product_codes, list):
        product_codes = [] # Si no es ni str ni list, inicializar como lista vacía

    # Nuevo parámetro para búsqueda por nombre
    product_name_query = parameters.get('product_name', '')

    if intent_display_name == 'GetProductDetails':
        if product_codes:
            all_product_details = []
            for code in product_codes:
                product_data = buscar_producto(code)
                all_product_details.append(_get_product_details_text(product_data))
            fulfillment_text = "\n".join(all_product_details)
        else:
            fulfillment_text = _get_random_response("PROVIDE_CODE")
    elif intent_display_name == 'GetProductStock':
        if product_codes:
            all_stock_info = []
            for code in product_codes:
                product_data = buscar_producto(code)
                all_stock_info.append(_get_stock_by_warehouse_text(product_data))
            fulfillment_text = "\n".join(all_stock_info)
        else:
            fulfillment_text = _get_random_response("PROVIDE_CODE")
    
    elif intent_display_name == 'SearchProductByName':
        if product_name_query:
            found_products = buscar_productos_por_nombre_flexible(product_name_query)
            if not found_products:
                fulfillment_text = f"No encontré productos que coincidan con '{product_name_query}'. ¿Puedes intentar con otro nombre o un código?"
            elif len(found_products) == 1:
                fulfillment_text = "¡Claro! Encontré este producto:\n" + _get_product_details_text(found_products[0])
            else:
                # --- Respuesta Enriquecida con Botones de Sugerencia ---
                product_list_text = "\n".join([f"- {p.get('nombre', 'N/A')} (Código: {p.get('codigo', 'N/A')})" for p in found_products])
                title = f"Encontré {len(found_products)} productos que coinciden. ¿A cuál te refieres?\n{product_list_text}"
                
                # Crear sugerencias rápidas (quick replies) con los códigos
                suggestions = [f"Detalles {p.get('codigo')}" for p in found_products]
                
                # Construir la respuesta JSON para Dialogflow
                response_payload = {
                    "fulfillmentMessages": [
                        {"text": {"text": [title]}},
                        {
                            "quickReplies": {
                                "title": "Puedes pedirme más detalles:",
                                "quickReplies": suggestions[:12] # Dialogflow tiene un límite de 13 sugerencias
                            }
                        }
                    ]
                }
                return jsonify(response_payload)
        else:
            fulfillment_text = _get_random_response("PROVIDE_NAME")

    elif intent_display_name == 'GetFullStockSummary':
        fulfillment_text = "Puedes consultar el stock completo en: https://kutt.it/Stock_Lineas_Hoy"
    
    elif intent_display_name == 'SendCatalog':
        # Reemplaza la URL de abajo con el enlace real a tu catálogo
        fulfillment_text = "¡Claro! Puedes ver nuestro catálogo completo aquí: https://tu-empresa.com/catalogo.pdf"
    else:
        logging.warning(f"Intención de Dialogflow no manejada: {intent_display_name}")
        fulfillment_text = _get_random_response("UNHANDLED_INTENT")
    
    return jsonify({"fulfillmentText": fulfillment_text})

# --- 7. Entry Point de Cloud Functions ---

@https_fn.on_request()
def api(req: https_fn.Request) -> https_fn.Response:
    """
    Punto de entrada principal para Google Cloud Functions/Run.
    Envuelve la aplicación Flask para ser ejecutada como una función HTTP.
    """
    # Manejar las solicitudes OPTIONS (preflight de CORS)
    if req.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*', # Se puede especificar el origen si es fijo
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization', # Añadir 'Authorization' si usas tokens
            'Access-Control-Max-Age': '3600' # Caché por 1 hora
        }
        return make_response("", 204, headers)

    # El entorno de prueba de Flask se utiliza para simular una solicitud HTTP.
    with flask_app.test_request_context(
        method=req.method,
        url=req.url,
        headers=req.headers,
        data=req.get_data(),
        query_string=req.query_string
    ):
        try:
            # Despachar la solicitud a la aplicación Flask
            flask_response = flask_app.dispatch_request()
            
            # Crear una respuesta de Firebase Functions a partir de la respuesta de Flask
            response = make_response(flask_response.get_data())
            response.status_code = flask_response.status_code
            for key, value in flask_response.headers:
                response.headers[key] = value
            
            # El encabezado Access-Control-Allow-Origin es manejado automáticamente
            # por la extensión Flask-CORS basada en la configuración anterior.
            # No es necesario sobreescribirlo aquí.
            return response
        except Exception as e:
            logging.error(f"Error al procesar la solicitud Flask: {e}", exc_info=True)
            # Asegúrate de que la respuesta de error también incluya el encabezado CORS.
            return make_response(f"Error interno del servidor: {e}", 500, {'Access-Control-Allow-Origin': req.headers.get("Origin", "*")})

# --- 8. Punto de Entrada para Desarrollo Local ---
if __name__ == '__main__':
    # Este bloque solo se ejecuta cuando el script se corre directamente
    # (ej. `python main.py`) y no cuando es importado por un servidor WSGI como Gunicorn.
    # Es ideal para desarrollo y depuración local.

    # Asegúrate de que Firebase se inicialice al arrancar
    initialize_firebase_once()

    # Corre la aplicación Flask en modo de depuración.
    # El puerto 5000 es el predeterminado para Flask.
    flask_app.run(debug=True, port=5000)