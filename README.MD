# Game Barcode Scanner

A simple python script made to save time by scraping information about a title and creating a CSV or XLS file with the information, or to output to the clipboard.

Was mainly meant to work with a barcode scanner, but in case nothing is found, a text search is also possible.

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
- [ ] Add setting for which Y/N symbol to use
- [ ] Add ability to re-order the column order from the setup tab
- [ ] Add ability to exclude columns per platform on setup tab
- [x] Add a setup tab to tweak settings file
