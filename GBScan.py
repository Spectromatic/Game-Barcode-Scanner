import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import curses
from curses.textpad import Textbox, rectangle
import logging
import os
import time
import json
import pyperclip

VERSION = "1.0.0"

logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load settings
with open('settings.json', 'r') as f:
    settings = json.load(f)

databases = ["Mobygames", "Pricecharting"]
database_index = 0

# Extract platforms from platform_mapping keys
platform_mapping = settings.get("platform_mapping", {})
platforms = list(platform_mapping.keys())

formats = settings.get("formats", ["NO", "FORMATS", "SPECIFIED"])
conditions = settings.get("conditions", ["NO", "CONDITIONS", "SPECIFIED"])
case_conditions = settings.get("case_conditions", ["NO", "CASE CONDITIONS", "SPECIFIED"])
contents = settings.get("contents", ["NO", "CONTENTS", "SPECIFIED"])
editions = settings.get("editions", ["NO", "EDITIONS", "SPECIFIED"])

selected_platform_index = 0
selected_format_index = 0
selected_condition_index = 0
selected_case_condition_index = 0
selected_content_index = 0
selected_editions_index = 0
selected_title_index = 0
selected_perspective_index = 0

platform_mapping = settings.get("platform_mapping", {})
if not platform_mapping:
    logging.warning("No platform mappings found in settings.json")

for platform in platforms:
    if platform not in platform_mapping:
        logging.warning(f"Missing platform mapping for: {platform}")

global message
message = "Please scan a barcode or press 'ESC' to exit."
global default_message
default_message = message
global message_success_str
message_success_str = " added successfully. Please scan another barcode."
global message_fail_str
message_fail_str = " discarded. Please scan another barcode."
global message_correct_game
message_correct_game = "Is this the correct game? (Y/N or F7 to switch titles, F8 to switch perspectives)"
global message_start
message_start = "Please scan a barcode or press 'ESC' to exit."
global message_no_game
message_no_game = "Game not found. Please scan another barcode."

global barcode
barcode = ""
global game_url
game_url = None
global game_data
game_data = None
global chosen_title
chosen_title = None
global titles
titles = None


def center_text(stdscr, text, y):
    screen_columns = curses.COLS
    center_x = screen_columns // 2
    stdscr.addstr(y, center_x - len(text) // 2, text)

def right_align_text(stdscr, text, y):
    screen_rows, screen_columns = stdscr.getmaxyx()
    if len(text) > screen_columns:
        stdscr.addstr(y, 0, "Error: Console window too small", curses.A_BOLD)
    else:
        stdscr.addstr(y, screen_columns - len(text), text)

def draw_line(stdscr, y):
    screen_columns = curses.COLS
    stdscr.addstr(y, 0, "\u2500" * screen_columns)

#TODO Make possible to right-align
def draw_menu_line(stdscr, y, header_str, color_header, color_selected, color_unselected, index, items):
    menu_separator = " | "
    bookend_str = " "
    header_str = bookend_str + header_str + bookend_str
    stdscr.addstr(y, 0, header_str, color_header | curses.A_UNDERLINE | curses.A_BOLD)
    # Display items
    item_line = bookend_str + menu_separator.join(items) + bookend_str
    stdscr.addstr(y, len(header_str), item_line, curses.A_DIM | curses.A_UNDERLINE | color_unselected)
    # Underline the selected item
    start_pos = len(header_str) + len(bookend_str) + sum(len(item) + len(menu_separator) for item in items[:index])
    stdscr.addstr(y, start_pos, items[index], color_selected | curses.A_UNDERLINE | curses.A_BOLD)

def draw_menu(stdscr):
    platform_str = " PLATFORM (F1) "
    format_str = " FORMAT (F2) "
    condition_str = " CONDITION (F3) "
    content_str = " CONTENT (F4) "
    edition_str = " EDITION (F5) "
    database_str = " DATABASE (F6) "
    
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_CYAN)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_YELLOW)
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_WHITE)
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_MAGENTA)
    curses.init_pair(7, curses.COLOR_MAGENTA, curses.COLOR_WHITE)
    curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(9, curses.COLOR_GREEN, curses.COLOR_WHITE)

    PLATFORM_UNSELECTED = curses.color_pair(1)
    PLATFORM_SELECTED = curses.color_pair(2)
    FORMAT_UNSELECTED = curses.color_pair(3)
    FORMAT_SELECTED = curses.color_pair(4)
    HEADER = curses.color_pair(5)
    CONDITION_UNSELECTED = curses.color_pair(6)
    CONDITION_SELECTED = curses.color_pair(7)
    CONTENT_UNSELECTED = curses.color_pair(8)
    CONTENT_SELECTED = curses.color_pair(9)
    #Platform Menu Placement
    pmenu_y = 0
    fmenu_y = 1
    cmenu_y = 2
    comenu_y = 3
    emenu_y = 4
    dmenu_y = 5

    stdscr.clear()
    
    screen_rows, screen_columns = stdscr.getmaxyx()
    if screen_columns < 30 or screen_rows < 10:  # Adjust these values as needed
        stdscr.addstr(0, 0, "Error: Console window too small", curses.A_BOLD)
    else:
        right_align_text(stdscr, f"\u2524 Game Barcode Scanner {VERSION} \u251c", 0)


    #Draw Platform string
    draw_menu_line(stdscr, pmenu_y, platform_str, HEADER, PLATFORM_SELECTED, PLATFORM_UNSELECTED, selected_platform_index, platforms)

    #Format string
    draw_menu_line(stdscr, fmenu_y, format_str, HEADER, FORMAT_SELECTED, FORMAT_UNSELECTED, selected_format_index, formats)

    #Condition string
    draw_menu_line(stdscr, cmenu_y, condition_str, HEADER, PLATFORM_SELECTED, PLATFORM_UNSELECTED, selected_condition_index, conditions)

    #Content string
    draw_menu_line(stdscr, comenu_y, content_str, HEADER, FORMAT_SELECTED, FORMAT_UNSELECTED, selected_content_index, contents)

    #Edition string
    draw_menu_line(stdscr, emenu_y, edition_str, HEADER, PLATFORM_SELECTED, PLATFORM_UNSELECTED, selected_editions_index, editions)

    #right_align_text(stdscr, , dmenu_y)
    draw_menu_line(stdscr, dmenu_y, database_str, HEADER,FORMAT_SELECTED, FORMAT_UNSELECTED, database_index, databases)

    stdscr.refresh()

def draw_message_window(stdscr, msg_string = message_start):
    message_win = curses.newwin(3, curses.COLS, curses.LINES - 6, 0)
    message_win.box()
    message_win.addstr(1, 1, msg_string)
    message_win.refresh()

def draw_scan_window(stdscr, barcode):
    scan_str = " Scan Barcode "
    
    #Scan string
    stdscr.addstr(curses.LINES - 2, 0, scan_str, curses.A_REVERSE | curses.A_BOLD)
    #Move cursor to the end of the scan string
    stdscr.move(curses.LINES - 2, len(scan_str) + 1)

    stdscr.addstr(curses.LINES -2, len(scan_str) + 1, barcode)

def draw_info(stdscr, game_data, selected_title_index, selected_perspective_index = 0):
    info_win = curses.newwin(curses.LINES - 12, curses.COLS, 6, 0)
    info_win.box()

    if game_data:
        max_lines_per_column = curses.LINES - 15  # Adjust for box and padding
        column_width = curses.COLS // 3
        col = 0
        row = 1

        titles = [game_data.get('title')]
        #Add alternate titles if they exist
        alternate_titles = [value for key, value in game_data.items() if key.startswith('alternate_title')]
        titles.extend(alternate_titles)
        title_highlight = titles[selected_title_index]

        perspectives = [game_data.get('perspective'), game_data.get('alternate_perspective')]
        perspective_highlight = perspectives[selected_perspective_index]

        #If there is no room, divide into columns
        for i, (key, value) in enumerate(game_data.items()):
            if row > max_lines_per_column:
                col += 1
                row = 1
            x = col * column_width + 2  # Adjust for padding
            info_win.addstr(row, x, f"{key.replace('_', ' ')}: ", curses.A_BOLD)
            info_win.addstr(row, x + len(f"{key.replace('_', ' ').title()}: "), f"{value}")
            if key == 'title' or key.startswith('alternate_title'):
                if value == title_highlight:
                    info_win.addstr(row, x + len(f"{key.replace('_', ' ').title()}: "), f"{value}", curses.A_UNDERLINE)
                else:
                    info_win.addstr(row, x + len(f"{key.replace('_', ' ').title()}: "), f"{value}")
            if key == 'perspective' or key == 'alternate_perspective':
                if value == perspective_highlight:
                    info_win.addstr(row, x + len(f"{key.replace('_', ' ').title()}: "), f"{value}", curses.A_UNDERLINE)
                else:
                    info_win.addstr(row, x + len(f"{key.replace('_', ' ').title()}: "), f"{value}")
            
            row += 1

    info_win.refresh()

def search_pricecharting(barcode):
    search_url = f"https://www.pricecharting.com/search-products?q={barcode}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    title = soup.find('h2', {'class': 'product_name'})
    if title:
        title = title.find('a').text.strip()
        logging.debug(f"Debug: Pricecharting Stripped Title: {title}")
        return title
    else:
        logging.debug("Debug: Pricecharting Title not found.")
        return None

def search_mobygames(barcode, selected_platform):
    global platform_mapping
    game_url = None
    search_url = f"https://www.mobygames.com/search/?q={barcode}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the first search result link
    results = soup.find_all('table', {'class': 'table mb'})
    first_result = results[0].find('a')
    logging.debug(f"Debug: Searching Mobygames - First Result: {first_result}")

    # Get the actual platform name from the selected_platform abbreviation
    actual_platform = platform_mapping.get(selected_platform, None)

    # Find the exact game URL that matches the selected platform
    if first_result:
        for result in results:
            platform_tags = result.find_all('small')
            #logging.debug(f"Debug: All Platform Tags: {platform_tags}")
            for platform_tag in platform_tags:
                logging.debug(f"Debug: Searching for {actual_platform} and found Platform Tag: {platform_tag}")
                if platform_tag and actual_platform in platform_tag.text:
                    exact_result = platform_tag.find_previous('a')
                    game_url = exact_result['href']
                    logging.debug(f"Debug: Found more exact game URL: {game_url}")
                    break
    
    if game_url:
        logging.debug(f"Debug: Returning Game URL")
        return game_url
    else:
        logging.debug("Debug: Game URL not found.")
        return None

def scrape_game_data(game_url, selected_platform, selected_format):
    global platform_mapping
    release_date = None
    game_data = {}

    response = requests.get(game_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Extract game data
    title = soup.find('h1', {'class':'mb-0'})
    if title:
        title = title.text.strip()
        game_data['title'] = title
        logging.debug(f"Debug: Scraped Title: {title}")

    alternate_title = soup.find('div', class_='text-sm text-normal text-muted')
    if alternate_title:
        alternate_titles = alternate_title.find_all('span')
        logging.debug(f"Debug: Found Alternate Title: {alternate_titles}")
        i = 1
        for alternate_title in alternate_titles:
            alternate_title = alternate_title.text.strip()
            alternate_title = re.sub(r'^\s*aka:\s*', '', alternate_title).strip()
            game_data[f'alternate_title{i}'] = alternate_title
            logging.debug(f"Debug: Scraped Alternate Title{i}: {alternate_title}")
            i += 1
    else:
        logging.debug("Debug: No Alternate Title found.")

    # Get the actual platform name from the selected_platform abbreviation
    actual_platform = platform_mapping.get(selected_platform, None)
    if not actual_platform:
        logging.debug(f"Error: Unknown platform abbreviation '{selected_platform}'")

    platform = soup.find('ul', id='platformLinks')
    if platform:
        platform = platform.text.strip()
        platforms = ''.join(platform.split()).replace(')', ',').replace('(', ',')

        # Extract the release date for the selected platform
        platform_list = platforms.split(',')
        for i in range(1, len(platform_list), 2):
            if platform_list[i].strip() == actual_platform:
                release_date = platform_list[i - 1].strip()
                break
        game_data['release_date'] = release_date
        logging.debug(f"Debug: Platform-matched Release Date: {release_date}")

    pacing = find_dt(soup, 'Pacing')
    if pacing:
        game_data['pacing'] = pacing
    if game_data.get('pacing') is None:
        game_data['pacing'] = 'Real-Time'
    developer = find_dt(soup, 'Developers')
    if developer:
        game_data['developer'] = developer
    genre = find_dt(soup, 'Genre')
    if genre:
        game_data['genre'] = genre
    perspective = find_dt_mul(soup, 'Perspective')
    if perspective:
        logging.debug(f"Debug: Perspective: {perspective}")
        game_data['perspective'] = perspective.get('Perspective1')
        game_data['alternate_perspective'] = perspective.get('Perspective2')
    # Use Visual as a backup for Perspective
    visual = find_dt(soup, 'Visual')
    if visual and game_data.get('perspective') is None:
        logging.debug(f"Debug: Using Visual as a backup for Perspective: {visual}")
        game_data['perspective'] = visual
    gameplay = find_dt(soup, 'Gameplay')
    if gameplay:
        game_data['gameplay'] = gameplay
    setting = find_dt(soup, 'Setting')
    if setting:
        game_data['setting'] = setting

    moby_score = soup.find('div', class_='mobyscore')
    if moby_score:
        moby_score = moby_score.text.strip()
        game_data['moby_score'] = moby_score
        logging.debug(f"Debug: Scraped Moby Score: {moby_score}")

    # Find the release date that matches the selected platform
    if release_date == None:
        logging.debug("Debug: Release Date not found. Trying another method.")
        release_date = soup.find('dt', string='Released').find_next_sibling('dd').find('a').text.strip()
        release_date = re.search(r'\d{4}', release_date).group()
        logging.debug(f"Debug: Backup Release Date: {release_date}")
        game_data['release_date'] = release_date

    logging.debug(f"Debug: Game Data: {game_data}")
    return game_data

def scrape_moby_specs(game_url):
    game_url = f"{game_url}/specs"
    response = requests.get(game_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    os_found_dict = {}

    # List of operating systems
    os_to_check = ['DOS', '3.1', '95', '98', '2000', 'XP', 'Vista', '7', '8', '10']
    
    specs = soup.find('table', class_='table table-nowrap text-sm')

    if specs:
        os_spec = soup.find('td', string='Minimum OS Class Required:')
        logging.debug(f"Debug: Found OS: {os_spec}")
        os_list = []
        if os_spec:
            os_version = os_spec.find_next_sibling('td').text.strip()
            os_version = os_version.replace('Windows ', '')
            logging.debug(f"Debug: Found OS Version: {os_version}")
            os_list.append(os_version)
            
            # Create a list with each OS and 'Y' or 'N' depending on whether it was found
            # Any OS later will be set to TBD
            found_y = False
            for os in os_to_check:
                if os not in os_list:
                    os_found_dict[os] = 'N'
                    continue
                if not found_y:
                    os_found_dict[os] = 'Y'
                    found_y = True
                    continue
                os_found_dict[os] = 'TBD'

        dx_spec = specs.find('td', string='Minimum DirectX Version Required:')
        logging.debug(f"Debug: Found DirectX: {dx_spec}")
        if dx_spec:
            dx_version = dx_spec.find_next_sibling('td').text.strip()
            #Strip everything that isn't or anything after the version number
            dx_version = re.search(r'\d+(\.\d+)?[a-zA-Z]*$', dx_version).group()
            logging.debug(f"Debug: DirectX Version: {dx_version}")
            os_found_dict['DX'] = 'DX' + dx_version

    if os_found_dict is not None:
        logging.debug(f"Debug: OS Found List: {os_found_dict}")

    return os_found_dict

def find_dt(soup, text):
    element = soup.find('dt', string=text)
    logging.debug(f"Debug: Found Element: {element}")
    if element:
        element = element.find_next_sibling('dd')
        element = element.find('a').text.strip()
        element = element.replace(',', '')
        logging.debug(f"Debug: {text}: {element}")
        return element
    return None

def find_dt_mul(soup, text):
    element = soup.find('dt', string=text)
    logging.debug(f"Debug: Found Element for multiple: {element}")

    primary_value = None
    alternate_value = None
    
    if element:
        siblings = element.find_next_siblings()
        logging.debug(f"Debug: Found Siblings: {siblings}")
        dd_elements = []
        for sibling in siblings:
            if sibling.name == 'dd':
                dd_elements.append(sibling)
                logging.debug(f"Debug: Found dd element: {sibling}")
                logging.debug(f"Debug: dd_elements: {dd_elements}")
                for dd_element in dd_elements:
                    a_tags = dd_element.find_all('a')
                    for a_tag in a_tags:
                        if primary_value is None:
                            primary_value = a_tag.text.strip()
                        elif alternate_value is None:
                            alternate_value = a_tag.text.strip()
            elif sibling.name == 'dt':
                break

    logging.debug(f"Debug: Returning {text}1: {primary_value}, {text}2: {alternate_value}")
    return {f'{text}1': primary_value, f'{text}2': alternate_value}

def handle_platform_selection(key):
    global selected_platform_index
    if key == curses.KEY_F1:
        selected_platform_index = (selected_platform_index + 1) % len(platforms)

def handle_format_selection(key):
    global selected_format_index
    if key == curses.KEY_F2:
        selected_format_index = (selected_format_index + 1) % len(formats)

def handle_condition_selection(key):
    global selected_condition_index
    if key == curses.KEY_F3:
        selected_condition_index = (selected_condition_index + 1) % len(conditions)

def handle_content_selection(key):
    global selected_content_index
    if key == curses.KEY_F4:
        selected_content_index = (selected_content_index + 1) % len(contents)

def handle_editions_selection(key):
    global selected_editions_index
    if key == curses.KEY_F5:
        selected_editions_index = (selected_editions_index + 1) % len(editions)

def handle_database_selection(key):
    global database_index
    if key == curses.KEY_F6:
        database_index = (database_index + 1) % len(databases)

def handle_title_selection(key, game_data):
    global selected_title_index
    if key == curses.KEY_F7:
        logging.debug(f"Hit F7")
        # Collect all titles and alternate titles
        titles = [game_data.get('title')]
        alternate_titles = [value for key, value in game_data.items() if key.startswith('alternate_title')]
        titles.extend(alternate_titles)

        logging.debug(f"Debug: {len(titles)} Available Titles: {titles}")
        logging.debug(f"Debug: Currently selected title: {selected_title_index}")

        # Update the selected_title_index based on the number of titles
        if len(titles) > 1:
            selected_title_index = (selected_title_index + 1) % len(titles)
            logging.debug(f"Debug: Updated selected_title_index: {selected_title_index}")
            logging.debug(f"Debug: Currently selected title: {titles[selected_title_index]}")

def handle_perspective_selection(key, game_data):
    global selected_perspective_index
    if key == curses.KEY_F8 and game_data.get('alternate_perspective') is not None:
        selected_perspective_index = (selected_perspective_index + 1) % 2
        logging.debug(f"Debug: Currently selected perspective: {selected_perspective_index}")

def write_to_file(data, platform):
    # Load settings
    with open('settings.json', 'r') as f:
        settings = json.load(f)

    file_name = f"{platform}_scanned_collection.csv"
    file_exists = os.path.isfile(file_name)
    xls_format = settings.get('use_xls', False)
    xls_collate = settings.get('use_xls_collate_sheets', False)
    clipboard = settings.get('use_clipboard', True)

    # Toggle whether to write xls to a single file with tabs or separate files
    if xls_format:
        file_name = f"{platform}_scanned_collection.xlsx"
        if xls_collate:
            file_name = "scanned_collection.xlsx"

    # Determine columns to drop
    # Drop the specified columns, or the columns that don't match the platform
    drop_columns = []
    for key, columns in settings['dropped_columns'].items():
        if key == platform or (key.startswith('NOT_') and key[4:] != platform):
            # Drop the specified columns, but only if they exist in the DataFrame
            drop_columns.extend([col for col in columns if col in data.columns])

    # Drop columns
    data = data.drop(columns=drop_columns, errors='ignore')    

    # Write the DataFrame to a CSV file with tab-separated fields
    if xls_format:
        with pd.ExcelWriter(file_name, mode='a', engine='overlay') as writer:
            data.to_excel(writer, sheet_name=platform, index=False, header=not file_exists)
            clipboard_data = data.to_excel(index=False)
    else:
        data.to_csv(file_name, mode='a', sep='\t', index=False, header=not file_exists)
        clipboard_data = data.to_csv(sep='\t', index=False)
    if clipboard:
        pyperclip.copy(clipboard_data)

def main(stdscr):
    global selected_platform_index, selected_format_index, selected_condition_index, selected_content_index, selected_editions_index, selected_title_index, selected_perspective_index, database_index, message, barcode, game_url, game_data, titles
    global message_correct_game, message_success_str, message_fail_str, message_no_game

    # Load settings
    with open('settings.json', 'r') as f:
        settings = json.load(f)

    curses.curs_set(1)  # Hide the cursor
    stdscr.nodelay(1)  # Make getch() non-blocking
    stdscr.timeout(100)  # Refresh every 100 milliseconds

    previous_platform_index = selected_platform_index

    while True:
        draw_menu(stdscr)
        draw_scan_window(stdscr, barcode)
        draw_info(stdscr, game_data, selected_title_index, selected_perspective_index)
        if message != default_message:
            draw_message_window(stdscr, message)
        else:
            draw_message_window(stdscr)
        
        key = stdscr.getch()
        
        if game_data:
            message = message_correct_game
            chosen_title = titles[selected_title_index]
            chosen_perspective = perspectives[selected_perspective_index]
        else:
            selected_title_index = 0
            selected_perspective_index = 0

        # Handle escape key
        if key == 27:
            break
        
        handle_platform_selection(key)
        handle_format_selection(key)
        handle_condition_selection(key)
        handle_content_selection(key)
        handle_editions_selection(key)
        handle_database_selection(key)

        def update_game_data():
            global game_data
            if game_data:
                game_data['platform'] = platforms[selected_platform_index] if settings.get('use_full_platform_name', False) else platform_mapping[platforms[selected_platform_index]]
                game_data['format'] = formats[selected_format_index]
                game_data['condition'] = conditions[selected_condition_index]
                game_data['content'] = contents[selected_content_index]
                game_data['edition'] = editions[selected_editions_index]
                if formats[selected_format_index] == "Cartridge" and contents[selected_content_index] == "Loose Disc":
                    contents[selected_content_index] = "Loose Cartridge"
                elif formats[selected_format_index] != "Cartridge" and contents[selected_content_index] == "Loose Cartridge":
                    contents[selected_content_index] = "Loose Disc"

        update_game_data()
        
        if game_data is not None:
            # Check for any alternate titles dynamically
            has_alternate_titles = any(key.startswith('alternate_title') for key in game_data.keys())
            if has_alternate_titles:
                handle_title_selection(key, game_data)
            if game_data.get('alternate_perspective') is not None:
                handle_perspective_selection(key, game_data)
        
        if ord('0') <= key <= ord('9') and game_data == None:
            # Handle number keys for the scan window
            barcode += chr(key)
        
        elif ord('a') <= key <= ord('z') or ord('A') <= key <= ord('Z') and game_data == None:
            # Handle letter keys for the scan window
            barcode += chr(key)

        elif key == ord(' ') and game_data == None:
            barcode += chr(key)

        elif (key == curses.KEY_BACKSPACE or key == 127 or key == 8) and game_data == None:
            barcode = barcode[:-1]

        elif key == 10 and game_data == None:  # Enter key
            if database_index == 0:
                logging.debug(f"Debug: Searching Mobygames for a {platforms[selected_platform_index]} game with barcode: {barcode}")
                game_url = search_mobygames(barcode, platforms[selected_platform_index])
            elif database_index == 1:
                title = search_pricecharting(barcode)
                logging.debug(f"Debug: Pricecharting Returned Title: {title}")
                if title:
                    game_url = search_mobygames(title, platforms[selected_platform_index])
                    logging.debug(f"Debug: Game URL: {game_url}")
                else:
                    message = message_no_game
                    logging.debug("Debug: Game not found.")
                    barcode = ""
            
            # Only do a scrape if a game URL was found
            if game_url != None:
                game_data = scrape_game_data(game_url, platforms[selected_platform_index], formats[selected_format_index])
                if platforms[selected_platform_index] == "PC":
                    extra_game_data = scrape_moby_specs(game_url)
                    if extra_game_data != None:
                        logging.debug(f"Debug: Extra Game Data: {extra_game_data}")
                        logging.debug(f"Debug: DirectX Version: {extra_game_data.get('DX')}")
                        logging.debug(f"Appending to game data: {extra_game_data}")
                        game_data.update(extra_game_data)
                        logging.debug(f"Debug: Updated Game Data: {game_data}")
                
                titles = [game_data.get('title')]
                # Add alternate titles if they exist
                alternate_titles = [value for key, value in game_data.items() if key.startswith('alternate_title')]
                titles.extend(alternate_titles)

                perspectives = [game_data.get('perspective'), game_data.get('alternate_perspective')]
                chosen_title = titles[selected_title_index]
                chosen_perspective = perspectives[selected_perspective_index]
                # Reset the game_url, so you don't get bad data if the next barcode is invalid
                

                #game_data['platform'] = platforms[selected_platform_index]
                game_data['platform'] = platforms[selected_platform_index] if settings.get('use_full_platform_name', False) else platform_mapping[platforms[selected_platform_index]]
                game_data['format'] = formats[selected_format_index]
                game_data['condition'] = conditions[selected_condition_index]
                game_data['content'] = contents[selected_content_index]
                game_data['edition'] = editions[selected_editions_index]

                game_url = None
                barcode = ""
            else:
                message = message_no_game
                logging.debug("Debug: Game not found.")
                barcode = ""
                    
        # Accept the game data and prepare it for writing to the file
        elif (key == ord('y') or key == 10) and game_data != None:

            message = chosen_title + message_success_str
            logging.debug(f"Debug: {chosen_title} added successfully.")
            
            # Move the "The" to the end if the title starts with "The " and it's enabled in settings
            if chosen_title.startswith("The ") and settings.get('suffix_the', True):
                chosen_title = chosen_title[4:] + ", The"
            
            # Set case, sleeve, and manual based on content
            case = 'Y' if contents[selected_content_index] not in ["No Case", "Sleeve Only", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'
            sleeve = 'Y' if contents[selected_content_index] not in ["No Sleeve", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'
            manual = 'Y' if contents[selected_content_index] not in ["No Manual", "Loose Disc", "Loose Cartridge", "Nothing"] else 'N'

            # Prepare the data to write to the file
            data = {
                    "Title": [chosen_title],
                    "Release Date": [game_data.get('release_date')] if game_data.get('release_date') else "",
                    "Platform": platforms[selected_platform_index] if settings.get('use_full_platform_name', False) else platform_mapping[platforms[selected_platform_index]],
                    "Case": [case],
                    "Sleeve": [sleeve],
                    "Manual": [manual],
                    #"Content": contents[selected_content_index],
                    "Condition": conditions[selected_condition_index],
                    "Format": formats[selected_format_index],
                    "Edition": editions[selected_editions_index],
                    "Developer": [game_data.get('developer')] if game_data.get('developer') else "",
                    "Payed": [game_data.get('payed')] if game_data.get('payed') else "",
                    "DOS": [game_data.get('DOS')] if game_data.get('DOS') else "",
                    "3.1": [game_data.get('3.1')] if game_data.get('3.1') else "",
                    "95": [game_data.get('95')] if game_data.get('95') else "",
                    "98": [game_data.get('98')] if game_data.get('98') else "",
                    "ME": [game_data.get('ME')] if game_data.get('ME') else "",
                    "2000": [game_data.get('2000')] if game_data.get('2000') else "",
                    "XP": [game_data.get('XP')] if game_data.get('XP') else "",
                    "Vista": [game_data.get('Vista')] if game_data.get('Vista') else "",
                    "Win7": [game_data.get('7')] if game_data.get('7') else "",
                    "Win10": [game_data.get('10')] if game_data.get('10') else "",
                    "DX": [game_data.get('DX')] if game_data.get('DX') else "",
                    "Ripped": [game_data.get('Ripped')] if game_data.get('Ripped') else "",
                    "Copy Protection": [game_data.get('Copy Protection')] if game_data.get('Copy Protection') else "",
                    "Playable": [game_data.get('Playable')] if game_data.get('Playable') else "",
                    "Spawnable": [game_data.get('Spawnable')] if game_data.get('Spawnable') else "",
                    "Force Feedback": [game_data.get('Force Feedback')] if game_data.get('Force Feedback') else "",
                    "Dimension": [game_data.get('Dimension')] if game_data.get('Dimension') else "",
                    "Time": [game_data.get('pacing')] if game_data.get('pacing') else "",
                    "Perspective": [chosen_perspective] if game_data.get('perspective') else "",
                    "Setting": [game_data.get('setting')] if game_data.get('setting') else "",
                    "Genre": [game_data.get('genre')] if game_data.get('genre') else "",
                    "Gameplay": [game_data.get('gameplay')] if game_data.get('gameplay') else ""
                }
            
            # Re-order the columns based on the order in the settings
            column_order = settings['column_order']
            ordered_data = {key: data[key] for key in column_order if key in data}

            df = pd.DataFrame(ordered_data)
            write_to_file(df, platforms[selected_platform_index])
            logging.debug(f"Debug: Data written to file: {df}")

            # Reset the game data, so we don't get the same data if the next barcode is invalid
            selected_title_index = 0
            selected_perspective_index = 0
            barcode = ""
            game_url = None
            game_data = None
        
        if key == ord('n') and game_data != None:
            selected_title_index = 0
            selected_perspective_index = 0
            barcode = ""
            game_url = None
            game_data = None
            message = chosen_title + message_fail_str
        
        # Check if the selected platform index has changed and set defaults
        if selected_platform_index != previous_platform_index:
            previous_platform_index = selected_platform_index
            platform = platforms[selected_platform_index]
            if platform in settings['platform_defaults']:
                selected_format_index = settings['platform_defaults'][platform]['selected_format_index']
                selected_condition_index = settings['platform_defaults'][platform]['selected_condition_index']
                selected_content_index = settings['platform_defaults'][platform]['selected_content_index']
                selected_editions_index = settings['platform_defaults'][platform]['selected_editions_index']
            elif "Default" in settings['platform_defaults']:
                selected_format_index = settings['platform_defaults']['Default']['selected_format_index']
                selected_condition_index = settings['platform_defaults']['Default']['selected_condition_index']
                selected_content_index = settings['platform_defaults']['Default']['selected_content_index']
                selected_editions_index = settings['platform_defaults']['Default']['selected_editions_index']



            

        

        


curses.wrapper(main)