# Game Barcode Scanner

A TKinter python program made to save time by scraping information about a title and creating a CSV or XLS file with the information, or to output to the clipboard, where the order and content is customizable.

Was mainly meant to work with a barcode scanner, but text search is more useful at the moment.

Since mobygames disallowed scraping, it now uses its own internal databases to fill in information (private until I've had a chance to fix the most glaring issues in them) instead of scraping it, but still scrapes prices and cover images from pricecharting. Uses its own taxonomy system, which is customizable.

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
- [ ] Add button to update scanned collection to an updated DB
- [X] Add button to export selected columns to a searchable PDF
- [ ] Add color / gradients to contexts
