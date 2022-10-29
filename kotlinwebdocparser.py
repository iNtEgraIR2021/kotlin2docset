import os
from pathlib import Path
from pprint import pprint
import logging
import re
import sys
from subprocess import call
from urllib.parse import unquote

from bs4 import BeautifulSoup
import htmlmin
import requests

from sqliteconnection import SQLiteConnection


class KotlinWebDocParser:
    def __init__(self, url: str, local_path: str, database: SQLiteConnection):
        self.url = url
        self.local_path = local_path
        self.database = database

    def mirror_website(self):
        call([
            'wget',
            '--mirror',
            '--convert-links',
            '--adjust-extension',
            '--page-requisites',
            '--no-parent',
            '--no-host-directories',
            '--directory-prefix', self.local_path,
            '--quiet',
            '--show-progress',
            self.url
        ])

        robots_txt = Path(self.local_path) / "robots.txt"
        if robots_txt.exists():
            logging.debug(f"deleting '{robots_txt}' ... ")
            robots_txt.unlink()

    def parse(self):
        html_files = list(Path(self.local_path).glob('**/*.html'))
        len_files = len(html_files)
        
        logging.debug(f"found {len_files} html files")
        
        for file_index in range(len_files):
            html_file = html_files[file_index]
            
            if file_index == 0:
                # parse css file names to get the right order to merge them into one file
                logging.debug(f"parsing css file names from '{html_file}' ... ")
                self.parse_css_js(html_file)
            
            logging.debug(f" {file_index+1}/{len_files} parsing '{html_file}' ... ")
            self.parse_file(html_file)

    def parse_css_js(self, file_path: str):
        """
        parse and merge css and javascript files referenced in file_path
        """

        css_links = []
        js_links = []

        with open(file_path, 'r') as page:
            html_str = str(page.read()).strip()
            html_str = re.sub(r'((<link)([^>]+))(>)', '\g<1>/>', html_str) # fix invalid 'link' DOM nodes

            soup = BeautifulSoup(html_str, features='html.parser')

            css_links = list(soup.select('link[rel^="stylesheet"]'))
            js_links = list(soup.select('script[src^="/_assets"]')) + list(soup.select('script[src^="../"]'))

        css_contents = ''
        for css_link in css_links:
            file_name = unquote(str(css_link.get('href'))).strip('/').replace('../','').strip('.css') + '.css'
            file_path = Path(self.local_path) / file_name
            
            if file_path.exists():
                try:
                    logging.debug(f"read contents of '{file_path}' ... ")
                    
                    css_temp = ''
                    with open(file_path, 'r') as fh:
                        css_temp = str(fh.read()).strip().strip('None')
                    
                    if len(css_temp) == 0 or '<html' in css_temp:
                        logging.error(f"while processing contents of '{file_path}' -> error: content is invalid!")
                    else:
                        css_contents += css_temp
                        # file_path.unlink()
                except Exception as e:
                    logging.error(f"failed to read '{file_path}' -> error: {e}")
            else:
                logging.error(f" while trying to access '{file_path}' -> file does not seem to exists")
        
        import_pattern = re.compile(r'(?m)(\@import url\()(http)*(s)*([^\)]+)(\))(;)*')
        dl_pattern = re.compile(r'(?m)url\((http)(s)(:\/\/)([^\)]+)(\))')

        css_imports = list(re.findall(import_pattern, css_contents))
        for import_url in css_imports:
            import_url_str = f"https:{import_url[3]}"
            import_req = requests.get(import_url_str)
            if import_req.ok:
                import_content = str(import_req.text)
                dl_files = list(re.findall(dl_pattern, import_content))
                # pprint(dl_files)

                for dl_file in dl_files:
                    font_path = Path(self.local_path) / "_assets" / "assets" / "fonts"

                    dl_file_url = f"https://{dl_file[3]}"
                    dl_file_name = dl_file_url.split('/')[-1]
                    asset_path = '/_assets/assets/fonts/'
                    if 'fonts.gstatic.com/s/' in dl_file_url:
                        font_dir = str(dl_file_url.replace('https://','').replace('fonts.gstatic.com/s/','').split('/')[0])
                        asset_path += font_dir + '/'
                        font_path = font_path / font_dir
                    
                    font_path.mkdir(parents=True, exist_ok=True) # create directory if not exists
                    font_path = font_path / dl_file_name

                    if not font_path.exists():
                        self.download_file(dl_file_url, font_path)
                    else:
                        logging.debug(f"file '{font_path}' does already seem to exists -> skipped download")

                    import_content = import_content.replace(''.join(dl_file).strip(')'), str(asset_path)+str(dl_file_name))

                css_contents = import_content + css_contents

        # remove import urls
        css_contents = re.sub(import_pattern,'',css_contents)

        css_styles = Path(self.local_path) / "_assets" / "styles.css"
        with open(css_styles, 'w+') as page:
            try:
                page.write(css_contents)
            except Exception as e:
                logging.error(f" failed to write merged css to '{css_styles}' -> error: {e}")

        js_contents = ''
        for js_link in js_links:
            file_name = unquote(str(js_link.get('src'))).strip('/').replace('../','')
            file_path = Path(self.local_path) / file_name
            
            if file_path.exists():
                try:
                    logging.debug(f"read contents of '{file_path}' ... ")
                    
                    js_temp = ''
                    with open(file_path, 'r') as fh:
                        js_temp = str(fh.read()).strip().strip('None')
                    
                    if len(js_temp) == 0 or '<html' in js_temp:
                        logging.error(f"while processing contents of '{file_path}' -> error: content is invalid!")
                    else:
                        js_contents += js_temp
                        # file_path.unlink()
                except Exception as e:
                    logging.error(f"failed to read '{file_path}' -> error: {e}")
            else:
                logging.error(f" while trying to access '{file_path}' -> file does not seem to exists")
        
        js_contents = re.sub(r'(?im)(http)(s)*(:\/\/)(data\.services\.jetbrains\.)([^\/]+)(\/)*[\w\/]+','',js_contents)

        js_file = Path(self.local_path) / "_assets" / "script.js"
        with open(js_file, 'w+') as page:
            try:
                page.write(js_contents)
            except Exception as e:
                logging.error(f" failed to write merged js to '{js_file}' -> error: {e}")

    def download_file(self, file_url: str, file_path: Path):
        """
        strean binary data from url and write to file_path
        """
        file_req = requests.get(file_url, stream=True)
        if file_req.ok:
            with open(file_path, 'wb') as f:
                for chunk in file_req:
                    f.write(chunk)

    def parse_file(self, file_path: str):
        html_str = ''

        with open(file_path, 'r') as page:
            html_str = str(page.read()).strip()
            html_str = re.sub(r'((<link)([^>]+))(>)', '\g<1>/>', html_str) # fix invalid 'link' DOM nodes

            soup = BeautifulSoup(html_str, features='html.parser')

            css_links = list(soup.select('link[rel^="stylesheet"]'))
            css_href = str(css_links[0].get('href'))
            css_links[0]['href'] = '/_assets/styles.css' # css_href.replace(css_href.split('/')[-1],'styles.css')
            css_link = str(css_links[0])

            # js_links = list(soup.select('script[src^="/_assets"]')) + list(soup.select('script[src^="../"]'))
            # js_href = str(js_links[0].get('src'))
            # js_links[0]['src'] = '/_assets/script.js' # js_href.replace(js_href.split('/')[-1],'script.js')
            # js_link = str(js_links[0])

            for tag_group in [soup.select('script[src^="/_assets"]'), soup.select('script[src^="../"]'), soup.select('link[rel^="stylesheet"]'), soup.select('link[rel^="dns"]'), soup.select('link[rel~="icon"]'), soup.select('link[rel$="icon"]'), soup.select('meta[property^="og"]'), soup.select('meta[property^="twitter"]'), soup.select('head > script'), soup.select('iframe'), soup.select('.global-layout > header'), soup.select('.global-layout > footer'), soup.select('a[href="/docs/home.html"]')]:
                for tag in tag_group:
                    tag.decompose()

            soup.head.append(BeautifulSoup(css_link, features='html.parser').link)
            # soup.body.append(BeautifulSoup(js_link, features='html.parser').script)

            for node in soup.find_all('div', attrs={'class': ['node-page-main', 'overload-group']}):
                signature = node.find('div', attrs={'class': 'signature'})
                if signature:
                    code_type = self.parse_code_type(signature.text.strip())
                    name_dom = soup.find('div', attrs={'class': 'api-docs-breadcrumbs'})
                    name = '.'.join(map(lambda string: string.strip(), name_dom.text.split('/')[2::]))
                    path = str(file_path).replace('kotlin.docset/Contents/Resources/Documents/', '')
                    if code_type is not None and name:
                        self.database.insert_into_index(name, code_type, path)
                        logging.info('%s -> %s -> %s' % (name, code_type, path))
            
            html_str = str(soup).strip()
        
        try:
            with open(file_path, "w+", encoding="utf-8") as fh:
                fh.write(htmlmin.minify(html_str, remove_empty_space=True))
        except Exception as e:
            logging.error(f"minification of '{file_path}' failed -> error: {e}")
            try:
                with open(file_path, "w+", encoding="utf-8") as fh:
                    fh.write(html_str)
            except Exception as e:
                logging.error(f" failed to write sanitized html to '{file_path}' -> error: {e}")

    def parse_code_type(self, code: str) -> str:
        tokens = list(filter(
            lambda token: token not in [
                'public',
                'private',
                'protected',
                'open',
                'const',
                'abstract',
                'suspend',
                'operator'
            ],
            code.split()
        ))
        if 'class' in tokens or 'typealias' in tokens:
            return 'Class'
        elif 'interface' in tokens:
            return 'Interface'
        elif 'fun' in tokens:
            return 'Function'
        elif 'val' in tokens or 'var' in tokens:
            return 'Property'
        elif 'object' in tokens:
            return 'Object'
        elif '<init>' in tokens or '<init>' in tokens[0]:
            return 'Constructor'
        elif re.match(r"[a-zA-Z0-9]*\(.*\)", code) or re.match(r"[a-zA-Z0-9]*\(.*\)", tokens[0]):
            return 'Constructor'
        elif re.match(r"[A-Z0-9\_]+", code):
            return 'Enum'
