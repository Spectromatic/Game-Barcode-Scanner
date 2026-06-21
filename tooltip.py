import tkinter as tk

class Tooltip:
    """Tooltip that shows some text on a widget"""
    def __init__(self, widget, text, delay=500, wraplength=400):
        self.widget = widget
        self.text = str(text)
        self.delay = int(delay)
        self.wraplength = wraplength
        self._widgettooltip = None
        self._tooltipwindow = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        self._widgettooltip = self.widget.after(self.delay, self._show)

    def _show(self):
        if self._tooltipwindow:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 1
        self._tooltipwindow = tk.Toplevel(self.widget)
        self._tooltipwindow.wm_overrideredirect(True)
        self._tooltipwindow.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self._tooltipwindow, text=self.text, justify="left", background="#ffffe0", relief="solid", borderwidth=1, wraplength=self.wraplength)
        lbl.pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        if self._widgettooltip:
            self.widget.after_cancel(self._widgettooltip)
            self._widgettooltip = None
        if self._tooltipwindow:
            self._tooltipwindow.destroy()
            self._tooltipwindow = None