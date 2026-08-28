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

class CanvasTooltip:
    """Tooltip that shows some text on a canvas item"""
    def __init__(self, canvas, item_id, text, delay=500, wraplength=400):
        self.canvas = canvas
        self.item_id = item_id
        self.text = str(text)
        self.delay = delay
        self.wraplength = wraplength
        self.after_id = None
        self.window = None

        canvas.tag_bind(item_id, "<Enter>", self._schedule)
        canvas.tag_bind(item_id, "<Leave>", self._hide)
        canvas.tag_bind(item_id, "<ButtonPress>", self._hide)

    def _schedule(self, event):
        self.after_id = self.canvas.after(self.delay, lambda: self._show(event))

    def _show(self, event):
        if self.window is not None:
            return

        x = event.x_root + 12
        y = event.y_root + 12

        self.window = tk.Toplevel(self.canvas)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.window, text=self.text, background="#ffffe0", relief="solid", borderwidth=1, justify="left", wraplength=self.wraplength)
        label.pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        if self.after_id is not None:
            self.canvas.after_cancel(self.after_id)
            self.after_id = None

        if self.window is not None:
            self.window.destroy()
            self.window = None