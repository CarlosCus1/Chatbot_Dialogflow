# Chatbot de Inventario con Dialogflow ES

Este proyecto es un chatbot diseñado para ser un asistente interno que responde a consultas sobre inventario, stock y detalles de productos. Está construido con Flask y se integra con Dialogflow ES.

## Prerrequisitos

Asegúrate de tener instalado lo siguiente:
- Python 3.6+
- pip (el gestor de paquetes de Python)
- Una cuenta de Google para usar Dialogflow ES
- [ngrok](https://ngrok.com/download) para exponer tu servidor local a internet.

## Instalación

1. Clona este repositorio en tu máquina local.
2. Abre una terminal en el directorio del proyecto.
3. Instala las dependencias de Python:
   ```bash
   pip install -r requirements.txt
   ```

## Cómo Ejecutar la Aplicación

1. En tu terminal, ejecuta la aplicación de Flask:
   ```bash
   python app.py
   ```
   El servidor se iniciará y estará escuchando en `http://127.0.0.1:5001`.

2. Para que Dialogflow pueda comunicarse con tu servidor local, necesitas exponerlo a internet. Usa ngrok para esto:
   ```bash
   ngrok http 5001
   ```
   ngrok te proporcionará una URL pública (por ejemplo, `https://abcdef123456.ngrok.io`). Copia esta URL.

## Configuración de Dialogflow ES

1. **Crear un Agente en Dialogflow ES:**
   - Ve a la [consola de Dialogflow ES](https://dialogflow.cloud.google.com/).
   - Crea un nuevo agente.

2. **Crear la Entidad `@producto`:**
   - En el menú de la izquierda, ve a "Entities".
   - Crea una nueva entidad llamada `producto`.
   - Añade las siguientes entradas (y sinónimos si lo deseas):
     - `laptops`
     - `teclados`
     - `mouse`
     - `monitores`

3. **Crear los Intents:**
   - Ve a la sección "Intents".
   - Crea los siguientes intents manualmente. Para cada uno, añade las frases de entrenamiento (`Training Phrases`) que se encuentran en `intents.json`.

   - **`saludo`**:
     - *Training Phrases*: "Hola", "¿Cómo estás?", etc.
     - *Responses*: "¡Hola! Soy tu asistente de inventario. ¿En qué puedo ayudarte?"

   - **`despedida`**:
     - *Training Phrases*: "Adiós", "Hasta luego", etc.
     - *Responses*: "¡Hasta luego! Que tengas un buen día."

   - **`agradecimiento`**:
     - *Training Phrases*: "Gracias", "Muchas gracias", etc.
     - *Responses*: "¡De nada! Estoy para ayudarte."

   - **`consultar_stock`**:
     - *Training Phrases*: "¿Cuál es el inventario de las `laptops`?", "Verificar el stock de los `teclados`". (Asegúrate de que Dialogflow anote automáticamente las palabras clave con la entidad `@producto`).
     - *Action and parameters*: Asegúrate de que haya un parámetro llamado `producto`.
     - *Fulfillment*: Activa la opción "Enable webhook call for this intent".

   - **`detalles_producto`**:
     - *Training Phrases*: "Dame los detalles de las `laptops`", "¿Qué información tienes sobre los `monitores`?". (Asegúrate de que Dialogflow anote las palabras clave con la entidad `@producto`).
     - *Action and parameters*: Asegúrate de que haya un parámetro llamado `producto`.
     - *Fulfillment*: Activa la opción "Enable webhook call for this intent".

   ### Nuevas Funcionalidades

   - **`ConsultarOfertas`**:
     - *Descripción*: Pregunta por los productos que están actualmente en oferta.
     - *Training Phrases*: "¿Qué productos están en oferta?", "Muéstrame las ofertas".
     - *Fulfillment*: Requiere webhook.

   - **`ConsultarProximosArribos`**:
     - *Descripción*: Consulta qué productos nuevos están por llegar al inventario.
     - *Training Phrases*: "¿Qué productos llegarán pronto?", "Próximos arribos".
     - *Fulfillment*: Requiere webhook.

   - **`ConsultarColores`**:
     - *Descripción*: Pregunta por los colores disponibles de un producto específico.
     - *Training Phrases*: "¿De qué colores tienes las `laptops`?", "¿Qué colores de `mouse` hay disponibles?".
     - *Action and parameters*: Requiere un parámetro `producto`.
     - *Fulfillment*: Requiere webhook.

4. **Configurar el Webhook:**
   - En el menú de la izquierda, ve a "Fulfillment".
   - Activa la opción "Webhook".
   - En el campo "URL", pega la URL de ngrok que copiaste anteriormente y añade `/webhook` al final. (Ej: `https://abcdef123456.ngrok.io/webhook`).
   - Guarda los cambios.

¡Y listo! Ahora puedes probar tu chatbot en el panel de pruebas de Dialogflow.
