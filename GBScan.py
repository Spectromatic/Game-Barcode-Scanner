import colorsys
import hashlib
import json
import os
import pyperclip
import re
import requests
import bs4 as bs
import pandas as pd
import subprocess
import tkinter as tk
import threading
import webbrowser

from io import BytesIO
from openpyxl import load_workbook
from openpyxl.styles import Border, PatternFill, Side
from openpyxl.utils import get_column_letter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageTk
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, SimpleDocTemplate, Paragraph
from reportlab.pdfbase.pdfmetrics import stringWidth
from xml.sax.saxutils import escape
from tkinter import ttk
from tkinter import messagebox, simpledialog
from tooltip import Tooltip, CanvasTooltip
from typing import Literal, cast
from urllib.parse import quote_plus

import sys
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
OUTPUT_DIR = Path(f"{BASE_DIR}/Output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_PER_ROW = 3
active_game_data = {}
active_game_is_new = False
active_perspective = None
active_contexts = {}
active_settings = None
active_selections = {}
active_specs = {}
active_taxonomy = {}
active_source_taxonomy = {}
active_source_game_data = {}
active_title = None
app_root = None
frames = []
frames_padded = []
infoframe = None
choicesframe = None
contextframe = None
contextlist = []
searchentry = None
acceptbutton = None
declinebutton = None
logframe = None
logtree = None
_exclusion_image_refs = []
_os_version_image_refs = []
missing_fields = {}
thumbnail_label = None
thumbnail_image = None
thumbnail_tooltip = None
thumbnail_refresh_btn = None
export_status = {}
collection_stats_labels = {}
col_stats_chart = {}
col_stats_chart_data = {}
col_stats_graph_frame = None
active_pricecharting_soup = None
active_pricecharting_requested_url = None
active_pricecharting_url = None

def add_id(key):
    print(f"Debug: Adding Moby ID")
    global active_game_data
    if not active_game_data:
        handle_error("No game data available.")
        return

    moby_id = simpledialog.askstring("Add MobyGames ID", f"Enter the MobyGames ID for '{active_game_data.get('title', '')}':")
    if moby_id is None:
        return

    moby_id = moby_id.strip()
    if not moby_id.isdigit():
        print(f"Debug: Invalid Moby ID '{moby_id}' provided.")
        return

    moby_url = f"https://www.mobygames.com/game/{moby_id}"
    thumbnail_path = handle_thumbnail_rename(moby_url)
    active_game_data[key] = moby_url

    if active_game_is_new:
        missing_fields.pop(key, None)
        update_info_frame()
        update_thumbnail(thumbnail_path)
        return

    missing_fields.pop(key, None)
    update_info_frame()
    update_thumbnail(thumbnail_path)

def add_upc():
    if not active_game_data:
        return

    new_upc = simpledialog.askstring("Add UPC", "Enter a 12- or 13-digit UPC:")
    if new_upc is None:
        return

    new_upc = new_upc.strip()
    if not is_upc(new_upc):
        handle_error("UPC must contain exactly 12 or 13 digits.")
        return

    existing_upcs = [value.strip() for value in str(active_game_data.get("upc", "")).split(",") if value.strip()]

    if new_upc not in existing_upcs:
        existing_upcs.append(new_upc)
        print(f"Debug: Added new UPC '{new_upc}'. There's now {len(existing_upcs)} UPCs.")

    active_game_data["upc"] = ", ".join(existing_upcs)
    update_info_frame()

def add_url(key):
    print(f"Debug: Adding URL for key '{key}'")
    global active_game_data
    if not active_game_data:
        handle_error("No game data available.")
        return

    new_url = simpledialog.askstring("Add URL", f"Enter the pricecharting URL for '{active_game_data.get('title', '')}':")
    if new_url is None:
        return

    new_url = new_url.strip()
    if not new_url.startswith("https://www.pricecharting.com"):
        handle_error("URL must start with 'https://www.pricecharting.com'.")
        return

    # Scrape for the price if we don't already have one
    if not active_contexts.get("price"):
        price, _ = scrape_pricecharting_price(active_game_data.get("upc") or active_game_data.get("title", ""), known_url=new_url)
        if price is not None:
            active_contexts["price"] = price

    if active_game_is_new:
        active_game_data[key] = new_url
        missing_fields.pop(key, None)
        update_info_frame()
        handle_thumbnail_missing()
        return

    active_game_data[key] = new_url
    missing_fields.pop(key, None)
    update_info_frame()
    handle_thumbnail_missing()

def append_new_source_record():
    if active_settings is None:
        handle_error("No settings available.")
        return

    platform = get_platform_name()
    record = get_source_record()

    source_file = Path(f"{BASE_DIR}/Data/{platform}.xlsx")
    source_data = pd.read_excel(source_file, engine="openpyxl", dtype=str).fillna("")
    source_data.columns = handle_normalized_list(source_data.columns)

    normalized_record = {str(key).lower().replace(" ", "_"): value for key, value in record.items()}
    new_row = {column: normalized_record.get(column, "") for column in source_data.columns}

    source_data = pd.concat([source_data, pd.DataFrame([new_row])], ignore_index=True)
    source_data.to_excel(source_file, engine="openpyxl", index=False)

def create_source_diff():
    # Create a file in the Diff directory to track new titles
    platform = get_platform_name()
    diff_dir = Path(f"{BASE_DIR}/Data/Diff")
    diff_dir.mkdir(parents=True, exist_ok=True)
    diff_file = diff_dir / f"{platform}_new.json"
    records = []

    if diff_file.exists():
        with diff_file.open("r", encoding="utf-8") as source:
            loaded_records = json.load(source)
            if isinstance(loaded_records, list):
                records = loaded_records

    record = get_source_record()
    normalized_record = {str(key).lower().replace(" ", "_"): value for key, value in record.items()}
    title = handle_normalized_text(normalized_record.get("title", ""))

    # Replace an older diff entry for this title.
    records = [item for item in records if handle_normalized_text(item.get("title", "")) != title]
    records.append(normalized_record)

    with diff_file.open("w", encoding="utf-8") as destination:
        json.dump(records, destination, indent=4, ensure_ascii=True)

def export_collection(export_format: str):
    generated_files = []
    if active_settings is None:
        return

    collection_path = get_collection_path()
    workbook = pd.ExcelFile(collection_path, engine="openpyxl")

    for platform in workbook.sheet_names:
        data = pd.read_excel(collection_path, sheet_name=platform, engine="openpyxl", dtype=str,).fillna("")
        columns_to_drop = {str(column).strip().casefold() for column in get_columns_to_drop(platform)}

        column_export = active_settings.get("column_export", {})
        export_columns = [str(column) for column in column_export if str(column).strip() and str(column).strip().casefold() not in columns_to_drop]
        actual_columns = {str(column).strip().casefold(): column for column in data.columns}
        selected_columns = [actual_columns[column.casefold()] for column in export_columns if column.casefold() in actual_columns]

        if not selected_columns:
            continue

        export_data = data.loc[:, selected_columns]

        # Apply export sorting if specified in the settings.
        sort_column = active_settings.get("export_sort", {}).get("column", "Title")
        sort_order = active_settings.get("export_sort", {}).get("order", "ascending")

        if sort_column in export_data.columns:
            ascending = sort_order != "descending"

            # Treat numeric-looking columns numerically instead of alphabetically.
            numeric_values = pd.to_numeric(export_data[sort_column].astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", "", regex=False), errors="coerce")

            if numeric_values.notna().any():
                export_data = (export_data.assign(_export_sort_value=numeric_values).sort_values("_export_sort_value", ascending=ascending, na_position="last", kind="stable").drop(columns="_export_sort_value"))
            else:
                export_data = export_data.sort_values(sort_column, ascending=ascending, na_position="last", kind="stable", key=lambda values: values.astype(str).str.casefold())

        if export_format == "tsv":
            tsv_folder = OUTPUT_DIR / "TSV"
            tsv_folder.mkdir(parents=True, exist_ok=True)
            export_data.to_csv(tsv_folder / f"{platform} Collection.tsv", sep="\t", index=False)
        elif export_format == "csv":
            csv_folder = OUTPUT_DIR / "CSV"
            csv_folder.mkdir(parents=True, exist_ok=True)
            export_data.to_csv(csv_folder / f"{platform} Collection.csv", index=False)
        elif export_format == "xlsx":
            xlsx_folder = OUTPUT_DIR / "XLSX"
            xlsx_folder.mkdir(parents=True, exist_ok=True)
            export_data.to_excel(xlsx_folder / f"{platform} Collection.xlsx", index=False, engine="openpyxl")
        elif export_format == "pdf":
            pdf_folder = OUTPUT_DIR / "PDF"
            pdf_folder.mkdir(parents=True, exist_ok=True)
            pdf_path = export_pdfs(platform, export_data, pdf_folder)
            if pdf_path is not None:
                generated_files.append(str(pdf_path))

    return generated_files

def export_pdfs(platform, data, pdf_folder):
    if active_settings is None:
        return

    if data is None or data.empty and len(data.columns) == 0:
        return None

    column_export = active_settings.get("column_export", {})
    if not column_export:
        handle_error("No columns have been selected for PDF export.")
        return

    export_colors = active_settings.get("theming", {}).get("export_colors", {})
    export_gradients = active_settings.get("theming", {}).get("export_gradients", {})

    data = data.fillna("")

    styles = getSampleStyleSheet()
    title_style = styles["Heading2"]
    header_style = ParagraphStyle("PdfHeader", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=8, textColor=colors.white)
    cell_style = ParagraphStyle("PdfCell", parent=styles["Normal"], fontName="Courier", fontSize=6, leading=7)
    paragraph_alignments = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}

    # PDF Page Setup
    pdf_path = pdf_folder / f"{platform} Collection.pdf"
    margin = 2 * mm
    document = SimpleDocTemplate(str(pdf_path), pagesize=landscape(A4), leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin)

    # PDF Cell Setup
    cell_padding = 6
    character_width = cell_style.fontSize * 0.6
    column_widths = [max(1, int(column_export[str(column)]["width"])) * character_width + cell_padding for column in data.columns]

    header_data = []
    for column_index, (column, column_width) in enumerate(zip(data.columns, column_widths)):
        character_count = max(1, int(column_export[str(column)]["width"]))
        header_text = str(column)[:character_count]

        available_width = max(1, column_width - cell_padding)
        while (len(header_text) > 1 and stringWidth(header_text, header_style.fontName, header_style.fontSize,) > available_width):
            header_text = header_text[:-1]

        align = column_export[str(column)].get("align", "left")
        if align not in paragraph_alignments:
            align = "left"

        column_header_style = ParagraphStyle(f"PdfHeader{column_index}", parent=header_style, alignment=cast(Literal[0, 1, 2, 4], paragraph_alignments[align]))
        header_data.append(Paragraph(f"<nobr>{escape(header_text)}</nobr>", column_header_style,))

    table_data = [header_data]

    for row in data.itertuples(index=False, name=None):
        table_row = []

        for column_index, (column, value) in enumerate(zip(data.columns, row)):
            character_count = max(1, int(column_export[str(column)]["width"]))
            value_text = str(value).strip()

            if "url" in str(column).casefold() and value_text.startswith(("http://", "https://")):
                if str(column).casefold() == "url":
                    link_text = "MobyGames"
                elif str(column).casefold() == "price url":
                    link_text = "PriceCharting"
                elif str(column).casefold() == "gameplay url":
                    link_text = "Gameplay"
                else:
                    link_text = "Open Link"

                link_text = link_text[:character_count]
                cell_text = (f'<nobr><link href="{escape(value_text)}">{escape(link_text)}</link></nobr>')
            else:
                cell_text = (f"<nobr>{escape(value_text[:character_count])}</nobr>")

            align = column_export[str(column)].get("align", "left")
            if align not in paragraph_alignments:
                align = "left"

            column_cell_style = ParagraphStyle(f"PdfCell{column_index}", parent=cell_style, alignment=cast(Literal[0, 1, 2, 4], paragraph_alignments[align]))
            table_row.append(Paragraph(cell_text, column_cell_style))

        table_data.append(table_row)

    table = LongTable(table_data, colWidths=column_widths, repeatRows=1, splitByRow=1,)

    custom_colors = active_settings.get("theming", {}).get("custom_colors", {})
    even_background = colors.HexColor(custom_colors.get("row_even_bg", "#f8f8f8"))
    odd_background = colors.HexColor(custom_colors.get("row_odd_bg", "#e8e8e8"))
    yes_background = colors.HexColor(custom_colors.get("yes", "#d8ffd8"))
    no_background = colors.HexColor(custom_colors.get("no", "#ffd8d8"))

    yes_symbol = str(active_settings.get("symbols", {}).get("yes", "Y")).casefold()
    no_symbol = str(active_settings.get("symbols", {}).get("no", "N")).casefold()

    padding_vertical = 1
    padding_horizontal = 1

    table_style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3F5F73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), padding_horizontal),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding_horizontal),
        ("TOPPADDING", (0, 0), (-1, -1), padding_vertical),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding_vertical),
    ]

    for row_index in range(1, len(table_data)):
        row_background = even_background if row_index % 2 == 1 else odd_background
        table_style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), row_background))

    for row_index, row in enumerate(data.itertuples(index=False, name=None), start=1):
        for column_index, value in enumerate(row):
            value_text = handle_normalized_text(value)

            if value_text == yes_symbol:
                table_style_commands.append((
                        "BACKGROUND",
                        (column_index, row_index),
                        (column_index, row_index),
                        yes_background,
                    ))
            elif value_text == no_symbol:
                table_style_commands.append((
                        "BACKGROUND",
                        (column_index, row_index),
                        (column_index, row_index),
                        no_background,
                    ))

            # Apply export gradient if available
            gradient_color = get_color_export_gradient(data.columns[column_index], value, data, export_gradients)
            if gradient_color is not None:
                table_style_commands.append((
                    "BACKGROUND",
                    (column_index, row_index),
                    (column_index, row_index),
                    gradient_color,
                ))

            # Apply export color if available
            color_key = get_color_export(data.columns[column_index], value)
            export_color = export_colors.get(color_key)
            if export_color is None:
                continue
            table_style_commands.append((
                    "BACKGROUND",
                    (column_index, row_index),
                    (column_index, row_index),
                    colors.HexColor(export_color),
                ))
            
    for column_index, column in enumerate(data.columns):
        align = column_export[str(column)].get("align", "left")

        table_style_commands.append((
                "ALIGN",
                (column_index, 0),
                (column_index, -1),
                align.upper(),
            ))

    table.setStyle(TableStyle(table_style_commands))
    platform_full_name = get_platform_full_name(platform)
    document.build([Paragraph(escape(str(f"{platform_full_name} Collection {get_timestamp()}")), title_style), table,])

    return pdf_path

def apply_taxonomy_style(key, menu):
    style_name = ("ModifiedTaxonomy.TMenubutton" if is_source_taxonomy_changed(key) else "Taxonomy.TMenubutton")
    menu.configure(style=style_name)

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
    global infoframe, active_game_data, active_taxonomy, active_contexts, active_title, active_perspective
    if infoframe is None:
        return
    
    if active_settings is None:
        return
    
    # Clear the info frame
    for widget in infoframe.winfo_children():
        widget.destroy()

    if not active_game_data:
        # Set using types from settings (preserve list vs scalar)
        active_game_data = {k: "" for k, v in active_settings.get("scraped_data", {}).items()}
        active_taxonomy = {k: "" for k, v in active_settings.get("taxonomy", {}).items()}

        # Set common physical/context fields and any custom contexts
        active_contexts = {}
        for k in get_all_contexts():
            active_contexts[k] = get_context_data(k)
        for ctx in ("payed", "price"):
            active_contexts[ctx] = ""
        

        active_title = None
        active_perspective = None

        # Render the Add-buttons via the existing renderer
        update_info_frame()
        return

def color_scanned_collection(file_name, sheet_name):
    if active_settings is None:
        return

    workbook = load_workbook(file_name)
    worksheet = workbook[sheet_name]

    even_fill = PatternFill(fill_type="solid", fgColor=active_settings["theming"]["custom_colors"]["row_even_bg"].lstrip("#"),)
    odd_fill = PatternFill(fill_type="solid", fgColor=active_settings["theming"]["custom_colors"]["row_odd_bg"].lstrip("#"),)
    yes_fill = PatternFill(fill_type="solid", fgColor=active_settings["theming"]["custom_colors"]["yes"].lstrip("#"),)
    no_fill = PatternFill(fill_type="solid", fgColor=active_settings["theming"]["custom_colors"]["no"].lstrip("#"),)

    border_color = active_settings["theming"]["custom_colors"]["export_border"].lstrip("#")
    thin_side = Side(style="thin", color=border_color)
    data_border = Border(bottom=thin_side, right=thin_side)

    for row_number in range(2, worksheet.max_row + 1):
        fill = even_fill if row_number % 2 == 0 else odd_fill

        for column_number in range(1, worksheet.max_column + 1):
            cell = worksheet.cell(row=row_number, column=column_number)
            cell.fill = fill
            cell.border = data_border
            if str(cell.value).casefold() == active_settings["symbols"]["yes"].casefold():
                cell.fill = yes_fill
            elif str(cell.value).casefold() == active_settings["symbols"]["no"].casefold():
                cell.fill = no_fill

    workbook.save(file_name)

def context_add(frame, entries, row_idx = 0, main_contextframe=None):
    if active_settings is None:
        return
    
    # Prompt the user for a new context name
    new_context = simpledialog.askstring("Add Context", "Enter the name of the new context:")
    if not new_context:
        return
    
    key = new_context.lower()
    
    # Add the new context to the settings
    active_settings.setdefault("custom_context", {})[key] = []

    # Duplicate fallback color into custom_colors so this context gets its own color
    theming = active_settings.setdefault("theming", {})
    custom_colors = theming.setdefault("custom_colors", {})
    fallback = custom_colors.get("custom_context_fallback", "#00AAAA")
    if key not in custom_colors:
        custom_colors[key] = fallback

    # Add the new context to the column order
    if key not in [col.lower() for col in active_settings.get("column_order", [])]:
        active_settings.setdefault("column_order", []).append(new_context)
    
    # Update the UI to reflect the new context
    settings_save()
    populate_context_setup(frame, entries, row_idx, main_contextframe)
    if main_contextframe is not None:
        populate_context_frames(main_contextframe, 0, contextlist, frames)

def context_delete(frame, entries, context_choice, main_contextframe=None):
    if active_settings is None:
        return

    key = context_choice.lower()

    # Remove the duplicated custom color
    active_settings["theming"]["custom_colors"].pop(key, None)
    
    # Remove the context from the settings
    active_settings.setdefault("custom_context", {}).pop(key, None)

    # Remove the context from the column order
    active_settings["column_order"] = [col for col in active_settings.get("column_order", []) if col.lower() != key]
    
    # Update the UI to reflect the removed context
    settings_save()
    populate_context_setup(frame, entries, 0, main_contextframe)
    if main_contextframe is not None:
        populate_context_frames(main_contextframe, 0, contextlist, frames)

def cycle_selection(name, direction=1):
    if active_settings is None:
        return
    if name == "release_range" and str(get_edition() or "").casefold() != "re-release":
        return
    var = active_selections.get(name)
    if not isinstance(var, tk.IntVar):
        return
    if name == "platforms":
        options = get_platforms()
    elif name in (active_settings.get("taxonomy") or {}):
        options = get_taxonomy_data(name)
    else:
        options = get_context_options(name)
    if not options:
        return
    var.set((var.get() + direction) % len(options))

def cycle_setup(name, direction):
    def handler(event):
        print(f"Debug: Cycling setup for {name} in direction {direction}")
        cycle_selection(name, direction)
        if searchentry is not None:
            searchentry.focus_set()
    return handler

def edit_data(data_dict, parent, key):
    value_var = tk.StringVar(value=str(data_dict.get(key, "")))

    entry = ttk.Entry(parent, textvariable=value_var)
    entry.grid(row=0, column=0, sticky="nsew")

    def save_value(event=None):
        new_value = value_var.get().strip()
        data_dict[key] = new_value

        if key.casefold() == "price_url":
            if new_value:
                query = (data_dict.get("upc") or data_dict.get("title", ""))
                price, _ = scrape_pricecharting_price(query, known_url=new_value)

                if price is not None:
                    active_contexts["price"] = price

                price_soup = get_soup(new_value)
                image_path = scrape_pricecharting_img(price_soup, force=True)

                if image_path is not None:
                    update_thumbnail(image_path)
            else:
                active_contexts["price"] = ""
        
        update_info_frame()
        return "break"

    entry.bind("<Return>", save_value)
    entry.bind("<FocusOut>", save_value)
    entry.bind("<Escape>", lambda event: update_info_frame())

    entry.focus_set()
    entry.select_range(0, tk.END)

def exclusion_rule_add(frame, platform, add_rule_vars, invert=False):
    if active_settings is None:
        return
    
    # Get all the columns from the frame's checkbuttons
    add_rule_vars = [col for col, var in add_rule_vars if var.get()]
    
    rule_name = f"NOT_{platform}" if invert else platform
    active_settings.setdefault("columns_to_drop", {})[rule_name] = add_rule_vars
    populate_rule_list(frame)
    settings_save()

def exclusion_rule_delete(frame, rule):
    if active_settings is None:
        return
    
    active_settings.setdefault("columns_to_drop", {}).pop(rule, None)
    populate_rule_list(frame)
    settings_save()

def exclusion_rule_edit(frame, rule, column, value):    
    if active_settings is None:
        return
    
    cols_to_drop = active_settings.setdefault("columns_to_drop", {}).setdefault(rule, [])
    if value:
        if column not in cols_to_drop:
            cols_to_drop.append(column)
    else:
        if column in cols_to_drop:
            cols_to_drop.remove(column)
    populate_rule_list(frame)
    settings_save()

def game_accept():
    if active_settings is None:
        handle_error("No settings available.")
        return
    
    if active_game_data is None:
        handle_error("No game data available.")
        return
    
    selected_title = active_game_data.get('title', '').strip() if active_game_data.get('title') else ''
    selected_platform = get_platform_key()
    selected_contents = get_contents()

    if selected_title and not active_source_game_data:
        active_game_is_new = True
    
    # Move the "The" to the end if the title starts with "The " and it's enabled in settings
    if selected_title.startswith("The ") and is_toggled('use_the_suffix'):
        selected_title = selected_title[4:] + ", The"
    
    contents = {}
    
    # Set case, sleeve, and manual based on content
    if is_toggled('use_content_split'):
        contents['Case'] = active_settings['symbols']['yes'] if selected_contents not in ["No Case", "Manual Only", "Sleeve Only", "Loose Disc", "Loose Cartridge", "Nothing"] else active_settings['symbols']['no']
        contents['Sleeve'] = active_settings['symbols']['yes'] if selected_contents not in ["Case Only", "Manual Only", "No Sleeve", "Loose Disc", "Loose Cartridge", "Nothing"] else active_settings['symbols']['no']
        contents['Manual'] = active_settings['symbols']['yes'] if selected_contents not in ["Case Only", "No Manual", "Loose Disc", "Loose Cartridge", "Nothing"] else active_settings['symbols']['no']
    else:
        contents['Contents'] = selected_contents

    contexts = {}
    for context in get_all_contexts():
        if context == "contents":
            continue  # Skip contents since it's already handled
        context_singular = context[:-1] if context.endswith('s') else context
        context_label = str(context_singular).replace("_", " ").title()
        context_value = get_context_data(context)

        if is_context_value(context, "editions", "re-release"):
            context_value = get_release_range()

        contexts[context_label] = context_value

    taxonomies = {}
    for taxonomy in get_taxonomy_keys():
        taxonomies[str(taxonomy).capitalize()] = active_taxonomy.get(taxonomy)

    # Set Singleplayer, Multiplayer, and Co-op based on taxonomy if they exist
    if is_toggled('use_playercount_split'):
        active_game_data.update(get_player_mode_flags())

    # Prepare the data to write to the file
    data = {
        "Title": [selected_title],
        "Release Date": [active_game_data.get('release_date')] if active_game_data.get('release_date') else "",
        "Platform": get_platform_name() if is_toggled('use_full_platform_name') else get_platform_key(),
        **contents,
        **contexts,
        "Developer": [active_game_data.get('developer')] if active_game_data.get('developer') else "",
        "Publisher": [active_game_data.get('publisher')] if active_game_data.get('publisher') else "",
        "Age Rating": [active_game_data.get('age_rating')] if active_game_data.get('age_rating') else "",
        "Moby Score": [active_game_data.get('moby_score')] if active_game_data.get('moby_score') else "",
        "Payed": [active_contexts.get('payed')] if active_contexts.get('payed') else "",
        "Value": [active_contexts.get('price')] if active_contexts.get('price') else "",
        **{key: [value] for key, value in get_os_record_fields().items()},
        "DX": [active_specs.get('DX', '')] if active_specs else "",
        "Ripped": [active_specs.get('Ripped', '')] if active_specs else "",
        "Copy Protection": [active_specs.get('Copy Protection', '')] if active_specs else "",
        "Playable": [active_specs.get('Playable', '')] if active_specs else "",
        "Spawnable": [active_specs.get('Spawnable', '')] if active_specs else "",
        "Force Feedback": [active_specs.get('Force Feedback', '')] if active_specs else "",
        "Coop": active_game_data.get('coop') if active_game_data.get('coop') is not None else "",
        "Multiplayer": active_game_data.get('multiplayer') if active_game_data.get('multiplayer') is not None else "",
        "Singleplayer": active_game_data.get('singleplayer') if active_game_data.get('singleplayer') is not None else "",
        "Hotseat": active_game_data.get('hotseat') if active_game_data.get('hotseat') is not None else "",
        **taxonomies,
        "Genre": active_taxonomy.get('genre') if active_taxonomy.get('genre') else "",
        "Added": [get_timestamp()],
        "Modified": [get_timestamp() if not active_game_is_new else ""],
        "UPC": [active_game_data.get('upc')] if active_game_data.get('upc') else "",
        "URL": [active_game_data.get('url')] if active_game_data.get('url') else "",
        "Price URL": [active_game_data.get('price_url')] if active_game_data.get('price_url') else "",
        "Gameplay URL": [get_gameplay_url()] if active_game_data else ""
    }
    
    # Re-order the columns based on the order in the settings
    ordered_data = {}
    for key in active_settings.get('column_order', []):
        for data_key in data.keys():
            if str(data_key).lower() == str(key).lower():
                ordered_data[data_key] = data[data_key]
                break

    # If the title is neew/unknown
    if active_game_is_new:
        response = messagebox.askyesnocancel("Add to source database", (f"Do you wish to add '{selected_title}' ({selected_platform}) to the source database?"))
        if response:
            create_source_diff()
            try:
                append_new_source_record()
            except Exception as exc:
                handle_error(f"Unable to add '{selected_title}' to the source database:\n{exc}")
                return
        elif response is False:
            pass
        else:
            return

    # If there's changes to the taxonomy 
    elif is_source_taxonomy_changed() or is_source_game_data_changed() or is_source_os_changed():
        response = messagebox.askyesnocancel("Update title", f"Do you wish to update the info for '{selected_title}' in the source database?")
        if response:
            create_source_diff()
        if response and not update_source_record():
            handle_error(f"Unable to update '{selected_title}' in the source database.")
            return
        elif response is False:
            pass
        else:
            return

    df = pd.DataFrame(ordered_data)

    write_to_file(df, get_platform_key())
    game_log(selected_title, selected_platform, active_game_data.get('release_date', ''), get_format(), get_condition(), get_case_condition(), get_contents(), get_edition())
    game_clear()
    game_search_clear()
    game_search_focus()

def game_clear():
    # Clear the active game data and reset the active title and perspective
    global active_game_data, active_taxonomy, active_contexts, active_title, active_perspective, active_game_is_new, active_source_taxonomy, active_specs
    active_source_taxonomy = {}
    active_game_data = {}
    active_taxonomy = {}
    active_contexts = {}
    active_specs = {}
    active_title = None
    active_perspective = None
    active_game_is_new = False

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
    if not active_game_is_new and (is_source_taxonomy_changed() or is_source_game_data_changed() or is_source_os_changed()):
        response = messagebox.askyesno("Update source database", "Do you wish to update the source database before discarding this game?")

        if response:
            title = active_game_data.get("title", "")
            if not update_source_record():
                handle_error(f"Unable to update '{title}' in the source database.")
                return

    game_clear()
    update_thumbnail()
    game_search_focus()

def game_log(title, platform, release_date, format, condition, case_condition, contents, edition):
    global logframe, logtree
    
    if logframe is None or logtree is None:
        return
    
    tag = 'even' if len(logtree.get_children()) % 2 == 0 else 'odd'
    logtree.insert("", "end", values=(title, release_date, platform, format, condition, case_condition, contents, edition), tags=(tag,))
    print(f"Debug: Logged game - Title: {title}, Platform: {platform}, Release Date: {release_date}, Format: {format}, Condition: {condition}, Case Condition: {case_condition}, Contents: {contents}, Edition: {edition}")

def get_case_condition():
    if active_settings is None:
        return None
    return active_settings["context"]["case_conditions"][active_selections.get("case_conditions", tk.IntVar()).get()]

def get_collection_path():
    return Path(f"{OUTPUT_DIR}/scanned_collection.xlsx")

def get_collection_status():
    statuses = {export_format: get_export_status(export_format) for export_format in ("tsv", "csv", "xlsx", "pdf")}

    if any(status == "Master collection not found" for status in statuses.values()):
        return "Master collection not found"

    current = [export_format.upper() for export_format, status in statuses.items() if status == "Current"]
    out_of_date = [export_format.upper() for export_format, status in statuses.items() if status == "Out of date"]
    not_exported = [export_format.upper() for export_format, status in statuses.items() if status == "Not exported"]

    status_parts = []

    if current:
        status_parts.append(f"Up to date: {', '.join(current)}")
    if out_of_date:
        status_parts.append(f"Out of date: {', '.join(out_of_date)}")
    if not_exported:
        status_parts.append(f"Not exported: {', '.join(not_exported)}")

    return " | ".join(status_parts)

def get_collection_stats():
    collection_path = get_collection_path()

    stats = {
        "titles": 0,
        "payed": 0.0,
        "value": 0.0,
        "platforms": 0,
        "platform_titles": {},
        "platform_value": {},
        "platform_payed": {}
    }

    if active_settings is None or not collection_path.exists():
        return stats

    workbook = pd.ExcelFile(collection_path, engine="openpyxl")

    for platform in workbook.sheet_names:
        data = pd.read_excel(collection_path, sheet_name=platform, engine="openpyxl", dtype=str).fillna("")
        columns = {str(column).strip().casefold(): column for column in data.columns}

        title_column = columns.get("title")
        payed_column = columns.get("payed")
        value_column = columns.get("value")

        if payed_column is not None:
            payed_values = (data[payed_column].astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", ".", regex=False))
            stats["payed"] += pd.to_numeric(payed_values, errors="coerce").fillna(0).sum()

        if value_column is not None:
            value_values = (data[value_column].astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", ".", regex=False))
            stats["value"] += pd.to_numeric(value_values, errors="coerce").fillna(0).sum() * (active_settings["currency_conversion"]["conversion_factor"] if is_toggled("use_currency_conversion") else 1)

        if title_column is not None:
            stats["titles"] += data[title_column].astype(str).str.strip().ne("").sum()

        stats["platform_titles"][platform] = data[title_column].astype(str).str.strip().ne("").sum()
        stats["platforms"] += 1
        stats["platform_value"][platform] = pd.to_numeric(value_values, errors="coerce").fillna(0).sum() * (active_settings["currency_conversion"]["conversion_factor"] if is_toggled("use_currency_conversion") else 1) if value_column is not None else 0
        stats["platform_payed"][platform] = pd.to_numeric(payed_values, errors="coerce").fillna(0).sum() if payed_column is not None else 0

    return stats

def get_color(name, default):
    if active_settings is None:
        return default
    return active_settings["theming"]["custom_colors"].get(name, active_settings["theming"]["custom_colors"].get("custom_context_fallback", "#00AAAA")) if is_toggled("use_custom_colors") else default

def get_color_export(column, value):
    column = handle_normalized_text(column)
    column = re.sub(r"[^a-z0-9]+", "_", column)
    column = column.strip("_")

    value = handle_normalized_text(value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")

    return f"{column}_{value}"

def get_color_export_gradient(column, value, data, export_gradients):
    column_key = get_color_export(column, "start").removesuffix("_start")

    start_hex = export_gradients.get(f"{column_key}_start")
    median_hex = export_gradients.get(f"{column_key}_mean")
    end_hex = export_gradients.get(f"{column_key}_end")

    if not start_hex or not end_hex:
        return None

    numeric_values = pd.to_numeric(data[column].astype(str).str.strip().str.replace("$", "", regex=False).str.replace(",", "", regex=False), errors="coerce").dropna()
    if numeric_values.empty:
        return None

    numeric_value = pd.to_numeric(str(value).strip().replace("$", "").replace(",", ""), errors="coerce")
    if pd.isna(numeric_value):
        return None

    minimum = numeric_values.min()
    maximum = numeric_values.max()

    start_color = colors.HexColor(start_hex)
    end_color = colors.HexColor(end_hex)

    if not median_hex:
        # Direct start-to-end gradient when the middle color is omitted.
        position = (numeric_value - minimum) / (maximum - minimum) if maximum != minimum else 0.0
        position = max(0.0, min(1.0, position))

        return colors.Color(
            start_color.red + (end_color.red - start_color.red) * position,
            start_color.green + (end_color.green - start_color.green) * position,
            start_color.blue + (end_color.blue - start_color.blue) * position,
        )

    # Three-color gradient using the platform-specific median.
    median_color = colors.HexColor(median_hex)
    median = numeric_values.median()

    if minimum == maximum:
        position = 0.5
    elif numeric_value <= median:
        position = 0.5 * (numeric_value - minimum) / max(median - minimum, 1e-12)
    else:
        position = 0.5 + 0.5 * (numeric_value - median) / max(maximum - median, 1e-12)

    position = max(0.0, min(1.0, position))

    if position <= 0.5:
        first_color = start_color
        second_color = median_color
        local_position = position * 2
    else:
        first_color = median_color
        second_color = end_color
        local_position = (position - 0.5) * 2

    return colors.Color(
        first_color.red + (second_color.red - first_color.red) * local_position,
        first_color.green + (second_color.green - first_color.green) * local_position,
        first_color.blue + (second_color.blue - first_color.blue) * local_position,
    )

def get_columns_to_drop(platform):
    if active_settings is None:
        return []

    platform_name = str(platform).strip().casefold()
    columns_to_drop = []

    for rule, columns in (active_settings.get("columns_to_drop") or {}).items():
        rule_name = str(rule).strip()

        if rule_name.casefold().startswith("not_"):
            applies = (rule_name[4:].strip().casefold() != platform_name)
        else:
            applies = rule_name.casefold() == platform_name

        if applies:
            columns_to_drop.extend(columns or [])

    return list(dict.fromkeys(columns_to_drop))

def get_condition():
    if active_settings is None:
        return None
    return active_settings["context"]["conditions"][active_selections.get("conditions", tk.IntVar()).get()]

def get_contents():
    if active_settings is None:
        return None
    return active_settings["context"]["contents"][active_selections.get("contents", tk.IntVar()).get()]

def get_fixed_contexts():
    if active_settings is None:
        return {}
    return active_settings.get("context", {}).keys()

def get_context_options(key) -> list:
    if active_settings is None:
        return []

    if key == "release_range":
        return get_release_ranges()
    
    return active_settings.get("context", {}).get(key, []) if key in active_settings.get("context", {}) else active_settings.get("custom_context", {}).get(key, [])

def get_context_data(key):
    if active_settings is None:
        return ""

    options = get_context_options(key)
    if not options:
        return ""

    selection = active_selections.get(key)
    index = selection.get() if selection is not None else 0

    if index < 0 or index >= len(options):
        index = 0
        if selection is not None:
            selection.set(index)

    return options[index]

def get_custom_contexts():
    if active_settings is None:
        return {}
    return active_settings.get("custom_context", {}).keys()

def get_all_contexts():
    if active_settings is None:
        return {}
    all_contexts = {}
    all_contexts.update(active_settings.get("context", {}))
    all_contexts.update(active_settings.get("custom_context", {}))
    return all_contexts

def get_custom_context_data(context):
    if active_settings is None:
        return []
    return active_settings["custom_context"][context][active_selections.get(context, tk.IntVar()).get()] if context in active_settings.get("custom_context", {}) else []

def get_edition():
    if active_settings is None:
        return None
    return active_settings["context"]["editions"][active_selections.get("editions", tk.IntVar()).get()]

def get_export_status(export_format):
    source_path = get_collection_path()
    if not source_path.exists():
        return "Master collection not found"

    export_folder = OUTPUT_DIR / export_format.upper()
    export_paths = [path for path in export_folder.glob(f"* Collection.{export_format}") if path != source_path]
    if not export_paths:
        return "Not exported"

    source_mtime = source_path.stat().st_mtime_ns
    if any(path.stat().st_mtime_ns < source_mtime for path in export_paths):
        return "Out of date"

    return "Current"

def get_format():
    if active_settings is None:
        return None
    return active_settings["context"]["formats"][active_selections.get("formats", tk.IntVar()).get()]

def get_game(query):
    threading.Thread(target=search_game, args=(query,), daemon=True).start()

def get_game_data(query, platform=None):
    if active_settings is None:
        handle_error("Settings file is missing")
        return

    platform = str(platform) if platform else str(get_platform_key())
    df = pd.DataFrame()  # Initialize an empty DataFrame
    file_name = get_collection_path()

    result = pd.read_excel(file_name, sheet_name=platform, engine="openpyxl", dtype=str)
    df = result[platform] if isinstance(result, dict) else result

    # Try both UPC and title
    if is_upc(query):
        # If the query is a UPC, search in the "UPC" column
        upc_col = next((c for c in df.columns if c.lower() == "upc"), None)
        if upc_col:
            return df[df[upc_col] == query].tail(1)
        else:
            handle_error("UPC column not found in the data.")
            return pd.DataFrame()  # Return an empty DataFrame if UPC column is missing

    title_col = next((c for c in df.columns if c.lower() == "title"), df.columns[0])
    q = str(query).strip().lower()
    df = df.fillna('')
    exact_match = df[df[title_col].str.strip().str.lower() == q]
    if not exact_match.empty:
        print(f"Debug: Found exact match for query '{query}'")
        matches = exact_match.copy()
        matches = matches.to_frame().T if isinstance(matches, pd.Series) else matches
        matches.columns = handle_normalized_list(matches.columns)
        return matches.iloc[0]
    contains_match = df[df[title_col].str.strip().str.lower().str.contains(q, na=False)]
    if not contains_match.empty:
        print(f"Debug: Found contains match for query '{query}'")
        matches = contains_match.copy()
        matches = matches.to_frame().T if isinstance(matches, pd.Series) else matches
        matches.columns = handle_normalized_list(matches.columns)
        return matches.iloc[0]
    
    handle_error(f"{query} not found.")
    return None

def get_game_source_data(query):
    if active_settings is None:
        return None

    platform = get_platform_name()
    if not platform:
        return None

    source_file = Path(f"Data/{platform}.xlsx")
    if not source_file.exists():
        handle_error(f"Source file for platform '{platform}' not found.")
        return None

    source_data = pd.read_excel(source_file, engine="openpyxl", dtype=str)

    if source_data.empty:
        handle_error(f"Source data for platform '{platform}' is empty.")
        return None

    source_data.columns = handle_normalized_list(source_data.columns)
    source_data = source_data.fillna("")

    normalized_query = handle_normalized_text(query)
    found_method = {}
    matches = pd.DataFrame()  # Initialize an empty DataFrame for matches
    
    if is_upc(query):
        matches = source_data[source_data["upc"].apply(lambda value: normalized_query in [handle_normalized_text(upc) for upc in str(value).split(",")])]

    if not matches.empty:
        found_method['upc'] = True

    if matches.empty:
        matches = source_data[source_data["title"].str.lower() == normalized_query]

    if not matches.empty:
        found_method['title'] = True

    # If the game begins with "The ", check for matches that end with ", The"
    if matches.empty and normalized_query.startswith("the "):
        matches = source_data[source_data["title"].map(handle_normalized_text) == normalized_query[4:] + ", the"]

    if not matches.empty:
        found_method['title_the'] = True

    if matches.empty:
        normalized_query = get_simplified_text(query)
        matches = source_data[source_data["title"].map(get_simplified_text) == normalized_query]

    if not matches.empty:
        found_method['title_normalized'] = True

    if matches.empty:
        matches = source_data[source_data["title"].map(get_simplified_text).str.endswith(normalized_query)]

    if not matches.empty:
        found_method['title_endswith'] = True

    if matches.empty:
        matches = source_data[source_data["title"].map(get_simplified_text).str.startswith(normalized_query)]

    if not matches.empty:
        found_method['title_startswith'] = True

    if matches.empty:
        return None

    print(f"Found through method: {found_method}")
    return matches.iloc[-1]

def get_gameplay_url():
    title = get_simplified_text(active_game_data.get("title", ""))
    release_date = str(active_game_data.get("release_date", "") or "")
    platform = get_platform_key()
    search_text = f"{title} {release_date} {platform} gameplay"
    search_text = " ".join(search_text.split())

    return f"https://www.youtube.com/results?search_query={quote_plus(search_text)}"

def get_moby_id(url=None):
    if url is None:
        if not active_game_data:
            return None
        url = active_game_data.get("url", "")

    if not url:
        return None

    return str(url).rstrip("/").split("/")[-1]

def get_options_for_key(key):
    if active_settings is None:
        return []
    if key == "release_range":
        return get_release_ranges()
    if key in active_settings.get("context", {}):
        return active_settings["context"][key]
    if key in active_settings.get("custom_context", {}):
        return active_settings["custom_context"][key]
    if key in active_settings.get("taxonomy", {}):
        return active_settings["taxonomy"][key]
    return []

def get_player_mode_flags(player_value=None):
    if player_value is None:
        player_value = active_taxonomy.get("player", "")

    player_modes = {mode.casefold() for mode in str(player_value or "").split("/") if mode.strip()}

    symbols = active_settings.get("symbols", {}) if active_settings else {}
    yes_symbol = symbols.get("yes", "Y")
    no_symbol = symbols.get("no", "N")

    return {
        "singleplayer": yes_symbol if "sp" in player_modes else no_symbol,
        "multiplayer": yes_symbol if "mp" in player_modes else no_symbol,
        "hotseat": yes_symbol if "hotseat" in player_modes else no_symbol,
        "coop": yes_symbol if "coop" in player_modes else no_symbol,
    }

def get_all_os_versions() -> dict:
    return {os_name: versions for os_name, versions in get_os().items()}

def get_os() -> dict:
    if active_settings is None:
        return {}
    platform = get_platform_key()
    return active_settings.get("OS", {}).get(platform, {})

def get_os_versions(os_name: str) -> list[str]:
    return get_os().get(os_name, [])

def get_os_version_status(os_name, version):
    versions = get_os_versions(os_name)
    selected_versions = set(active_specs.get(os_name, []))

    if not selected_versions or version not in versions:
        return "" if not selected_versions else "TBD"

    if version in selected_versions:
        return "Y"

    selected_indices = [versions.index(selected_version) for selected_version in selected_versions if selected_version in versions]
    if not selected_indices:
        return ""

    return "N" if versions.index(version) < max(selected_indices) else "TBD"

def get_os_record_fields(os_name=None):
    fields = {}

    for current_os_name, versions in get_os().items():
        if os_name is not None and current_os_name != os_name:
            continue

        if handle_normalized_text(current_os_name) == "dos":
            selected_versions = active_specs.get(current_os_name, [])
            fields[current_os_name] = selected_versions[0] if selected_versions else ""
        else:
            for version in versions:
                status = get_os_version_status(current_os_name, version)
                fields[str(version)] = "N" if status == "TBD" else status

    return fields

def get_os_specs(source_data):
    global active_specs
    active_specs = {}
    if active_settings is None or source_data is None:
        return

    normalized_source_data = handle_normalized_dict(source_data)
    yes_symbol = handle_normalized_text(active_settings.get("symbols", {}).get("yes", "Y"))

    for os_name, versions in get_os().items():
        normalized_os_name = handle_normalized_text(os_name)
        if normalized_os_name == "dos":
            saved_version = str(normalized_source_data.get("dos", "") or "").strip()
            if saved_version in [str(version) for version in versions]:
                active_specs[os_name] = [saved_version]

            continue

        selected_versions = []

        for version in versions:
            source_key = handle_normalized_text(str(version).replace(" ", "_"))
            saved_status = handle_normalized_text(normalized_source_data.get(source_key, "") or "")
            if saved_status == yes_symbol:
                selected_versions.append(str(version))

        if selected_versions:
            active_specs[os_name] = selected_versions

def get_platform_key():
    if active_settings is None:
        return None
    
    platforms = get_platforms()
    if not platforms:
        return None

    platform_selection = active_selections.get("platforms")
    if platform_selection is None:
        return platforms[0]

    index = platform_selection.get()
    if index < 0 or index >= len(platforms):
        return platforms[0]

    return platforms[index]

def get_platforms() -> list:
    if active_settings is None:
        return []
    return list(active_settings["platforms"].keys())

def get_platform_alias():
    if active_settings is None:
        return None

    platform_key = get_platform_key()
    platform_name = get_platform_name()

    alias = active_settings.get("platform_aliases", {}).get(platform_key)
    return alias or platform_name if platform_name else None

def get_platform_name():
    if active_settings is None:
        return None
    return active_settings["platforms"][get_platform_key()]

def get_platform_full_name(platform_key=None):
    if active_settings is None:
        return None

    if platform_key is None:
        platform_key = get_platform_key()

    platform_name = active_settings["platforms"].get(platform_key)
    return platform_name if platform_name else None

def get_named_release_ranges():
    return [value for value in get_release_ranges() if value.strip()]

def get_release_range():
    named_ranges = get_named_release_ranges()

    if not named_ranges:
        return ""

    if len(named_ranges) == 1:
        if str(get_edition() or "").casefold() == "re-release":
            return named_ranges[0]
        return ""

    return str(active_contexts.get("release_range", "") or "")

def get_release_ranges():
    if active_settings is None:
        return []

    platform = get_platform_key()
    ranges = active_settings.get("release_ranges", {}).get(platform, [])
    return [str(value) for value in ranges if value is not None]

def get_response(url, timeout=100, **kwargs):
    try:
        print(f"Fetching URL: {url}")
        return requests.get(url, timeout=timeout, **kwargs)
    except requests.RequestException as e:
        handle_error(f"Error fetching URL: {url}\n{e}")
        return None

def get_simplified_text(text):
    text = handle_normalized_text(text)
    symbols = [":", "!", "-", ".", "•", ",", "(", ")", "[", "]"]
    for symbol in symbols:
        text = text.replace(symbol, " ")
    non_separating_symbols = ["'"]
    for symbol in non_separating_symbols:
        text = text.replace(symbol, "")
    text = text.replace("&", "and")
    # Get rid of extra spaces between words
    text = " ".join(text.split())
    return text

def get_filtered_game_data(game_data=None):
    if active_settings is None:
        return {}
    game_data = active_game_data if game_data is None else game_data
    exclusions = {str(key).strip().casefold() for key in active_settings.get("scraped_data_exclusion", [])}

    return {key: game_data.get(key, "") for key in active_settings.get("scraped_data", {}) if str(key).strip().casefold() not in exclusions}

def get_soup(url):
    response = get_response(url)
    if response is None:
        return None
    soup = bs.BeautifulSoup(response.text, 'html.parser')
    return soup if soup is not None else None

def get_source_record(game_data=None):
    timestamp = get_timestamp()
    record = get_filtered_game_data(game_data)
    record.update({
        "added": timestamp if active_game_is_new else active_source_game_data.get("added", ""),
        "modified": "" if active_game_is_new else timestamp,
        "platform": get_platform_name(),
        **get_player_mode_flags(),
        **get_os_record_fields(),
    })

    for key in get_taxonomy_keys():
        record[key] = active_taxonomy.get(key, "")

    for key in get_all_contexts():
        source_key = key[:-1] if key.endswith("s") else key
        record[source_key] = active_contexts.get(key, "")

    return record

def get_specific_soup_by_class(url, tag, class_name, known_soup=None):
    if known_soup is not None:
        soup = known_soup
        response_url = url
    else:
        response = get_response(url)
        if response is None:
            return False, None, None, None

        soup = bs.BeautifulSoup(response.text, "html.parser")
        response_url = response.url

    element = soup.find(tag, class_=class_name)

    return element is not None, element, soup, response_url

def get_specific_soup_by_id(url, tag, id_name, known_soup=None):
    if known_soup is not None:
        soup = known_soup
        response_url = url
    else:
        response = get_response(url)
        if response is None:
            return False, None, None, None

        soup = bs.BeautifulSoup(response.text, "html.parser")
        response_url = response.url

    element = soup.find(tag, id=id_name)

    return element is not None, element, soup, response_url

def get_taxonomy_keys() -> list:
    if active_settings is None:
        return []
    return list(active_settings.get("taxonomy", {}).keys())

def get_taxonomy_data(key):
    if active_settings is None:
        return {}
    return active_settings.get("taxonomy", {}).get(key, [])

def get_taxonomy_default_idx(key: str) -> int:
    if active_settings is None:
        return 0
    defaults = active_settings.get("platform_defaults", {})
    platform_defaults = defaults.get(get_platform_key(), defaults.get("Default", {}))
    idx = 0
    if key in platform_defaults:
        idx = int(platform_defaults[key])
    return idx

def get_thumbnail_path(url=None):
    game_id = None
    if url is not None:
        game_id = get_moby_id(url)
    platform = get_platform_name()
    title = get_simplified_text(active_game_data.get("title", "")) if active_game_data else ""

    if not platform:
        return None

    image_dir = Path(f"{BASE_DIR}/Data/Images/{platform}")
    image_path = Path(image_dir / f"{game_id}.png") if game_id is not None else Path(image_dir / f"{title.replace(' ', '_')}.png")

    return image_path if image_path.is_file() else None

def get_timestamp():
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

def handle_accept_key(root, event):
        if isinstance(root.focus_get(), (ttk.Entry, tk.Entry)):
            return
        if acceptbutton is not None and acceptbutton.instate(['!disabled']):
            acceptbutton.invoke()

def handle_decline_key(root, event):
    if isinstance(root.focus_get(), (ttk.Entry, tk.Entry)):
        return
    if declinebutton is not None and declinebutton.instate(['!disabled']):
        declinebutton.invoke()

def handle_ellipsis(text, max_length=30):
    return text if len(text) <= max_length else text[:max_length-3] + "..."

def handle_error(message):
    # Display the error message in a message box
    messagebox.showerror("Error", message)

def handle_keypad_enter(event):
    focused_widget = event.widget
    if isinstance(focused_widget, ttk.Button):
        focused_widget.invoke()
        return "break"

def handle_missing_field(widget, key):
    info = widget.grid_info()
    parent = widget.master
    row = info['row']
    column = info['column']
    text = widget.cget("text")

    if text.startswith("Add "):
        widget.destroy()

    var = tk.StringVar()
    entry = ttk.Entry(parent, textvariable=var)
    entry.grid(row=row, column=column, sticky="nsew")
    # Ensure focus after the event loop finishes
    parent.after_idle(entry.focus_set)
    # store the live entry widget so identity checks work
    missing_fields[key] = entry

    def on_submit(event=None, k=key, v=var):
        v.set(v.get().strip())
        update_info_choice(k, v)
        if k.lower() == "title" and acceptbutton is not None and declinebutton is not None:
            state = "normal" if v.get().strip() else "disabled"
            acceptbutton.config(state=state)
            declinebutton.config(state=state)

    entry.bind("<Return>", on_submit)
    entry.bind("<FocusOut>", on_submit)
    entry.bind("<Escape>", lambda e: update_info_frame())

    return entry

def handle_missing_id_shortcut(event=None):
    if infoframe is None:
        return

    id_button = missing_fields.get("url")
    if id_button:
        id_button.focus_set()
        id_button.invoke()
        return "break"

    return None

def handle_missing_price_url_shortcut(event=None):
    if infoframe is None:
        return

    id_button = missing_fields.get("price_url")
    if id_button:
        id_button.focus_set()
        id_button.invoke()
        return "break"

    return None

def handle_missing_upc_shortcut(event=None):
    if infoframe is None:
        return
    
    # Find the row with the UPC entry
    upc_button = missing_fields.get('upc')
    if upc_button:
        upc_button.focus_set()
        upc_button.invoke()
        return "break"

    if "upc" in active_game_data:
        add_upc()
        return "break"
    
    return None

def handle_normalized_text(text):
    # Normalize text to lowercase and stripped of whitespace
    return str(text).strip().casefold()

def handle_normalized_list(cols):
    # Normalize column names to lowercase and stripped of whitespace
    return [str(col).replace(" ", "_").strip().casefold().strip('_') for col in cols]

def handle_normalized_dict(d):
    # Normalize dictionary keys to lowercase and stripped of whitespace
    return {handle_normalized_text(str(k).replace(" ", "_")): handle_normalized_text(v) for k, v in d.items()}

def handle_normalized_os_status(value):
    value = handle_normalized_text(value)
    return "n" if value == "tbd" else value

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

def handle_tab_key(root, event, direction=1):
    print("Debug: Tab key pressed - cycling through missing fields")
    # Cycle through the missing field entries when Tab is pressed
    if not missing_fields:
        return

    focused_widget = root.focus_get()
    keys = list(missing_fields.keys())

    # If focus is in a plain entry that's NOT one of our missing-field entries, let Tab behave normally
    if isinstance(focused_widget, (ttk.Entry, tk.Entry)) and focused_widget is not None and focused_widget not in set(missing_fields.values()):
        return
    
    # Get the index of the currently focused missing field, if we're in one
    focused_index = None
    for idx, k in enumerate(keys):
        if missing_fields.get(k) is focused_widget:
            focused_index = idx
            break

    # If we're not currently focused in any of the missing-field entries, focus the first one
    if focused_index is None:
        next_key = keys[0] if direction > 0 else keys[-1]
        widget = missing_fields[next_key]

        if isinstance(widget, ttk.Button):
            entry = handle_missing_field(widget, next_key)
            if entry:
                root.after_idle(entry.focus_set)
            else:
                widget.focus_set()
            print(f"Debug: No missing field focused, focusing first missing field: {next_key}")
        else:
            widget.focus_set()

        return "break"
    
    # If we are focused inside one of our missing-field entries, commit it and move to the next missing field
    current_key = keys[focused_index]
    if isinstance(focused_widget, (ttk.Entry, tk.Entry)):
        update_info_choice(current_key, focused_widget.get().strip())

    # Once done, move to the next key based on the previous list
    next_idx = (focused_index + direction) % len(keys)
    next_key = keys[next_idx]
    if next_key in missing_fields:
        widget = missing_fields[next_key]
        if isinstance(widget, ttk.Button):
            entry = handle_missing_field(widget, next_key)
            if entry:
                root.after_idle(entry.focus_set)
        else:
            widget.focus_set()

    return "break"

def handle_thumbnail_missing():
    image_path = get_thumbnail_path(active_game_data.get("url")) if active_game_data else None

    if image_path is None:
        price_url = active_game_data.get("price_url", "")
        soup = get_soup(price_url)
        if soup is None:
            handle_error("Unable to fetch thumbnail from the price URL.")
            return

        image_path = scrape_pricecharting_img(soup)
    
    update_thumbnail(image_path)
    return image_path

def handle_thumbnail_refresh():
    if not active_game_data:
        return

    moby_url = active_game_data.get("url", "")
    price_url = active_game_data.get("price_url", "")

    if not moby_url or not price_url:
        return

    soup = get_soup(price_url)
    if soup is None:
        handle_error("Unable to fetch the thumbnail from the PriceCharting URL.")
        return

    image_path = scrape_pricecharting_img(soup, force=True)
    if image_path is None:
        handle_error("Unable to refresh the thumbnail.")
        return

    update_thumbnail(image_path)

def handle_thumbnail_rename(url):
    if not active_game_data or not url:
        return None

    title_image_path = get_thumbnail_path()
    platform = get_platform_name()
    id = get_moby_id(url)

    if not platform or not id:
        return title_image_path

    image_dir = Path(f"{BASE_DIR}/Data/Images/{platform}")
    moby_image_path = image_dir / f"{id}.png"

    if moby_image_path.exists():
        return moby_image_path

    if title_image_path is None or title_image_path == moby_image_path:
        return moby_image_path if moby_image_path.exists() else title_image_path

    try:
        title_image_path.rename(moby_image_path)
        return moby_image_path
    except OSError as exc:
        print(f"Debug: Failed to rename thumbnail: {exc}")
        return title_image_path

def handle_toggle_change(toggle):
    if active_settings is None:
        return
    toggles = active_settings.setdefault("toggles", {})
    toggles[toggle] = not toggles.get(toggle, False)

    # Update the context choices if a toggle change affects them
    update_choices(changes=True)
    settings_save()

def handle_url(event, url):
    if url:
        webbrowser.open_new_tab(url)

def is_context_value(context, key, value):
    if context.casefold() != key.casefold():
        return False
    
    selected_value = get_context_data(key)
    return str(selected_value or "").casefold() == str(value or "").casefold()

def is_os():
    if active_settings is None:
        return False
    return get_platform_key() in active_settings.get("OS", {})

def is_release_range_large_enough():
    return len(get_named_release_ranges()) > 1

def is_source_game_data_changed(key = None):
    if active_game_is_new or not active_source_game_data:
        return False

    source_record = get_filtered_game_data()
    source_keys = source_record.keys()

    if key is not None:
        if key not in source_keys:
            return False
        return str(active_game_data.get(key, "")) != str(active_source_game_data.get(key, ""))
    
    return any(str(active_game_data.get(source_key, "")) != str(active_source_game_data.get(source_key, "")) for source_key in source_keys)

def is_source_os_changed(os_name=None):
    if active_game_is_new or not active_source_game_data:
        return False

    source_fields = handle_normalized_dict(active_source_game_data)
    current_fields = handle_normalized_dict(get_os_record_fields(os_name))
    return any(current_fields.get(key, "") != source_fields.get(key, "") for key in current_fields)

def is_source_taxonomy_changed(key = None):
    if active_game_is_new or not active_source_taxonomy:
        return False

    if key is not None:
        return str(active_taxonomy.get(key, "")) != str(active_source_taxonomy.get(key, ""))
    return any(str(active_taxonomy.get(k, "")) != str(active_source_taxonomy.get(k, "")) for k in get_taxonomy_keys())

def is_thumbnail_missing():
    if thumbnail_label is None:
        return True
    return thumbnail_label.cget("image") == ""

def is_toggled(toggle):
    if active_settings is None:
        return False
    return active_settings.get("toggles", {}).get(toggle, False)

def is_upc(text: str) -> bool:
    # Check if the text is a 12 or 13 digit UPC
    return bool(re.fullmatch(r'\d{13}', text) or re.fullmatch(r'\d{12}', text))

def modify_color(hex_color: str, amount: float) -> str:
    hex_color = hex_color.strip().lstrip('#')
    if len(hex_color) != 6:
        return hex_color
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    new_v = max(0.0, min(1.0, v + amount))
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, new_v)
    return "#{:02x}{:02x}{:02x}".format(int(round(nr*255)), int(round(ng*255)), int(round(nb*255)))

def open_column_order_window():
    if active_settings is None:
        return
    
    column_order_window = tk.Toplevel(class_="GBScan")
    column_order_window.title("GBScan - Change Column Order")
    column_order_window.geometry("400x600")
    column_order_window.columnconfigure(0, weight=1)
    column_order_window.rowconfigure(0, weight=1)

    column_order_frame = ttk.LabelFrame(column_order_window, text="Column Order")
    column_order_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    column_order_frame.columnconfigure(0, weight=1)
    column_order_frame.rowconfigure(0, weight=1)
    column_order_frame.rowconfigure(1, weight=1)

    columns = active_settings.get("column_order", [])
    column_listbox = tk.Listbox(column_order_frame)
    column_listbox.config(font=("Consolas", 10))
    column_listbox.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=4, pady=4)
    
    for col in columns:
        column_listbox.insert(tk.END, col)

    def move_up():
        selected = column_listbox.curselection()
        if not selected or selected[0] == 0:
            return
        idx = selected[0]
        columns[idx-1], columns[idx] = columns[idx], columns[idx-1]
        column_listbox.delete(0, tk.END)
        for col in columns:
            column_listbox.insert(tk.END, col)
        column_listbox.select_set(idx-1)
        
        if active_settings is None:
            return
        active_settings["column_order"] = columns
        settings_save()

    def move_down():
        selected = column_listbox.curselection()
        if not selected or selected[0] == len(columns) - 1:
            return
        idx = selected[0]
        columns[idx+1], columns[idx] = columns[idx], columns[idx+1]
        column_listbox.delete(0, tk.END)
        for col in columns:
            column_listbox.insert(tk.END, col)
        column_listbox.select_set(idx+1)
        
        if active_settings is None:
            return
        active_settings["column_order"] = columns
        settings_save()

    up_button = ttk.Button(column_order_frame, text="Move Up", command=move_up)
    up_button.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

    down_button = ttk.Button(column_order_frame, text="Move Down", command=move_down)
    down_button.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)

    close_button = ttk.Button(column_order_frame, text="Close", command=column_order_window.destroy)
    close_button.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)

def open_column_export_window():
    if active_settings is None:
        return

    column_export_window = tk.Toplevel(class_="GBScan")
    column_export_window.title("GBScan - Export Columns")
    column_export_window.columnconfigure(0, weight=1)
    column_export_window.rowconfigure(0, weight=1)

    column_selection_frame = ttk.LabelFrame(column_export_window, text="Column Selection", padding=4)
    column_selection_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
    column_selection_frame.columnconfigure(0, weight=1)
    column_selection_frame.columnconfigure(2, weight=1)
    column_selection_frame.rowconfigure(0, weight=1)

    column_order_frame = ttk.Label(column_selection_frame)
    column_order_frame.grid(row=0, column=0, sticky="nsew")
    column_order_frame.columnconfigure(0, weight=1)
    column_order_frame.rowconfigure(0, weight=1)

    columns = active_settings.get("column_order", [])
    column_listbox = tk.Listbox(column_order_frame, height=25)
    column_listbox.grid(row=0, column=0, sticky="nsew")
    for col in columns:
        column_listbox.insert(tk.END, col)
    column_scrollbar = ttk.Scrollbar(column_order_frame, orient="vertical", command=column_listbox.yview)
    column_scrollbar.grid(row=0, column=1, sticky="ns")
    column_listbox.configure(yscrollcommand=column_scrollbar.set)

    column_control_frame = ttk.Label(column_selection_frame)
    column_control_frame.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
    column_control_frame.rowconfigure(0, weight=1)

    def refresh_columns():
        if active_settings is None:
            return

        column_export = active_settings.setdefault("column_export", {})
        column_order = active_settings.get("column_order", [])

        ordered_columns = sorted(column_export, key=lambda column: column_order.index(column) if column in column_order else len(column_order),)
        active_settings["column_export"] = {column: column_export[column] for column in ordered_columns}

        for child in column_export_frame.winfo_children():
            child.destroy()

        ttk.Label(column_export_frame, text="Column",).grid(row=0, column=0, sticky="nw", padx=2)
        ttk.Label(column_export_frame, text="Width",).grid(row=0, column=1, sticky="nw", padx=2)
        ttk.Label(column_export_frame, text="Align",).grid(row=0, column=2, sticky="nw", padx=2)

        for row, column in enumerate(ordered_columns, start=1):
            ttk.Label(column_export_frame, text=column,).grid(row=row, column=0, sticky="w", padx=2, pady=1)

            width_var = tk.StringVar(value=str(column_export.get(column, {}).get("width", 10)))
            width_entry = ttk.Entry(column_export_frame, textvariable=width_var, width=6)
            width_entry.grid(row=row, column=1, sticky="w", padx=2, pady=1)

            align_var = tk.StringVar(value=column_export.get(column, {}).get("align", "left"))
            align_menu = ttk.Combobox(column_export_frame, textvariable=align_var, values=("left", "center", "right"), state="readonly", width=7)
            align_menu.grid(row=row, column=2, sticky="w", padx=2, pady=1)

            rem_btn = ttk.Button(column_export_frame, text="Remove", command=lambda c=column: rem_column(c),)
            rem_btn.configure(padding=0)
            rem_btn.grid(row=row, column=3, sticky="w")

            def save_width(event=None, c=column, v=width_var):
                if active_settings is None:
                    return
                try:
                    width = max(1, int(v.get()))
                except ValueError:
                    width = 10

                v.set(str(width))
                active_settings["column_export"][c]["width"] = width

            def save_align(event=None, c=column, v=align_var):
                if active_settings is None:
                    return

                align = v.get()
                if align not in ("left", "center", "right"):
                    align = "left"

                v.set(align)
                active_settings["column_export"][c]["align"] = align

            width_entry.bind("<FocusOut>", save_width)
            width_entry.bind("<Return>", save_width)
            align_menu.bind("<FocusOut>", save_align)
            align_menu.bind("<Return>", save_align)

    def add_column():
        if active_settings is None:
            return
        selected_indices = column_listbox.curselection()
        column_export = active_settings.setdefault("column_export", {})

        for index in selected_indices:
            column = column_listbox.get(index)

            if column not in column_export:
                column_export[column] = {"width": 10, "align": "left"}

        refresh_columns()

    def rem_column(column):
        if active_settings is None:
            return
        active_settings.setdefault("column_export", {}).pop(column, None)
        refresh_columns()

    def save_and_close():
        settings_save()
        column_export_window.destroy()

    column_control_add_btn = ttk.Button(column_control_frame, text=">", command=add_column)
    column_control_add_btn.grid(row=0, column=0, sticky="nsew")

    column_export_frame = ttk.Label(column_selection_frame)
    column_export_frame.grid(row=0, column=2, sticky="nsew")
    column_export_frame.columnconfigure(0, weight=1)
    column_export_frame.rowconfigure(0, weight=1)

    export_listbox = tk.Listbox(column_export_frame, height=25)
    export_listbox.grid(row=0, column=0, sticky="nsew")
    refresh_columns()
    
    close_button = ttk.Button(column_selection_frame, text="Close", command=save_and_close)
    close_button.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=0, pady=(4,0))

def open_custom_colors_window():
    if active_settings is None:
        return
    
    custom_colors_window = tk.Toplevel(class_="GBScan")
    custom_colors_window.title("GBScan - Edit Custom Colors")
    custom_colors_window.columnconfigure(0, weight=1)
    custom_colors_window.rowconfigure(0, weight=1)

    frame = ttk.LabelFrame(custom_colors_window, text="Custom Colors")
    frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=3)

    theming = active_settings.setdefault("theming", {})
    custom_colors = theming.setdefault("custom_colors", {})
    
    for i, (key, color) in enumerate(custom_colors.items()):
        ttk.Label(frame, text=key).grid(row=i, column=0, sticky="nsew", padx=4, pady=4)
        color_var = tk.StringVar(value=color)
        color_entry = ttk.Entry(frame, textvariable=color_var)
        color_entry.grid(row=i, column=1, sticky="nsew", padx=4, pady=4)

        def update_color(event=None,key=key, var=color_var):
            new_color = var.get()
            if re.fullmatch(r'#?[0-9a-fA-F]{6}', new_color):
                if not new_color.startswith('#'):
                    new_color = '#' + new_color
                custom_colors[key] = new_color
                settings_save()
            else:
                messagebox.showerror("Invalid Color", f"{new_color} is not a valid hex color.")

        color_entry.bind("<FocusOut>", update_color)
        color_entry.bind("<Return>", update_color)

    close_button = ttk.Button(frame, text="Close", command=custom_colors_window.destroy)
    close_button.grid(row=len(custom_colors), column=0, columnspan=2, sticky="nsew", padx=4, pady=4)

def open_exclusion_window():
    global _exclusion_image_refs
    if active_settings is None:
        return
    exclusion_window = tk.Toplevel(class_="GBScan")
    exclusion_window.title("GBScan - Exclusion List")

    platforms = get_platforms()
    columns = active_settings.get("column_order", [])

    exclusion_root_frame = ttk.Frame(exclusion_window)
    exclusion_root_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    add_rule_frame = ttk.Labelframe(exclusion_root_frame, text="Add Exclusion Rule")
    add_rule_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    add_rule_col = 0

    add_not_check_var = tk.BooleanVar(value=False)
    add_not_check = ttk.Checkbutton(add_rule_frame, text="NOT_", variable=add_not_check_var)
    add_not_check.grid(row=1, column=add_rule_col, sticky=tk.W, padx=4, pady=4)
    add_rule_col += 1

    add_platform_var = tk.StringVar(value=platforms[0] if platforms else "")
    add_platform_menu = ttk.OptionMenu(add_rule_frame, add_platform_var, add_platform_var.get(), *platforms)
    add_platform_menu.grid(row=1, column=add_rule_col, sticky=tk.W, padx=4, pady=4)
    add_rule_col += 1

    add_rule_vars = []
    for col in columns:
        img = rotated_text_image(col, font_size=10)
        _exclusion_image_refs.append(img)
        label = ttk.Label(add_rule_frame, image=img)
        label.grid(row=0, column=add_rule_col, sticky="sw")
        var = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(add_rule_frame, variable=var, compound="top")
        chk.grid(row=1, column=add_rule_col, sticky="nsew")
        add_rule_vars.append((col, var))
        add_rule_col += 1

    add_rule_button = ttk.Button(add_rule_frame, text="Add Rule", command=lambda: exclusion_rule_add(list_rule_frame, add_platform_var.get(), add_rule_vars, invert=add_not_check_var.get()))
    add_rule_button.grid(row=1, column=add_rule_col, sticky="nsew", padx=4, pady=4)

    list_rule_frame = ttk.Labelframe(exclusion_root_frame, text="Current Rules")
    list_rule_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
    populate_rule_list(list_rule_frame)

    close_rules_button = ttk.Button(exclusion_root_frame, text="Close", command=exclusion_window.destroy)
    close_rules_button.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)

def open_platform_mapping_window(platform_list=None):
    if active_settings is None:
        return
    
    platform_mapping_window = tk.Toplevel(class_="GBScan")
    platform_mapping_window.title("GBScan - Edit Platform Mapping")
    platform_mapping_window.columnconfigure(0, weight=1)
    platform_mapping_window.rowconfigure(0, weight=1)

    frame = ttk.LabelFrame(platform_mapping_window, text="Platform Mapping")
    frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=3)

    pmlabel = ttk.Label(frame, text="Key is what appears in the selection. Name must match the tag on Mobygames.")
    pmlabel.grid(row=0, column=0, columnspan=2, sticky="w", pady=(8, 8))

    columns = ["Key", "Name"]
    for j, col in enumerate(columns):
        label = ttk.Label(frame, text=col)
        label.grid(row=1, column=j, sticky="nsew", padx=2, pady=2)
    
    populate_platform_mapping_list(frame, platform_list=platform_list, window=platform_mapping_window)

def open_platform_defaults_window():
    if active_settings is None:
        return
    
    platform_defaults_window = tk.Toplevel(class_="GBScan")
    platform_defaults_window.title("GBScan - Edit Platform Defaults")
    platform_defaults_window.columnconfigure(0, weight=1)
    platform_defaults_window.rowconfigure(0, weight=1)

    platform_defaults_frame = ttk.Frame(platform_defaults_window)
    platform_defaults_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    platform_defaults_frame.columnconfigure(0, weight=1)
    platform_defaults_frame.rowconfigure(0, weight=1)

    platform_defaults_notebook = ttk.Notebook(platform_defaults_frame)
    platform_defaults_notebook.grid(row=0, column=0, sticky="nsew")

    # Tabs
    contexts_tab = ttk.Frame(platform_defaults_notebook)
    taxonomy_tab = ttk.Frame(platform_defaults_notebook)
    platform_defaults_notebook.add(contexts_tab, text="Context Defaults")
    platform_defaults_notebook.add(taxonomy_tab, text="Taxonomy Defaults")

    # Key lists
    context_keys = list(dict.fromkeys(get_all_contexts()))
    taxonomy_keys = list(dict.fromkeys(get_taxonomy_keys()))

    ########################
    # Context Defaults Tab #
    ########################
    frame = ttk.Frame(contexts_tab)
    frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=3)

    context_add_frame = ttk.LabelFrame(frame, text="Add Platform Default")
    context_add_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)

    context_keys = list(dict.fromkeys(get_all_contexts()))

    platforms_with_default = get_platforms() + ["Default"]
    ttk.Label(context_add_frame, text="Platform").grid(row=0, column=0, padx=4, pady=2, sticky="w")
    for i, key in enumerate(context_keys, start=1):
        ttk.Label(context_add_frame, text=key.replace("_", " ").title()).grid(row=0, column=i, padx=4, pady=2, sticky="w")

    add_platform_var = tk.StringVar(value=platforms_with_default[0] if platforms_with_default else "Default")
    add_platform_menu = ttk.OptionMenu(context_add_frame, add_platform_var, add_platform_var.get(), *platforms_with_default)
    add_platform_menu.configure(padding=(4, 0))
    add_platform_menu.grid(row=1, column=0, padx=4, pady=4, sticky="w")

    # Create a dropdown for each settings key and store the StringVar in a dictionary for later retrieval
    add_setting_vars = {}
    for i, key in enumerate(context_keys, start=1):
        options = get_options_for_key(key)
        var = tk.StringVar(value=options[0] if options else "")
        menu = ttk.OptionMenu(context_add_frame, var, var.get(), *options)
        menu.configure(padding=(0, 0))
        menu.config(width=len(max(options, key=len)) + 2 if options else 10)
        menu.grid(row=1, column=i, padx=2, pady=2, sticky="w")
        add_setting_vars[key] = var

    def default_add_context():
        if active_settings is None:
            return
        platform = add_platform_var.get()
        if not platform:
            return
        new_defaults = {}
        for key, var in add_setting_vars.items():
            options = get_options_for_key(key)
            idx = options.index(var.get()) if var.get() in options else 0
            new_defaults[key] = idx
        active_settings.setdefault("platform_defaults", {})[platform] = new_defaults
        settings_save()
        populate_platform_defaults_list(context_list_frame, context_keys)

    # Add Default button for context defaults
    context_add_button = ttk.Button(context_add_frame, text="Add Default", command=default_add_context)
    context_add_button.configure(padding=(0, 0))
    context_add_button.grid(row=1, column=len(context_keys) + 1, padx=4, pady=4, sticky="w")

    # Create list for the existing defaults
    context_list_frame = ttk.LabelFrame(contexts_tab, text="Current Defaults")
    context_list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
    populate_platform_defaults_list(context_list_frame, context_keys)

    #########################
    # Taxonomy Defaults Tab #
    #########################
    taxonomy_add_frame = ttk.LabelFrame(taxonomy_tab, text="Add / Update Default")
    taxonomy_add_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=2)

    taxonomy_keys = list(dict.fromkeys(get_taxonomy_keys()))
    
    # Platform label for taxonomy defaults
    ttk.Label(taxonomy_add_frame, text="Platform").grid(row=0, column=0, padx=4, pady=2, sticky="w")
    
    # Row of labels for each taxonomy key
    for i, key in enumerate(taxonomy_keys, start=1):
        ttk.Label(taxonomy_add_frame, text=key.replace("_", " ").title()).grid(row=0, column=i, padx=4, pady=2, sticky="w")

    # Platform dropdown
    add_platform_var2 = tk.StringVar(value=platforms_with_default[0] if platforms_with_default else "Default")
    add_platform_menu2 = ttk.OptionMenu(taxonomy_add_frame, add_platform_var2, add_platform_var2.get(), *platforms_with_default)
    add_platform_menu2.configure(padding=(4, 0))
    add_platform_menu2.grid(row=1, column=0, padx=4, pady=2, sticky="w")

    # Dropdowns for each taxonomy key
    add_setting_vars_tax = {}
    for i, key in enumerate(taxonomy_keys, start=1):
        options = get_options_for_key(key)
        var = tk.StringVar(value=options[0] if options else "")
        menu = ttk.OptionMenu(taxonomy_add_frame, var, var.get(), *options)
        menu.configure(padding=(0, 0))
        menu.config(width=len(max(options, key=len)) + 2 if options else 10)
        menu.grid(row=1, column=i, padx=2, pady=2, sticky="w")
        add_setting_vars_tax[key] = var

    def default_add_taxonomy():
        if active_settings is None:
            return
        platform = add_platform_var2.get()
        if not platform:
            return
        new_defaults = {}
        for k, v in add_setting_vars_tax.items():
            options = get_options_for_key(k)
            idx = options.index(v.get()) if v.get() in options else 0
            new_defaults[k] = idx
        active_settings.setdefault("platform_defaults", {})[platform] = {**active_settings.setdefault("platform_defaults", {}).get(platform, {}), **new_defaults}
        settings_save()
        populate_platform_defaults_list(taxonomy_list_frame, taxonomy_keys)

    # Add Default button for taxonomy defaults
    taxonomy_add_button = ttk.Button(taxonomy_add_frame, text="Add Default", command=default_add_taxonomy)
    taxonomy_add_button.configure(padding=(0, 0))
    taxonomy_add_button.grid(row=1, column=len(taxonomy_keys) + 1, padx=4, pady=0, sticky="w")

    # Create list for the existing taxonomy defaults
    taxonomy_list_frame = ttk.LabelFrame(taxonomy_tab, text="Current Defaults")
    taxonomy_list_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
    populate_platform_defaults_list(taxonomy_list_frame, taxonomy_keys)

    close_button = ttk.Button(platform_defaults_frame, text="Close", command=platform_defaults_window.destroy)
    close_button.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)

def populate_context_choices(frame, name):
    # Populate a menu with the given options
    label_text = name.capitalize().replace("_", " ")
    if active_settings is None:
        return
    shortcut = active_settings.get("shortcuts", {}).get(name)
    if shortcut:
        label_text += f" ({shortcut})"

    options = get_platforms() if name == "platforms" else get_context_options(name)

    max_length = max(len(option) for option in options)
    label_width = max(20, len(label_text))
    label = ttk.Label(frame, text=label_text, width=label_width, anchor=tk.W)
    label.pack(side=tk.LEFT, padx=4)
    
    existing_var = active_selections.get(name)
    var = existing_var if existing_var else tk.IntVar(value=0)
    active_selections[name] = var
    for modes, cbname in var.trace_info():
        for mode in modes:
            var.trace_remove(mode, cbname)
    buttons = []

    def on_change(*args):
        idx = var.get()
        for i, btn in enumerate(buttons):
            btn.state(['pressed'] if i == idx else ['!pressed'])
        selections_update(name, idx)

    var.trace_add("write", on_change)
    release_range_enabled = (name != "release_range" or str(get_edition() or "").casefold() == "re-release")

    # Button theming and button position
    for index, option in enumerate(options):
        
        style_name = f"{name.capitalize()}Button.TButton"
        style = ttk.Style()
        style.configure(style_name, 
                        background=get_color(name, "#e0e0e0"), 
                        foreground="#000000",
                        lightcolor=modify_color(get_color(name, "#d0d0d0"), 0.2),
                        darkcolor=modify_color(get_color(name, "#c0c0c0"), -0.1),
                        bordercolor=modify_color(get_color(name, "#a0a0a0"), -0.2))
        style.map(style_name,
                    background=[("disabled", "#b0b0b0"), ('pressed', modify_color(get_color(name, "#d0d0d0"), -0.1)), ('active', modify_color(get_color(name, "#d0d0d0"), 0.1))],
                    foreground=[("disabled", "#707070"), ('pressed', modify_color(get_color(name, "#000000"), 0.25)), ('active', modify_color(get_color(name, "#000000"), 0.5))],
                    bordercolor=[("disabled", "#a0a0a0"), ('pressed', modify_color(get_color(name, "#a0a0a0"), -0.3)), ('active', modify_color(get_color(name, "#a0a0a0"), -0.1))],
                    relief=[("disabled", "raised"), ('pressed', 'sunken'), ('!pressed', 'raised')])
        btn = ttk.Button(frame, text=option, width=max_length, command=lambda i=index: var.set(i), style=style_name, state="normal" if release_range_enabled else "disabled")
        btn.config(padding=(0, 0))
        btn.pack(side=tk.LEFT)
        buttons.append(btn)

    # Sync button visuals without calling selections_update
    current = var.get()
    for i, btn in enumerate(buttons):
        btn.state(['pressed'] if i == current else ['!pressed'])

def populate_context_frames(contextframe, contextrow, contextlist, frames) -> int:
    # Populate the frames used for the normal and custom contexts choices from the settings file.
    
    # Clear existing widgets in the context frame
    for child in contextframe.winfo_children():
        child.destroy()

    # Rebuild the lists to avoid stale frame references
    contextlist.clear()
    frames.clear()

    # Create the platforms frame first
    platform_frame = ttk.Frame(contextframe, padding="2")
    platform_frame.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(platform_frame)
    contextlist.append(("platforms", platform_frame))
    contextrow += 1

    for context in get_fixed_contexts():
        if context == "release_range" and not is_release_range_large_enough():
            continue

        frame = ttk.Frame(contextframe, padding="2")
        frame.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
        frames.append(frame)
        contextrow += 1
        contextlist.append((context, frame))

    for context in get_custom_contexts():
        frame = ttk.Frame(contextframe, padding="2")
        frame.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
        frames.append(frame)
        contextrow += 1
        contextlist.append((context, frame))

    return contextrow

def populate_context_setup(frame, entries, row_idx, main_contextframe) -> int:
    if active_settings is None:
        return row_idx
    
    # Clear existing widgets in the frame
    for child in frame.winfo_children():
        child.destroy()
    
    for context_choice in get_fixed_contexts():
        label = ttk.Label(frame, text=f"{context_choice.capitalize()}:")
        label.grid(row=row_idx, column=0, sticky=tk.W)
        stringvar = tk.StringVar(value="; ".join(active_settings.get("context", {}).get(context_choice, [])))
        entry = ttk.Entry(frame, textvariable=stringvar)
        entry.grid(row=row_idx, column=1, sticky=tk.W+tk.E)
        entries[context_choice] = stringvar
        row_idx += 1

    for context_choice in get_custom_contexts():
        label = ttk.Label(frame, text=f"{context_choice.capitalize()}:")
        label.grid(row=row_idx, column=0, sticky=tk.W)
        stringvar = tk.StringVar(value="; ".join(active_settings.get("custom_context", {}).get(context_choice, [])))
        entry = ttk.Entry(frame, textvariable=stringvar)
        entry.grid(row=row_idx, column=1, sticky=tk.W+tk.E)
        entries[context_choice] = stringvar
        del_btn = ttk.Button(frame, text="Delete", command=lambda c=context_choice, mcf=main_contextframe: context_delete(frame, entries, c, mcf))
        del_btn.grid(row=row_idx, column=2, sticky=tk.W)
        row_idx += 1

    saddcontextbutton = ttk.Button(frame, text="Add Context", command=lambda mcf=main_contextframe: context_add(frame, entries, row_idx, mcf))
    saddcontextbutton.grid(row=row_idx, column=0, sticky="nsew", columnspan=3)
    row_idx += 1

    for child in frame.winfo_children():
        child.grid_configure(padx=4, pady=4)

    return row_idx

def populate_export_buttons(frame, row=0):
    global export_status

    export_formats = (
        ("pdf", "Export as PDF"),
        ("csv", "Export as CSV"),
        ("tsv", "Export as TSV"),
        ("xlsx", "Export as XLSX"),
    )

    def run_export(export_format):
        export_collection(export_format)
        update_export_statuses()

    for column, (export_format, button_text) in enumerate(export_formats, start=1):
        frame.columnconfigure(column, weight=1)

        export_button = ttk.Button(frame, text=button_text, command=lambda fmt=export_format: run_export(fmt))
        export_button.grid(row=row, column=column, sticky="ew", padx=4, pady=(0, 0))
        export_button.configure(padding=0)

        status_label = ttk.Label(frame, text=get_export_status(export_format), anchor="center")
        status_label.grid(row=row+1, column=column, sticky="ew", padx=4, pady=(0, 2))

        export_status[export_format] = status_label
    
    update_export_statuses()

def populate_platform_defaults_list(frame, settings_keys):
    if active_settings is None:
        return
    
    for child in frame.winfo_children():
        child.destroy()

    def default_edit(platform, key, var):
        if active_settings is None:
            return
        options = get_options_for_key(key)
        idx = options.index(var.get()) if var.get() in options else 0
        active_settings.setdefault("platform_defaults", {}).setdefault(platform, {})[key] = idx
        settings_save()

    def default_remove(platform):
        if active_settings is None:
            return
        active_settings.setdefault("platform_defaults", {}).pop(platform, None)
        settings_save()
        populate_platform_defaults_list(frame, settings_keys)

    for i, (platform, settings) in enumerate(active_settings.setdefault("platform_defaults", {}).items()):
        platform_name = platform
        row_frame = ttk.Frame(frame)
        row_frame.grid(sticky="nsew", padx=4, pady=2)
        ttk.Label(row_frame, text=platform_name, width=15).grid(row=0, column=0, padx=4, pady=2, sticky="w")
        for j, key in enumerate(settings_keys, start=1):
            options = get_options_for_key(key)
            idx = settings.get(key, 0)
            var = tk.StringVar(value=options[idx] if options else "")
            menu = ttk.OptionMenu(row_frame, var, var.get(), *options)
            menu.configure(padding=(0, 0))
            menu.config(width=len(max(options, key=len)) + 2 if options else 10)
            menu.grid(row=0, column=j, padx=2, pady=2, sticky="w")

            # Add trace to update the settings when the dropdown value changes
            var.trace_add("write", lambda *args, p=platform, k=key, v=var: default_edit(p, k, v))
        
        delete_button = ttk.Button(row_frame, text="Delete", command=lambda p=platform: default_remove(p))
        delete_button.configure(padding=(0, 0))
        delete_button.grid(row=0, column=len(settings_keys) + 1, padx=4, pady=2, sticky="w")

def populate_platform_mapping_list(frame, platform_list=None, window=None):
    if active_settings is None:
        return
    
    for child in frame.winfo_children():
        child.destroy()

    def pm_add():
        if active_settings is None:
            return
        
        new_key = f"Platform{len(active_settings['platforms'])+1}"
        active_settings["platforms"][new_key] = new_key
        populate_platform_mapping_list(frame, platform_list=platform_list, window=window)

    def pm_close():
        pm_save(entries=entries)
        if window is not None:
            window.destroy()

    def pm_remove(key):
        if active_settings is None:
            return
        active_settings["platforms"].pop(key, None)
        entries.pop(key, None)
        pm_save(entries=entries)
        populate_platform_mapping_list(frame, platform_list=platform_list, window=window)

    def pm_save(event=None, entries=None):
        if active_settings is None or entries is None:
            return
        new_platforms = {}
        for k, (key_entry, name_entry) in entries.items():
            new_platforms[key_entry.get().strip() or k] = name_entry.get().strip() or key_entry.get().strip() or k
        active_settings["platforms"] = new_platforms
        if platform_list is not None:
            platform_list.set("; ".join(get_platforms()))
        settings_save()

    entries = {}
    platforms = get_platforms()
    for i, key in enumerate(platforms, start=2):
        name = active_settings["platforms"].get(key, key)
        key_entry = ttk.Entry(frame)
        key_entry.grid(row=i, column=0, sticky="nsew", padx=2, pady=2)
        key_entry.insert(0, key)

        name_entry = ttk.Entry(frame)
        name_entry.grid(row=i, column=1, sticky="nsew", padx=2, pady=2)
        name_entry.insert(0, name)

        entries[key] = (key_entry, name_entry)

        pmremovebutton = ttk.Button(frame, text="Delete", command=lambda k=key: pm_remove(k))
        pmremovebutton.grid(row=i, column=2, sticky="nsew", padx=2, pady=2)

        name_entry.bind("<FocusOut>", lambda event, e=entries: pm_save(event, e))
        name_entry.bind("<Return>", lambda event, e=entries: pm_save(event, e))
        key_entry.bind("<FocusOut>", lambda event, e=entries: pm_save(event, e))
        key_entry.bind("<Return>", lambda event, e=entries: pm_save(event, e))

    pmactionsframe = ttk.Frame(frame)
    pmactionsframe.grid(row=len(platforms) + 2, column=0, columnspan=3, sticky="nsew", padx=2, pady=2)
    pmactionsframe.columnconfigure(0, weight=1)
    pmactionsframe.columnconfigure(1, weight=1)
    pmaddbutton = ttk.Button(pmactionsframe, text="Add Platform", command=lambda: pm_add())
    pmaddbutton.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
    pmclosebutton = ttk.Button(pmactionsframe, text="Close", command=pm_close)
    pmclosebutton.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

def populate_rule_list(frame):
    if active_settings is None:
        return
    
    columns = active_settings.get("column_order", [])
    cols_to_drop = active_settings.get("columns_to_drop", {})

    for child in frame.winfo_children():
        child.destroy()

    for i, (rule, drop_col) in enumerate(cols_to_drop.items()):
        # Set the inversion bool based on the rule name
        invert = rule.startswith("NOT_")
        rule_name = rule[4:] if invert else rule

        not_var = tk.BooleanVar(value=invert)
        not_check = ttk.Checkbutton(frame, text="NOT_", variable=not_var)
        not_check.grid(row=i, column=0, sticky="nw", padx=4, pady=4)

        rule_platform = tk.StringVar(value=rule_name)
        rule_platform_menu = ttk.OptionMenu(frame, rule_platform, rule_platform.get(), *get_platforms())
        rule_platform_menu.grid(row=i, column=1, sticky="nw", padx=4, pady=4)

        for j, col in enumerate(columns, start=2):
            var = tk.BooleanVar(value=col in drop_col)
            chk = ttk.Checkbutton(frame, variable=var)
            chk.grid(row=i, column=j, sticky="nsew")
            var.trace_add("write", lambda *args, rk=rule, c=col, v=var: exclusion_rule_edit(frame, rk, c, v.get()))

        rule_delete_button = ttk.Button(frame, text="Delete", command=lambda r=rule: exclusion_rule_delete(frame, r))
        rule_delete_button.grid(row=i, column=j+1, sticky="nsew", padx=4, pady=4)

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

        btn_text = handle_ellipsis(t)
        btn = ttk.Button(frame, text=btn_text, command=on_click)
        btn.grid(row=row, column=btn_col, sticky="nsew")
        btn.config(padding=(0, 0))
        Tooltip(btn, text=t)
        sel_buttons.append((btn, t))

    for btn, val in sel_buttons:
        btn.state(['pressed'] if val == active_selection.get() else ['!pressed'])

    return active_selection, offset

def populate_taxonomy_setup(frame, entries, row_idx):
    if active_taxonomy is None:
        return row_idx
    
    # Clear existing widgets in the frame
    for child in frame.winfo_children():
        child.destroy()

    for taxonomy_key in get_taxonomy_keys():
        label = ttk.Label(frame, text=f"{taxonomy_key.capitalize()}:")
        label.grid(row=row_idx, column=0, sticky=tk.W)
        stringvar = tk.StringVar(value="; ".join(get_taxonomy_data(taxonomy_key)))
        entry = ttk.Entry(frame, textvariable=stringvar)
        entry.grid(row=row_idx, column=1, sticky=tk.W+tk.E)
        entries[taxonomy_key] = stringvar
        del_btn = ttk.Button(frame, text="Delete", padding=(0, 0), command=lambda c=taxonomy_key: taxonomy_delete(frame, entries, c))
        del_btn.grid(row=row_idx, column=2, sticky=tk.W)
        row_idx += 1

    addtaxonomybutton = ttk.Button(frame, text="Add Taxonomy", command=lambda: taxonomy_add(frame, entries, row_idx))
    addtaxonomybutton.grid(row=row_idx, column=0, sticky="nsew", columnspan=3)
    row_idx += 1

    for child in frame.winfo_children():
        child.grid_configure(padx=4, pady=4)

    return row_idx

def populate_toggles(frame):
    if active_settings is None:
        return
    
    max_columns = 5
    toggle_column = 0
    toggle_row = 0
    toggles = active_settings.get("toggles", {})
    toggle_descs = active_settings.get("toggle_descriptions", {})
    for toggle, value in toggles.items():
        var = tk.BooleanVar(value=value)
        btn = ttk.Checkbutton(frame, text=toggle.replace("_", " ").title(), variable=var, command=lambda t=toggle: handle_toggle_change(t))
        btn.grid(row=toggle_row, column=toggle_column, sticky=tk.W)
        tooltip_text = toggle_descs.get(toggle, "")
        if tooltip_text:
            Tooltip(btn, text=tooltip_text)
        toggle_column += 1
        if toggle_column >= max_columns:
            toggle_column = 0
            toggle_row += 1

def rebuild_context_choices():
    if contextframe is None:
        return

    populate_context_frames(contextframe, 0, contextlist, frames)

    for key, frame in contextlist:
        populate_context_choices(frame, key)

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

    match = get_game_data(title, platform)
    if match is None:
        handle_error(f"No matching row found for '{title}' on platform '{platform}' in the log.")
        return
    
    clipboard_data = match.to_csv(sep="\t", index=False, header=False)

    pyperclip.copy(clipboard_data)

    messagebox.showinfo("Recalled", f"Copied latest matching row for '{title}' to clipboard")

def rotated_text_image(text, font_size=12, font_path=None):
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    dummy = Image.new("RGBA", (1,1), (255,255,255,0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0,0), text, font=font)
    w, h = int(bbox[2] - bbox[0]), int((bbox[3] - bbox[1])*1.5)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), text, fill="black", font=font)
    img = img.rotate(-90, expand=True)
    return ImageTk.PhotoImage(img)

def scrape_pricecharting_img(soup, force=False):
    if soup is None:
        return None

    img_soup = soup.find('div', class_='cover')
    if img_soup is None:
        return None

    platform = get_platform_name()
    filename = get_moby_id() or get_simplified_text(active_game_data.get('title', "unknown")).replace(" ", "_")
    
    img = img_soup.find('img')
    img_path = Path(f"{BASE_DIR}/Data/Images/{platform}/{filename}.png")

    if img_path.is_file() and not force:
        print(f"Debug: Image already exists at {img_path}.")
        return img_path

    img_url = img['src'] if img else None
    if img_url is None:
        print("Debug: No image URL found.")
        return None

    try:
        response = requests.get(img_url, timeout=30)
        response.raise_for_status()

        img_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(BytesIO(response.content)) as image:
            image.convert("RGBA").save(img_path, "PNG")

        print(f"Debug: Saved PriceCharting image to {img_path}")
        return img_path

    except (requests.RequestException, OSError) as exc:
        print(f"Debug: Failed to save PriceCharting image: {exc}")
        return None

def scrape_pricecharting_price(query, known_url=None):
    global active_pricecharting_soup, active_pricecharting_requested_url, active_pricecharting_url
    skip = False
    if skip:
        print("Debug: Skipping PriceCharting scrape due to skip flag.")
        return None, None

    title = get_simplified_text(active_game_data.get('title')) if active_game_data else None
    edition = str(get_edition() or "").casefold()

    if active_settings is None:
        return None, None

    price_soup = None
    big_soup = None
    product_page = False
    response_url = None
    product_response_url = None
    search_url = known_url if known_url is not None else None

    # Try title first since we generally have more luck with that
    if price_soup is None and known_url is None:
        search_url = f"https://www.pricecharting.com/search-products?type=prices&q={title}"
        _, price_soup, big_soup, response_url = get_specific_soup_by_class(search_url, "table", "js-addable hoverable-rows sortable")

    # Try the UPC as a fallback
    if is_upc(query) and price_soup is None and known_url is None:
        search_url = f"https://www.pricecharting.com/search-products?type=prices&q={query}"
        _, price_soup, big_soup, response_url = get_specific_soup_by_class(search_url, "table", "js-addable hoverable-rows sortable")

    if known_url is not None:
        if (active_pricecharting_soup is not None and known_url in (active_pricecharting_url, active_pricecharting_requested_url)):
            big_soup = active_pricecharting_soup
            response_url = active_pricecharting_url
            _, price_soup, _, product_response_url = get_specific_soup_by_id(known_url, "table", "price_data", known_soup=big_soup)
        else:
            product_page, price_soup, big_soup, product_response_url = get_specific_soup_by_id(known_url, "table", "price_data", known_soup=big_soup)

    if price_soup is None:
        product_page, price_soup, big_soup, product_response_url = get_specific_soup_by_id(search_url, "table", "price_data", known_soup=big_soup)

    if big_soup is not None:
        product_page = True
        active_pricecharting_soup = big_soup
        active_pricecharting_requested_url = search_url
        active_pricecharting_url = response_url

    # Ensure that the redirected URL is used if available
    response_url = response_url or product_response_url

    if known_url is None:
        print(f"Debug: Search URL: {search_url}")
    if price_soup is None:
        print("Debug: No prices table found.")
        return None, None

    # Get the mapped platform name from settings
    platform_alias = get_platform_alias()
    if platform_alias is None:
        return None, None
    
    # Find the row that contains the platform name
    use_pal = is_toggled("use_pal")
    text_to_find = "pal " + platform_alias.lower() if use_pal else platform_alias.lower()
    condition = get_condition()
    sealed = condition and 'sealed' in condition.lower()
    contents = get_contents()
    loose = contents and 'loose' in contents.lower()

    if product_page:
        platform_row = price_soup
        item_link = response_url
        price = None
        price_labels = {}

        full_prices = big_soup.find("div", id="full-prices") if big_soup else None
        # Use the full prices section if available, otherwise fall back to the price row
        if full_prices is None:
            if sealed:
                price_cell_id = "new_price"
            elif loose:
                price_cell_id = "used_price"
            else:
                price_cell_id = "complete_price"
    
            price_cell = price_soup.find("td", id=price_cell_id)
            price_span = price_cell.find("span", class_="price") if price_cell else None
            price = price_span.get_text(" ", strip=True) if price_span else None
    
            return price, item_link
        
        for row in full_prices.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            label = cells[0].get_text(" ", strip=True).casefold()
            value = cells[1].get_text(" ", strip=True)
            if value != "-":
                price_labels[label] = value

        if sealed:
            price_label = "new"
        else:
            content_value = str(contents or "").casefold()

            price_label = {
                "cib": "complete",
                "no manual": "item & box",
                "no case": "item & manual",
                "no sleeve": "item & box",
                "manual only": "manual only",
                "sleeve only": "manual only",
                "case only": "box only",
                "loose disc": "loose",
                "nothing": "loose"
            }.get(content_value, "complete")

        price = price_labels.get(price_label)

        return price, item_link

    # Get all rows that contain the platform name, avoiding duplicates
    platform_rows = []
    for platform_link in price_soup.find_all("a", string=lambda text: (text and text_to_find in text.casefold())):
        row = platform_link.find_parent("tr")
        if row is not None and row not in platform_rows:
            platform_rows.append(row)

    # Among platform rows, find the one with the matching title
    platform_row = None
    modified_title = title
    edition = str(get_edition() or "").casefold()
    release_range = get_release_range()

    # Adjust title for platinum edition if applicable
    if release_range and edition == "re-release":
        modified_title = f"{title} {release_range}"
        print(f"Debug: Adjusted title for release range: {modified_title}")

    for row in platform_rows:
        title_cell = row.find("td", class_="title")
        title_link = title_cell.find("a") if title_cell else None
        row_title = title_link.get_text(" ", strip=True) if title_link else ""
        row_title_normalized = get_simplified_text(row_title)

        if row_title_normalized == modified_title:
            platform_row = row
            break

        if not release_range and row_title_normalized == title:
            platform_row = row
            break

    if platform_row is None:
        print(f"Debug: No price info found for '{title}' ({platform_alias}).")
        return None, None

    # Get the link to item that matches the platform
    item_cell = platform_row.find('td', class_='title')
    item_link = item_cell.find('a')['href'] if item_cell else None
    
    price_type = 'New Price' if sealed else 'Loose' if loose else 'CIB Price'
    # Get the corresponding Used Price or New Price column depending on the condition
    price_header_text = price_soup.find('span', string=price_type)

    # Get the sometime alternate header text if the expected one isn't found
    if price_header_text is None:
        price_type = 'High Price' if sealed else 'Low Price' if loose else 'Mid Price'
        price_header_text = price_soup.find('span', string=price_type)

    print(f"Debug: Price Header Text: {price_header_text}")
    price_header = price_header_text.find_parent('th') if price_header_text else None

    print(f"Debug: Price Header: {price_header}")

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

def scrape_upc(soup):
    print(f"Debug: Scraping UPC")
    if soup is None:
        return None

    upc_soup = soup.find('table', id='attribute')

    if upc_soup is None:
        print("Debug: No UPC table found.")
        return None
    
    # Find the row that contains the platform name
    upc_row = upc_soup.find('tr', itemprop='identifier')
    if upc_row is None:
        print(f"Debug: No UPC found {upc_row}.")
        return None

    upc = upc_row.find('td', class_='details').text.strip()
    if upc is None or upc.lower() == "none":
        print(f"Debug: UPC not found in the expected cell: {upc}")
        return None

    print(f"Debug: Found UPC: {upc}")
    return upc   

def search_game(query):
    global active_game_data, active_taxonomy, active_contexts, active_title, active_perspective, active_game_is_new, active_source_taxonomy, active_source_game_data, active_specs
    global active_pricecharting_soup, active_pricecharting_requested_url, active_pricecharting_url
    active_pricecharting_soup = None
    active_pricecharting_requested_url = None
    active_pricecharting_url = None
    active_game_data = {}
    active_taxonomy = {}
    active_contexts = {}
    active_specs = {}
    active_source_taxonomy = {}
    active_game_is_new = False
    
    if active_settings is None:
        return None

    match = get_game_source_data(query)

    if match is None:
        handle_error(f"No matching game found for query '{query}'")
        active_game_is_new = True

        active_game_data = {key: "" for key in active_settings.get("scraped_data", {})}
        active_taxonomy = {key: "" for key in active_settings.get("taxonomy", {})}
        active_contexts = {key: get_context_data(key) for key in get_all_contexts()}
        active_source_taxonomy = {}
        active_source_game_data = {}

        active_game_data["title"] = str(query).strip() if not is_upc(query) else ""
        active_game_data["publisher"] = ""
        active_game_data["developer"] = ""
        active_game_data["release_date"] = ""
        active_game_data["url"] = ""
        active_game_data["upc"] = query if is_upc(query) else ""

        active_contexts["payed"] = ""
        active_contexts["price"] = ""

        def finish_unknown():
            settings_set_defaults()
            update_button_states("normal")
            update_info_frame()
            button_focus_accept()

        if app_root is not None:
            app_root.after(100, finish_unknown)

        return

    normalized_match = handle_normalized_dict(match)
    active_game_data["title"] = match.get("title", "")
    active_game_data["developer"] = match.get("developer", "")
    active_game_data["release_date"] = match.get("release_date", "")
    active_game_data["publisher"] = match.get("publisher", "")
    active_game_data["moby_score"] = match.get("moby_score", "")
    active_game_data["age_rating"] = match.get("age_rating", "")
    active_game_data["upc"] = match.get("upc", "")
    active_game_data["url"] = match.get("url", "")
    active_game_data["price_url"] = ""

    for taxonomy_key in get_taxonomy_keys():
        value = match.get(taxonomy_key, "")
        active_taxonomy[taxonomy_key] = value
        active_source_taxonomy[taxonomy_key] = value

    active_source_game_data = get_filtered_game_data(match)
    get_os_specs(match)

    # Populate the active_source_game_data with OS-specific versions from the match
    for os_name, versions in get_os().items():
        if os_name == "DOS":
            active_source_game_data["DOS"] = normalized_match.get("dos", "")
        else:
            for version in versions:
                source_key = handle_normalized_text(str(version).replace(" ", "_"))
                active_source_game_data[str(version)] = normalized_match.get(source_key, "")

    # Get the context data from the match or use the default values if not found
    for context in get_all_contexts():
        context_singular = context[:-1] if context.endswith("s") else context
        active_contexts[context] = match.get(context_singular, get_context_data(context))
        # Update context selections based on the active_contexts
        if context in active_selections:
            options = get_context_options(context)
            if options:
                idx = options.index(active_contexts[context])
                active_selections[context].set(idx)
        print(f"Debug: Context '{context_singular}': {active_contexts[context]}")

    active_contexts["price"], item_link = scrape_pricecharting_price(query)
    if item_link:
        active_game_data["price_url"] = item_link
        print(f"Debug: Got link scraping {item_link}")
        pc_soup = get_soup(item_link) if active_pricecharting_soup is None else active_pricecharting_soup
        upc = scrape_upc(pc_soup) if not is_upc(query) else ""
        active_game_data["upc"] = upc if upc else active_game_data.get("upc", "")
        cover_img_path = scrape_pricecharting_img(pc_soup)
    else:
        active_game_data.setdefault('upc', '')
        print("Debug: No UPC found from search query or item page.")
    active_contexts["payed"] = ""
    
    def finish():
        update_button_states("normal")
        update_info_frame()
        button_focus_accept()

    if app_root is None:
        return
    app_root.after(100, finish)

def selections_update(name, value):
    # Update the defaults based on the platform selection
    if name == "platforms":
        settings_set_defaults(value)

        release_selection = active_selections.get("release_range")
        release_options = get_release_ranges()

        if release_selection is not None:
            if not release_options:
                release_selection.set(0)
            elif release_selection.get() >= len(release_options):
                release_selection.set(0)

        rebuild_context_choices()

    if active_settings is None:
        return
    
    old_condition = str(active_contexts.get("conditions") or "").casefold()
    old_content = str(active_contexts.get("contents") or "").casefold()

    for setting in active_contexts.keys():   
        options_key = "release_range" if setting == "release_range" else setting if setting.endswith("s") else setting + "s"
        options = get_context_options(options_key)
        if not options:
            continue
        active_contexts[setting] = options[active_selections.get(options_key, tk.IntVar()).get()]

    # Refetch the price if the condition or content has changed in a way that affects the price
    if name in ("conditions", "contents"):
        new_condition = str(active_contexts.get("conditions") or "").casefold()
        new_content = str(active_contexts.get("contents") or "").casefold()
        should_refetch = (name == "conditions" and (("sealed" in new_condition and "sealed" not in old_condition) or ("sealed" in old_condition and "sealed" not in new_condition))) or new_content != old_content
        price = None
        if should_refetch and (active_game_data.get("title") != "" or active_game_data.get("upc") != ""):
            print(f"Debug: Getting new prices due to change in condition/content. Old Condition: {old_condition}, New Condition: {new_condition}, Old Content: {old_content}, New Content: {new_content}")
            price, _ = scrape_pricecharting_price(active_game_data.get("upc") or active_game_data.get("title", ""), known_url=active_game_data.get("price_url", None))

        if price is not None:
            active_contexts["price"] = price

    if name == "editions":
        rebuild_context_choices()

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

def settings_save():
    # Save settings to the settings.json file
    global active_settings
    if active_settings is None:
        return
    try:
        with open(os.path.join(BASE_DIR, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(active_settings, f, indent=4, ensure_ascii=True)
        print("Settings saved successfully.")
    except Exception as e:
        print(f"Error saving settings: {e}")
        handle_error(f"Error saving settings: {e}")

def settings_set_defaults(platform_index:int = 0):
    # Set default values for settings based on the selected platform
    global active_settings
    if active_settings is None:
        active_settings = {}

    if platform_index is None:
        return

    # Get all the defaults for the selected platform, or use the "Default" defaults if the platform is not found
    platform_settings = active_settings.get("platform_defaults", {})
    platform_key = get_platform_key()
    platform_defaults = platform_settings.get(platform_key, platform_settings.get("Default", {}))

    for setting, value in platform_defaults.items():
        # Contexts
        if isinstance(active_selections.get(setting), tk.IntVar):
            active_selections[setting].set(value)
            continue

        # Taxonomy
        if setting in active_settings.get("taxonomy", {}):
            if active_taxonomy.get(setting):
                continue  # Skip if the taxonomy field already has a value
            options = active_settings.get("taxonomy", {}).get(setting, "")
            idx = int(value) if isinstance(value, int) else 0
            idx = max(0, min(idx, len(options) - 1))  # Ensure idx is within bounds
            active_taxonomy[setting] = options[idx] if options else ""
            continue

    update_info_frame()

    return

def taxonomy_add(frame, entries, row_idx=0):
    global active_settings, active_taxonomy
    if active_settings is None:
        return
    
    new_field = simpledialog.askstring("Add Taxonomy", "Enter the name of the new taxonomy field:")
    if not new_field:
        return
    
    key = new_field.lower()
    active_settings.setdefault("taxonomy", {})[key] = []

    # Add title-case version to column_order
    key_title_case = new_field.title()
    column_order_lower = [c.lower() for c in active_settings.setdefault("column_order", [])]
    
    if key not in column_order_lower:
        column_order = active_settings.setdefault("column_order", [])
        column_order.append(key_title_case)
        active_settings["column_order"] = column_order

    settings_save()
    populate_taxonomy_setup(frame, entries, row_idx)
    
    # Rebuild active_taxonomy
    for k, v in active_settings.get("taxonomy", {}).items():
        active_taxonomy[k] = v
    update_info_frame()

def taxonomy_delete(frame, entries, taxonomy_choice):
    global active_settings, active_taxonomy
    if active_settings is None:
        return
    
    key = taxonomy_choice.lower()
    active_settings.setdefault("taxonomy", {}).pop(key, None)

    # Remove any matching column_order entries (case-insensitive)
    column_order = active_settings.setdefault("column_order", [])
    column_order[:] = [c for c in column_order if c.lower() != key.lower()]
    active_settings["column_order"] = column_order

    settings_save()
    populate_taxonomy_setup(frame, entries, 0)

    # Rebuild active_taxonomy
    for k, v in active_settings.get("taxonomy", {}).items():
        active_taxonomy[k] = v
    update_info_frame()

def update_button_states(state):
    # Find the search frame in the frames_padded list and update the state of the buttons
    search_frame = None
    for frame in frames_padded:
        if isinstance(frame, ttk.LabelFrame) and frame.cget("text") == "Search":
            search_frame = frame
            break
    if search_frame is not None:
        for child in search_frame.winfo_children():
            if isinstance(child, ttk.Button):
                child.config(state=state)

def update_choices(contextentries = None, taxonomyentries = None, changes=False):
    # Update the choices for context selection
    global active_settings
    if active_settings is None:
        return

    if contextentries is None:
        contextentries = {}

    if taxonomyentries is None:
        taxonomyentries = {}

    for context_choice, entry in contextentries.items():
        # We save the changes for platforms elsewhere, so always assume there are changes
        if context_choice == "platforms":
            changes = True
            continue

        # Get the text in the entry and split it by semicolons
        text = entry.get()
        choices = [t.strip() for t in text.split(";") if t.strip()]

        # Save the normal context choices to the context dict in settings
        if context_choice in active_settings.get("context", {}):
            if active_settings.get("context", {}).get(context_choice) == choices:
                continue

            active_settings.setdefault("context", {})[context_choice] = choices
            changes = True

        # Save the custom context choices to the custom_context dict in settings
        if context_choice in active_settings.get("custom_context", {}):
            if active_settings.get("custom_context", {}).get(context_choice) == choices:
                continue

            active_settings.setdefault("custom_context", {})[context_choice] = choices
            changes = True

    for taxonomy, entry in taxonomyentries.items():
        # Get the text in the entry and split it by semicolons
        text = entry.get()
        choices = [t.strip() for t in text.split(";") if t.strip()]
        if taxonomy in active_settings.get("taxonomy", {}):
            if active_settings.get("taxonomy", {}).get(taxonomy) == choices:
                continue

            active_settings.setdefault("taxonomy", {})[taxonomy] = choices
            changes = True

    if not changes:
        return

    settings_save()
    for key, frame in contextlist:
        if contextentries and key not in contextentries:
            continue
        
        # clear existing widgets so populate_menu doesn't duplicate
        for child in frame.winfo_children():
            child.destroy()
        populate_context_choices(frame, key)
    update_info_frame()

def update_collection_pie_chart(chart_name, values, title=None):
    global col_stats_graph_frame, col_stats_chart, col_stats_chart_data

    if col_stats_graph_frame is None:
        return
    
    col_stats_chart_data[chart_name] = (values, title)

    chart_padding = 4
    available_width = col_stats_graph_frame.winfo_width()
    chart_width = max(1, (available_width - (CHARTS_PER_ROW + 1) * chart_padding) // CHARTS_PER_ROW)
    chart_height = max(280, chart_width // 2)

    chart_index = list(col_stats_chart_data).index(chart_name)
    chart_row = chart_index // CHARTS_PER_ROW
    chart_column = chart_index % CHARTS_PER_ROW

    canvas = col_stats_chart.get(chart_name)
    if canvas is None or not canvas.winfo_exists():
        canvas = tk.Canvas(col_stats_graph_frame, width=chart_width, height=chart_height, background="white", highlightthickness=0)
        col_stats_chart[chart_name] = canvas
    else:
        canvas.configure(width=chart_width)
    canvas.grid(row=chart_row, column=chart_column, sticky="nsew", padx=chart_padding, pady=chart_padding)
    canvas.delete("all")

    chart_values = {}
    for label, value in values.items():
        numeric_value = float(value)
        if numeric_value > 0:
            chart_values[str(label)] = numeric_value

    chart_width = int(canvas.cget("width"))
    chart_height = int(canvas.cget("height"))

    if not chart_values:
        canvas.create_text(chart_width // 2, chart_height // 2, text="No collection data", anchor="center")
        return

    total = sum(chart_values.values())
    title_space = 30
    vertical_padding = 20
    left_margin = 20
    legend_gap = 25
    legend_width = chart_width // 2

    available_pie_width = (chart_width - left_margin - legend_gap - legend_width)
    available_pie_height = chart_height - title_space - vertical_padding

    chart_size = max(1, min(available_pie_width, available_pie_height))

    chart_left = left_margin
    chart_top = title_space + (available_pie_height - chart_size) // 2
    chart_right = chart_left + chart_size
    chart_bottom = chart_top + chart_size

    colors = (
        "#3F5F73",
        "#D97757",
        "#6A9A8B",
        "#C6A15B",
        "#7A6FA8",
        "#4F86A8",
        "#B35C75",
        "#759C5E",
    )

    if title:
        canvas.create_text(chart_width // 4, 20, text=title, anchor="center")

    start_angle = 90
    legend_x = chart_right + 25
    legend_y = 25
    canvas_tooltips = []

    for index, (label, value) in enumerate(chart_values.items()):
        slice_angle = value / total * 360
        slice_color = colors[index % len(colors)]
        percentage = value / total * 100

        arc_id = canvas.create_arc(chart_left, chart_top, chart_right, chart_bottom, start=start_angle, extent=-slice_angle, fill=slice_color, outline="white", width=1)
        canvas_tooltips.append(CanvasTooltip(canvas, arc_id, text=f"{label}: {value:,.1f} ({percentage:.1f}%)"))

        canvas.create_rectangle(legend_x, legend_y - 7, legend_x + 12, legend_y + 5, fill=slice_color, outline=slice_color)
        canvas.create_text(legend_x + 18, legend_y, text=f"{label}: {value:,.1f} ({percentage:.1f}%)", anchor="w")

        legend_y += 24
        start_angle -= slice_angle

def update_collection_stats():
    stats = get_collection_stats()
    update_collection_pie_chart("platform_titles", stats["platform_titles"], title="Titles by Platform")
    update_collection_pie_chart("platform_payed", stats["platform_payed"], title="Payed by Platform")
    update_collection_pie_chart("platform_value", stats["platform_value"], title="Value by Platform")

    if "titles" in collection_stats_labels:
        collection_stats_labels["titles"].configure(text=f"Titles: {stats['titles']:,}")

    if "platforms" in collection_stats_labels:
        collection_stats_labels["platforms"].configure(text=f"Platforms: {stats['platforms']:,}")

    if "payed" in collection_stats_labels:
        collection_stats_labels["payed"].configure(text=f"Total Payed: {stats['payed']:,.2f}")

    if "value" in collection_stats_labels:
        collection_stats_labels["value"].configure(text=f"Total Value: {stats['value']:,.2f}")

def update_export_statuses():
    global export_status

    for export_format, status_label in export_status.items():
        status_label.configure(text=get_export_status(export_format))

    return export_status

def update_info_choice(key, value):
    global active_title, active_perspective
    selected_value = value if isinstance(value, str) else value.get()
    if key in active_game_data:
        active_game_data[key] = selected_value
    elif key in active_taxonomy:
        active_taxonomy[key] = selected_value
    elif key in active_contexts:
        active_contexts[key] = selected_value

def update_info_frame():
    global infoframe, active_game_data, active_taxonomy, active_contexts, active_title, active_perspective, missing_fields
    if infoframe is None:
        return
    
    if active_settings is None:
        return
    
    clear_infoframe()
    _os_version_image_refs.clear()
    missing_fields.clear()
    update_thumbnail()
    
    active_game_items = list(active_game_data.items())
    active_taxonomy_items = list(active_taxonomy.items())
    active_physical_items = list(active_contexts.items())

    max_rows = max(len(active_game_items), len(active_taxonomy_items), len(active_physical_items))

    active_game_data_offset = 0
    active_taxonomy_offset = 0
    active_physical_data_offset = 0

    def _on_submit_data(event=None, k=None, v=None):
        if v is None or k is None:
            return
        new_value = v.get().strip()
        update_info_choice(k, new_value)
        update_info_frame()
        if k.lower() == "title" and acceptbutton is not None and declinebutton is not None:
            state = "normal" if v.get().strip() else "disabled"
            acceptbutton.config(state=state)
            declinebutton.config(state=state)
        if event is not None and event.keysym == "Return":
            return "break"
    # Update the info frame with the current game data
    for i in range(max_rows):
        key, value = active_game_items[i] if i < len(active_game_items) else ("", "")
        display_value = handle_ellipsis(str(value)) if value else ""
        row = i + active_game_data_offset
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(handle_single_option(f"{key.capitalize()}{suffix}")), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=row, column=0, sticky="nsew")

        # Determine the background color based on whether the source game data has changed
        modified = is_source_game_data_changed(key)
        row_style = (f"ModifiedInfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel" if modified else f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")

        url_title = get_simplified_text(active_game_data.get("title", ""))
        url_fallback_moby = "https://www.mobygames.com/search/?q=" + quote_plus(str(url_title))
        release_range = get_release_range()
        edition = get_edition()
        if release_range and edition == "re-release":
            url_title = f"{url_title} {release_range}"
        url_fallback_price = "https://www.pricecharting.com/search-products?type=prices&q=" + quote_plus(str(url_title))
        url_fallback_yt = get_gameplay_url()

        fallback_url = url_fallback_price if key.casefold() == "price_url" else url_fallback_moby if key.casefold() == "url" else url_fallback_yt
        fallback_text = "Search Pricecharting" if key.casefold() == "price_url" else "Search MobyGames" if key.casefold() == "url" else "See Gameplay"

        if (key.casefold() == "url" or key.casefold() == "price_url" or key.casefold() == "gameplay_url") and value == "" and active_game_data.get("title", "") != "":
            url_frame = ttk.Frame(infoframe)
            url_frame.grid(row=row, column=1, sticky="nsew", padx=0, pady=0)
            url_frame.columnconfigure(0, weight=1)
            url_frame.columnconfigure(1, weight=0)
            value_label = tk.Label(url_frame, text=handle_ellipsis(fallback_text), fg="#0563C1", cursor="hand2", anchor="w", background=(active_settings["theming"]["custom_colors"]["row_even_bg"] if row % 2 == 0 else active_settings["theming"]["custom_colors"]["row_odd_bg"]),)
            value_label.bind("<Button-1>", lambda event, url=fallback_url: handle_url(event, url),)
            value_label.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
            Tooltip(value_label, text=fallback_url)
            if key.casefold() == "url":
                add_value_btn = ttk.Button(url_frame, text="Add ID", command=lambda k=key: add_id(k))
            elif key.casefold() == "price_url":
                add_value_btn = ttk.Button(url_frame, text="Add URL", command=lambda k=key: add_url(k))
            elif key.casefold() == "gameplay_url":
                add_value_btn = ttk.Label(url_frame, text="")
            add_value_btn.grid(row=0, column=1, sticky="nsew")
            add_value_btn.configure(padding=(0, 0))
            missing_fields[key] = add_value_btn
        elif key.casefold() == "url" and value or key.casefold() == "price_url" and value:
            value_frame = ttk.Frame(infoframe)
            value_frame.grid(row=row, column=1, sticky="nsew")
            value_frame.columnconfigure(0, weight=1)
            
            value_label = tk.Label(value_frame, text=handle_ellipsis(f"{value}"), fg="#0563C1", cursor="hand2", anchor="w", background=(active_settings["theming"]["custom_colors"]["row_even_bg"] if row % 2 == 0 else active_settings["theming"]["custom_colors"]["row_odd_bg"]),)
            value_label.bind("<Button-1>", lambda event, url=str(value): handle_url(event, url),)
            value_label.grid(row=0, column=0, sticky="nsew")
            if display_value.endswith("..."):
                Tooltip(value_label, text=str(value))

            edit_button = ttk.Button(value_frame, text="Edit", command=lambda d=active_game_data, p=value_frame, k=key: edit_data(d, p, k))
            edit_button.grid(row=0, column=1, sticky="nsew")
            edit_button.configure(padding=(0, 0))

        elif key.casefold() == "upc":
            upc_frame = ttk.Frame(infoframe)
            upc_frame.grid(row=row, column=1, sticky="nsew")
            upc_frame.columnconfigure(0, weight=1)

            value_label = ttk.Label(upc_frame, text=display_value, style=row_style)
            value_label.grid(row=0, column=0, sticky="nsew")
            if display_value.endswith("..."):
                Tooltip(value_label, text=str(value))

            add_upc_button = ttk.Button(upc_frame, text="Add UPC", command=add_upc)
            add_upc_button.grid(row=0, column=1, sticky="nsew")
            add_upc_button.configure(padding=(0, 0))
        elif key:
            value_frame = ttk.Frame(infoframe)
            value_frame.grid(row=row, column=1, sticky="nsew")
            value_frame.columnconfigure(0, weight=1)
            value_frame.configure(style="ModifiedInfoData.TFrame" if modified else "InfoData.TFrame")
            if not value:
                var = tk.StringVar(value="")
                entry = ttk.Entry(value_frame, textvariable=var)
                entry.grid(row=0, column=0, sticky="nsew")
                missing_fields[key] = entry
    
                entry.bind("<Return>", lambda e, value_key=key, value_var=var: _on_submit_data(event=e, k=value_key, v=value_var))
                entry.bind("<FocusOut>", lambda e, value_key=key, value_var=var: _on_submit_data(event=e, k=value_key, v=value_var))
                entry.bind("<Escape>", lambda e: update_info_frame())
            else:
                value_label = ttk.Label(value_frame, text=display_value, style=row_style)
                value_label.grid(row=0, column=0, sticky="nsew")

                edit_button = ttk.Button(value_frame, text="Edit", command=lambda d=active_game_data, p=value_frame, k=key: edit_data(d, p, k))
                edit_button.grid(row=0, column=1, sticky="nsew")
                edit_button.configure(padding=(0, 0))
                if display_value.endswith("..."):
                    Tooltip(value_label, text=str(value))
        else:
            value_label = ttk.Label(infoframe, text="", style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=row, column=1, sticky="nsew")


    # Update the info frame with the current taxonomy data
    for j in range(max_rows):
        key, value = active_taxonomy_items[j] if j < len(active_taxonomy_items) else ("", "")
        row = j + active_taxonomy_offset
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=row, column=2, sticky="nsew")
        options = get_taxonomy_data(key) if key else []

        if key and options:
            pd_idx = get_taxonomy_default_idx(key)
            platform_default = options[pd_idx] if options and 0 <= pd_idx < len(options) else None

            # initial selection preference: explicit value > platform default > first option > empty
            
            initial = value if value else (platform_default if platform_default in options else options[0] if options else "")

            var = tk.StringVar(value=initial)

            taxonomy_modified = is_source_taxonomy_changed(key)
            style_name = ("ModifiedTaxonomy.TMenubutton" if taxonomy_modified else "Taxonomy.TMenubutton")

            menu = ttk.OptionMenu(infoframe, var, var.get(), *options)
            menu.configure(style=style_name, padding=(0, 0))
            menu.grid(row=row, column=3, sticky="nsew")
            menu.bind("<Button-1>", lambda event, widget=menu: widget.focus_set(), add="+")
            missing_fields[key] = menu

            def on_taxonomy_change(*_, k=key, v=var, m=menu):
                update_info_choice(k, v)
                apply_taxonomy_style(k, m)

            var.trace_add("write", on_taxonomy_change)
            apply_taxonomy_style(key, menu)
            
            def _make_cycle_handler(opts, v, direction):
                def handler(event):
                    if not opts:
                        return "break"
                    try:
                        i = opts.index(v.get())
                    except ValueError:
                        i = 0
                    i = (i + direction) % len(opts)
                    v.set(opts[i])
                    return "break"
                return handler

            menu.bind("<Up>", _make_cycle_handler(options, var, -1))
            menu.bind("<Down>", _make_cycle_handler(options, var, 1))
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(handle_single_option(value)), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=row, column=3, sticky="nsew")

    # Update the info frame with the current physical data
    for k in range(max_rows):
        key, value = active_physical_items[k] if k < len(active_physical_items) else ("", "")
        display_value = handle_ellipsis(str(value)) if value else ""
        row = k + active_physical_data_offset
        suffix = ":" if key else ""
        data_label = ttk.Label(infoframe, text=handle_ellipsis(f"{key.capitalize()}{suffix}"), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
        data_label.grid(row=row, column=4, sticky="nsew")
        if key.casefold() == "release_range":
            value_label = ttk.Label(infoframe, text=handle_ellipsis(str(value)), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=row, column=5, sticky="nsew")
            if display_value.endswith("..."):
                Tooltip(value_label, text=str(value))
        elif key.casefold() == "payed" and value:
            value_frame = ttk.Frame(infoframe)
            value_frame.grid(row=row, column=5, sticky="nsew")
            value_frame.columnconfigure(0, weight=1)

            value_label = ttk.Label(value_frame, text=handle_ellipsis(str(value)), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=0, column=0, sticky="nsew")

            edit_button = ttk.Button(value_frame, text="Edit", command=lambda d=active_contexts, p=value_frame, k=key: edit_data(d, p, k))
            edit_button.grid(row=0, column=1, sticky="nsew")
            edit_button.configure(padding=(0, 0))
        elif key and not value:
            var = tk.StringVar(value="")
            entry = ttk.Entry(infoframe, textvariable=var)
            entry.grid(row=row, column=5, sticky="nsew")
            missing_fields[key] = entry

            entry.bind("<Return>", lambda e, value_key=key, value_var=var: _on_submit_data(event=e, k=value_key, v=value_var))
            entry.bind("<FocusOut>", lambda e, value_key=key, value_var=var: _on_submit_data(event=e, k=value_key, v=value_var))
            entry.bind("<Escape>", lambda e: update_info_frame())
        else:
            value_label = ttk.Label(infoframe, text=handle_ellipsis(f"{value}"), style=f"InfoData{'Even' if row % 2 == 0 else 'Odd'}.TLabel")
            value_label.grid(row=row, column=5, sticky="nsew")
            if display_value.endswith("..."):
                Tooltip(value_label, text=str(value))

    # Handle OS versions display
    os_row = len(active_physical_items) + active_physical_data_offset

    for os_name, versions in get_os().items():
        if not versions:
            continue

        frame_modified = is_source_os_changed(os_name)

        os_frame = ttk.Frame(infoframe, style="ModifiedOSFrame.TFrame" if frame_modified else "OSFrame.TFrame", padding=0)
        os_frame.grid(row=os_row, column=4, columnspan=2, rowspan=2, sticky="nsew")
        os_frame.columnconfigure(0, weight=1)

        os_label = ttk.Label(os_frame, text=f"{os_name}:", style=f"InfoData{'Even' if os_row % 2 == 0 else 'Odd'}.TLabel")
        os_label.grid(row=0, column=0, rowspan=2, sticky="nsew")

        for version_index, version in enumerate(versions, start=1):
            version_image = rotated_text_image(str(version), font_size=10)
            _os_version_image_refs.append(version_image)

            selected = version in active_specs.get(os_name, [])
            version_var = tk.BooleanVar(value=selected)

            version_label = ttk.Label(os_frame, image=version_image)
            version_label.grid(row=0, column=version_index, sticky="sw")

            checkpoint = ttk.Checkbutton(os_frame, variable=version_var, command=lambda family=os_name, selected_version=version, var=version_var: update_os_version(family, selected_version, var))
            checkpoint.grid(row=1, column=version_index, sticky="nsew")

        os_row += 2

    cols, rows = infoframe.grid_size()
    for col in range(cols):
        infoframe.columnconfigure(col, weight=0 if col % 2 == 0 else 1, minsize=100 if col % 2 == 0 else 10)
    for row in range(rows):
        infoframe.rowconfigure(row, weight=1, minsize=20)

    infoframe.update_idletasks()

def update_os_version(os_name, version, selected_var):
    global active_specs

    if os_name == "DOS":
        if selected_var.get():
            active_specs["DOS"] = [version]
        else:
            active_specs.pop("DOS", None)
    else:
        selected_versions = active_specs.setdefault(os_name, [])

        if selected_var.get():
            if version not in selected_versions:
                selected_versions.append(version)
        elif version in selected_versions:
            selected_versions.remove(version)

        if not selected_versions:
            active_specs.pop(os_name, None)

    update_info_frame()

def update_source_record():
    if not active_game_data:
        handle_error("No game data available.")
        return False

    source_title = active_source_game_data.get("title", active_game_data.get("title", ""))
    title = handle_normalized_text(source_title)
    platform = get_platform_name()
    source_file = Path(f"{BASE_DIR}/Data/{platform}.xlsx")

    try:
        source_data = pd.read_excel(source_file, engine="openpyxl", dtype=str).fillna("")
        source_data.columns = handle_normalized_list(source_data.columns)
        matching_row = (source_data["title"].map(handle_normalized_text) == title)
        if not matching_row.any():
            handle_error(f"No matching game found for title '{title}' in source data.")
            return False

        existing_row = source_data.loc[matching_row]
        existing_added = existing_row["added"].iloc[0]
        existing_modified = existing_row["modified"].iloc[0] if "modified" in existing_row else None

        record = get_filtered_game_data()
        record.update({
            "platform": platform,
            "added": existing_added,
            **get_os_record_fields()
        })

        for key in get_taxonomy_keys():
            record[key] = active_taxonomy.get(key, "")

        for key in get_all_contexts():
            source_key = key[:-1] if key.endswith("s") else key
            record[source_key] = active_contexts.get(key, "")

        normalized_record = handle_normalized_dict(record)
        changed = any(str(existing_row.get(column, "")) != str(value) for column, value in normalized_record.items())
        normalized_record["modified"] = (get_timestamp() if changed else existing_modified)

        for column, value in normalized_record.items():
            if column in source_data.columns:
                source_data.loc[matching_row, column] = value

        source_data.to_excel(source_file, engine="openpyxl", index=False)

        active_source_taxonomy.update(active_taxonomy)
        print(f"Debug: Updated source data for title '{title}' ({platform})")
        return True

    except Exception as exc:
        handle_error(f"Error updating source data: {exc}")
        return False

def update_thumbnail(image_path=None):
    global thumbnail_label, thumbnail_image, thumbnail_tooltip, thumbnail_refresh_btn

    if thumbnail_label is None:
        return

    if thumbnail_refresh_btn is not None:
        has_moby_url = bool(active_game_data.get("url", ""))
        has_price_url = bool(active_game_data.get("price_url", ""))
        thumbnail_refresh_btn.configure(state="normal" if has_moby_url and has_price_url else "disabled")

    thumbnail_size = (180, 240)

    # Always create a transparent canvas so the thumbnail area keeps its size.
    canvas = Image.new("RGBA", thumbnail_size, (0, 0, 0, 0))

    if image_path is None:
        url = active_game_data.get("url", "")
        image_path = get_thumbnail_path(url)

    if image_path is not None:
        cover = Image.open(image_path).convert("RGBA")
        cover.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)

        x_offset = (thumbnail_size[0] - cover.width) // 2
        y_offset = (thumbnail_size[1] - cover.height) // 2
        canvas.alpha_composite(cover, (x_offset, y_offset))

        if thumbnail_tooltip is not None:
            thumbnail_tooltip.text = f"{image_path.name}"
    elif thumbnail_tooltip is not None:
        thumbnail_tooltip = Tooltip(thumbnail_label, text="Game cover will appear here if available.")

    thumbnail_image = ImageTk.PhotoImage(canvas)
    thumbnail_label.configure(image=thumbnail_image)

def write_new_headers(data, existing_data: pd.DataFrame):
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
    global export_status
    if active_settings is None:
        return

    file_name = get_collection_path()
    clipboard = is_toggled('use_clipboard')

    # Read the existing file and make sure the platform sheet exists if using xls
    file_exists = os.path.isfile(file_name)
    existing = pd.DataFrame()
    if file_exists:
        xl = pd.ExcelFile(file_name, engine='openpyxl')
        if platform in xl.sheet_names:
            existing = pd.read_excel(file_name, sheet_name=platform, engine='openpyxl', dtype=str)

    # Make sure the headers are right
    combined, new_reindexed = write_new_headers(data, existing)
    use_split = is_toggled('use_content_split')
    if use_split:
        combined = combined.drop(columns=['Contents'], errors='ignore')
        new_reindexed = new_reindexed.drop(columns=['Contents'], errors='ignore')
    else:
        drop_content_cols = ['Case', 'Sleeve', 'Manual']
        for col in drop_content_cols:
            combined = combined.drop(columns=[col], errors='ignore')
        new_reindexed = new_reindexed.drop(columns=[col for col in drop_content_cols if col in new_reindexed.columns], errors='ignore')

    # Drop the specified columns, or the columns that don't match the platform
    drop_columns = [column for column in get_columns_to_drop(platform) if column in combined.columns]
    combined = combined.drop(columns=drop_columns, errors='ignore')  
    new_reindexed = new_reindexed.drop(columns=drop_columns, errors='ignore')

    # Write the file back with new data
    with pd.ExcelWriter(file_name, engine='openpyxl', mode='a' if file_exists else 'w', if_sheet_exists='replace') as writer:
        combined.to_excel(writer, sheet_name=platform, index=False)

    color_scanned_collection(file_name, platform)
    update_collection_stats()
    if export_status:
        update_export_statuses()

    if clipboard:
        pyperclip.copy(new_reindexed.to_csv(sep='\t', index=False, header=False))

def main():
    global infoframe, searchentry, logframe, logtree, acceptbutton, declinebutton, contextlist
    global app_root, thumbnail_label, thumbnail_image, thumbnail_tooltip, thumbnail_refresh_btn, contextframe
    global col_stats_chart, col_stats_graph_frame, collection_stats_labels
    if active_settings is None:
        handle_error("No settings available.")
        return

    root = tk.Tk(className="GBScan")
    app_root = root
    root.tk.call('encoding', 'system', 'utf-8')
    root.title("GBScan")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    style = ttk.Style(root)
    if is_toggled('use_custom_ttk_theme'):
        style.theme_use(active_settings['theming'].get('ttk_theme', 'default'))
    even_bg = active_settings["theming"]["custom_colors"]["row_even_bg"]
    odd_bg = active_settings["theming"]["custom_colors"]["row_odd_bg"]
    style.configure("InfoDataEven.TLabel", background=even_bg)
    style.configure("InfoDataOdd.TLabel", background=odd_bg)

    modified_color = get_color("taxonomy_modified", "#FFCC66")

    style.configure("ModifiedInfoDataEven.TLabel", background=modified_color, foreground="#000000")
    style.configure("ModifiedInfoDataOdd.TLabel", background=modified_color, foreground="#000000")
    style.configure("ModifiedTaxonomy.TMenubutton", background=modified_color, foreground="#000000", lightcolor=modify_color(modified_color, 0.2), darkcolor=modify_color(modified_color, -0.1), bordercolor=modify_color(modified_color, -0.2))
    style.map("ModifiedTaxonomy.TMenubutton", background=[("active", modified_color), ("pressed", modified_color), ("!disabled", modified_color)])
    # Select Columns button style on the collection tab
    style.configure("SelectColumns.TButton", background=modified_color, foreground="#000000", lightcolor=modify_color(modified_color, 0.3), darkcolor=modify_color(modified_color, -0.1), bordercolor=modify_color(modified_color, -0.2), padding=0, relief="raised")
    style.map("SelectColumns.TButton", background=[("active", modify_color(modified_color, -0.05)), ("pressed", modified_color), ("!disabled", modified_color)])
    style.configure("ModifiedOSFrame.TFrame", background=modified_color, foreground="#000000")

    main_notebook = ttk.Notebook(root)
    main_notebook.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

    mainrow = 0
    mainframe = ttk.Frame(main_notebook, padding="8")
    mainframe.grid(row=0, column=0, sticky="nsew")

    contextrow = 0
    contextframe = ttk.LabelFrame(mainframe, text="Physical State", padding="8")
    contextframe.grid(row=mainrow, column=0, sticky=tk.W+tk.E)
    mainrow += 1

    contextrow = populate_context_frames(contextframe, contextrow, contextlist, frames)

    databaseframe = ttk.Frame(contextframe, padding="2")
    databaseframe.grid(row=contextrow, column=0, sticky=tk.W+tk.E)
    frames.append(databaseframe)
    contextrow += 1

    info_container = ttk.Frame(mainframe)
    info_container.grid(row=mainrow, column=0, sticky="nsew")
    info_container.columnconfigure(1, weight=1)
    info_container.rowconfigure(0, weight=1)
    frames_padded.append(info_container)

    thumbnail_frame = ttk.LabelFrame(info_container, text="Cover", padding="2", relief=tk.RIDGE)
    thumbnail_frame.grid(row=0, column=0, sticky="nsew")
    thumbnail_frame.columnconfigure(0, weight=1)
    thumbnail_frame.rowconfigure(0, weight=1)
    thumbnail_frame.rowconfigure(1, weight=0)

    thumbnail_label = tk.Label(thumbnail_frame, text="")
    thumbnail_label.grid(row=0, column=0, sticky="nsew")
    thumbnail_tooltip = Tooltip(thumbnail_label, text="Game cover will appear here if available.")

    thumbnail_refresh_btn = ttk.Button(thumbnail_frame, text="Refresh", command=lambda: handle_thumbnail_refresh(), state="disabled")
    thumbnail_refresh_btn.grid(row=1, column=0, sticky="nsew")

    infoframe = ttk.LabelFrame(info_container, text="Info", padding="2", relief=tk.SUNKEN)
    infoframe.grid(row=0, column=1, sticky="nsew")
    frames_padded.append(infoframe)
    mainrow += 1

    rebuild_context_choices()
    update_info_frame()

    logframe = ttk.LabelFrame(mainframe, text="Log", padding="2")
    logframe.grid(row=mainrow, column=0, sticky="nsew")
    frames_padded.append(logframe)
    mainrow += 1

    # Add a scrollable tree view to the log frame with 5 rows visible at a time and 3 columns for Title, Platform, and Release Date
    logtree = ttk.Treeview(logframe, columns=("Title", "Release Date", "Platform", "Format", "Condition", "Case Condition", "Contents", "Edition"), show="headings", height=5)
    logtree.heading("Title", text="Title")
    logtree.heading("Platform", text="Platform")
    logtree.heading("Release Date", text="Release Date")
    logtree.heading("Format", text="Format")
    logtree.heading("Condition", text="Condition")
    logtree.heading("Case Condition", text="Case Condition")
    logtree.heading("Contents", text="Contents")
    logtree.heading("Edition", text="Edition")
    logtree.column("Title", width=300)
    logtree.column("Release Date", width=15)
    logtree.column("Platform", width=15)
    logtree.column("Format", width=15)
    logtree.column("Condition", width=40)
    logtree.column("Case Condition", width=40)
    logtree.column("Contents", width=40)
    logtree.column("Edition", width=40)
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
    searchbutton = ttk.Button(searchframe, text="Search", command=lambda: get_game(searchentry.get() if searchentry is not None else ""))
    searchbutton.grid(row=0, column=2, sticky=tk.W)

    acceptbutton = ttk.Button(searchframe, text="Accept (Y)", state="disabled", command=lambda: game_accept())
    acceptbutton.grid(row=0, column=3, sticky=tk.W)
    declinebutton = ttk.Button(searchframe, text="Discard (N)", state="disabled", command=lambda: game_decline())
    declinebutton.grid(row=0, column=4, sticky=tk.W)

    # Setup Tab where the user can set edit the settings.json file
    setup_tab = ttk.Frame(main_notebook, padding="4")
    setup_tab.columnconfigure(0, weight=1)
    setuprow = 0
    contextentries = {}

    platformsframe = ttk.Frame(setup_tab, padding="4")
    platformsframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    platformsframe.columnconfigure(1, weight=1)
    frames_padded.append(platformsframe)
    setuprow += 1

    splatformslabel = ttk.Label(platformsframe, text="Platforms:")
    splatformslabel.grid(row=0, column=0, sticky=tk.W)
    splatformsstringvar = tk.StringVar(value="; ".join(get_platforms()))
    splatformsentry = ttk.Label(platformsframe, textvariable=splatformsstringvar, relief=tk.SUNKEN)
    splatformsentry.grid(row=0, column=1, sticky=tk.W+tk.E)
    splatformseditbutton = ttk.Button(platformsframe, text="Edit", command=lambda: open_platform_mapping_window(splatformsstringvar))
    splatformseditbutton.grid(row=0, column=2, sticky=tk.W)
    contextentries["platforms"] = splatformsstringvar

    choicesframe = ttk.LabelFrame(setup_tab, text="Contexts", padding="4")
    choicesframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    choicesframe.columnconfigure(1, weight=1)
    frames_padded.append(choicesframe)
    setuprow += 1
    choicesrow = 0

    choicesrow = populate_context_setup(choicesframe, contextentries, choicesrow, contextframe)

    taxonomyentries = {}
    taxonomyframe = ttk.LabelFrame(setup_tab, text="Taxonomy", padding="4")
    taxonomyframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    taxonomyframe.columnconfigure(1, weight=1)
    frames_padded.append(taxonomyframe)
    setuprow += 1
    taxonomyrow = 0

    taxonomyrow = populate_taxonomy_setup(taxonomyframe, taxonomyentries, taxonomyrow)

    exclusionframe = ttk.LabelFrame(setup_tab, text="Tweaks", padding="4")
    exclusionframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    exclusionframe.columnconfigure(0, weight=1)
    exclusionframe.columnconfigure(1, weight=1)
    exclusionframe.columnconfigure(2, weight=1)
    exclusionframe.columnconfigure(3, weight=1)
    frames_padded.append(exclusionframe)
    setuprow += 1

    eexcludebutton = ttk.Button(exclusionframe, text="Edit Columns Per Platform", command=lambda: open_exclusion_window())
    eexcludebutton.grid(row=0, column=0, sticky="nsew")

    eorderbutton = ttk.Button(exclusionframe, text="Edit Column Order", command=lambda: open_column_order_window())
    eorderbutton.grid(row=0, column=1, sticky="nsew")

    edefaultsbutton = ttk.Button(exclusionframe, text="Edit Platform Defaults", command=lambda: open_platform_defaults_window())
    edefaultsbutton.grid(row=0, column=2, sticky="nsew")

    ecustomcolorsbutton = ttk.Button(exclusionframe, text="Edit Custom Colors", command=lambda: open_custom_colors_window())
    ecustomcolorsbutton.grid(row=0, column=3, sticky="nsew")

    # Display all the toggles from the settings file
    togglesframe = ttk.LabelFrame(setup_tab, text="Toggles", padding="4")
    togglesframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    frames_padded.append(togglesframe)
    setuprow += 1
    populate_toggles(togglesframe)

    symbolsframe = ttk.LabelFrame(setup_tab, text="Symbols", padding="4")
    symbolsframe.grid(row=setuprow, column=0, sticky=tk.W+tk.E)
    frames_padded.append(symbolsframe)
    setuprow += 1

    symyeslabel = ttk.Label(symbolsframe, text="Yes:")
    symyeslabel.grid(row=0, column=0, sticky=tk.W)
    symyesentrystringvar = tk.StringVar(value=active_settings.get("symbols", {}).get("yes", "Y"))
    symyesentry = ttk.Entry(symbolsframe, textvariable=symyesentrystringvar)
    symyesentry.grid(row=0, column=1, sticky=tk.W+tk.E)

    symnolabel = ttk.Label(symbolsframe, text="No:")
    symnolabel.grid(row=0, column=2, sticky=tk.W)
    symnoentrystringvar = tk.StringVar(value=active_settings.get("symbols", {}).get("no", "N"))
    symnoentry = ttk.Entry(symbolsframe, textvariable=symnoentrystringvar)
    symnoentry.grid(row=0, column=3, sticky=tk.W+tk.E)

    def sym_paste(entry, var):
        text = pyperclip.paste()
        print(f"Debug paste: {repr(text)}")
        var.set(text.strip())
        return "break"
    
    def sym_save(name, var, event=None):
        if active_settings is None:
            print("Debug: Cannot save symbol, settings not loaded.")
            return
        if "symbols" not in active_settings:
            active_settings["symbols"] = {}
        active_settings.setdefault("symbols", {})[name] = var.get().strip()
        print(f"Debug: Set symbol {name}: {active_settings['symbols'][name]}")

    symyesentry.bind('<<Paste>>', lambda e: sym_paste(symyesentry, symyesentrystringvar))
    symnoentry.bind('<<Paste>>', lambda e: sym_paste(symnoentry, symnoentrystringvar))
    symyesentrystringvar.trace_add('write', lambda *a: sym_save("yes", symyesentrystringvar))
    symnoentrystringvar.trace_add('write',  lambda *a: sym_save("no",  symnoentrystringvar))

    # Collections Tab
    col_tab = ttk.Frame(main_notebook, padding="4")
    col_tab.columnconfigure(0, weight=1)

    col_loc_frame = ttk.LabelFrame(col_tab, padding="4", text="Collection Location")
    col_loc_frame.grid(row=0, column=0, sticky="ew")
    col_loc_frame.columnconfigure(1, weight=1)

    col_loc_label = ttk.Label(col_loc_frame, text="Location:")
    col_loc_label.grid(row=0, column=0, sticky="w")
    col_loc_entry_var = tk.StringVar(value=str(OUTPUT_DIR))
    col_loc_entry = ttk.Entry(col_loc_frame, textvariable=col_loc_entry_var)
    col_loc_entry.grid(row=0, column=1, sticky="ew", padx=4)

    col_loc_indicator = ttk.Label(col_loc_frame, text="")
    col_loc_indicator.grid(row=0, column=3, sticky="w", padx=4)

    def open_folder():
        folder_path = col_loc_entry_var.get().strip()
        subprocess.Popen(["xdg-open", str(folder_path)])

    col_loc_btn = ttk.Button(col_loc_frame, text="Open Folder", command=open_folder)
    col_loc_btn.grid(row=0, column=2, sticky="ew")
    col_loc_btn.configure(padding=0)

    # Export Frame
    col_exp_frame = ttk.LabelFrame(col_tab, padding="4", text="Export", relief="raised")
    col_exp_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
    col_exp_frame.columnconfigure(0, weight=1)
    col_exp_frame.columnconfigure(1, weight=1)
    col_exp_frame.columnconfigure(2, weight=1)
    col_exp_frame.columnconfigure(3, weight=1)
    col_exp_frame.columnconfigure(4, weight=1)

    def save_export_sort():
        if active_settings:
            active_settings.setdefault("export_sort", {}).update({"column": sort_column_var.get(), "order": sort_order_var.get(),})
        settings_save()

    sort_frame = ttk.Frame(col_exp_frame)
    sort_frame.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 4))
    sort_column_var = tk.StringVar(value=active_settings.setdefault("export_sort", {}).get("column", "Title"))
    sort_order_var = tk.StringVar(value=active_settings.setdefault("export_sort", {}).get("order", "ascending"))

    ttk.Label(sort_frame, text="Sort by:").grid(row=0, column=0, sticky="e", padx=(4, 2), pady=4)
    sort_column_menu = ttk.Combobox(sort_frame, textvariable=sort_column_var, values=list(active_settings.get("column_export", {}).keys()), state="readonly", height=20)
    sort_column_menu.grid(row=0, column=1, sticky="ew", padx=2, pady=4)

    ttk.Label(sort_frame, text="Order:").grid(row=0, column=2, sticky="e", padx=(4, 2), pady=4)
    sort_order_menu = ttk.OptionMenu(sort_frame, sort_order_var, sort_order_var.get(), "ascending", "descending")
    sort_order_menu.grid(row=0, column=3, sticky="ew", padx=2, pady=4)
    sort_order_menu.configure(padding=0)

    sort_column_menu.bind("<<ComboboxSelected>>", lambda e: save_export_sort())
    sort_order_menu.bind("<<ComboboxSelected>>", lambda e: save_export_sort())

    # Select Columns Button
    col_exp_col_select_btn = ttk.Button(col_exp_frame, text="Select Columns", command=lambda: open_column_export_window(), style="SelectColumns.TButton")
    col_exp_col_select_btn.grid(row=1, column=0, sticky="ew")

    # Export Buttons
    populate_export_buttons(col_exp_frame, row=1)

    # Collection Stats Frame
    col_exp_stats = ttk.LabelFrame(col_tab, padding="4", text="Collection Stats", relief="raised")
    col_exp_stats.grid(row=3, column=0, columnspan=5, sticky="ew", pady=2)
    col_exp_stats.columnconfigure(0, weight=1)

    collection_stats_labels.clear()

    stats_definitions = (
        ("titles", "Titles: 0"),
        ("platforms", "Platforms: 0"),
        ("payed", "Total Payed: 0.00"),
        ("value", "Total Value: 0.00"),
    )
    col_stats_column = 0
    for column, (stat_name, initial_text) in enumerate(stats_definitions):
        stat_label = ttk.Label(col_exp_stats, text=initial_text, anchor="center")
        stat_label.grid(row=0, column=column, sticky="ew", padx=8, pady=4)
        col_exp_stats.columnconfigure(column, weight=1)
        collection_stats_labels[stat_name] = stat_label
        col_stats_column += 1

    # Entry for conversion factor
    col_conversion_factor_frame = ttk.Frame(col_exp_stats)
    col_conversion_factor_frame.grid(row=0, column=col_stats_column, sticky="ew", padx=8, pady=4) 
    col_conversion_factor_label = ttk.Label(col_conversion_factor_frame, text="Conversion Factor:", anchor="center")
    col_conversion_factor_label.grid(row=0, column=0, sticky="ew")
    col_conversion_factor_var = tk.StringVar(value=str(active_settings.get("currency_conversion", {}).get("conversion_factor", "")))
    col_conversion_factor_entry = ttk.Entry(col_conversion_factor_frame, textvariable=col_conversion_factor_var)
    col_conversion_factor_entry.grid(row=0, column=1, sticky="ew")
    def conversion_factor_changed():
        if active_settings is None:
            return

        text = col_conversion_factor_var.get().strip()
        try:
            conversion_factor = float(text)
        except ValueError:
            return

        active_settings.setdefault("currency_conversion", {})["conversion_factor"] = conversion_factor

        settings_save()
        update_collection_stats()

    col_conversion_factor_btn = ttk.Button(col_conversion_factor_frame, text="Apply", command=conversion_factor_changed)
    col_conversion_factor_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))
    col_conversion_factor_btn.configure(padding=0)
    col_conversion_factor_frame.columnconfigure(1, weight=1)

    col_stats_graph_frame = ttk.Frame(col_exp_stats, relief="sunken")
    col_stats_graph_frame.grid(row=1, column=0, columnspan=len(stats_definitions)+2, sticky="ew", padx=2, pady=2)
    col_stats_graph_frame.columnconfigure(0, weight=1)

    for column in range(CHARTS_PER_ROW):
        col_stats_graph_frame.columnconfigure(column, weight=1)

    def handle_tab_changed(event):
        update_choices(contextentries, taxonomyentries)
        if event.widget.select() == str(col_tab):
            update_collection_stats()

    main_notebook.add(mainframe, text="Main")
    main_notebook.add(setup_tab, text="Setup")
    main_notebook.add(col_tab, text="Collection")

    # Invoke the Search button when Enter is pressed inside the entry
    searchentry.bind('<Return>', lambda event: searchbutton.invoke())
    # Make the search entry focused when the application starts
    searchentry.focus()

    logtree.bind("<Double-1>", recall_log_item)
    root.bind_all("<KP_Enter>", handle_keypad_enter)
    root.bind_all('<y>', lambda event: handle_accept_key(root, event))
    root.bind_all('<Y>', lambda event: handle_accept_key(root, event))
    root.bind_all('<n>', lambda event: handle_decline_key(root, event))
    root.bind_all('<N>', lambda event: handle_decline_key(root, event))
    root.bind_all('<Delete>', lambda event: handle_decline_key(root, event))
    root.bind_all('<Control-q>', lambda event: root.quit())
    root.bind_all('<Insert>', handle_missing_upc_shortcut)
    root.bind_all('<Page_Up>', handle_missing_id_shortcut)
    root.bind_all('<Page_Down>', handle_missing_price_url_shortcut)
    root.bind('<Tab>', lambda event: handle_tab_key(root, event, 1))
    root.bind('<Shift-Tab>', lambda event: handle_tab_key(root, event, -1))
    root.bind('<ISO_Left_Tab>', lambda event: handle_tab_key(root, event, -1))
    if searchentry is not None:
        root.bind_all('<Control-a>', button_select_all)

    main_notebook.bind("<<NotebookTabChanged>>", handle_tab_changed)

    # Get the shortcuts and bind them, with and without shift if applicable
    shortcuts = active_settings.get("shortcuts", {}) if active_settings else {}
    for name, key in shortcuts.items():
        root.bind_all(f"<{key}>", cycle_setup(name, 1), add="+")
        if not key.startswith("shift-"):
            root.bind_all(f"<Shift-{key}>", cycle_setup(name, -1), add="+")

    for frame in frames_padded:
        for child in frame.winfo_children():
            child.grid_configure(padx=2, pady=2)

    root.after(0, settings_set_defaults)
    root.mainloop()

if __name__ == "__main__":
    settings_load()
    main()