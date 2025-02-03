# crawler_booking
# 1. **Descripción**
Extrae los sitemaps country de todos los tipos de alojamientos, descomprime y busca dentro los españoles. 
Y extrae los datos de los 10 primeros de cada pagina de alojamientos y guarda el nombre, url, latitud y longitud.

# 2. **Configuración**

En el archivo de settings se puede cambiar el navegador a usar (chromium, firefox, etc) en esta var:
PLAYWRIGHT_BROWSER_TYPE = 'chromium'

Si no se quiere mostrar el navegador mientras se ejecuta el script:
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
En caso de querer verlo poner False.

Para evitar errores de carga en la extraccion de datos se recomienda no elevar esta variable mas de 8 (raspberry pi 4 (4gb) test server):
CONCURRENT_REQUESTS = 8
