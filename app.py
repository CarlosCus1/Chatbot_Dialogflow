from flask import Flask, request, jsonify
from data import productos
import json
import random

app = Flask(__name__)

# Cargar intents desde el archivo JSON
with open('intents.json', 'r', encoding='utf-8') as file:
    intents_data = json.load(file)

def get_response_for_intent(intent_name):
    for intent in intents_data['intents']:
        if intent['displayName'] == intent_name:
            return random.choice(intent['responses'])
    return None

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json(silent=True, force=True)
    intent_name = req.get('queryResult', {}).get('intent', {}).get('displayName', '')
    parameters = req.get('queryResult', {}).get('parameters', {})

    response_text = ""

    if intent_name == 'consultar_stock':
        producto_nombre = parameters.get('producto', '').lower()
        if producto_nombre in productos:
            stock = productos[producto_nombre]['stock']
            response_text = f"Tenemos {stock} unidades de {producto_nombre} en stock."
        else:
            response_text = f"No he podido encontrar el producto {producto_nombre} en nuestro inventario."

    elif intent_name == 'detalles_producto':
        producto_nombre = parameters.get('producto', '').lower()
        if producto_nombre in productos:
            detalles = productos[producto_nombre]['detalles']
            response_text = f"Detalles de {producto_nombre}: {detalles}"
        else:
            response_text = f"No tengo detalles sobre el producto {producto_nombre}."

    elif intent_name == 'ConsultarOfertas':
        ofertas = [p for p, d in productos.items() if d.get('en_oferta')]
        if ofertas:
            response_text = f"Los siguientes productos están en oferta: {', '.join(ofertas)}."
        else:
            response_text = "Actualmente no hay productos en oferta."

    elif intent_name == 'ConsultarProximosArribos':
        arribos = {p: d['fecha_llegada'] for p, d in productos.items() if d['fecha_llegada'] not in ['En stock', 'Llegaron hoy']}
        if arribos:
            lista_arribos = [f"{p} ({t})" for p, t in arribos.items()]
            response_text = f"Los siguientes productos llegarán pronto: {', '.join(lista_arribos)}."
        else:
            response_text = "No se esperan nuevos arribos por el momento."

    elif intent_name == 'ConsultarColores':
        producto_nombre = parameters.get('producto', '').lower()
        if producto_nombre in productos:
            colores = productos[producto_nombre].get('colores', [])
            if colores:
                response_text = f"Los colores disponibles para {producto_nombre} son: {', '.join(colores)}."
            else:
                response_text = f"No tengo información de colores para {producto_nombre}."
        else:
            response_text = f"No he podido encontrar el producto {producto_nombre}."

    else:
        # Manejar intents generales desde intents.json
        response = get_response_for_intent(intent_name)
        if response:
            response_text = response
        else:
            response_text = "Lo siento, no entendí tu solicitud. ¿Puedes intentarlo de nuevo?"

    return jsonify({'fulfillmentText': response_text})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
