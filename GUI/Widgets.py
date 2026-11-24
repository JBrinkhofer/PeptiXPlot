import tkinter as tk
import ttkbootstrap as ttk


class CollapsibleFrame(ttk.Frame):

    def __init__(self, master, text, **kwargs):
        super().__init__(master=master, **kwargs)
        
        self.master = master
        self._dummy_update_id = None
        self._scroll_refresh_id = None
        self.columnconfigure(1, weight=1)

        # This is the easiest way to ensure proper resizing of the labelframe when collapsing
        self.dummy_labelframe = ttk.LabelFrame(self)
        self.dummy_labelframe.grid(row=0, column=0, rowspan=2, columnspan=2, sticky=tk.NSEW, pady=4, ipady=12)
        self.dummy_labelframe.bind("<Button-1>", self.toggle)

        # The actual labelframe that keeps the data
        self.labelframe = ttk.LabelFrame(self)
        self.labelframe.grid(row=0, column=0, rowspan=2, columnspan=2, sticky=tk.NSEW, pady=4)
        self.labelframe.grid_remove()

        self.labelframe.rowconfigure(0, weight=1)
        self.labelframe.columnconfigure(0, weight=1)

        # The content frame inside of the labelframe
        self.content = ttk.Frame(self.labelframe)
        self.content.grid(row=0, column=0, sticky=tk.NSEW, pady=(8,4), padx=4)
        self.content.columnconfigure(0, weight=1)

        # Ensure geometry propagation so requested sizes are respected
        try:
            self.labelframe.grid_propagate(True)
            self.content.grid_propagate(True)
        except Exception:
            pass

        # Bind configure on content and labelframe so changes propagate
        self.content.bind("<Configure>", self._update_dummy)
        self.labelframe.bind("<Configure>", self._update_dummy)

        # The label of the collapsible frame
        self.header_label = ttk.Label(self, text=text, padding=0)
        self.header_label.bind("<Button-1>", self.toggle)
        # Button for expansion and closing
        self.header_button = ttk.Button(self, text="Expand", command=self.toggle, bootstyle="secondary")
        self.header_button.configure(padding=(0,0))

        self.header_label.grid(row=0, column=0, sticky=tk.NW, padx=5, pady=(0, 4))
        self.header_button.grid(row=0, column=1, sticky=tk.NE, padx=(0,10), pady=(0, 6))

    def toggle(self, *args):
        if self.labelframe.winfo_ismapped():
            self.collapse()

        else:
            self.expand()

    def collapse(self, *args):

        self.header_button.configure(text="Expand")
        self.labelframe.grid_remove()
        self._refresh_scroll_parent(reset_view=True)

        # When collapsed, ensure the dummy placeholder represents the
        # (now-hidden) labelframe requested size so the outer layout
        # reserves appropriate space.

    def expand(self, *args):
        self.header_button.configure(text="Collapse")
        self.labelframe.grid()
        self._refresh_scroll_parent()

    def _refresh_scroll_parent(self, reset_view=False):
        if not self.winfo_ismapped():
            return

        if self._scroll_refresh_id is not None:
            return

        parent = self.master
        while parent is not None:
            refresh = getattr(parent, "_on_content_configure", None)
            if refresh is not None:
                def apply_refresh():
                    self._scroll_refresh_id = None
                    try:
                        parent.update_idletasks()
                        refresh(None)
                        if reset_view:
                            parent.yview_moveto(0)
                    except tk.TclError:
                        pass

                self._scroll_refresh_id = self.after_idle(apply_refresh)
                return
            parent = getattr(parent, "master", None)

    # Keep the dummy labelframe size in sync with the actual content so
    # surrounding scrolled containers allocate the correct space.
    def _update_dummy(self, event=None):
        if not self.winfo_ismapped():
            return

        if self._dummy_update_id is not None:
            return

        def _apply():
            self._dummy_update_id = None
            try:
                req_w = self.labelframe.winfo_reqwidth()
                current_w = int(self.dummy_labelframe.cget("width"))
                if req_w > 1 and req_w != current_w:
                    self.dummy_labelframe.configure(width=req_w)
            except (tk.TclError, ValueError):
                pass

        self._dummy_update_id = self.after_idle(_apply)
