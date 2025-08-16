import pytest
from unittest.mock import MagicMock
import json

# Importa la aplicación Flask y las funciones que quieres probar
from main import flask_app, buscar_producto

# --- Configuración de Pytest ---

@pytest.fixture
def client():
    """
    Configura la aplicación Flask para el modo de prueba y proporciona un cliente de prueba.
    """
    flask_app.config['TESTING'] = True
    # Inicializa Firebase una vez para el contexto de prueba si es necesario
    # En un entorno de prueba real, esto también se podría mockear.
    with flask_app.app_context():
        from main import initialize_firebase_once
        if not initialize_firebase_once():
            # Si la inicialización real es un problema, la mockeamos aquí
            pass

    with flask_app.test_client() as client:
        yield client

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

def test_buscar_producto_no_encontrado(mocker):
    """
    Prueba la función 'buscar_producto' cuando el producto NO se encuentra.
    """
    # 1. Preparación
    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # 2. Actuación
    producto = buscar_producto('P999')

    # 3. Aserción
    assert producto is None

# --- 2. Pruebas de Integración para Endpoints de la API ---

def test_get_product_endpoint(client, mocker):
    """
    Prueba el endpoint /api/producto/<codigo> cuando el producto existe.
    """
    # Preparación: Reutilizamos la misma lógica de mock que en la prueba unitaria
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.id = 'P002'
    mock_doc.to_dict.return_value = {'nombre': 'API Test Product'}

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # Actuación: Usa el cliente de prueba para hacer una solicitud GET
    response = client.get('/api/producto/P002')
    response_data = json.loads(response.data)

    # Aserción
    assert response.status_code == 200
    assert response_data['codigo'] == 'P002'
    assert response_data['nombre'] == 'API Test Product'

def test_get_product_endpoint_not_found(client, mocker):
    """
    Prueba el endpoint /api/producto/<codigo> cuando el producto no se encuentra.
    """
    # Preparación
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # Actuación
    response = client.get('/api/producto/P999')

    # Aserción
    assert response.status_code == 404
    assert b'no encontrado' in response.data

# --- 3. Pruebas de Integración para el Webhook de Dialogflow ---

def test_dialogflow_webhook_get_details(client, mocker):
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
    dialogflow_request = {
        "queryResult": {
            "intent": {
                "displayName": "GetProductDetails"
            },
            "parameters": {
                "product_code": "P123"
            }
        }
    }

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

def test_buscar_productos_flexible_por_codigo_exacto(mocker):
    """Prueba que la búsqueda flexible priorice el código de producto."""
    # 1. Preparación: Mockear buscar_producto para que devuelva un resultado
    mocker.patch('main.buscar_producto', return_value={'codigo': 'P001', 'nombre': 'Producto Por Codigo'})
    # Mockear las otras búsquedas para asegurar que no se llamen
    mock_db = MagicMock()
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # 2. Actuación
    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('P001')

    # 3. Aserción
    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por Codigo'
    # Asegurarse de que no se intentó buscar por EAN o por keywords
    mock_db.collection.return_value.where.assert_not_called()


def test_buscar_productos_flexible_por_ean(mocker):
    """Prueba que la búsqueda flexible funcione con código EAN si no es código de producto."""
    # 1. Preparación: buscar_producto no encuentra nada
    mocker.patch('main.buscar_producto', return_value=None)
    
    # Mockear la respuesta de Firestore para la búsqueda por EAN
    mock_doc_ean = MagicMock()
    mock_doc_ean.to_dict.return_value = {'nombre': 'Producto Por EAN', 'cod_ean': '12345'}
    mock_doc_ean.id = 'P002'
    
    mock_db = MagicMock()
    # .stream() devuelve un iterador, así que lo simulamos con una lista
    mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [mock_doc_ean]
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # 2. Actuación
    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('12345')

    # 3. Aserción
    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por EAN'
    # Verificar que se llamó a la consulta por EAN
    mock_db.collection.return_value.where.assert_called_with('cod_ean', '==', '12345')


def test_buscar_productos_flexible_por_nombre(mocker):
    """Prueba que la búsqueda por nombre (keywords) funcione como fallback."""
    # 1. Preparación: Ni el código ni el EAN encuentran nada
    mocker.patch('main.buscar_producto', return_value=None)
    
    mock_doc_nombre = MagicMock()
    mock_doc_nombre.to_dict.return_value = {'nombre': 'Producto Por Nombre', 'keywords': ['producto', 'por', 'nombre']}
    mock_doc_nombre.id = 'P003'

    mock_db = MagicMock()
    # La primera llamada a where() es por EAN (devuelve vacío), la segunda es por keywords
    mock_db.collection.return_value.where.side_effect = [
        MagicMock(limit=MagicMock(stream=MagicMock(return_value=[]))), # Búsqueda por EAN
        MagicMock(limit=MagicMock(stream=MagicMock(return_value=[mock_doc_nombre]))) # Búsqueda por Keyword
    ]
    mocker.patch('main._get_firestore_db', return_value=mock_db)

    # 2. Actuación
    from main import buscar_productos_por_nombre_flexible
    resultados = buscar_productos_por_nombre_flexible('producto nombre')

    # 3. Aserción
    assert len(resultados) == 1
    assert resultados[0]['nombre'] == 'Producto Por Nombre'
    assert mock_db.collection.return_value.where.call_count == 2

# --- 5. Pruebas adicionales para el Webhook de Dialogflow ---

def test_dialogflow_webhook_get_stock(client, mocker):
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
    dialogflow_request = {
        "queryResult": {
            "intent": {"displayName": "GetProductStock"},
            "parameters": {"product_code": "P123"}
        }
    }
    response = client.post('/', json=dialogflow_request)
    response_data = json.loads(response.data)
    assert response.status_code == 200
    assert 'Almacen Central: 100 unidades' in response_data['fulfillmentText']
    assert 'Almacen Sur: 5 unidades' in response_data['fulfillmentText']
    assert 'Almacen Norte' not in response_data['fulfillmentText']

def test_dialogflow_webhook_unhandled_intent(client):
    """Prueba que el webhook responde correctamente a una intención no manejada."""
    dialogflow_request = {
        "queryResult": {
            "intent": {"displayName": "IntencionDesconocida"},
            "parameters": {}
        }
    }
    response = client.post('/', json=dialogflow_request)
    response_data = json.loads(response.data)
    assert response.status_code == 200
    assert 'No estoy seguro de cómo manejar esa solicitud' in response_data['fulfillmentText']