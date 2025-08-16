import pytest
from unittest.mock import MagicMock
import json

# Importa la aplicación Flask y las funciones que quieres probar
from main import flask_app, buscar_producto

# --- Configuración de Pytest ---

@pytest.fixture
def client(mocker):
    """
    Configura la aplicación Flask para el modo de prueba y proporciona un cliente de prueba.
    También mockea la inicialización de Firebase para evitar llamadas reales a la red.
    """
    flask_app.config['TESTING'] = True
    # Mockeamos la inicialización para que las pruebas no dependan del entorno real de Firebase.
    mocker.patch('main.initialize_firebase_once')

    with flask_app.test_client() as client:
        yield client

@pytest.fixture
def mock_product_found(mocker):
    """Fixture que mockea buscar_producto para que devuelva un producto de prueba."""
    test_product = {
        'codigo': 'P001',
        'nombre': 'Producto de Prueba',
        'linea': 'test'
    }
    return mocker.patch('main.buscar_producto', return_value=test_product)

@pytest.fixture
def mock_product_not_found(mocker):
    """Fixture que mockea buscar_producto para que devuelva None."""
    return mocker.patch('main.buscar_producto', return_value=None)

@pytest.fixture
def mock_firestore_db(mocker):
    """Fixture que mockea la instancia de la base de datos de Firestore."""
    mock_db = MagicMock()
    mocker.patch('main._get_firestore_db', return_value=mock_db)
    return mock_db

@pytest.fixture(autouse=True)
def mock_get_all_products(mocker):
    """Mockea automáticamente la función de paginación para evitar llamadas no deseadas."""
    mocker.patch('main.get_all_products_from_firestore', return_value=([], 0))

@pytest.fixture
def mock_flexible_search(mocker, mock_firestore_db):
    """
    Fixture avanzada para mockear los diferentes caminos de la búsqueda flexible.
    Retorna una función 'factory' para configurar el escenario de prueba deseado.
    """
    def _setup_mocks(found_by_code=None, found_by_ean=None, found_by_keyword=None):
        # Mockear la búsqueda por código de producto
        mocker.patch('main.buscar_producto', return_value=found_by_code)

        # Preparar las respuestas de Firestore para EAN y keywords
        ean_results = [found_by_ean] if found_by_ean else []
        keyword_results = [found_by_keyword] if found_by_keyword else []

        # Simular las dos búsquedas consecutivas en Firestore
        mock_firestore_db.collection.return_value.where.side_effect = [
            # Búsqueda por EAN
            MagicMock(limit=MagicMock(stream=MagicMock(return_value=ean_results))),
            # Búsqueda por Keyword
            MagicMock(limit=MagicMock(stream=MagicMock(return_value=keyword_results)))
        ]
        
        # Mockear los documentos para que tengan un ID y un método to_dict()
        if found_by_ean: found_by_ean.id = 'P_EAN'
        if found_by_keyword: found_by_keyword.id = 'P_KW'

    return _setup_mocks

@pytest.fixture
def dialogflow_request_factory():
    """
    Fixture que actúa como una fábrica para crear cuerpos de solicitud de Dialogflow.
    Simplifica las pruebas del webhook al eliminar la repetición de JSON.
    """
    def _factory(intent_name: str, parameters: dict = None):
        if parameters is None:
            parameters = {}
        return {
            "queryResult": {
                "intent": {"displayName": intent_name},
                "parameters": parameters
            }
        }
    return _factory

# --- 1. Pruebas Unitarias para Funciones Auxiliares ---

# La fixture 'mocker' viene de pytest-mock y facilita la creación de mocks.
def test_buscar_producto_encontrado(mocker):
    """
    Prueba la función 'buscar_producto' cuando el producto se encuentra.
    """
    # 1. Preparación (Arrange): Crea un mock para el documento de Firestore
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.id = 'P001'
    mock_doc.to_dict.return_value = {
        'nombre': 'Producto de Prueba',
        'linea': 'test'
    }

    # 2. Preparación: Simula el cliente de Firestore y sus métodos
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    # Usa patch para reemplazar la función _get_firestore_db con nuestro mock
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # 3. Actuación (Act): Llama a la función que estamos probando
    producto = buscar_producto('P001')

    # 4. Aserción (Assert): Verifica si el resultado es el esperado
    assert producto is not None
    assert producto['codigo'] == 'P001'
    assert producto['nombre'] == 'Producto de Prueba'
    # Verifica que el mock fue llamado correctamente
    mock_db.collection.return_value.document.assert_called_with('P001')
    
def test_buscar_producto_no_encontrado(mocker, mock_firestore_db):
    """
    Prueba la función 'buscar_producto' cuando el producto NO se encuentra.
    """
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_firestore_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    producto = buscar_producto('P999')
    assert producto is None

# --- 2. Pruebas de Integración para Endpoints de la API ---

def test_get_product_endpoint(client, mock_product_found):
    """
    Prueba el endpoint /api/producto/<codigo> cuando el producto existe.
    """
    response = client.get('/api/producto/P001')
    response_data = json.loads(response.data)

    assert response.status_code == 200
    assert response_data['codigo'] == 'P001'
    assert response_data['nombre'] == 'Producto de Prueba'

def test_get_product_endpoint_not_found(client, mock_product_not_found):
    """
    Prueba el endpoint /api/producto/<codigo> cuando el producto no se encuentra.
    """
    response = client.get('/api/producto/P999')

    # Aserción
    assert response.status_code == 404
    assert b'no encontrado' in response.data

def test_get_all_products_paginated(client, mocker):
    """
    Prueba el endpoint /api/all-products con paginación.
    """
    # Preparación: Mockear la función de Firestore para que devuelva datos de prueba
    # Simulamos que devuelve 2 productos y un total de 10
    mock_products = [
        {'codigo': 'P001', 'nombre': 'Producto 1'},
        {'codigo': 'P002', 'nombre': 'Producto 2'}
    ]
    mocker.patch('main.get_all_products_from_firestore', return_value=(mock_products, 10))

    # Actuación: Hacer una solicitud con parámetros de paginación
    response = client.get('/api/all-products?page=1&page_size=2')
    response_data = json.loads(response.data)

    # Aserción
    assert response.status_code == 200
    assert response_data['page'] == 1
    assert response_data['page_size'] == 2
    assert len(response_data['data']) == 2
    assert response_data['data'][0]['nombre'] == 'Producto 1'

@pytest.mark.parametrize("page, page_size", [
    ("abc", "20"),  # page no es un número
    ("1", "xyz"),   # page_size no es un número
    ("0", "20"),    # page es cero
    ("-1", "20"),   # page es negativo
    ("1", "0"),     # page_size es cero
    ("1", "-5"),    # page_size es negativo
])
def test_get_all_products_invalid_pagination_params(client, page, page_size):
    """
    Prueba el endpoint /api/all-products con parámetros de paginación inválidos.
    """
    response = client.get(f'/api/all-products?page={page}&page_size={page_size}')
    assert response.status_code == 400
    assert b'error' in response.data

# --- 3. Pruebas de Integración para el Webhook de Dialogflow ---

def test_dialogflow_webhook_get_details(client, mocker, dialogflow_request_factory):
    """
    Prueba el webhook de Dialogflow para la intención 'GetProductDetails'.
    """
    # Preparación: Simula la función buscar_producto para que devuelva datos de prueba
    mocker.patch(
        'main.buscar_producto', 
        return_value={
            'codigo': 'P123',
            'nombre': 'Producto para Webhook',
            'linea': 'webhook',
            'master': 12,
            'precio': 150.50,
            'cod_ean': '1234567890123',
            'can_kg_um': 0.5
        }
    )

    # Preparación: Crea una solicitud JSON de Dialogflow de ejemplo
    dialogflow_request = dialogflow_request_factory("GetProductDetails", {"product_code": "P123"})

    # Actuación: Envía una solicitud POST al endpoint del webhook
    response = client.post('/', json=dialogflow_request)
    response_data = json.loads(response.data)

    # Aserción
    assert response.status_code == 200
    assert 'fulfillmentText' in response_data
    assert 'Producto para Webhook' in response_data['fulfillmentText']
    assert 'Código: P123' in response_data['fulfillmentText']
    assert 'Precio: 150.5' in response_data['fulfillmentText']

# --- 4. Pruebas para la lógica de búsqueda flexible mejorada ---

def test_buscar_productos_flexible_por_codigo_exacto(mock_flexible_search):
    """Prueba que la búsqueda flexible priorice el código de producto."""
    mock_flexible_search(found_by_code={'codigo': 'P001', 'nombre': 'Producto Por Codigo'})
    
    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('P001')

    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por Codigo'

def test_buscar_productos_flexible_por_ean(mock_flexible_search):
    """Prueba que la búsqueda flexible funcione con código EAN si no es código de producto."""
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {'nombre': 'Producto Por EAN', 'cod_ean': '12345'}
    mock_flexible_search(found_by_ean=mock_doc)

    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('12345')

    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por EAN'

def test_buscar_productos_flexible_filtrado_secundario_falla(mock_flexible_search):
    """
    Prueba que el filtrado secundario de keywords funciona correctamente.
    El producto es encontrado por el primer keyword, pero es descartado porque no contiene el segundo.
    """
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {'nombre': 'Producto Azul', 'keywords': ['producto', 'azul']}
    mock_flexible_search(found_by_keyword=mock_doc)

    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('producto rojo')

    assert len(resultados) == 0

def test_buscar_productos_flexible_por_nombre(mock_flexible_search):
    """Prueba que la búsqueda por nombre (keywords) funcione como fallback."""
    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {'nombre': 'Producto Por Nombre', 'keywords': ['producto', 'por', 'nombre']}
    mock_flexible_search(found_by_keyword=mock_doc)

    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('producto nombre')

    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por Nombre'

# --- 5. Pruebas adicionales para el Webhook de Dialogflow ---

def test_dialogflow_webhook_get_stock(client, mocker, dialogflow_request_factory):
    """Prueba el webhook de Dialogflow para la intención 'GetProductStock'."""
    mocker.patch(
        'main.buscar_producto', 
        return_value={
            'codigo': 'P123',
            'nombre': 'Producto Con Stock',
            'almacenes': [
                {'nombre': 'Almacen Central', 'disponible': 100},
                {'nombre': 'Almacen Norte', 'disponible': 0}, # No debe aparecer
                {'nombre': 'Almacen Sur', 'disponible': 5},
            ]
        }
    )
    dialogflow_request = dialogflow_request_factory("GetProductStock", {"product_code": "P123"})
    response = client.post('/', json=dialogflow_request)
    response_data = json.loads(response.data)
    assert response.status_code == 200
    assert 'Almacen Central: 100 unidades' in response_data['fulfillmentText']
    assert 'Almacen Sur: 5 unidades' in response_data['fulfillmentText']
    assert 'Almacen Norte' not in response_data['fulfillmentText']

def test_dialogflow_webhook_unhandled_intent(client, dialogflow_request_factory):
    """Prueba que el webhook responde correctamente a una intención no manejada."""
    dialogflow_request = dialogflow_request_factory("IntencionDesconocida")
    response = client.post('/', json=dialogflow_request)
    response_data = json.loads(response.data)
    assert response.status_code == 200
    assert 'No estoy seguro de cómo ayudarte con eso' in response_data['fulfillmentText']