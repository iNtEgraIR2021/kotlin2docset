# Kotlin2Docset
## Kotlin Docset generator for Dash

### Requirements
- Python 3
- BeautifulSoup
- wget
- Pretty decent internet connection

### Usage
In order to start docset build process, run:

```bash
python3 kotlindoc2set.py
```

This will start querying main [KotlinLang pages](https://kotlinlang.org/api/latest/jvm/stdlib/). The process itself takes a lot of time, since all the URLs are queried one by one. 

After webpages are downloaded, HTML files are parsed and mapped by assigned elements to proper docset categories (methods, classes, etc). Then, a docset file is generated in the script's main directory.

### Changes after docset is generated

After docset generation, find `styles.css` file and change:

- Removing header with search bar
  - `.global-header-panel` set `display:none;`
  - `.global-header` set `display:none;`
  - `.docs-nav, .docs-nav-new` set `display:none;`

- Removing footer
  - `.global-footer` set `display:none;`

- Removing left navigation menu from content
  - `.g-grid` remove `margin-right:-30px;`
  - add `.g-3{display:none;}`
  - add `.page-content` set `width:100%;`