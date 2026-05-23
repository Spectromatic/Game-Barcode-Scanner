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
logframe = None
logtree = None

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
    
    # Move the "The" to the end if the title starts with "The " and it's enabled in settings
    if selected_title.startswith("The ") and active_settings['toggles'].get('use_the_suffix', True):
        selected_title = selected_title[4:] + ", The"
    
    contents = {}
    
    # Set case, sleeve, and manual based on content
    if active_settings['toggles'].get('use_content_split'):
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
        "Format": active_settings['formats'][active_selections.get("formats", tk.IntVar()).get()],
        "Edition": active_settings['editions'][active_selections.get("editions", tk.IntVar()).get()],
        "Developer": [active_game_data.get('developer')] if active_game_data.get('developer') else "",
        "Payed": [active_game_data.get('payed')] if active_game_data.get('payed') else "",
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
        "Gameplay": [active_taxonomy.get('gameplay')] if active_taxonomy.get('gameplay') else ""
    }
    
    # Re-order the columns based on the order in the settings
    ordered_data = {key: data[key] for key in active_settings['column_order'] if key in data}

    df = pd.DataFrame(ordered_data)

    write_to_file(df, active_settings["platforms"][active_selections.get("platforms", tk.IntVar()).get()])
    game_log(selected_title, selected_platform, active_game_data.get('release_date', ''))
    game_clear()
    game_search_clear()
    game_search_focus()

def game_clear():
    if infoframe is None:
        return
    for widget in infoframe.winfo_children():
        widget.destroy()

    # Clear the active game data and reset the active title and perspective
    global active_game_data, active_taxonomy, active_physical_data, active_title, active_perspective
    active_game_data = {}
    active_taxonomy = {}
    active_physical_data = {}
    active_title = None
    active_perspective = None

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

def game_log(title, platform, release_date):
    global logframe, logtree

    if logframe is None or logtree is None:
        return
    
    logtree.insert("", "end", values=(title, platform, release_date))
    print(f"Debug: Logged game - Title: {title}, Platform: {platform}, Release Date: {release_date}")

def handle_ellipsis(text, max_length=30):
    return text if len(text) <= max_length else text[:max_length-3] + "..."

def handle_error(message):
    # Display the error message in a message box
    messagebox.showerror("Error", message)

def populate_menu(frame, name, options):
    # Populate a menu with the given options
    label = ttk.Label(frame, text=name.capitalize(), width=12, anchor=tk.W)
    label.pack(side=tk.LEFT, padx=4)

    max_length = max(len(option) for option in options)
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
        btn = ttk.Button(frame, text=option, width=max_length, command=lambda i=index: var.set(i))
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
    active_physical_data['content'] = active_settings["contents"][active_selections.get("contents", tk.IntVar()).get()]
    active_physical_data['edition'] = active_settings["editions"][active_selections.get("editions", tk.IntVar()).get()]

    print(f"Debug: Game Data: {active_game_data}")
    print(f"Debug: Taxonomy Data: {active_taxonomy}")
    print(f"Debug: Physical Data: {active_physical_data}")
    return active_game_data

def scrape_moby_specs(game_url):
    game_url = f"{game_url}/specs"
    response = requests.get(game_url)
    soup = bs.BeautifulSoup(response.text, 'html.parser')

    os_found_dict = {}

    # List of operating systems
    os_to_check = ['DOS', '3.1', '95', '98', 'ME', '2000', 'XP', 'Vista', '7', '8', '10']
    
    specs = soup.find('table', class_='table table-nowrap text-sm')

    if specs is None:
        print("Debug: No specs table found.")
        return None

    os_spec = soup.find('td', string='Minimum OS Class Required:')
    print(f"Debug: Found OS: {os_spec}")

    os_list = []
    if os_spec:
        os_version = os_spec.find_next_sibling('td').text.strip()
        os_version = os_version.replace('Windows ', '')
        print(f"Debug: Found OS Version: {os_version}")
        os_list.append(os_version)
        
        # Create a list with each OS and 'Y' or 'N' depending on whether it was found
        # Any OS later will be set to TBD
        found_y = False
        for os in os_to_check:
            if os not in os_list and not found_y:
                os_found_dict[os] = 'N'
                continue
            if not found_y:
                os_found_dict[os] = 'Y'
                found_y = True
                continue
            os_found_dict[os] = 'TBD'

    dx_spec = specs.find('td', string='Minimum DirectX Version Required:')
    print(f"Debug: Found DirectX: {dx_spec}")
    if dx_spec:
        dx_version = dx_spec.find_next_sibling('td').text.strip()
        #Strip everything that isn't or anything after the version number
        dx_version = re.search(r'\d+(\.\d+)?[a-zA-Z]*$', dx_version)
        if dx_version is not None:
            dx_version = dx_version.group()
        print(f"Debug: DirectX Version: {dx_version}")
        os_found_dict['DX'] = 'DX' + dx_version if dx_version else 'Unknown'

    if os_found_dict is not None:
        print(f"Debug: OS Found List: {os_found_dict}")

    return os_found_dict

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
    active_specs = scrape_moby_specs(url)
    update_button_states("normal")
    update_info_frame()

def selections_update(name, value):
    # Update the defaults based on the platform selection
    if name == "platforms":
        settings_set_defaults(value)

    if active_settings is None:
        return

    for setting in active_physical_data.keys():
        setting_plural = setting + "s"
        active_physical_data[setting] = active_settings[setting_plural][active_selections.get(setting_plural, tk.IntVar()).get()]

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
    
    # Clear the info frame
    for widget in infoframe.winfo_children():
        widget.destroy()

    if not active_game_data:
        for i in range(6):
            for j in range(3):
                empty_label = ttk.Label(infoframe, text="", style=f"InfoData{'Even' if (i + j) % 2 == 0 else 'Odd'}.TLabel")
                empty_label.grid(row=i, column=j*2, sticky="nsew")
                empty_label = ttk.Label(infoframe, text="", style=f"InfoData{'Even' if (i + j) % 2 == 0 else 'Odd'}.TLabel")
                empty_label.grid(row=i, column=j*2+1, sticky="nsew")
        return
    
    active_game_items = list(active_game_data.items())
    active_taxonomy_items = list(active_taxonomy.items())
    active_physical_items = list(active_physical_data.items())

    extra_titles = max(len(active_game_data.get('title', [])) - 1, 0)
    extra_perspectives = max(len(active_taxonomy.get('perspective', [])) - 1, 0)
    max_extra = max(extra_titles, extra_perspectives)
    max_rows = max(len(active_game_items) + extra_titles, len(active_taxonomy_items) + extra_perspectives, len(active_physical_items))

    style = ttk.Style()
    style.configure("InfoDataEven.TLabel", background="#f8f8f8")
    style.configure("InfoDataOdd.TLabel", background="#e8e8e8")

    current_title = active_title.get() if isinstance(active_title, tk.StringVar) else None
    current_perspective = active_perspective.get() if isinstance(active_perspective, tk.StringVar) else None

    active_game_data_offset = 0
    active_taxonomy_offset = 0
    active_physical_data_offset = 0
    # Update the info frame with the current game data
    for i in range(max_rows - len(active_game_data.get('title', []))):
        key, value = active_game_items[i] if i < len(active_game_items) else ("", "")
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if (i + active_game_data_offset) % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=i + active_game_data_offset, column=0, sticky="nsew")

        if key and key.lower() == 'title' and len(value) > 1:
            active_title, active_game_data_offset = populate_selections(infoframe, i, active_game_data_offset, current_title, value, 'title', 0, 1)
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(f"{value}"), style=f"InfoData{'Even' if (i + active_game_data_offset) % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=i + active_game_data_offset, column=1, sticky="nsew")

    # Update the info frame with the current taxonomy data
    for j in range(max_rows - len(active_taxonomy.get('perspective', []))):
        key, value = active_taxonomy_items[j] if j < len(active_taxonomy_items) else ("", "")
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if (j + active_taxonomy_offset) % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=j + active_taxonomy_offset, column=2, sticky="nsew")

        if key and key.lower() == 'perspective' and len(value) > 1:
            active_perspective, active_taxonomy_offset = populate_selections(infoframe, j, active_taxonomy_offset, current_perspective, value, 'perspective', 2, 3)
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(f"{value}"), style=f"InfoData{'Even' if (j + active_taxonomy_offset) % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=j + active_taxonomy_offset, column=3, sticky="nsew")

    # Update the info frame with the current physical data
    for k in range(max_rows - max_extra):
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

def write_to_file(data, platform):
    # Load settings
    with open('settings.json', 'r') as f:
        settings = json.load(f)

    file_name = f"{platform}_scanned_collection.csv"
    xls_format = settings['toggles'].get('use_xls', False)
    xls_collate = settings['toggles'].get('use_xls_collate_sheets', False)
    clipboard = settings['toggles'].get('use_clipboard', True)

    # Toggle whether to write xls to a single file with tabs or separate files
    if xls_format:
        file_name = f"{platform}_scanned_collection.xlsx"
        if xls_collate:
            file_name = "scanned_collection.xlsx"

    # Determine columns to drop
    # Drop the specified columns, or the columns that don't match the platform
    drop_columns = []
    for key, columns in settings['columns_to_drop'].items():
        if key == platform or (key.startswith('NOT_') and key[4:] != platform):
            # Drop the specified columns, but only if they exist in the DataFrame
            drop_columns.extend([col for col in columns if col in data.columns])

    # Drop columns
    data = data.drop(columns=drop_columns, errors='ignore')  
    file_exists = os.path.isfile(file_name) 
    mode = 'a' if file_exists else 'w' 

    # Write the DataFrame to a CSV file with tab-separated fields
    if xls_format and file_exists: 
        with pd.ExcelWriter(file_name, mode='a', engine='openpyxl', if_sheet_exists='overlay') as writer:
            start_row = writer.sheets[platform].max_row if platform in writer.sheets else 0
            data.to_excel(writer, sheet_name=platform, index=False, header=not file_exists, startrow=start_row)
    elif xls_format and not file_exists:
        with pd.ExcelWriter(file_name, mode='w', engine='openpyxl') as writer:
            data.to_excel(writer, sheet_name=platform, index=False, header=True)
    else:
        data.to_csv(file_name, mode=mode, sep='\t', index=False, header=not file_exists)
        
    if clipboard:
        clipboard_data = data.to_csv(sep='\t', index=False, header=False)
        pyperclip.copy(clipboard_data)

    return

def main():
    global infoframe, searchentry, logframe, logtree
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
    logtree = ttk.Treeview(logframe, columns=("Title", "Platform", "Release Date"), show="headings", height=5)
    logtree.heading("Title", text="Title")
    logtree.heading("Platform", text="Platform")
    logtree.heading("Release Date", text="Release Date")
    logtree.column("Title", width=200)
    logtree.column("Platform", width=100)
    logtree.column("Release Date", width=100)
    logtree.grid(row=0, column=0, sticky="nsew")
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
        if root.focus_get() != searchentry:
            acceptbutton.invoke()

    def handle_decline_key(event):
        if root.focus_get() != searchentry:
            declinebutton.invoke()

    root.bind_all('<y>', handle_accept_key)
    root.bind_all('<n>', handle_decline_key)
    root.bind_all('<Y>', handle_accept_key)
    root.bind_all('<N>', handle_decline_key)
    root.bind_all('<Control-q>', lambda event: root.quit())

    for frame in frames_padded:
        for child in frame.winfo_children():
            child.grid_configure(padx=4, pady=4)

    settings_set_defaults()
    root.mainloop()

if __name__ == "__main__":
    settings_load()
    main()