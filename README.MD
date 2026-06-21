# Game Barcode Scanner

A simple TKinter python program made to save time by scraping information about a title and creating a CSV or XLS file with the information, or to output to the clipboard, where the order and content is customizable.

Was mainly meant to work with a barcode scanner, but text search is also possible.

# Requirements

- Pandas
- Beautiful Soup
- Requests
- Openpyxl
- Pyperclip

## Runtime Requirements

- xclip, xdotool, wl-clipboard or similar

# How to run

Run the following command in your terminal:

``` python GBScan.py ```

# TODO

- [ ] Make it less janky
- [x] Add setting for which Y/N symbol to use
- [x] Add ability to re-order the column order from the setup tab
- [x] Add ability to exclude columns per platform on setup tab
- [x] Add a setup tab to tweak settings file
- [x] Add ability to set defaults per platform
- [ ] Add ability to set rules per context
- [x] Add all context to listview
- [ ] Make recall respect current columns
- [ ] Add payed context
- [ ] Add ability to define custom contexts
- [ ] Add ability to add unknown game
- [x] Add ability to quickly add missing fields
