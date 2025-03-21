import sqlite3
import re
import html2text
from bs4 import BeautifulSoup, Tag
from typing import List, Tuple
from download import download_and_save_to_db

TABLE_ID_PATTERN = r"表([0-9]+)"

def init_database_for_parse(db_file: str):
    '''
    Create tables with defined data schema
    '''
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS apis;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            method TEXT NOT NULL,
            uri TEXT NOT NULL,
            description TEXT,
            root_table_id INTEGER NOT NULL,
            doc_page TEXT
        )''')

    cursor.execute('DROP TABLE IF EXISTS uri_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uri_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id INTEGER NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT
        )''')
    
    cursor.execute("DROP TABLE IF EXISTS request_tables;")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_tables (
            api_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            caption TEXT,
            url TEXT,
            anchor_id TEXT,
            PRIMARY KEY (api_id, table_id)
        )''')

    cursor.execute('DROP TABLE IF EXISTS request_parameters;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL,
            parameter TEXT NOT NULL,
            mandatory BOOLEAN NOT NULL,
            type TEXT,
            description TEXT,
            ref_table_id INTEGER
        )''')
    
    conn.commit()
    conn.close()

def get_html2text_converter():
    converter = html2text.HTML2Text()
    converter.ignore_links = True
    converter.ignore_images = True
    converter.body_width = 0
    converter.ul_item_mark = '-'
    return converter

def parse_html_table(table_tag: Tag) -> Tuple[Tag | None, List[Tag], List[List[Tag]]]:
    """
    Parse a BeautifulSoup <table> Tag.

    Returns:
        caption: Table's <caption> Tag (if it exists).
        headers: List of column name <th> Tag.
        rows: List of row, which is a List of <td> Tag.
    """
    # 1. extract table caption
    caption = table_tag.find("caption")

    # 2. extract column names from <thead>
    headers = []
    thead = table_tag.find('thead')
    assert thead is not None, "Could not find thead!"
    # assume the header row is in a <tr> inside <thead>
    header_row = thead.find('tr')
    assert header_row is not None, "Could not find header_row tr!"
    for header_cell in header_row.find_all('th'):
        headers.append(header_cell)
    
    # 3. extract rows from <tbody>
    rows = []
    tbody = table_tag.find('tbody')
    assert tbody is not None, "Could not find tbody!"
    for row_tag in tbody.find_all('tr'):
        row = []
        for cell in row_tag.find_all('td'):
            row.append(cell)
        rows.append(row)
    
    return caption, headers, rows

def clean_markdown(text: str) -> str:
    """
    Removes leading/trailing spaces and empty lines from Markdown.
    """
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())

def parse_row(headers: List[Tag], row: List[Tag]):
    '''
    Parse a row in the table.

    Args:
        headers: List of Tags
        row: List of Tags

    Returns:
        parameter, mandatory, type, description
    '''
    converter = get_html2text_converter()

    parameter = None
    mandatory = None
    type = None
    description = None
    for i, cell in enumerate(row):
        column_name = headers[i].get_text().strip()
        cell_text = cell.get_text().strip()
        if column_name in ["参数", "名称", "参数名称", "名", "属性"]:
            parameter = cell_text
        elif column_name in ["是否必选", "必选"]:
            if cell_text == "是":
                mandatory = True
            elif cell_text == "否":
                mandatory = False
        elif column_name in ["参数类型", "类型"]:
            type = cell_text
        elif column_name in ["描述", "说明"]:
            description = clean_markdown(converter.handle(cell.decode_contents()))
        else:
            print(f"ERROR\tunidentified column_name: {column_name}")
    return parameter, mandatory, type, description

def extract_links(tags: List[Tag]) -> List[str]:
    '''
    Extract all links in a list of HTML Tags.
    '''
    links = []
    for tag in tags:
        anchor_tags = tag.find_all('a', href=True)
        links += [a['href'] for a in anchor_tags]
    return links

def is_object_type(type: str) -> bool:
    '''
    Determine if a type is an object type, i.e. needs to reference another parameter table.
    '''
    return "object" in type.lower()

def match_table_id_from_tag(tag: Tag | None) -> int | None:
    '''
    Search for TABLE_ID_PATTERN in a Tag
    '''
    if tag is None:
        return None
    tag_text = tag.get_text()
    match = re.search(TABLE_ID_PATTERN, tag_text)
    if match:
        return int(match.group(1))
    else:
        return None

def parse_doc_page(doc_page: str, html_content: str, db_file: str, target_list: List[str] = None) -> bool:
    '''
    Parse a page describing an API, store to db_file.

    Returns:
        success (bool)
    '''
    # 1. connect to database (or create one if it does not exist)
    conn = sqlite3.connect(db_file)
    api_name = None
    try:
        cursor = conn.cursor()

        # 2. parse HTML content using BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # find "support-main" <div>
        support_main = soup.find("div", class_="support-main")
        assert support_main is not None, "Could not find the support-main div!"

        # find "crumbs" <div> under "support-main"
        # crumbs = support_main.find("div", class_="crumbs")
        # assert crumbs is not None, "Could not find the crumbs div!"
        # crumbs = "/".join(crumb.get_text().strip() for crumb in crumbs.find_all("a"))

        # find "help-content" <div> under "support-main"
        help_content = support_main.find("div", class_="help-content")
        assert help_content is not None, "Could not find the help-content div!"

        # find "updateTime" <div> under "help-content"
        # updateTime = help_content.find("div", class_="updateTime")
        # assert updateTime is not None, "Could not find the updateTime div!"
        # and "updateInfo" <span> under that
        # updateInfo = updateTime.find("span", class_="updateInfo")
        # assert updateInfo is not None, "Could not find the updateInfo span!"
        # update_timestamp = updateInfo.text.strip()

        # find title <h1> under "help-content"
        title_h1 = help_content.find('h1')
        assert title_h1 is not None, "Could not find the title h1!"
        api_name = title_h1.text.strip()

        if target_list is not None and api_name not in target_list:
            return False

        # find the content div, which should be the first div immediately after the title h1
        content_div = title_h1.find_next('div')
        assert content_div is not None, "Could not find the content div!"
        # content = content_div.decode().strip()

        # extract the sections
        # sections = content_div.find_all('div', class_="section", recursive=False)

        # Handle divs outside section e.g. 查询云服务器详情列表, 查询规格详情和规格扩展信息列表
        def organize_sections(content_div: Tag) -> List[Tag]:
            section_divs = []
            last_section_div = None

            all_children = content_div.find_all(recursive=False)
            for child in all_children:
                assert isinstance(child, Tag)
                classes = child.get('class', default=[])
                if child.name == "div" and "section" in classes:
                    section_divs.append(child)
                    last_section_div = child
                else:
                    if last_section_div is not None:
                        child.extract()
                        last_section_div.append(child)
                    else:
                        pass
            
            return section_divs
        sections = organize_sections(content_div)

        # 3. extract API parameters

        def find_section_by_title(sections: List[Tag], title: str) -> Tag | None:
            for section in sections:
                sectiontitle = section.find("h4", class_="sectiontitle", recursive=False)
                if sectiontitle is not None and sectiontitle.get_text().strip() == title:
                    return section
            return None

        # 3.1. apis

        # method and URI
        uri_section = find_section_by_title(sections, "URI")
        assert uri_section is not None, "Could not find the URI section!"
        method_uri_pattern = re.compile(
            r'\b(GET|PUT|POST|DELETE|HEAD|PATCH)\b' # valid HTTP methods in uppercase
            r'[ \t]+' # one or more spaces/tabs (no newlines)
            r'(/\S*)' # a slash followed by non-whitespace characters
        )
        match = method_uri_pattern.search(uri_section.text)
        assert match is not None, "Could not match method and URI!"
        method, uri = match.groups()
        uri = "https://{endpoint}" + uri

        # description
        description_section = find_section_by_title(sections, "功能介绍")
        assert description_section is not None, "Could not find the 功能介绍 section!"
        converter = get_html2text_converter()
        description = clean_markdown(converter.handle(description_section.decode_contents()))

        # insert
        cursor.execute("""
            INSERT INTO apis (name, method, uri, description, root_table_id, doc_page)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (api_name, method, uri, description, -1, doc_page))
        # root_table_id will be updated later

        # get api_id
        cursor.execute("""
            SELECT id FROM apis WHERE name = ?
        """, (api_name, ))
        api_id = cursor.fetchone()[0]

        # 3.2. uri_parameters

        # insert "endpoint" as default
        cursor.execute("""
            INSERT INTO uri_parameters (api_id, parameter, mandatory, type, description)
            VALUES (?, ?, ?, ?, ?)
        """, (api_id, "endpoint", True, "String", "指定承载REST服务端点的服务器域名或IP，不同服务不同区域的Endpoint不同，您可以从地区和终端节点获取。\n例如IAM服务在“华北-北京四”区域的Endpoint为“iam.cn-north-4.myhuaweicloud.com”。"))

        uri_tables = uri_section.find_all('table')
        for uri_table in uri_tables:
            caption, headers, rows = parse_html_table(uri_table)
            for row in rows:
                parameter, mandatory, type_, description = parse_row(headers, row)
                cursor.execute("""
                    INSERT INTO uri_parameters (api_id, parameter, mandatory, type, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (api_id, parameter, mandatory, type_, description))
    
        # 3.3. request_tables and request_parameters

        request_body_section = find_section_by_title(sections, "请求消息") or find_section_by_title(sections, "请求参数")
        assert request_body_section is not None, "Could not find the 请求消息/请求参数 section!"
        request_body_tables = request_body_section.find_all('table')

        # skip request_body_tables[0] if it's about header (Content-Type, X-Auth-Token)
        if len(request_body_tables) >= 1:
            caption_tag, _, _ = parse_html_table(request_body_tables[0])
            if caption_tag is not None and "请求Header参数" in caption_tag.get_text():
                request_body_tables = request_body_tables[1:]

        # preprocess all tables in this section
        tables_info = []
        # list of tuples (table_id (int), caption (str), anchor_id (str), <table> tag (Tag)) for all tables on doc_page
        table_cnt = 0

        for request_body_table in request_body_tables:
            caption_tag = request_body_table.find('caption')
            explicit_table_id = match_table_id_from_tag(caption_tag)
            anchor_id = request_body_table.get('id')
            tables_info.append( (explicit_table_id, caption_tag.get_text() if caption_tag is not None else None, anchor_id, request_body_table) )

        def insert_request_table(table: Tag, base_url: str) -> int:
            '''
            A recursive function that receives a table Tag, inserts it into database, and returns its id.

            returns: table_id of this table
            '''
            nonlocal table_cnt
            # table_cnt += 1
            nonlocal doc_page
            caption, headers, rows = parse_html_table(table)

            # request_tables

            # request_tables.anchor_id
            anchor_id = table.get('id')
            assert anchor_id is not None, f"table {caption} does not have anchor_id"

            # request_tables.table_id
            cursor.execute("""
                SELECT 1
                FROM request_tables
                WHERE api_id = ? AND url = ? AND anchor_id = ?
                LIMIT 1
            """, (api_id, base_url, anchor_id)) # search for the same api_id, url and anchor_id
            result = cursor.fetchone()
            if result is not None: # this table is already inserted, assign a new table_id
                table_cnt += 1
                table_id = table_cnt + 100 # 101, 102, ...
            elif base_url == doc_page: # this table is in doc_page, could use caption
                table_id = match_table_id_from_tag(caption)
                if table_id is None: # fallback
                    table_cnt += 1
                    table_id = table_cnt + 100
            else: # this table is not in doc_page
                table_cnt += 1
                table_id = table_cnt + 100

            # request_tables.caption
            caption = caption.get_text().strip() if caption is not None else None

            # print(f"INSERT INTO request_tables: {api_id} ({api_name}), {table_id}, {caption}, {base_url}, {anchor_id}")
            cursor.execute("""
                INSERT INTO request_tables (api_id, table_id, caption, url, anchor_id)
                VALUES (?, ?, ?, ?, ?)
            """, (api_id, table_id, caption, base_url, anchor_id))

            # request_parameters

            for row in rows:
                parameter, mandatory, type_, description = parse_row(headers, row)

                ref_table_id = None
                if is_object_type(type_): # requires a ref table
                    links = extract_links(row)

                    # consider these types of link in order:
                    # 1) page internal link to another table
                    for link in links:
                        if link.startswith('#'):
                            anchor_id = link[1:]
                            cursor.execute("""SELECT html FROM pages WHERE url = ?""", (base_url, ))
                            html_content = cursor.fetchone()[0]
                            soup = BeautifulSoup(html_content, "html.parser")
                            table_tag = soup.find(id=anchor_id)
                            if table_tag is None or table_tag.name != "table":
                                continue
                            ref_table_id = insert_request_table(table_tag, base_url)
                            if ref_table_id is not None:
                                break
                    
                    # 2) referencing TABLE_ID_PATTERN in description
                    if ref_table_id is None:
                        matches = re.findall(TABLE_ID_PATTERN, description)
                        for matched_id in matches:
                            for this_table_id, _, _, table_tag in tables_info:
                                if matched_id == this_table_id:
                                    ref_table_id = insert_request_table(table_tag, base_url)
                                    break
                            if ref_table_id is not None:
                                break
                    
                    # 3) external link to a section/table in another page
                    if ref_table_id is None:
                        for link in links:
                            # print(link)
                            if not link.startswith('#') and '#' in link:
                                # split the base url and anchor
                                ref_url, _, ref_id = link.partition('#')
                                # download this page and save to db
                                cursor.execute("""SELECT COUNT(*) FROM pages WHERE url = ?""", (ref_url, ))
                                count = cursor.fetchone()[0]
                                if count == 0:
                                    download_and_save_to_db(ref_url, cursor=cursor)
                                cursor.execute("""SELECT html FROM pages WHERE url = ?""", (ref_url, ))
                                ref_html = cursor.fetchone()[0]
                                # find this anchor in html, make sure it's a <table> element, or find the <table> under it (otherwise continue)
                                ref_soup = BeautifulSoup(ref_html, "html.parser")
                                ref_element = ref_soup.find(id=ref_id)
                                # assert ref_element is not None, f"cannot find element with id {ref_id} in page {ref_url}"
                                if ref_element is None:
                                    continue
                                if ref_element.name != "table":
                                    if ref_element.name == "h4":
                                        ref_element = ref_element.parent # h4 -> section
                                    ref_element = ref_element.find("table")
                                    # assert ref_element is not None, f"cannot find table under id {ref_id} in page {ref_url}"
                                    if ref_element is None:
                                        continue
                                # insert this external table (recursively), get its table_id
                                ref_table_id = insert_request_table(ref_element, ref_url)
                            if ref_table_id is not None:
                                break
                    
                    # 4) this parameter's name in another table's caption
                    if ref_table_id is None:
                        for _, caption, _, table_tag in tables_info:
                            if parameter in caption:
                                ref_table_id = insert_request_table(table_tag, base_url)

                    # 5) raise an error at last
                    if ref_table_id is None:
                        raise ValueError(f"cannot find ref_table_id for parameter '{parameter}' (type: {type_})")
                
                # modify the description, delete any TABLE_ID_PATTERN that is not ref_table_id and add ref_table_id
                matches = re.findall(TABLE_ID_PATTERN, description)
                assert len(matches) <= 1, "more than 1 TABLE_ID_PATTERN found in description"
                if ref_table_id is not None:
                    if len(matches) > 0:
                        description = re.sub(TABLE_ID_PATTERN, f"表{ref_table_id}", description)
                    else:
                        description = description + f"\n\n详情请参见表{ref_table_id}"
                else:
                    pass

                cursor.execute("""
                    INSERT INTO request_parameters (api_id, table_id, parameter, mandatory, type, description, ref_table_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (api_id, table_id, parameter, mandatory, type_, description, ref_table_id))

            return table_id
        
        if len(request_body_tables) == 0: # request body is empty
            root_table_id = -1
        else:
            root_table_id = insert_request_table(request_body_tables[0], doc_page)
        cursor.execute("""
            UPDATE apis
            SET root_table_id = ?
            WHERE id = ?
        """, (root_table_id, api_id))

        # 4. commit changes
        conn.commit()
        conn.close()
        print(f"SUCCESS\t{api_name} ({doc_page}) parsed and saved to {db_file}")
        return True

    except Exception as e:
        print(f"ERROR\t{api_name} ({doc_page}) is not saved because an error occured: {e}")
        conn.rollback()
        conn.close()
        return False

def parse(db_file: str, api_list: List[str] = None):
    init_database_for_parse(db_file)

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("""SELECT url, html FROM pages""")
    pages_cnt = 0
    success_cnt = 0
    for url, html in cursor.fetchall():
        pages_cnt += 1
        success = parse_doc_page(url, html, db_file, api_list)
        if success:
            success_cnt += 1
    print(f"parse(): parsed {success_cnt} / {len(api_list) if api_list is not None else pages_cnt} APIs")

if __name__ == "__main__":
    parse(db_file="parse.sqlite")
