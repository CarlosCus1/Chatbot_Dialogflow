# Chatbot Backend con Flask y Dialogflow

Este proyecto es el backend para un chatbot de gestión de stock, desarrollado con Python, Flask y Dialogflow. Se conecta a una base de datos Firestore en Firebase para consultar información de productos y expone una API REST para ser consumida por un frontend y un webhook para Dialogflow.

## Características Principales

- **API REST**: Endpoints para consultar productos por código, por línea y obtener un listado completo.
- **Webhook para Dialogflow**: Procesa intenciones como `GetProductDetails`, `GetProductStock`, y `SearchProductByName`.
- **Búsqueda Flexible**: Implementa una búsqueda de productos por nombre utilizando un sistema de palabras clave (`keywords`) en Firestore.
- **Integración Segura**: Se conecta de forma segura a Firebase Firestore utilizando las credenciales del entorno.
- **CORS Configurado**: Permite peticiones desde un frontend (ej. React en `localhost:3000`).

## Stack Tecnológico

- **Backend**: Python 3, Flask
- **NLU**: Google Dialogflow
- **Base de Datos**: Google Firebase (Firestore)
- **Despliegue**: Preparado para Google Cloud Functions o Cloud Run

---

## Requisitos Previos

- Python 3.8 o superior
- `pip` y `venv` para la gestión de dependencias y entornos virtuales.
- Una cuenta de Google Cloud con un proyecto de Firebase y Dialogflow configurado.

## Configuración del Entorno

Sigue estos pasos para configurar el proyecto en tu máquina local.

1.  **Clonar el repositorio:**
    ```bash
    git clone <URL-de-tu-repositorio>
    cd Chatbot_Dialogflow
    ```

2.  **Crear y activar un entorno virtual:**
    ```bash
    # Crear el entorno
    python -m venv venv

    # Activarlo en Windows
    .\venv\Scripts\activate

    # Activarlo en macOS/Linux
    source venv/bin/activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Credenciales de Firebase:**

    Este proyecto se autentica con Firebase usando las **Credenciales Predeterminadas de la Aplicación** (Application Default Credentials).

    -   **Para desarrollo local:**
        1.  Ve a tu consola de Firebase → Configuración del proyecto → Cuentas de servicio.
        2.  Genera una **nueva clave privada** y descarga el archivo JSON.
        3.  Guarda este archivo en una ubicación segura **fuera** de la carpeta del proyecto.
        4.  Establece la variable de entorno `GOOGLE_APPLICATION_CREDENTIALS` para que apunte a la ruta de tu archivo JSON.

            *   **Windows (PowerShell):**
                ```powershell
                $env:GOOGLE_APPLICATION_CREDENTIALS="C:\ruta\completa\a\tu\archivo.json"
                ```
            *   **macOS/Linux:**
                ```bash
                export GOOGLE_APPLICATION_CREDENTIALS="/ruta/completa/a/tu/archivo.json"
                ```

    -   **Para despliegue en Google Cloud:** No se necesita configuración adicional. La plataforma provee las credenciales automáticamente al entorno de ejecución.

---

## Ejecución Local

Gracias al bloque `if __name__ == '__main__':` añadido en `main.py`, puedes ejecutar el servidor de Flask directamente para pruebas:

```bash
python main.py


La aplicación estará disponible en http://127.0.0.1:5000.

Endpoints de la API
Método	Ruta	Descripción
GET	/api/producto/<codigo>	Obtiene los detalles de un producto por su código.
GET	/api/productos_por_linea/<linea_nombre>	Obtiene productos filtrados por una línea.
GET	/api/all-products	Obtiene un listado de todos los productos.
POST	/	Webhook para recibir y procesar peticiones de Dialogflow.
Estructura del Proyecto
plaintext
├── .gitignore          # Archivos y carpetas a ignorar por Git.
├── main.py             # Lógica principal de la aplicación Flask, API y webhook.
├── requirements.txt    # Dependencias de Python para el proyecto.
└── venv/               # Carpeta del entorno virtual (ignorada por Git).
Despliegue
El punto de entrada api(req) está diseñado para ser desplegado como una Google Cloud Function.

Asegúrate de tener el Google Cloud SDK instalado y configurado.
Utiliza el comando gcloud functions deploy para desplegar la función, especificando api como el punto de entrada.
Para más detalles, consulta la documentación oficial de Google Cloud Functions.