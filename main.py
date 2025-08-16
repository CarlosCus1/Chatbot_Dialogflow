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
CORS(flask_app, origins=["http://localhost:3000", "https://stock-manager-app-v2.web.app"], supports_credentials=True)

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

def get_all_products_from_firestore(page: int = 1, page_size: int = 20) -> tuple[list, int]:
    """
    Obtiene todos los productos de la colección 'productos' en Firestore.
    Implementa paginación para manejar grandes volúmenes de datos.
    Retorna una tupla: (lista de productos de la página, total de productos).
    """
    firestore_db = _get_firestore_db()
    if not firestore_db:
        return [], 0
    try:
        collection_ref = firestore_db.collection('productos')
        
        # Para obtener el total, la forma más eficiente en Firestore es mantener un contador
        # en un documento separado. Como alternativa (menos eficiente para millones de documentos),
        # podemos contar todos los IDs, pero esto puede tener costos asociados.
        # Por simplicidad, aquí lo omitimos, pero en una app real se usaría un contador.
        # Asumiremos un total grande para el ejemplo o lo dejaremos fuera de la respuesta.
        total_products = 0 # En una app real, obtendrías esto de un documento contador.

        all_products = []
        # Firestore no tiene un 'count' directo ni un 'offset' simple. La paginación se hace con cursores.
        # Para una paginación numérica simple (menos performante pero más fácil de empezar):
        # Nota: El uso de offset tiene limitaciones de rendimiento en Firestore.
        query = collection_ref.order_by('nombre').limit(page_size).offset((page - 1) * page_size)
        docs = query.stream()
        for doc in docs:
            product_data = doc.to_dict()
            product_data['codigo'] = doc.id
            all_products.append(product_data)
        return all_products, total_products # Devolvemos 0 como total por ahora
    except Exception as e:
        logging.error(f"Error al obtener todos los productos: {e}", exc_info=True)
        return [], 0

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
    # Es una práctica estándar de API REST devolver una lista vacía con un estado 200 si no se encuentran resultados para un filtro.
    return jsonify(productos)

@flask_app.route('/api/all-products', methods=['GET'])
def get_all_products_endpoint():
    """
    Endpoint para obtener todos los productos con paginación.
    Acepta los query params: ?page=<numero>&page_size=<numero>
    """
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
    except ValueError:
        return jsonify({"error": "Los parámetros 'page' y 'page_size' deben ser números enteros."}), 400

    if page < 1 or page_size < 1:
        return jsonify({"error": "Los parámetros 'page' y 'page_size' deben ser números positivos."}), 400

    products, total = get_all_products_from_firestore(page=page, page_size=page_size)
    
    response = {
        "page": page,
        "page_size": page_size,
        # "total_products": total, # Descomentar si implementas un contador de total
        "data": products
    }
    
    return jsonify(response)

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

    # Usar .get() con un valor por defecto ('N/A' o 'No disponible') para evitar errores
    # si un campo no existe en la base de datos.
    response_text = (
        f"¡Aquí tienes los detalles de {product_data.get('nombre', 'producto')}!\n"
        f"Código: {product_data.get('codigo', 'N/A')}\n"
        f"Línea: {product_data.get('linea', 'N/A')}\n"
        f"Unidades Master: {product_data.get('master', 'N/A')}\n"
        f"Precio: {product_data.get('precio', 'N/A')}\n"
        f"Código EAN: {product_data.get('cod_ean', 'N/A')}\n"
        f"Peso: {product_data.get('can_kg_um', 'N/A')} kg"
    )
    return response_text

def _get_stock_by_warehouse_text(product_data: dict | None) -> str:
    """
    Formatea la información de stock por almacén para la respuesta de Dialogflow.
    Es más robusto al verificar la existencia y tipo de 'almacenes'.
    """
    if not product_data:
        return _get_random_response("PRODUCT_NOT_FOUND")

    codigo = product_data.get('codigo', 'N/A')
    descripcion = product_data.get('nombre', 'N/A')
    
    stock_info = []
    # Comprobación robusta: Asegúrate de que 'almacenes' exista y sea una lista antes de iterar.
    if isinstance(product_data.get('almacenes'), list):
        for almacen in product_data['almacenes']:
            # Asegurarse de que el almacén es un diccionario y tiene los campos necesarios.
            if isinstance(almacen, dict) and 'nombre' in almacen and 'disponible' in almacen:
                disponible = int(almacen.get('disponible', 0))
                if disponible > 0: # Mostrar solo si hay stock
                    stock_info.append(f"   - {almacen['nombre']}: {disponible} unidades")
    
    if stock_info:
        response_text = f"Este es el stock para {descripcion} (Código: {codigo}):\n" + "\n".join(stock_info)
    else:
        response_text = f"Actualmente no hay stock disponible en ningún almacén para {descripcion} (Código: {codigo})."

    return response_text

def _handle_get_product_details(parameters: dict) -> dict:
    """Maneja la lógica para la intención 'GetProductDetails'."""
    product_codes = _get_product_codes_from_params(parameters)
    if not product_codes:
        return {"fulfillmentText": _get_random_response("PROVIDE_CODE")}
    
    all_product_details = [_get_product_details_text(buscar_producto(code)) for code in product_codes]
    return {"fulfillmentText": "\n".join(all_product_details)}

def _handle_get_product_stock(parameters: dict) -> dict:
    """Maneja la lógica para la intención 'GetProductStock'."""
    product_codes = _get_product_codes_from_params(parameters)
    if not product_codes:
        return {"fulfillmentText": _get_random_response("PROVIDE_CODE")}

    all_stock_info = [_get_stock_by_warehouse_text(buscar_producto(code)) for code in product_codes]
    return {"fulfillmentText": "\n".join(all_stock_info)}

def _handle_search_product_by_name(parameters: dict) -> dict:
    """Maneja la lógica para la intención 'SearchProductByName'."""
    product_name_query = parameters.get('product_name', '')
    if not product_name_query:
        return {"fulfillmentText": _get_random_response("PROVIDE_NAME")}

    found_products = buscar_productos_por_nombre_flexible(product_name_query)
    if not found_products:
        return {"fulfillmentText": f"No encontré productos que coincidan con '{product_name_query}'. ¿Puedes intentar con otro nombre o un código?"}
    
    if len(found_products) == 1:
        return {"fulfillmentText": "¡Claro! Encontré este producto:\n" + _get_product_details_text(found_products[0])}
    
    # Respuesta enriquecida con botones de sugerencia
    product_list_text = "\n".join([f"- {p.get('nombre', 'N/A')} (Código: {p.get('codigo', 'N/A')})" for p in found_products])
    title = f"Encontré {len(found_products)} productos que coinciden. ¿A cuál te refieres?\n{product_list_text}"
    suggestions = [f"Detalles {p.get('codigo')}" for p in found_products]
    
    return {
        "fulfillmentMessages": [
            {"text": {"text": [title]}},
            {
                "quickReplies": {
                    "title": "Puedes pedirme más detalles:",
                    "quickReplies": suggestions[:12] # Límite de Dialogflow
                }
            }
        ]
    }

def _handle_get_full_stock_summary(parameters: dict) -> dict:
    """Maneja la lógica para la intención 'GetFullStockSummary'."""
    return {"fulfillmentText": "Puedes consultar el stock completo en: https://kutt.it/Stock_Lineas_Hoy"}

def _handle_send_catalog(parameters: dict) -> dict:
    """Maneja la lógica para la intención 'SendCatalog'."""
    return {"fulfillmentText": "¡Claro! Puedes ver nuestro catálogo completo aquí: https://tu-empresa.com/catalogo.pdf"}

def _get_product_codes_from_params(parameters: dict) -> list:
    """Extrae y normaliza los códigos de producto de los parámetros de Dialogflow."""
    product_codes = parameters.get('product_code')
    if isinstance(product_codes, str):
        return [product_codes]
    if isinstance(product_codes, list):
        return product_codes
    return [] # Devuelve una lista vacía si no es str ni list

@flask_app.route('/', methods=['POST'])
def dialogflow_webhook():
    """
    Endpoint principal para el webhook de Dialogflow.
    Procesa las intenciones y parámetros para generar la respuesta adecuada.
    """
    request_json = request.get_json(silent=True)
    if not request_json:
        logging.warning("Solicitud vacía o no es JSON.")
        return jsonify({"fulfillmentText": _get_random_response("GENERIC_ERROR")}), 400

    logging.info(f"Solicitud de Dialogflow recibida: {request_json}")

    intent_handlers = {
        'GetProductDetails': _handle_get_product_details,
        'GetProductStock': _handle_get_product_stock,
        'SearchProductByName': _handle_search_product_by_name,
        'GetFullStockSummary': _handle_get_full_stock_summary,
        'SendCatalog': _handle_send_catalog,
    }

    query_result = request_json.get('queryResult', {})
    intent_name = query_result.get('intent', {}).get('displayName')
    parameters = query_result.get('parameters', {})

    handler = intent_handlers.get(intent_name)

    if handler:
        response_payload = handler(parameters)
    else:
        logging.warning(f"Intención de Dialogflow no manejada: {intent_name}")
        response_payload = {"fulfillmentText": _get_random_response("UNHANDLED_INTENT")}
    
    return jsonify(response_payload)

# --- 7. Entry Point de Cloud Functions ---

@https_fn.on_request()
def api(req: https_fn.Request) -> https_fn.Response:
    """
    Punto de entrada principal para Google Cloud Functions/Run.
    Envuelve la aplicación Flask para ser ejecutada como una función HTTP.
    """
    # La forma más simple y robusta de servir una app WSGI (como Flask)
    # en una Cloud Function de 2da Gen es pasar la solicitud directamente.
    # Flask y Flask-CORS se encargarán del enrutamiento, la lógica y las cabeceras.
    try:
        return flask_app(req.environ, lambda status, headers: None)
    except Exception as e:
        logging.error(f"Error no controlado en la aplicación Flask: {e}", exc_info=True)
        # Devuelve una respuesta de error genérica.
        return https_fn.Response("Error interno del servidor.", status=500)

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