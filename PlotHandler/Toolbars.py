import tkinter as tk
import ttkbootstrap as tb
from matplotlib import cbook
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
from matplotlib.backends._backend_tk import add_tooltip
from matplotlib.backend_bases import _Mode
from matplotlib.backend_tools import Cursors
import numpy as np

# Derived from matplotlib.backends._backend_tk.py (Matplotlib 3.11.1).
# Copyright (c) 2012- Matplotlib Development Team; All Rights Reserved
# Changes: replaced Matplotlib's resource lookup with PeptiXPlot icons,
# added PeptiXPlot theme handling for toolbar button images and added
# custom button behavior.
# License: LICENSES/MATPLOTLIB_LICENSE.txt

# Necessary for custom images in toolbar
from pathlib import Path
from PIL import Image, ImageTk


# Add new Modes to the _Mode class in mpl
_Mode.PEAKS = "pick peaks"
_Mode.INT = "integrate"
_Mode.TXT = "place text"


# Modified Toolbar
class Toolbar(NavigationToolbar2Tk):
    
    def __init__(self, canvas, parent, plotclass):

        # Since the toolbar is packed on another frame and it needs to access the methods of the root window, set rootwindow to parent.master, plotclass is the class it is initiated in
        self.parent = plotclass
        self.rootwindow = parent.master
        self.toolitems = (
            #(Name,Description,Image,Function)
            ("Home", "Reset original view", "home", "home"),
            ("Back", "Back to previous view", "back", "back"),
            ("Forward", "Forward to next view", "forward", "forward"),
            (None, None, None, None),
            ("Pan", "Left button pans, Right button zooms\n""x/y fixes axis, CTRL fixes aspect", "move", "pan"),
            ("Zoom", "Zoom\n""x/y fixes axis", "zoom_to_rect", "zoom"),  
        )

        self.new_toolitems = (
            # New own Buttons
            (None, None, None, None),
            ("PeakPicker", "Pick peaks", "peak", "pickpeaks"),
            ("Integrator", "Integrate", "integral", "integrate"),
            ("FreeText", "Place free text", "text", "place_text")
        )

        # Whether the window is in dark_mode or not
        self._dark = self.rootwindow._dark
        
        super().__init__(canvas, parent, pack_toolbar=False)
        
        self.mode = _Mode.NONE # Initialize the mode to NONE
        
        # Add new items
        for text, tooltip_text, image_file, callback in self.new_toolitems:
            if text is None:
                # Add a spacer; return value is unused.
                self._Spacer()
            else:
                self._buttons[text] = button = self._custom_Button(
                    text,
                    str(f"{image_file}.png"),
                    toggle=callback in ["pickpeaks", "integrate", "place_text"],
                    command=getattr(self, callback),
                )
                if tooltip_text is not None:
                    add_tooltip(button, tooltip_text)

        self.is_home = True

        self.update_theme()

    def _Button(self, text, image_file, toggle, command):
        if not toggle:
            b = tk.Button(
                master=self, text=text, command=command,
                relief="flat", overrelief="groove", borderwidth=1,
            )
        else:
            # There is a bug in tkinter included in some python 3.6 versions
            # that without this variable, produces a "visual" toggling of
            # other near checkbuttons
            # https://bugs.python.org/issue29402
            # https://bugs.python.org/issue25684
            var = tk.IntVar(master=self)
            b = tk.Checkbutton(
                master=self, text=text, command=command, indicatoron=False,
                variable=var, offrelief="flat", overrelief="groove",
                borderwidth=1
            )
            b.var = var
        b._image_file = image_file
        if image_file is not None:
            # Explicit class because ToolbarTk calls _Button.
            Toolbar._set_image_for_button(self, b)
        else:
            b.configure(font=self._label_font)
        b.pack(side=tk.LEFT)
        return b


    def _set_image_for_button(self, button):

        # Derived from matplotlib.backends._backend_tk.py:
        # _set_image_for_button, modified for PeptiXPlot.
        
        """
        Set the image for a button based on its pixel size.

        The pixel size is determined by the DPI scaling of the window.
        """
        if button._image_file is None:
            return

        # Allow _image_file to be relative to Matplotlib's "images" data
        # directory.
        path_regular = cbook._get_data_path('images', button._image_file)
        path_large = path_regular.with_name(
            path_regular.name.replace('.png', '_large.png'))
        size = button.winfo_pixels('18p')

        # Nested functions because ToolbarTk calls  _Button.
        def _get_color(color_name):
            # `winfo_rgb` returns an (r, g, b) tuple in the range 0-65535
            return button.winfo_rgb(button.cget(color_name))

        def _is_dark(color):
            if isinstance(color, str):
                color = _get_color(color)
            return max(color) < 65535 / 2

        def _recolor_icon(image, color):
            image_data = np.asarray(image).copy()
            black_mask = (image_data[..., :3] == 0).all(axis=-1)
            image_data[black_mask, :3] = color
            return Image.fromarray(image_data, mode="RGBA")

        # Use the high-resolution (48x48 px) icon if it exists and is needed
        with Image.open(path_large if (size > 24 and path_large.exists())
                        else path_regular) as im:
            # assure a RGBA image as foreground color is RGB
            im = im.convert("RGBA")
            image = ImageTk.PhotoImage(im.resize((size, size)), master=self)
            button._ntimage = image

            # create a version of the icon with the button's text color
            foreground = (255 / 65535) * np.array(
                button.winfo_rgb(button.cget("foreground")))
            im_alt = _recolor_icon(im, foreground)
            image_alt = ImageTk.PhotoImage(
                im_alt.resize((size, size)), master=self)
            button._ntimage_alt = image_alt

        if self._dark:
            # For Checkbuttons, we need to set `image` and `selectimage` at
            # the same time. Otherwise, when updating the `image` option
            # (such as when changing DPI), if the old `selectimage` has
            # just been overwritten, Tk will throw an error.
            image_kwargs = {"image": image_alt}
        else:
            image_kwargs = {"image": image}
        # Checkbuttons may switch the background to `selectcolor` in the
        # checked state, so check separately which image it needs to use in
        # that state to still ensure enough contrast with the background.
        if (
            isinstance(button, tk.Checkbutton)
            and button.cget("selectcolor") != ""
        ):
            if self._windowingsystem != "x11":
                selectcolor = "selectcolor"
            else:
                # On X11, selectcolor isn't used directly for indicator-less
                # buttons. See `::tk::CheckEnter` in the Tk button.tcl source
                # code for details.
                r1, g1, b1 = _get_color("selectcolor")
                r2, g2, b2 = _get_color("activebackground")
                selectcolor = ((r1+r2)/2, (g1+g2)/2, (b1+b2)/2)
            if _is_dark(selectcolor):
                image_kwargs["selectimage"] = image_alt
            else:
                image_kwargs["selectimage"] = image

        button.configure(**image_kwargs, height='18p', width='18p')


    def _custom_Button(self, text, image_file, toggle, command):
        
        # Derived from matplotlib.backends._backend_tk.py:
        # _Button, modified for PeptiXPlot.

        if not toggle:
            b = tk.Button(
                master=self, text=text, command=command,
                relief="flat", overrelief="groove", borderwidth=1,
            )
        else:
            # There is a bug in tkinter included in some python 3.6 versions
            # that without this variable, produces a "visual" toggling of
            # other near checkbuttons
            # https://bugs.python.org/issue29402
            # https://bugs.python.org/issue25684
            var = tk.IntVar(master=self)
            b = tk.Checkbutton(
                master=self, text=text, command=command, indicatoron=False,
                variable=var, offrelief="flat", overrelief="groove",
                borderwidth=1
            )
            b.var = var
        b._image_file = image_file
        if image_file is not None:
            # Explicit class because ToolbarTk calls _Button.
            Toolbar._set_image_for_custom_button(self, b)
        else:
            b.configure(font=self._label_font)
        b.pack(side=tk.LEFT)
        return b


    def _set_image_for_custom_button(self, button):

        # Derived from matplotlib.backends._backend_tk.py:
        # _set_image_for_button, modified for PeptiXPlot's local icons.


        """
        Set the image for a button based on its pixel size.

        The pixel size is determined by the DPI scaling of the window.
        """
        if button._image_file is None:
            return

        # Allow _image_file to be relative to the repository
        path_regular = self._get_data_path('icons', button._image_file)
        path_large = path_regular.with_name(
            path_regular.name.replace('.png', '_large.png'))
        size = button.winfo_pixels('18p')

        # Nested functions because ToolbarTk calls  _Button.
        def _get_color(color_name):
            # `winfo_rgb` returns an (r, g, b) tuple in the range 0-65535
            return button.winfo_rgb(button.cget(color_name))

        def _is_dark(color):
            if isinstance(color, str):
                color = _get_color(color)
            return max(color) < 65535 / 2

        def _recolor_icon(image, color):
            image_data = np.asarray(image).copy()
            black_mask = (image_data[..., :3] == 0).all(axis=-1)
            image_data[black_mask, :3] = color
            return Image.fromarray(image_data, mode="RGBA")

        # Use the high-resolution (48x48 px) icon if it exists and is needed
        with Image.open(path_large if (size > 24 and path_large.exists())
                        else path_regular) as im:
            # assure a RGBA image as foreground color is RGB
            im = im.convert("RGBA")
            image = ImageTk.PhotoImage(im.resize((size, size)), master=self)
            button._ntimage = image

            # create a version of the icon with the button's text color
            foreground = (255 / 65535) * np.array(
                button.winfo_rgb(button.cget("foreground")))
            im_alt = _recolor_icon(im, foreground)
            image_alt = ImageTk.PhotoImage(
                im_alt.resize((size, size)), master=self)
            button._ntimage_alt = image_alt

        if self._dark:
            # For Checkbuttons, we need to set `image` and `selectimage` at
            # the same time. Otherwise, when updating the `image` option
            # (such as when changing DPI), if the old `selectimage` has
            # just been overwritten, Tk will throw an error.
            image_kwargs = {"image": image_alt}
        else:
            image_kwargs = {"image": image}
        # Checkbuttons may switch the background to `selectcolor` in the
        # checked state, so check separately which image it needs to use in
        # that state to still ensure enough contrast with the background.
        if (
            isinstance(button, tk.Checkbutton)
            and button.cget("selectcolor") != ""
        ):
            if self._windowingsystem != "x11":
                selectcolor = "selectcolor"
            else:
                # On X11, selectcolor isn't used directly for indicator-less
                # buttons. See `::tk::CheckEnter` in the Tk button.tcl source
                # code for details.
                r1, g1, b1 = _get_color("selectcolor")
                r2, g2, b2 = _get_color("activebackground")
                selectcolor = ((r1+r2)/2, (g1+g2)/2, (b1+b2)/2)
            if _is_dark(selectcolor):
                image_kwargs["selectimage"] = image_alt
            else:
                image_kwargs["selectimage"] = image

        button.configure(**image_kwargs, height='18p', width='18p')

        
    def _get_data_path(self, folder, image):
        # Return the absolute path to the ./icons folder
        return Path(__file__).resolve().parent.parent / folder / image
        
    def save_figure(self, *args, **kwargs):
        # Override save function
        pass

    def home(self, *args):
        super().home(*args)
        # This needs to be checked so that in case of multiplots, initialization does not fail
        # Only do this if autoadjust_y is True, otherwise it will make the ylim values behave weirdly
        if self.rootwindow.plottype not in ["MultiPlot", "Assay"]:
            self.parent.ax.set_ylim(top=self.parent.plot_data["y_axis_max"],
                                    bottom=self.parent.plot_data["y_axis_min"])
            self.parent.ax.set_xlim(right=self.parent.plot_data["x_axis_max"],
                                    left=self.parent.plot_data["x_axis_min"])
            if self.parent.insetplotted:
                self.parent.ax.inset.set_ylim(top = self.parent.plot_data["inset_y_axis_max_percent"]/100*self.parent.max_y_val)
                self.parent.ax.inset.set_xlim(right=self.parent.plot_data["inset_x_axis_max"],
                                              left=self.parent.plot_data["inset_x_axis_min"])

        elif self.rootwindow.plottype == "Assay":
            self.parent.ax.set_ylim(top=self.parent.multiplot_data["PlotOptions"]["y_axis_max"],
                                    bottom=self.parent.multiplot_data["PlotOptions"]["y_axis_min"])
            self.parent.ax.set_xlim(right=self.parent.multiplot_data["PlotOptions"]["x_axis_max"],
                                    left=self.parent.multiplot_data["PlotOptions"]["x_axis_min"])

        self.is_home = True

    def _update_view(self):
        super()._update_view()
        self.parent.refresh_for_blitting(self.parent.ax)

    def release_zoom(self, event):
        super().release_zoom(event)
        self.parent.refresh_for_blitting(self.parent.ax)
        self.is_home = False

    def release_pan(self, event):
        super().release_pan(event)
        self.parent.refresh_for_blitting(self.parent.ax)
        self.is_home = False

    def zoom(self):
        super().zoom(self)
        self._update_buttons_checked()

    def pan(self):
        super().pan(self)
        self._update_buttons_checked()

    def pickpeaks(self, *args):

        if self.mode != _Mode.PEAKS:
            self.mode = _Mode.PEAKS
            self.canvas.widgetlock.release(self)
        else:
            self.mode = _Mode.NONE
            self.canvas.widgetlock.release(self)
            
        self._update_buttons_checked()

    def hover_pickpeaks(self, event):
        self.canvas.set_cursor(Cursors.SELECT_REGION if event.inaxes else Cursors.POINTER)
        
    def integrate(self, *args):
        if self.mode != _Mode.INT:
            self.mode = _Mode.INT
            self.canvas.widgetlock.release(self)
        else:
            self.mode = _Mode.NONE
            self.canvas.widgetlock.release(self)

        self._update_buttons_checked()

    def hover_integrate(self, event):
        self.canvas.set_cursor(Cursors.RESIZE_HORIZONTAL if event.inaxes else Cursors.POINTER)

    def place_text(self, *args):
        if self.mode != _Mode.TXT:
            self.mode = _Mode.TXT
            self.canvas.widgetlock.release(self)
        else:
            self.mode = _Mode.NONE
            self.canvas.widgetlock.release(self)

        self._update_buttons_checked()

    def hover_place_text(self, event):
        self.canvas.set_cursor(Cursors.SELECT_REGION if event.inaxes else Cursors.POINTER)

    def _update_buttons_checked(self):
        # sync button checkstates to match active mode
        for text, mode in [('Zoom', _Mode.ZOOM), 
                           ('Pan', _Mode.PAN), 
                           ("PeakPicker", _Mode.PEAKS), 
                           ("Integrator", _Mode.INT),
                           ("FreeText", _Mode.TXT)]:
            if text in self._buttons:
                if self.mode == mode:
                    self._buttons[text].select()  # NOT .invoke()
                else:
                    self._buttons[text].deselect()

        if self.mode == _Mode.PEAKS:
            for ann in self.parent.annotations + self.parent.iannotations:
                ann.draggable(False)
            for axle in self.parent.manual_HPLC_baseline_axles:
                axle.draggable(False)
            self.parent.PeakSelector.set_active(True)
            if self.parent.insetplotted:
                self.parent.InsetPeakSelector.set_active(True)
            self.parent.IntegrateSelector.set_active(False)
            try:
                self.canvas.mpl_disconnect(self.hover_cursor)
            except:
                pass
            self.hover_cursor = self.canvas.mpl_connect("motion_notify_event", self.hover_pickpeaks)
        elif self.mode == _Mode.INT:
            for ann in self.parent.annotations + self.parent.iannotations:
                ann.draggable(False)
            for axle in self.parent.manual_HPLC_baseline_axles:
                axle.draggable(False)
            self.parent.IntegrateSelector.set_active(True)
            self.parent.PeakSelector.set_active(False)
            if self.parent.insetplotted:
                self.parent.InsetPeakSelector.set_active(False)
            try:
                self.canvas.mpl_disconnect(self.hover_cursor)
            except:
                pass
            self.hover_cursor = self.canvas.mpl_connect("motion_notify_event", self.hover_integrate)
        elif self.mode == _Mode.TXT:
            for ann in self.parent.annotations + self.parent.iannotations:
                ann.draggable(False)
            for axle in self.parent.manual_HPLC_baseline_axles:
                axle.draggable(False)
            self.parent.IntegrateSelector.set_active(False)
            self.parent.PeakSelector.set_active(False)
            if self.parent.insetplotted:
                self.parent.InsetPeakSelector.set_active(False)
            try:
                self.canvas.mpl_disconnect(self.hover_cursor)
            except:
                pass
            self.hover_cursor = self.canvas.mpl_connect("motion_notify_event", self.hover_place_text)
        else:
            for ann in self.parent.annotations + self.parent.iannotations:
                ann.draggable(True, use_blit=True)
            for axle in self.parent.manual_HPLC_baseline_axles:
                axle.draggable(True, use_blit=True)
            self.parent.PeakSelector.set_active(False)
            self.parent.IntegrateSelector.set_active(False)
            if self.parent.insetplotted:
                self.parent.InsetPeakSelector.set_active(False)
            try:
                self.canvas.mpl_disconnect(self.hover_cursor)
            except:
                pass
            self.canvas.set_cursor(Cursors.POINTER)

    def set_history_buttons(self):
        super().set_history_buttons()
        if self._nav_stack._pos == 0:
            self.is_home = True

    # Check whether a button is supposed to be active or disabled
    def check_whether_active(self):
        
        # Deactive buttons that should not be selected in another mode
        if self.rootwindow.plottype == "HPLC":
            self._buttons["Integrator"].configure(state = "active")
        else:
            self._buttons["Integrator"].configure(state = "disabled")

        # Deactive buttons that should not be selected in another mode
        if self.rootwindow.plottype in ["Fluorescence", "HPLC", "MALDI", "UV/vis"]:
            self._buttons["PeakPicker"].configure(state = "active")
        else:
            self._buttons["PeakPicker"].configure(state = "disabled")

    def update_theme(self):
        style = tb.Style()
        
        background = style.lookup("secondary.TButton", "background")
        foreground = style.lookup("secondary.TButton", "foreground")
        activebackground = style.lookup("secondary.TButton", "background", state=["active"])
        activeforeground = style.lookup("secondary.TButton", "foreground", state=["active"])
        
        for btn in self.winfo_children():
            if isinstance(btn, tk.Button) or isinstance(btn, tk.Checkbutton):
                btn.config(bg=background, fg=foreground, activebackground=activebackground, activeforeground=activeforeground)

