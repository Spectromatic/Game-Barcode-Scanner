import json
import os
import pyperclip
import re
import requests
import bs4 as bs
import pandas as pd
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

import sys
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)

active_game_data = {}
active_perspective = None
active_physical_data = {}
active_settings = None
active_selections = {}
active_specs = {}
active_taxonomy = {}
active_title = None
frames = []
frames_padded = []
infoframe = None
searchentry = None
acceptbutton = None
logframe = None
logtree = None

def button_focus_accept():
    global acceptbutton
    if acceptbutton is not None and acceptbutton.instate(['!disabled']):
        acceptbutton.after_idle(acceptbutton.focus_set)

def button_select_all(event=None):
    global searchentry
    if searchentry is None:
        return "break"
    
    searchentry.focus_set()
    searchentry.select_range(0, tk.END)
    searchentry.icursor(tk.END)
    return "break"

def clear_infoframe():
    global infoframe
    if infoframe is None:
        return
    
    # Clear the info frame
    for widget in infoframe.winfo_children():
        widget.destroy()
    
    if not active_game_data:
        for i in range(6):
            for j in range(3):
                empty_label = ttk.Label(infoframe, text="", style=f"InfoData{'Even' if (i) % 2 == 0 else 'Odd'}.TLabel")
                empty_label.grid(row=i, column=j*2, sticky="nsew")
                empty_label = ttk.Label(infoframe, text="", style=f"InfoData{'Even' if (i) % 2 == 0 else 'Odd'}.TLabel")
                empty_label.grid(row=i, column=j*2+1, sticky="nsew")
                infoframe.columnconfigure(j*2, weight=1, uniform="info")
                infoframe.columnconfigure(j*2+1, weight=1, uniform="info")
        return

def cycle_selection(name, direction=1):
    if active_settings is None:
        return
    var = active_selections.get(name)
    if not isinstance(var, tk.IntVar):
        return
    options = active_settings.get(name, [])
    if not options:
        return
    var.set((var.get() + direction) % len(options))

def cycle_setup(name, direction):
    def handler(event):
        cycle_selection(name, direction)
        if searchentry is not None:
            searchentry.focus_set()
    return handler

def game_accept():
    if active_settings is None:
        handle_error("No settings available.")
        return
    
    if active_game_data is None:
        handle_error("No game data available.")
        return
    
    if active_title is None:
        handle_error("No title available.")
        return
    
    selected_title = active_title.get()
    selected_platform = active_settings['platforms'][active_selections.get("platforms", tk.IntVar()).get()]
    selected_contents = active_settings['contents'][active_selections.get("contents", tk.IntVar()).get()]
    selected_format = active_settings['formats'][active_selections.get("formats", tk.IntVar()).get()]
    
    # Move the "The" to the end if the title starts with "The " and it's enabled in settings
    if selected_title.startswith("The ") and active_settings['toggles'].get('use_the_suffix', True):
        selected_title = selected_title[4:] + ", The"
    
    contents = {}
    
    # Set case, sleeve, and manual based on content
    if active_settings.get('toggles', {}).get('use_content_split', False):
        contents['Case'] = 'Y' if selected_contents not in ["No Case", "Manual Only", "Sleeve Only", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'
        contents['Sleeve'] = 'Y' if selected_contents not in ["Case Only", "Manual Only", "No Sleeve", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'
        contents['Manual'] = 'Y' if selected_contents not in ["Case Only", "No Manual", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'
    else:
        contents['Contents'] = selected_contents

    # Prepare the data to write to the file
    data = {
        "Title": [selected_title],
        "Release Date": [active_game_data.get('release_date')] if active_game_data.get('release_date') else "",
        "Platform": active_settings['platform_mapping'][active_settings['platforms'][active_selections.get("platforms", tk.IntVar()).get()]] if active_settings['toggles'].get('use_full_platform_name', False) else active_settings['platforms'][active_selections.get("platforms", tk.IntVar()).get()],
        **contents,
        "Condition": active_settings['conditions'][active_selections.get("conditions", tk.IntVar()).get()],
        "Case Condition": active_settings['case_conditions'][active_selections.get("case_conditions", tk.IntVar()).get()],
        "Format": selected_format,
        "Edition": active_settings['editions'][active_selections.get("editions", tk.IntVar()).get()],
        "Developer": [active_game_data.get('developer')] if active_game_data.get('developer') else "",
        "Payed": [active_game_data.get('payed')] if active_game_data.get('payed') else "",
        "Value": [active_physical_data.get('price')] if active_physical_data.get('price') else "",
        "DOS": [active_specs.get('DOS', '')] if active_specs else "",
        "3.1": [active_specs.get('3.1', '')] if active_specs else "",
        "95": [active_specs.get('95', '')] if active_specs else "",
        "98": [active_specs.get('98', '')] if active_specs else "",
        "ME": [active_specs.get('ME', '')] if active_specs else "",
        "2000": [active_specs.get('2000', '')] if active_specs else "",
        "XP": [active_specs.get('XP', '')] if active_specs else "",
        "Vista": [active_specs.get('Vista', '')] if active_specs else "",
        "Win7": [active_specs.get('7', '')] if active_specs else "",
        "Win10": [active_specs.get('10', '')] if active_specs else "",
        "DX": [active_specs.get('DX', '')] if active_specs else "",
        "Ripped": [active_specs.get('Ripped', '')] if active_specs else "",
        "Copy Protection": [active_specs.get('Copy Protection', '')] if active_specs else "",
        "Playable": [active_specs.get('Playable', '')] if active_specs else "",
        "Spawnable": [active_specs.get('Spawnable', '')] if active_specs else "",
        "Force Feedback": [active_specs.get('Force Feedback', '')] if active_specs else "",
        "Dimension": [active_taxonomy.get('Dimension')] if active_taxonomy.get('Dimension') else "",
        "Time": [active_taxonomy.get('pacing')] if active_taxonomy.get('pacing') else "",
        "Perspective": [active_perspective.get()] if isinstance(active_perspective, tk.StringVar) else [str(active_perspective)] if str(active_perspective) else "",
        "Setting": [active_taxonomy.get('setting')] if active_taxonomy.get('setting') else "",
        "Genre": [active_taxonomy.get('genre')] if active_taxonomy.get('genre') else "",
        "Gameplay": [active_taxonomy.get('gameplay')] if active_taxonomy.get('gameplay') else "",
        "Moby Score": [active_taxonomy.get('moby_score')] if active_taxonomy.get('moby_score') else "",
        "Added": [pd.Timestamp.now().strftime("%Y-%m-%d")],
        "UPC": [active_physical_data.get('upc')] if active_physical_data.get('upc') else ""
    }
    
    # Re-order the columns based on the order in the settings
    ordered_data = {key: data[key] for key in active_settings['column_order'] if key in data}

    df = pd.DataFrame(ordered_data)

    write_to_file(df, active_settings["platforms"][active_selections.get("platforms", tk.IntVar()).get()])
    game_log(selected_title, selected_platform, active_game_data.get('release_date', ''), selected_format)
    game_clear()
    game_search_clear()
    game_search_focus()

def game_clear():
    # Clear the active game data and reset the active title and perspective
    global active_game_data, active_taxonomy, active_physical_data, active_title, active_perspective
    active_game_data = {}
    active_taxonomy = {}
    active_physical_data = {}
    active_title = None
    active_perspective = None

    clear_infoframe()

def game_search_clear():
    # Focus the search entry
    if searchentry is None:
        return
    searchentry.delete(0, tk.END)

def game_search_focus():
    # Focus the search entry
    if searchentry is None:
        return
    searchentry.focus_set()

def game_decline():
    game_clear()
    game_search_focus()

def game_log(title, platform, release_date, format):
    global logframe, logtree
    
    if logframe is None or logtree is None:
        return
    
    tag = 'even' if len(logtree.get_children()) % 2 == 0 else 'odd'
    logtree.insert("", "end", values=(title, release_date, platform, format), tags=(tag,))
    print(f"Debug: Logged game - Title: {title}, Platform: {platform}, Release Date: {release_date}, Format: {format}")

def get_condition():
    if active_settings is None:
        return None
    return active_settings["conditions"][active_selections.get("conditions", tk.IntVar()).get()]

def get_contents():
    if active_settings is None:
        return None
    return active_settings["contents"][active_selections.get("contents", tk.IntVar()).get()]

def get_platform_name():
    if active_settings is None:
        return None
    return active_settings.get("platform_mapping", {}).get(active_settings["platforms"][active_selections.get("platforms", tk.IntVar()).get()])

def handle_ellipsis(text, max_length=30):
    return text if len(text) <= max_length else text[:max_length-3] + "..."

def handle_error(message):
    # Display the error message in a message box
    messagebox.showerror("Error", message)

def handle_single_option(options):
    # Handle the case where there is only one option available
    if not options:
        return ""
    if not isinstance(options, list):
        return str(options)
    if len(options) == 1:
        return str(options[0])
    # If it's not a single option, just return the list back
    return ", ".join(str(x) for x in options)

def is_upc(text: str) -> bool:
    # Check if the text is a 12 or 13 digit UPC
    return bool(re.fullmatch(r'\d{13}', text) or re.fullmatch(r'\d{12}', text))

def populate_menu(frame, name, options):
    # Populate a menu with the given options
    label_text = name.capitalize().replace("_", " ")
    if active_settings is None:
        return
    shortcut = active_settings.get("shortcuts", {}).get(name)
    if shortcut:
        label_text += f" ({shortcut})"

    max_length = max(len(option) for option in options)
    label_width = max(20, len(label_text))
    label = ttk.Label(frame, text=label_text, width=label_width, anchor=tk.W)
    label.pack(side=tk.LEFT, padx=4)
    
    var = tk.IntVar(value=0)
    active_selections[name] = var
    buttons = []

    def on_change(*args):
        idx = var.get()
        for i, btn in enumerate(buttons):
            btn.state(['pressed'] if i == idx else ['!pressed'])
        selections_update(name, idx)

    var.trace_add("write", on_change)

    for index, option in enumerate(options):
        style_name = f"{name.capitalize()}Button.TButton"
        style = ttk.Style()
        style.configure(style_name, background=active_settings["theming"]["custom_colors"].get(name, "#e0e0e0"), foreground="#000000")
        btn = ttk.Button(frame, text=option, width=max_length, command=lambda i=index: var.set(i), style=style_name)
        btn.config(padding=(0, 0))
        btn.pack(side=tk.LEFT)
        buttons.append(btn)

    on_change()

def populate_selections(frame, i, offset, current_selection, value, key, label_col, btn_col):
    active_selection = tk.StringVar(value=current_selection if current_selection is not None and current_selection in value else value[0])
    sel_buttons = []

    for idx, t in enumerate(value):
        if idx == 0:
            row = i + offset
        else:
            offset += 1
            row = i + offset
            empty_label = ttk.Label(frame, text="", style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            empty_label.grid(row=row, column=label_col, sticky="nsew")

        def on_click(v=t, btns=sel_buttons):
            update_info_choice(key, v)
            for b, bv in btns:
                b.state(['pressed'] if bv == v else ['!pressed'])

        btn = ttk.Button(frame, text=handle_ellipsis(t), command=on_click)
        btn.grid(row=row, column=btn_col, sticky="nsew")
        btn.config(padding=(0, 0))
        sel_buttons.append((btn, t))

    for btn, val in sel_buttons:
        btn.state(['pressed'] if val == active_selection.get() else ['!pressed'])

    return active_selection, offset

def recall_log_item(event=None):
    global logtree, active_settings
    if logtree is None:
        return

    row_id = logtree.identify_row(event.y) if event is not None else None
    if not row_id:
        return

    vals = logtree.item(row_id, "values")
    if not vals:
        return
    title = vals[0] if len(vals) > 0 else ""
    platform = vals[2] if len(vals) > 2 else ""

    if active_settings is None:
        handle_error("Settings file is missing")
        return

    toggles = active_settings.get("toggles", {})
    use_xls = toggles.get("use_xls", False)
    xls_collate = toggles.get("use_xls_collate_sheets", False)

    if use_xls:
        file_name = "scanned_collection.xlsx" if xls_collate else f"{platform}_scanned_collection.xlsx"
        df = pd.read_excel(file_name, sheet_name=platform, engine="openpyxl", dtype=str)
    else:
        file_name = f"{platform}_scanned_collection.csv"
        df = pd.read_csv(file_name, sep="\t", dtype=str)

    title_col = next((c for c in df.columns if c.lower() == "title"), df.columns[0])

    # Choose the last matching row
    selected_row = df[df[title_col] == title].tail(1)
    clipboard_data = selected_row.to_csv(sep="\t", index=False, header=False)

    pyperclip.copy(clipboard_data)

    messagebox.showinfo("Recalled", f"Copied latest matching row for '{title}' to clipboard from {file_name}")

def scrape_data_moby_score(soup):
    moby_score = soup.find('div', class_='mobyscore')
    if moby_score is None:
        return
    
    active_taxonomy['moby_score'] = moby_score.text.strip()
    return active_taxonomy.get('moby_score')

def scrape_data_perspective(soup):
    global active_perspective, active_taxonomy
    if soup is None:
        return

    perspectives = scrape_for_dt_mul(soup, 'Perspective') or []

    if not perspectives:
        visual = scrape_for_dt(soup, 'Visual')
        if visual:
            perspectives = [visual]

    active_taxonomy['perspective'] = perspectives
    active_perspective = tk.StringVar(value=perspectives[0]) if perspectives else None

    return active_taxonomy.get('perspective')

def scrape_data_release_date(soup):
    if active_settings is None:
        return
    # Get the actual platform name from the selected_platform abbreviation
    platform_mapping = active_settings.get("platform_mapping", {})
    selected_index = active_selections.get("platforms", tk.IntVar()).get()
    selected_abbrev = active_settings["platforms"][selected_index]
    actual_platform = platform_mapping.get(selected_abbrev, None)
    if not actual_platform:
        handle_error(f"Unknown platform abbreviation '{selected_abbrev}'")
        return None

    platform_soup = soup.find('ul', id='platformLinks')

    if platform_soup is None:
        print("Debug: Release Date not found. Trying another method.")
        release_date = soup.find('dt', string='Released')
        if release_date is not None:
            release_date = release_date.find_next_sibling('dd').find('a').text.strip()
        if release_date is not None:
            release_date = re.search(r'\d{4}', release_date)
        if release_date is not None:
            release_date = release_date.group()
        active_game_data['release_date'] = release_date
        return active_game_data.get('release_date')

    # Convert the platform soup to a list of platforms and release dates
    platform_soup = platform_soup.text.strip()
    platform_list = [part for part in re.split(r'[(),]', platform_soup)]

    # Extract the release date for the selected platform
    for i in range(1, len(platform_list), 2):
        if platform_list[i].strip() == actual_platform:
            release_date = platform_list[i - 1].strip()
            break
    active_game_data['release_date'] = release_date

    return active_game_data.get('release_date')

def scrape_data_title(soup):
    global active_game_data, active_title
    if soup is None:
        return

    titles = []
    title_soup = soup.find('h1', {'class':'mb-0'})
    
    if title_soup is not None:
        titles.append(title_soup.text.strip())

    aka_soup = soup.find('div', class_='text-sm text-normal text-muted')
    if aka_soup is not None:
        for title in aka_soup.find_all('span'):
            title = title.text.strip()
            title = re.sub(r'^\s*aka:\s*', '', title).strip()
            titles.append(title)
    
    active_game_data['title'] = titles
    active_title = tk.StringVar(value=titles[0])
    return titles

def scrape_game_data(game_url):
    global active_game_data, active_taxonomy, active_physical_data

    if active_settings is None:
        return None
    
    active_game_data = {key: value for key, value in active_settings.get("scraped_data", {}).items()}
    active_taxonomy = {key: value for key, value in active_settings.get("scraped_taxonomy", {}).items()}
    print(f"Debug: Initial Game Data: {active_game_data}")
    print(f"Debug: Initial Taxonomy Data: {active_taxonomy}")

    response = requests.get(game_url)

    if response.status_code != 200:
        handle_error(f"Failed to retrieve game data from the website. Status code: {response.status_code}")
        return None

    soup = bs.BeautifulSoup(response.text, 'html.parser')

    if soup is None:
        handle_error("Failed to retrieve game data from the website.")
        return None

    # Extract game data
    scrape_data_moby_score(soup)
    scrape_data_perspective(soup)
    scrape_data_release_date(soup)
    scrape_data_title(soup)

    active_game_data['developer'] = scrape_for_dt(soup, 'Developers') or ''
    active_taxonomy['pacing'] = scrape_for_dt(soup, 'Pacing') or 'Real-Time'
    active_taxonomy['genre'] = scrape_for_dt(soup, 'Genre') or ''
    active_taxonomy['gameplay'] = scrape_for_dt(soup, 'Gameplay') or ''
    active_taxonomy['setting'] = scrape_for_dt(soup, 'Setting') or ''

    active_physical_data['format'] = active_settings["formats"][active_selections.get("formats", tk.IntVar()).get()]
    active_physical_data['condition'] = active_settings["conditions"][active_selections.get("conditions", tk.IntVar()).get()]
    active_physical_data['case_condition'] = active_settings["case_conditions"][active_selections.get("case_conditions", tk.IntVar()).get()]
    active_physical_data['content'] = active_settings["contents"][active_selections.get("contents", tk.IntVar()).get()]
    active_physical_data['edition'] = active_settings["editions"][active_selections.get("editions", tk.IntVar()).get()]

    print(f"Debug: Game Data: {active_game_data}")
    print(f"Debug: Taxonomy Data: {active_taxonomy}")
    print(f"Debug: Physical Data: {active_physical_data}")
    return active_game_data

def scrape_min_os(soup, dict={}):
    os_spec = soup.find('td', string='Minimum OS Class Required:')
    
    if os_spec is None:
        print("Debug: Minimum OS Class not found.")
        return None

    # List of operating systems
    os_to_check = ['DOS', '3.1', '95', '98', 'ME', '2000', 'XP', 'Vista', '7', '8', '10']

    os_list = []

    os_version = os_spec.find_next_sibling('td').text.strip()
    os_version = os_version.replace('Windows ', '')
    print(f"Debug: Found OS Version: {os_version}")
    os_list.append(os_version)
    
    # Create a list with each OS and 'Y' or 'N' depending on whether it was found
    # Any OS later will be set to TBD
    found_y = False
    for os in os_to_check:
        if os not in os_list and not found_y:
            dict[os] = 'N'
            continue
        if not found_y:
            dict[os] = 'Y'
            found_y = True
            continue
        dict[os] = 'TBD'

    return dict

def scrape_dx(specs, dict={}):
    dx_spec = specs.find('td', string='Minimum DirectX Version Required:')

    if dx_spec is None:
        print("Debug: Minimum DirectX Version not found.")
        return None

    if dx_spec:
        dx_version = dx_spec.find_next_sibling('td').text.strip()
        #Strip everything that isn't or anything after the version number
        dx_version = re.search(r'\d+(\.\d+)?[a-zA-Z]*$', dx_version)
        dx_version = dx_version.group() if dx_version else None

        if dx_version and active_settings and active_settings.get("toggles", {}).get("use_dx_point_drop", False):
            dx_version = re.sub(r'\..*$', '', dx_version)

        print(f"Debug: DirectX Version: {dx_version}")
        dict['DX'] = 'DX' + dx_version if dx_version else 'Unknown'

def scrape_prices(game_url, ):
    game_url = f"{game_url}/stores"
    response = requests.get(game_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')

    price_soup = soup.find('table', class_='table table-borders table-hover')

    if price_soup is None:
        print("Debug: No prices table found.")
        return None

    # Get the mapped platform name from settings
    platform_name = get_platform_name()
    if platform_name is None:
        return None
    
    # Find the row that contains the platform name
    platform_row = price_soup.find_all('td', string=lambda text: text and platform_name in text)
    if not platform_row:
        print(f"Debug: No prices found for platform {platform_name}.")
        return None
    
    condition = get_condition()
    sealed = condition and 'sealed' in condition.lower()
    price_type = 'New Price' if sealed else 'Used Price'
    # Get the corresponding Used Price or New Price column depending on the condition
    price_header = price_soup.find('th', string=price_type)
    if price_header is None:
        print(f"Debug: No '{price_type}' column found in prices table.")
        return None
    
    price_index = price_header.parent.find_all('th').index(price_header)
    price = None
    for row in platform_row:
        platform_tr = row.find_parent('tr')
        row_cells = platform_tr.find_all(['th', 'td'])
        price_cell = row_cells[price_index]
        price_text = ' '.join(price_cell.stripped_strings)

        if not re.search(r'[\d\£\$\€]', price_text):
            continue
        
        price = price_text

    return price if price else None

def scrape_price_pricecharting(barcode):
    if active_settings is None:
        return None, None
    
    search_url = f"https://www.pricecharting.com/search-products?type=prices&q={barcode}"
    response = requests.get(search_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')

    price_soup = soup.find('table', class_='js-addable hoverable-rows sortable')

    if price_soup is None:
        print("Debug: No prices table found.")
        return None, None

    # Get the mapped platform name from settings
    platform_name = get_platform_name()
    if platform_name is None:
        return None, None
    
    # Find the row that contains the platform name
    use_pal = active_settings.get("toggles", {}).get("use_pal", False)
    text_to_find = "pal " + platform_name.lower() if use_pal else platform_name.lower()
    platform_text = price_soup.find_all('a', string=lambda text: text and (text_to_find in text.lower()))
    platform_row = platform_text[0].find_parent('tr') if platform_text else None
    if not platform_row:
        print(f"Debug: No prices found for platform {platform_name}.")
        return None, None

    # Get the link to item that matches the platform
    item_cell = platform_row.find('td', class_='title')
    item_link = item_cell.find('a')['href'] if item_cell else None
    
    condition = get_condition()
    sealed = condition and 'sealed' in condition.lower()
    contents = get_contents()
    loose = contents and 'loose' in contents.lower()
    price_type = 'New Price' if sealed else 'Loose' if loose else 'CIB Price'
    # Get the corresponding Used Price or New Price column depending on the condition
    price_header_text = price_soup.find('span', string=price_type)
    print(f"Debug: Price Header Text: {price_header_text}")
    price_header = price_header_text.find_parent('th') if price_header_text else None

    if price_header is None:
        header_tr = price_soup.find('thead').find('tr') if price_soup.find('thead') else None
        if header_tr is None:
            return None, None

        for th in header_tr.find_all('th'):
            txt = th.get_text(separator=' ', strip=True).lower()
            if price_type.lower() in txt or (loose and 'loose' in txt):
                price_header = th
                break

    if price_header is None:
        print(f"Debug: No '{price_type}' column found in prices table.")
        return None, None
    
    price_index = price_header.parent.find_all('th').index(price_header)
    price = None
    for row in platform_row:
        platform_tr = row.find_parent('tr')
        row_cells = platform_tr.find_all(['th', 'td'])
        price_cell = row_cells[price_index]
        price_text = ' '.join(price_cell.stripped_strings)

        if not re.search(r'[\d\£\$\€]', price_text):
            continue
        
        price = price_text

    return (price if price else None, item_link)

def scrape_specs(game_url):
    game_url = f"{game_url}/specs"
    response = requests.get(game_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')
    
    specs = soup.find('table', class_='table table-nowrap text-sm')

    if specs is None:
        print("Debug: No specs table found.")
        return None

    scraped_specs = {}
    scraped_specs = scrape_min_os(specs, scraped_specs) or scraped_specs
    scraped_specs = scrape_dx(specs, scraped_specs) or scraped_specs

    if scraped_specs is not None:
        print(f"Debug: Specs: {scraped_specs}")

    return scraped_specs

def scrape_for_dt(soup, text):
    element = soup.find('dt', string=text)
    print(f"Debug: Found Element: {element}")
    if element:
        element = element.find_next_sibling('dd')
        element = element.find('a').text.strip()
        element = element.replace(',', '')
        print(f"Debug: {text}: {element}")
        return element
    return None

def scrape_for_dt_mul(soup, text):
    # Scrape multiple dd elements for a given dt element and return them as a list
    element = soup.find('dt', string=text)

    if element is None:
        return None
    
    siblings = element.find_next_siblings()
    dd_elements = []
    for sibling in siblings:
        if sibling.name == 'dd':
            dd_elements.append(sibling) 
        elif sibling.name == 'dt':
            break

    a_elements = []
    for dd_element in dd_elements:
        a_tags = dd_element.find_all('a')
        for a_tag in a_tags:
            a_elements.append(a_tag.text.strip())

    return a_elements

def scrape_upc(game_url):
    response = requests.get(game_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')

    upc_soup = soup.find('table', id='attribute')

    if upc_soup is None:
        print("Debug: No UPC table found.")
        return None
    
    # Find the row that contains the platform name
    upc_row = upc_soup.find('tr', itemprop='identifier')
    if not upc_row:
        print(f"Debug: No UPC found {upc_row}.")
        return None
    
    upc = upc_row.find('td', class_='details').text.strip()
    print(f"Debug: Found UPC: {upc}")
    
    return upc if upc else None     

def search_game(query):
    global active_specs
    # Search for the name in the settings and return the corresponding value
    if active_settings is None:
        return None

    search_url = f"https://www.mobygames.com/search/?q={query}"
    response = requests.get(search_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')
    
    # Find the first search result link
    results = soup.find_all('table', {'class': 'table mb'})

    # Get the current platform from the active selections    
    active_platform_index = active_selections.get("platforms", tk.IntVar()).get()
    active_platform = active_settings["platforms"][active_platform_index]

    # Use platform mapping to convert the platform name to the format used on Mobygames
    platform_mapping = active_settings.get("platform_mapping", {})
    platform_name = platform_mapping.get(active_platform, active_platform)

    url = None
    # Find the URL that matches the selected platform
    for result in results:
        platform_tags = result.find_all('small')
        for platform_tag in platform_tags:
            if platform_name not in platform_tag.text:
                continue

            exact_result = platform_tag.find_previous('a')
            url = exact_result['href']
            print(f"Debug: Found URL: {url}")
            break

    if url is None:
        handle_error(f"No results found for {query} for {platform_name}")
        return None
    
    active_game_data = scrape_game_data(url)
    if active_game_data is None:
        handle_error("Failed to scrape game data.")
        return None
    
    # Only the specs for PC titles
    if platform_name.lower() in ["pc", "windows"]:
        active_specs = scrape_specs(url)

    #active_physical_data['price'] = scrape_prices(url)
    active_physical_data['price'], item_link = scrape_price_pricecharting(query)
    if is_upc(query):
        active_physical_data['upc'] = query
        print(f"Debug: Using UPC from search query: {active_physical_data['upc']}")
    elif item_link:
        active_physical_data['upc'] = scrape_upc(item_link)
        print(f"Debug: Scraped UPC: {active_physical_data['upc']}")
    else:
        print("Debug: No UPC found from search query or item page.")
    update_button_states("normal")
    update_info_frame()
    button_focus_accept()

def selections_update(name, value):
    # Update the defaults based on the platform selection
    if name == "platforms":
        settings_set_defaults(value)

    if active_settings is None:
        return
    
    old_condition = active_physical_data.get("condition", "").lower()
    old_content = active_physical_data.get("content", "").lower()

    for setting in active_physical_data.keys():
        setting_plural = setting + "s"
        options = active_settings.get(setting_plural, [])
        if not options:
            continue
        active_physical_data[setting] = active_settings[setting_plural][active_selections.get(setting_plural, tk.IntVar()).get()]

    if name in ("conditions", "contents"):
        new_condition = (active_physical_data.get("condition") or "").lower()
        new_content = (active_physical_data.get("content") or "").lower()
        should_refetch = (name == "conditions" and ("sealed" in new_condition or ("sealed" in old_condition and "sealed" not in new_condition))) or (name == "contents" and ("loose" in new_content or ("loose" in old_content and "loose" not in new_content)))
        price = None
        if should_refetch:
            price, _ = scrape_price_pricecharting(active_physical_data.get("upc") or active_game_data.get("title", [None])[0])

        if price is not None:
            active_physical_data["price"] = price
            print(f"Debug: Re-fetched price for UPC {active_physical_data.get('upc') or active_game_data.get('title', [None])[0]}: {price}")

    update_info_frame()

def settings_load():
    # Load settings from the settings.json file
    global active_settings
    try:
        with open(os.path.join(BASE_DIR, "settings.json"), "r") as f:
            active_settings = json.load(f)
        print("Settings loaded successfully.")
    except Exception as e:
        print(f"Error loading settings: {e}")
        #handle_error(f"Error loading settings: {e}")
        active_settings = None

def settings_set_defaults(platform_index:int = 0):
    # Set default values for settings based on the selected platform
    global active_settings
    if active_settings is None:
        active_settings = {}

    if platform_index is None:
        return

    # Get all the defaults for the selected platform, or use the "Default" defaults if the platform is not found
    platform_settings = active_settings.get("platform_defaults", {})
    platform_name = active_settings["platforms"][platform_index]
    platform_defaults = platform_settings.get(platform_name, platform_settings.get("Default", {}))

    for setting, value in platform_defaults.items():
        if isinstance(active_selections.get(setting), tk.IntVar):
            active_selections[setting].set(value)

    return

def update_button_states(state):
    # Find the search frame in the frames_padded list and update the state of the buttons
    search_frame = None
    for frame in frames_padded:
        if frame.cget("text") == "Search":
            search_frame = frame
            break
    if search_frame is not None:
        for child in search_frame.winfo_children():
            if isinstance(child, ttk.Button):
                child.config(state=state)

def update_info_choice(key, value):
    global active_title, active_perspective
    selected_value = value if isinstance(value, str) else value.get()
    if key == 'title' and isinstance(active_game_data.get('title'), list):
        if active_title is None or not isinstance(active_title, tk.StringVar):
            active_title = tk.StringVar(value=selected_value)
        else:
            active_title.set(selected_value)
    elif key == 'perspective' and isinstance(active_taxonomy.get('perspective'), list):
        if active_perspective is None or not isinstance(active_perspective, tk.StringVar):
            active_perspective = tk.StringVar(value=selected_value)
        else:
            active_perspective.set(selected_value)
    elif key in active_game_data:
        active_game_data[key] = selected_value
    elif key in active_taxonomy:
        active_taxonomy[key] = selected_value
    elif key in active_physical_data:
        active_physical_data[key] = selected_value

def update_info_frame():
    global infoframe, active_game_data, active_taxonomy, active_physical_data, active_title, active_perspective
    if infoframe is None:
        return
    
    if active_settings is None:
        handle_error("Settings file is missing")
        return
    
    clear_infoframe()
    
    active_game_items = list(active_game_data.items())
    active_taxonomy_items = list(active_taxonomy.items())
    active_physical_items = list(active_physical_data.items())

    extra_titles = max(len(active_game_data.get('title', [])) - 1, 0)
    extra_perspectives = max(len(active_taxonomy.get('perspective', [])) - 1, 0)
    max_rows = max(len(active_game_items) + extra_titles, len(active_taxonomy_items) + extra_perspectives, len(active_physical_items))

    current_title = active_title.get() if isinstance(active_title, tk.StringVar) else None
    current_perspective = active_perspective.get() if isinstance(active_perspective, tk.StringVar) else None

    active_game_data_offset = 0
    active_taxonomy_offset = 0
    active_physical_data_offset = 0
    # Update the info frame with the current game data
    for i in range(max_rows - extra_titles):
        key, value = active_game_items[i] if i < len(active_game_items) else ("", "")
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(handle_single_option(f"{key.capitalize()}{suffix}")), style=f"InfoData{'Even' if (i + active_game_data_offset) % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=i + active_game_data_offset, column=0, sticky="nsew")

        if key and key.lower() == 'title' and len(value) > 1:
            active_title, active_game_data_offset = populate_selections(infoframe, i, active_game_data_offset, current_title, value, 'title', 0, 1)
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(handle_single_option(value)), style=f"InfoData{'Even' if (i + active_game_data_offset) % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=i + active_game_data_offset, column=1, sticky="nsew")

    # Update the info frame with the current taxonomy data
    for j in range(max_rows - extra_perspectives):
        key, value = active_taxonomy_items[j] if j < len(active_taxonomy_items) else ("", "")
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if (j + active_taxonomy_offset) % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=j + active_taxonomy_offset, column=2, sticky="nsew")

        if key and key.lower() == 'perspective' and len(value) > 1:
            active_perspective, active_taxonomy_offset = populate_selections(infoframe, j, active_taxonomy_offset, current_perspective, value, 'perspective', 2, 3)
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(handle_single_option(value)), style=f"InfoData{'Even' if (j + active_taxonomy_offset) % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=j + active_taxonomy_offset, column=3, sticky="nsew")

    # Update the info frame with the current physical data
    for k in range(max_rows):
        key, value = active_physical_items[k] if k < len(active_physical_items) else ("", "")
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if (k + active_physical_data_offset) % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=k + active_physical_data_offset, column=4, sticky="nsew")
        value_label = ttk.Label(infoframe, text=handle_ellipsis(f"{value}"), style=f"InfoData{'Even' if (k + active_physical_data_offset) % 2 == 0 else 'Odd'}.TLabel")
        value_label.grid(row=k + active_physical_data_offset, column=5, sticky="nsew")

    cols, rows = infoframe.grid_size()
    for col in range(cols):
        infoframe.columnconfigure(col, weight=1, uniform="info")
    for row in range(rows):
        infoframe.rowconfigure(row, weight=1, minsize=20)

def write_new_headers(data, existing_data):
    desired_order_cols = []
    if active_settings and isinstance(active_settings, dict):
        desired_order_cols = [c for c in (active_settings.get('column_order') or []) if isinstance(c, str)]

    existing_cols = list(existing_data.columns) if existing_data is not None and not existing_data.empty else []
    # Build a full column list that starts with the desired order from settings, 
    # then adds any existing columns that aren't in the desired order, 
    # and finally adds any new columns from the data that aren't in either of those lists
    full_columns = []
    for col in desired_order_cols:
        if col not in full_columns:
            full_columns.append(col)
    for col in existing_cols:
        if col not in full_columns:
            full_columns.append(col)
    for col in data.columns:
        if col not in full_columns:
            full_columns.append(col)
    if not full_columns:
        full_columns = list(data.columns)

    # Reindex existing and new data to the full column set, filling missing cells with empty strings
    existing_reindexed = existing_data.reindex(columns=full_columns, fill_value="") if not existing_data.empty else pd.DataFrame(columns=full_columns)
    new_reindexed = data.reindex(columns=full_columns, fill_value="")

    # Combine and write back so header contains all columns
    combined = pd.concat([existing_reindexed, new_reindexed], ignore_index=True)

    return combined, new_reindexed

def write_to_file(data, platform):
    if active_settings is None:
        return

    file_name = f"{platform}_scanned_collection.csv"
    # Toggle whether to write xls to a single file with tabs or separate files
    if active_settings['toggles'].get('use_xls', False):
        file_name = f"{platform}_scanned_collection.xlsx" if not active_settings['toggles'].get('use_xls_collate_sheets', False) else "scanned_collection.xlsx"
    clipboard = active_settings['toggles'].get('use_clipboard', True)

    # Read the existing file and make sure the platform sheet exists if using xls
    file_exists = os.path.isfile(file_name)
    use_xls = active_settings['toggles'].get('use_xls', False)
    existing = pd.DataFrame()
    if file_exists:
        if use_xls:
            xl = pd.ExcelFile(file_name, engine='openpyxl')
            if platform in xl.sheet_names:
                existing = pd.read_excel(file_name, sheet_name=platform, engine='openpyxl', dtype=str)
        else:
            existing = pd.read_csv(file_name, sep='\t', dtype=str)

    # Make sure the headers are right
    combined, new_reindexed = write_new_headers(data, existing)
    use_split = active_settings.get('toggles', {}).get('use_content_split', False)
    if use_split:
        combined = combined.drop(columns=['Contents'], errors='ignore')
        new_reindexed = new_reindexed.drop(columns=['Contents'], errors='ignore')
    else:
        drop_content_cols = ['Case', 'Sleeve', 'Manual']
        for col in drop_content_cols:
            combined = combined.drop(columns=[col], errors='ignore')
        new_reindexed = new_reindexed.drop(columns=[col for col in drop_content_cols if col in new_reindexed.columns], errors='ignore')

    # Drop the specified columns, or the columns that don't match the platform
    drop_columns = []
    for key, columns in (active_settings.get('columns_to_drop') or {}).items():
        if key == platform or (key.startswith('NOT_') and key[4:] != platform):
            # Drop the specified columns, but only if they exist in the DataFrame
            drop_columns.extend([col for col in (columns or []) if col in combined.columns])
    combined = combined.drop(columns=drop_columns, errors='ignore')  
    new_reindexed = new_reindexed.drop(columns=drop_columns, errors='ignore')

    # Write the file back with new data
    if use_xls:
        with pd.ExcelWriter(file_name, engine='openpyxl', mode='a' if file_exists else 'w', if_sheet_exists='replace') as writer:
            combined.to_excel(writer, sheet_name=platform, index=False)
    else:
        combined.to_csv(file_name, sep='\t', index=False)

    if clipboard:
        pyperclip.copy(new_reindexed.to_csv(sep='\t', index=False, header=False))

def main():
    global infoframe, searchentry, logframe, logtree, acceptbutton
    if active_settings is None:
        handle_error("No settings available.")
        return

    root = tk.Tk()
    root.title("GBScan")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    style = ttk.Style(root)
    if active_settings['toggles'].get('use_custom_ttk_theme', False):
        style.theme_use(active_settings['theming'].get('ttk_theme', 'default'))
    even_bg = active_settings["theming"]["custom_colors"]["row_even_bg"]
    odd_bg = active_settings["theming"]["custom_colors"]["row_odd_bg"]
    style.configure("InfoDataEven.TLabel", background=even_bg)
    style.configure("InfoDataOdd.TLabel", background=odd_bg)

    mainrow = 0
    mainframe = ttk.Frame(root, padding="8")
    mainframe.grid(row=0, column=0, sticky=tk.N+tk.S+tk.E+tk.W)

    contextrow = 0
    contextframe = ttk.LabelFrame(mainframe, text="Setup", padding="8")
    contextframe.grid(row=mainrow, column=0, sticky=tk.W+tk.E)
    mainrow += 1

    platformframe = ttk.Frame(contextframe, padding="2")
    platformframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(platformframe)
    contextrow += 1

    populate_menu(platformframe, "platforms", active_settings["platforms"])

    formatframe = ttk.Frame(contextframe, padding="2")
    formatframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(formatframe)
    contextrow += 1

    populate_menu(formatframe, "formats", active_settings["formats"])

    conditionframe = ttk.Frame(contextframe, padding="2")
    conditionframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(conditionframe)
    contextrow += 1

    populate_menu(conditionframe, "conditions", active_settings["conditions"])

    caseconditionframe = ttk.Frame(contextframe, padding="2")
    caseconditionframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(caseconditionframe)
    contextrow += 1

    populate_menu(caseconditionframe, "case_conditions", active_settings["case_conditions"])

    contentframe = ttk.Frame(contextframe, padding="2")
    contentframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(contentframe)
    contextrow += 1

    populate_menu(contentframe, "contents", active_settings["contents"])

    editionframe = ttk.Frame(contextframe, padding="2")
    editionframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(editionframe)
    contextrow += 1

    populate_menu(editionframe, "editions", active_settings["editions"])

    databaseframe = ttk.Frame(contextframe, padding="2")
    databaseframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(databaseframe)
    contextrow += 1

    infoframe = ttk.LabelFrame(mainframe, text="Info", padding="2", relief=tk.SUNKEN)
    infoframe.grid(row=mainrow, column=0, sticky="nsew")
    frames_padded.append(infoframe)
    mainrow += 1

    update_info_frame()

    logframe = ttk.LabelFrame(mainframe, text="Log", padding="2")
    logframe.grid(row=mainrow, column=0, sticky="nsew")
    frames_padded.append(logframe)
    mainrow += 1

    # Add a scrollable tree view to the log frame with 5 rows visible at a time and 3 columns for Title, Platform, and Release Date
    logtree = ttk.Treeview(logframe, columns=("Title", "Release Date", "Platform", "Format"), show="headings", height=5)
    logtree.heading("Title", text="Title")
    logtree.heading("Platform", text="Platform")
    logtree.heading("Release Date", text="Release Date")
    logtree.heading("Format", text="Format")
    logtree.column("Title", width=200)
    logtree.column("Release Date", width=50)
    logtree.column("Platform", width=50)
    logtree.column("Format", width=50)
    logtree.grid(row=0, column=0, sticky="nsew")
    logtree.tag_configure('even', background=even_bg)
    logtree.tag_configure('odd', background=odd_bg)
    logframe.rowconfigure(0, weight=1)
    logframe.columnconfigure(0, weight=1)

    searchframe = ttk.LabelFrame(mainframe, text="Search", padding="2")
    searchframe.grid(row=mainrow, column=0, sticky="ew")
    searchframe.columnconfigure(1, weight=1)
    frames_padded.append(searchframe)
    mainrow += 1

    searchlabel = ttk.Label(searchframe, text="Barcode:")
    searchlabel.grid(row=0, column=0, sticky=tk.W)
    searchentry = ttk.Entry(searchframe, width=40)
    searchentry.grid(row=0, column=1, sticky=tk.W+tk.E)
    searchbutton = ttk.Button(searchframe, text="Search", command=lambda: search_game(searchentry.get() if searchentry is not None else ""))
    searchbutton.grid(row=0, column=2, sticky=tk.W)

    acceptbutton = ttk.Button(searchframe, text="Accept", state="disabled", command=lambda: game_accept())
    acceptbutton.grid(row=0, column=3, sticky=tk.W)
    declinebutton = ttk.Button(searchframe, text="Decline", state="disabled", command=lambda: game_decline())
    declinebutton.grid(row=0, column=4, sticky=tk.W)

    # Invoke the Search button when Enter is pressed inside the entry
    searchentry.bind('<Return>', lambda event: searchbutton.invoke())
    # Make the search entry focused when the application starts
    searchentry.focus()
    def handle_accept_key(event):
        if root.focus_get() != searchentry and acceptbutton is not None and acceptbutton['state'] == 'normal':
            acceptbutton.invoke()

    def handle_decline_key(event):
        if root.focus_get() != searchentry and declinebutton is not None and declinebutton['state'] == 'normal':
            declinebutton.invoke()

    logtree.bind("<Double-1>", recall_log_item)
    root.bind_all('<y>', handle_accept_key)
    root.bind_all('<n>', handle_decline_key)
    root.bind_all('<Y>', handle_accept_key)
    root.bind_all('<N>', handle_decline_key)
    root.bind_all('<Control-q>', lambda event: root.quit())
    if searchentry is not None:
        root.bind_all('<Control-a>', button_select_all)

    # Get the shortcuts and bind them, with and without shift if applicable
    shortcuts = active_settings.get("shortcuts", {}) if active_settings else {}
    for name, key in shortcuts.items():
        root.bind_all(f"<{key}>", cycle_setup(name, 1))
        if not key.startswith("shift-"):
            root.bind_all(f"<Shift-{key}>", cycle_setup(name, -1))

    for frame in frames_padded:
        for child in frame.winfo_children():
            child.grid_configure(padx=4, pady=4)

    settings_set_defaults()
    root.mainloop()

if __name__ == "__main__":
    settings_load()
    main()