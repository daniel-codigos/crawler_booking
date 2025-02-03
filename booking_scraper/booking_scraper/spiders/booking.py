import scrapy
import re
import gzip
import io
import csv
import os
from scrapy_playwright.page import PageMethod
import xml.etree.ElementTree as ET


class BookingSitemapSpider(scrapy.Spider):
    name = "booking_sitemap"
    allowed_domains = ["booking.com"]
    start_urls = ["https://www.booking.com/robots.txt"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num_hoteles_buscar = 250
        self.extraidos = set()

    def parse(self, response):
        lineas = response.text.split("\n")
        buscar = re.compile(r"https:\/\/www\.booking\.com\/sitembk-themed-country-.*\.xml")
        cada_sitemap = []
        for cada_linea in lineas:
            if cada_linea.startswith("Sitemap") and buscar.search(cada_linea):
                url = cada_linea.split(": ")[1]
                cada_sitemap.append(url)

        all_sitemaps = [url for url in cada_sitemap]
        for todo in all_sitemaps:
            if len(self.extraidos) >= self.num_hoteles_buscar:
                break
            else:
                yield scrapy.Request(
                    url=todo,
                    callback=self.parse_sitemap,
                    meta={
                        "playwright": True,
                        "playwright_page_methods": [
                            PageMethod("wait_for_load_state", "domcontentloaded")
                        ],
                        "url": todo
                    }
                )


    async def parse_sitemap(self, response):
        sitemap_url = response.meta["url"]
        contenido = response.text
        regex = re.compile(r"<loc>(https://www\.booking\.com/sitembk-themed-country-[^<]*?-es\.[^<]*?)</loc>")
        urls_filtradas = regex.findall(contenido)

        if urls_filtradas:
            all_urls_clean = [url for url in urls_filtradas]
            for todo in all_urls_clean:
                if len(self.extraidos) >= self.num_hoteles_buscar:
                    break
                else:
                    yield scrapy.Request(url=todo, callback=self.parse_gz, meta={'gz_url': todo}, dont_filter=True)
        else:
            self.logger.info(f"{sitemap_url} NO tiene '-es.'")



    async def parse_gz(self, response):
        gz_url = response.meta["gz_url"]
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(response.body), mode='rb') as f:
                xml_content = f.read().decode('utf-8')
            tostr = ET.fromstring(xml_content)
            str_buscar = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locs_buscar = tostr.findall(".//ns:loc", str_buscar)

            urls_extraidas = [loc.text.strip() for loc in locs_buscar if loc.text]
            regex_es_es = re.compile(r"https://www\.booking\.com/.*/es\.es.*")
            urls_esp = [url for url in urls_extraidas if regex_es_es.search(url)]

            if urls_esp:
                for url in urls_esp:
                    if len(self.extraidos) >= self.num_hoteles_buscar:
                        break
                    else:
                        yield scrapy.Request(
                            url=url,
                            callback=self.parse_info,
                            meta={
                                "playwright": True,
                                "playwright_include_page": True,
                                "playwright_page_methods": [
                                    PageMethod("wait_for_load_state", "domcontentloaded")
                                ],
                                "url": url
                            }
                        )
            else:
                self.logger.info(f"NO contiene URLs con '/es.es. :  {gz_url}'")

        except Exception as e:
            self.logger.error(f"Error al descomprimir {gz_url}: {e}")

    async def parse_info(self, response):
        info_url = response.meta["url"]
        play_page = response.meta["playwright_page"]
        try:
            await play_page.wait_for_load_state("domcontentloaded", timeout=60000)

            # Cerrar popup si aparece
            popup = await play_page.query_selector("button[data-command='noop']")
            if popup:
                await popup.click()

            h_links = await play_page.query_selector_all("a.bui-card__header_full_link_wrap")
            if not h_links:
                self.logger.warning("No encuentra hoteles")
                return

            urls_hoteles = []
            for link in h_links:
                href = await link.get_attribute("href")
                if href:
                    urls_hoteles.append(f"https://www.booking.com{href}")

            for index, url in enumerate(urls_hoteles):
                if len(self.extraidos) >= self.num_hoteles_buscar:
                    break
                else:
                    await self.info_hotel(index, url, play_page)

        except Exception as e:
            self.logger.error(f"Error al interactuar con {info_url}: {e}")
        finally:
            await play_page.close() 


    async def info_hotel(self, index, url, page):
        self.logger.info(f"Hotel: {url}")
        if len(self.extraidos) >= self.num_hoteles_buscar:
            #self.save_file(self.extraidos, "hoteles_spain.csv")
            await page.context.close()
            self.crawler.engine.close_spider(self, "Límite de hoteles alcanzado")
            return
        try:

            #print("-----------------------------------------------------------------------")
            #print(len(self.extraidos))
            hotel_pag = await page.context.new_page()
            await hotel_pag.goto(url, timeout=90000, wait_until="domcontentloaded")

            ele_titulo = await hotel_pag.query_selector("h2.d2fee87262.pp-header__title")
            ele_ubica = await hotel_pag.query_selector("a#map_trigger_header_pin")
            if ele_ubica and ele_titulo:
                titulo = await ele_titulo.inner_text()
                ubicacion = await ele_ubica.get_attribute("data-atlas-latlng")
                latitud = ubicacion.split(",")[0]
                longitud = ubicacion.split(",")[1]
                json_fin = {"titulo": titulo, "latitud": latitud, "longitud": longitud, "url": url}
                # **Evitar guardar duplicados**
                if url not in self.extraidos:
                    self.logger.info(f"Guardando hotel: {titulo} - {latitud}, {longitud}")
                    self.extraidos.add(url)
                    self.save_file(json_fin,"fin_data_saved_hotels_booking.csv")
            else:
                self.logger.error(f"Error al encontrar los elementos.")
            await hotel_pag.close()
        except Exception as e:
            self.logger.error(f"Error en hotel: {url} {e}")

    def save_file(self, data, name):
        existe = os.path.isfile(name)
        with open(name, mode='a', newline='', encoding='utf-8') as file:
            fieldnames = ["titulo", "latitud", "longitud", "url"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not existe:
                writer.writeheader()
            writer.writerow(data)
