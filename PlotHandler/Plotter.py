import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
import ttkbootstrap as ttk
from types import MethodType
mpl.use("TkAgg")
mpl.rcParams["mathtext.default"]="rm"
from matplotlib.widgets import RectangleSelector, SpanSelector
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.backend_bases import _Mode
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, AnchoredSizeLocator
from mpl_toolkits.axes_grid1 import Divider, Size
from mpl_toolkits.mplot3d import Axes3D
from scipy.integrate import trapezoid
from molmass import Formula
from math import ceil, floor
from bisect import bisect_right, bisect_left
import ast
import copy
import uuid

# Part of this application
from PlotHandler.Toolbars import Toolbar
from HelperScripts.formats import autoscripts, autoscripts_reverse
from HelperScripts.math import normalize, get_maximum, get_minimum, lorentzian, find_indexes, sigmoidal_constant_baseline, sigmoidal_linear_baseline, sigmoidal_quadratic_baseline, michaelis_menten, vant_hoff, gaussian
# modified annotate method to give custom Annotations which work better with the implemented blitting logic
from PlotHandler.CustomArtists import annotate, custom_Dot, custom_DraggableLegend, custom_DraggableText

# Suppress warnings from matplotlib about mathtext parsing 
import logging

logging.getLogger("matplotlib.mathtext").setLevel(logging.ERROR)

# This module handles the Plot itself and interactions with the plot
DEBUG = False

class Editor_Menu(tk.Toplevel):
    """Floating editor menu that stays above the active text editor."""

    def __init__(self, master=None, editor=None, text_data=None, artist=None, **kwargs):
        if DEBUG: print("Initiating editor menu")
        self.root = master.winfo_toplevel() if master is not None and hasattr(master, "winfo_toplevel") else master
        super().__init__(self.root, **kwargs)
        self.withdraw()
        self.attributes("-topmost", True)

        try:
            self.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        
        self.overrideredirect(True)
        self.artist = artist
        self.text_data = text_data

        if self.artist is not None:
            self.fig = self.artist.get_figure()

        self.fontsize = tk.DoubleVar(value=float(text_data["fontsize"]))
        self.color = mpl.colors.to_hex(text_data["color"])
        self.font = tk.StringVar(value=str(text_data["font"]))
        self.border = tk.BooleanVar(value=bool(text_data["border"]))
        self.border_alpha = tk.DoubleVar(value=float(text_data["border_alpha"]))
        self.alignment = tk.StringVar(value=str(text_data["alignment"]))

        self.scaling = float(self.tk.call("tk","scaling"))

        self.color_image = None

        self.editor = editor
        self.center_id = None
        self.pick_id = None

        self._configure_bind_id = None
        if self.editor is not None and self.root is not None:
            self._configure_bind_id = self.root.bind("<Configure>", self._on_configure, add="+")

        self.__create_widgets()

    def destroy(self):
        if DEBUG: print("Destroying editor menu")

        if getattr(self, "editor", None) is not None and self.root is not None:
            if DEBUG: print("Unbinding modifying event")
            try:
                self.editor.unbind("<<Modified>>")
            except tk.TclError:
                pass

        if getattr(self, "_configure_bind_id", None) and self.root is not None:
            if DEBUG: print("Unbinding configure event")
            try:
                self.root.unbind("<Configure>", self._configure_bind_id)
            except tk.TclError:
                pass

        if getattr(self, "center_id", None) is not None:
            self.after_cancel(self.center_id)
            
        if getattr(self, "pick_id", None) is not None:
            self.after_cancel(self.pick_id)
        
        super().destroy()

    def _on_configure(self, event=None):
        if not self.winfo_exists():
            return  
        if self.editor is not None and self.winfo_ismapped():
            if self.center_id is None:
                self.center_id = self.after_idle(self.center_on_artist)

    def __create_widgets(self):

        self.font_combobox = ttk.Combobox(self,
                                          values=sorted(mpl.font_manager.get_font_names()),
                                          state="readonly",
                                          textvariable=self.font
                                        )

        self.font_combobox.pack(side=tk.LEFT, pady=5, padx=(5, 1), ipady=0, ipadx=0)

        self.font_combobox.bind("<<ComboboxSelected>>", self.update_font)
        self.font_combobox.bind("<Return>",  self.update_font)
        self.font_combobox.bind("<FocusOut>",  self.update_font)

        self.fontsize_spinbox = ttk.Spinbox(self,
                                            from_=1, 
                                            to=np.inf, 
                                            increment=1, 
                                            textvariable=self.fontsize, 
                                            width=2,
                                            command=self.update_font)

        self.fontsize_spinbox.bind("<Return>", self.update_font)
        self.fontsize_spinbox.bind("<FocusOut>", self.update_font)
        
        self.fontsize_spinbox.pack(side=tk.LEFT, pady=5, padx=1, ipady=0, ipadx=0)

        if self.color_image is None:
            self.create_color_image()

        self.color_btn = tk.Label(self,
                                  image=self.color_image,
                                  bd=0,
                                  highlightthickness=0,
                                  cursor="hand2",
                                )
        self.color_btn.pack(side=tk.LEFT, padx=1)
        self.color_btn.bind("<Button-1>", self.choose_color)


        self.alignment_combobox = ttk.Combobox(self, 
                                               values=["left", "center", "right"],
                                               state="readonly",
                                               width=6,
                                               textvariable=self.alignment
                                               )

        self.alignment_combobox.pack(side=tk.LEFT, padx=1)

        self.alignment_combobox.bind("<<ComboboxSelected>>", self.update_alignment)

        self.vertical_separator = ttk.Separator(self, orient=tk.VERTICAL)
        self.vertical_separator.pack(side=tk.LEFT, fill=tk.Y, padx=5)


        ttk.Label(self, text="Border:").pack(side=tk.LEFT, padx=1)
        self.border_checkbox = ttk.Checkbutton(self,
                                               text="",
                                               variable=self.border,
                                               command=self.update_border
                                               )
        self.border_checkbox.pack(side=tk.LEFT, padx=1, fill="both", expand=True)

        ttk.Label(self, text="Alpha:").pack(side=tk.LEFT, padx=1)
        self.border_alpha_entry = ttk.Spinbox(self,
                                              textvariable=self.border_alpha,
                                              from_=0,
                                              to=1,
                                              increment=0.1,
                                              width=3,
                                              command=self.update_border
                                              )

        self.border_alpha_entry.pack(side=tk.LEFT, padx=(1, 5))

        self.border_alpha_entry.bind("<Return>", self.update_border)
        self.border_alpha_entry.bind("<FocusOut>", self.update_border)

    def update_editor(self, *args):
        if DEBUG: print("Updating editor")
        if self.editor is not None:
            mpl_dpi = self.fig.get_dpi()
            screen_dpi = self.master.winfo_fpixels("1i")
            scaled_font_size = floor(self.artist.master.scale_artist_size(
                self.text_data["fontsize"], axes=self.artist.axes
            ) * (mpl_dpi / screen_dpi))

            self.editor.config(font=(self.text_data["font"],
                                        scaled_font_size),
                                fg=self.text_data["color"])
    
            tk_font = tk.font.Font(family=self.text_data["font"], size=scaled_font_size)
            self.editor.font = tk_font
            event = tk.Event()
            event.widget = self.editor

            self.editor.pick_on_modified(event)

        if DEBUG: print("Done updating editor")

    def update_border(self, *args):

        if self.editor is None: return

        self.text_data["border"] = bool(self.border.get())
        self.text_data["border_alpha"] = float(self.border_alpha.get())

        self.artist.set_bbox(dict(boxstyle="round,pad=0.4", 
                            facecolor="white", 
                            edgecolor="gray",
                            linewidth=1.0, 
                            alpha=self.text_data["border_alpha"]) if self.text_data["border"]
                            else None)

        self.editor.blit_redraw()

    def update_font(self, *args):

        if DEBUG: print("Updating font")
        if self.editor is None: return

        self.text_data["fontsize"] = float(self.fontsize.get())
        self.text_data["font"] = str(self.font.get())        

        self.artist.set_fontsize(self.artist.master.scale_artist_size(
            self.text_data["fontsize"], axes=self.artist.axes
        ))
        self.artist.set_fontfamily(self.text_data["font"])

        self.editor.blit_redraw()

        if DEBUG: print("Calling update_editor in update_font")
        self.update_editor()

        if self.center_id is None:
            
            self.center_id = self.after_idle(self.center_on_artist)

        if DEBUG: print("Updated font")

    def update_alignment(self, *args):

        self.text_data["alignment"] = str(self.alignment.get())
    
        self.editor.tag_configure("alignment", justify=self.text_data["alignment"])
        renderer = self.fig.canvas.get_renderer()
        if renderer is None:
            return

        try:
            bbox = self.artist.get_tightbbox(renderer)
        except AttributeError:
            return
        if bbox is None:
            return

        transform = self.artist.get_transform()
        current_display = transform.transform(self.artist.get_position())

        if self.text_data["alignment"] == "left":
            desired_display_x = bbox.x0
        elif self.text_data["alignment"] == "center":
            desired_display_x = (bbox.x0 + bbox.x1) / 2
        elif self.text_data["alignment"] == "right":
            desired_display_x = bbox.x1
        else:
            desired_display_x = current_display[0]

        new_position = transform.inverted().transform((desired_display_x, current_display[1]))
        self.artist.set_position(new_position)
        self.artist.set_ha(self.text_data["alignment"])
        self.editor.blit_redraw()

        if self.center_id is None:
            self.center_id = self.after_idle(self.center_on_artist)

    def center_on_artist(self):
        if self.editor is None or self.artist is None or not self.winfo_exists() or not self.editor.winfo_exists():
            return

        # Reset center id
        if getattr(self, "center_id", None) is not None:
            self.after_cancel(self.center_id)

        self.center_id = None

        fig = self.artist.get_figure()
        if fig is None and getattr(self.artist, "axes", None) is not None:
            fig = self.artist.axes.figure
        if fig is None:
            return

        self.fig = fig

        if not hasattr(self.fig, "canvas") or self.fig.canvas is None:
            return

        renderer = self.fig.canvas.get_renderer()
        if renderer is None:
            return

        try:
            bbox = self.artist.get_tightbbox(renderer)
        except AttributeError:
            return
        if bbox is None:
            return

        self.editor.update_idletasks()

        # After doing self.editor.update_idletasks(), the existance of the windows is updated and therefore must be checked here again
        # to prevent errors because of stale references to the non-existing toplevel
        if self.editor is None or self.artist is None or not self.winfo_exists() or not self.editor.winfo_exists():
            if DEBUG: print("Editor or menu does not exist, aborting center_on_artist")
            return


        center_x = (bbox.x0 + bbox.x1) / 2
        center_y = (bbox.y0 + bbox.y1) / 2
        x = center_x - self.editor.winfo_reqwidth() / 2
        y = self.fig.bbox.height - center_y - self.editor.winfo_reqheight() / 2

        self.editor.place_configure(x=x, y=y)
        self.position_above()

    def create_color_image(self):

        height = self.fontsize_spinbox.winfo_reqheight()
        size = ceil(height)
        gray_border_size = 1

        img = tk.PhotoImage(width=size, height=size)
        # Put a gray block inside to create a nice border around the color of the plot, this also leaves some padding on the right
        img.put("darkgray", to=(0,
                                0,
                                size,
                                size))
        
        # Fill the image with the current color of the plot
        img.put(self.color, to=(gray_border_size,
                                gray_border_size,
                                size-gray_border_size,
                                size-gray_border_size))

        self.color_image = img

    def choose_color(self, *args):
        color = tk.colorchooser.askcolor(color=self.color, parent=self)
        if color[1] is not None:
            self.color = color[1]
            self.create_color_image()
            self.color_btn.configure(image=self.color_image)

            self.text_data["color"] = mpl.colors.to_hex(self.color)
            self.update_editor()

    def position_above(self, offset_x=0, offset_y=0):
        if self.editor is None or not self.winfo_exists() or not self.editor.winfo_exists():
            return

        if self.center_id is not None:
            self.after_cancel(self.center_id)
        self.center_id = None

        if DEBUG: print("Positioning above")
        
        self.update()

        # After doing self.update, the existance of the windows is updated and therefore must be checked here again
        # to prevent errors because of stale references to the non-existing toplevel
        if self.editor is None or not self.winfo_exists() or not self.editor.winfo_exists():
            if DEBUG: print("Editor or menu does not exist, aborting positioning")
            return

        # Position the editor menu above the text editor, with optional offsets
        x = self.editor.winfo_rootx() + offset_x
        y = self.editor.winfo_rooty() - max(self.winfo_reqheight(), 1) - 10 + offset_y
        # Center the editor menu horizontally relative to the text editor
        x += (self.editor.winfo_width() - self.winfo_reqwidth()) // 2

        self.geometry(f"+{x}+{y}")
        self.lift()
        self.attributes("-topmost", True)
        self.deiconify()
        if DEBUG: print("Done positioning above")
        
    def hide(self):
        self.withdraw()

class CanvasPlot:
    
    def __init__(self, DEBUG):

        self.plot_data = {}

        # Store info of polygons for HPLC
        self.polygons = []

        # Dictionary to keep track of the corrected ypoints
        self.corrected_ypoints = {} #iid: corrected_ypoints, this needs to be updated whenever something is changed in correct_ypoints

        # Store list for simulations on graph
        self.simulation = []
        self.isimulation = []

        # keep track whether an inset was already drawn
        self.insetplotted = False
        
        # keep track of x-position of inset
        self.xpos_inset = "upper right"

        # Variable self.initiated is used when a new graph is opened so that the program can distinguish between a known graph being opened again
        self.initiated = False

        # Multiplot info, needs to be here otherwise it often results in errors
        self.multiplot_lines = {}
        self.multiplot_labels = {}
        self.free_texts = {}
        self.legend = None

        # Keep track of HPLC baseline
        self.HPLC_baseline = None
        self.line = None
        self.inset_line = None
        self.fit = None
        self.Vmax_constant = None
        self.Km_rectangle = None
        self.fit_params = None
        self.tm_baselines = []
        # Keep track of all "axles" for changing the manual baseline
        self.manual_HPLC_baseline_axles = []
        # Whether to skip baseline drawing in blitting for axle dragging
        self.skip_HPLC_baseline = False

        # Keep track of the artist selected by clicking
        self.selected_artist = None
        self.picked_axle = False
        
        # Variables to keep track of after methods for certain events
        self._refresh = None
        self._configured_mathtext_font = None

        self._redraw = None

        self._blit = None

        self._pick = None

        self._save = None

        # Keep track whether a pick_widget exists
        self.pick_text = None
        self.editor_menu = None

        self.fig = plt.figure(dpi=75)
        self.figure_boundary_artist1 = None
        self.figure_boundary_artist2 = None
        
        self.ax = self.add_ax(self.fig)

    def get_scale(self, figure):
        """Return the uniform scale that fits ``figure`` into the reference size.

        Matplotlib sizes text and line widths in points, so DPI changes the
        number of rendered pixels but not their physical size.  The scale
        therefore has to be based on the figure dimensions in inches rather
        than on its DPI or pixel dimensions.
        """
        if figure is self.fig:

            renderer = figure.canvas.get_renderer()
    
            columns = [sum(col) for col in figure.divider.get_horizontal_sizes(renderer)]
            rows = [sum(row) for row in figure.divider.get_vertical_sizes(renderer)]

            current_width, current_height = columns[1], rows[1]
            reference_width, reference_height, *_ = self._get_layout()

            width_scale = current_width / reference_width
            height_scale = current_height / reference_height

            return min(width_scale, height_scale)
                        
        else: return 1

    def _get_layout_option(self, name, default):
        try:
            if self.master.plottype == "MultiPlot":
                plottype = self.multiplot_data["PlotOptions"]["plottype"]
            else:
                plottype = self.master.plottype

            if plottype is None:
                plottype = "General"

            return float(self.master.plotoptions_data[plottype].get(name, default))
        except (AttributeError, KeyError, TypeError, ValueError):
            return default

    def _get_layout(self):
        plot_width = self._get_layout_option("plot_width", 5.6)
        plot_height = self._get_layout_option("plot_height", 3.8)

        padding_left = self._get_layout_option("padding_left", 0.1)
        padding_right = self._get_layout_option("padding_right", 0.1)
        padding_bottom = self._get_layout_option("padding_bottom", 0.1)
        padding_top = self._get_layout_option("padding_top", 0.1)

        return (
            max(0.1, plot_width),
            max(0.1, plot_height),
            max(0.0, padding_left),
            max(0.0, padding_right),
            max(0.0, padding_bottom),
            max(0.0, padding_top),
        )

    def scale_artist_size(self, size, axes=None):
        if axes is None:
            figure = self.fig
            axes = self.ax
        else:
            figure = axes.figure

        return float(size) * self.get_scale(figure)
    
    def scale_3D_padding(self, size, axes=None, ticks=False):
        if axes is None:
            figure = self.fig
            axes = self.ax
        else:
            figure = axes.figure

        offset = 8 if ticks else 21

        scale = self.get_scale(figure)

        return (float(size) + offset) * scale - offset

    def _get_inset_borderpad(self, axes):
        borderpad = self.plot_data["inset_borderpad"]
        scale = self.get_scale(axes.figure)

        if isinstance(borderpad, tuple):
            return tuple(value * scale for value in borderpad)
        return borderpad * scale

    def _update_inset_borderpad(self, axes):
        if not hasattr(axes, "inset"):
            return

        locator = axes.inset.get_axes_locator()
        if isinstance(locator, AnchoredSizeLocator):
            locator.borderpad = self._get_inset_borderpad(axes)

    def _sync_export_legend_location(self):
        if not hasattr(self, "expax"):
            return

        source_legend = self.ax.get_legend()
        export_legend = self.expax.get_legend()
        if source_legend is None or export_legend is None:
            return

        source_bbox = source_legend.get_window_extent(self.fig.canvas.get_renderer())
        source_axes_bbox = self.ax.get_window_extent(self.fig.canvas.get_renderer())
        source_center = source_bbox.get_points().mean(axis=0)

        relative_center = (
            (source_center[0] - source_axes_bbox.x0) / source_axes_bbox.width,
            (source_center[1] - source_axes_bbox.y0) / source_axes_bbox.height,
        )

        export_legend.set_loc("center")
        export_legend.set_bbox_to_anchor(relative_center, transform=self.expax.transAxes)

    def scale_axes_strokes(self, axes, inset=False):

        # Separate main_axes and the axes used for plotting because the scaling should always be based on the size of the main_axes for consistency
        main_axes = axes

        if inset:
            axes = axes.inset

        axes_linewidth = self.scale_artist_size(mpl.rcParams["axes.linewidth"], main_axes)
        for spine in axes.spines.values():
            spine.set_linewidth(axes_linewidth)

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            xtick_major_pad = self.scale_3D_padding(mpl.rcParams["xtick.major.pad"], main_axes, ticks=True)
            xtick_minor_pad = self.scale_3D_padding(mpl.rcParams["xtick.minor.pad"], main_axes, ticks=True)
            ytick_major_pad = self.scale_3D_padding(mpl.rcParams["ytick.major.pad"], main_axes, ticks=True)
            ytick_minor_pad = self.scale_3D_padding(mpl.rcParams["ytick.minor.pad"], main_axes, ticks=True)
        else:
            xtick_major_pad = self.scale_artist_size(mpl.rcParams["xtick.major.pad"], main_axes)
            xtick_minor_pad = self.scale_artist_size(mpl.rcParams["xtick.minor.pad"], main_axes)
            ytick_major_pad = self.scale_artist_size(mpl.rcParams["ytick.major.pad"], main_axes)
            ytick_minor_pad = self.scale_artist_size(mpl.rcParams["ytick.minor.pad"], main_axes)

        if self.master.plottype is None:
            config_plottype = "General"
        else:
            config_plottype = self.master.plottype
        fontsize = self.scale_artist_size(self.master.plotoptions_data[config_plottype]["fontsize"], axes=axes)

        axes.tick_params(
            axis="x",
            which="major",
            width=self.scale_artist_size(mpl.rcParams["xtick.major.width"], main_axes),
            length=self.scale_artist_size(mpl.rcParams["xtick.major.size"], main_axes),
            labelsize=fontsize,
            pad=xtick_major_pad,
        )
        axes.tick_params(
            axis="x",
            which="minor",
            width=self.scale_artist_size(mpl.rcParams["xtick.minor.width"], main_axes),
            length=self.scale_artist_size(mpl.rcParams["xtick.minor.size"], main_axes),
            labelsize=fontsize,
            pad=xtick_minor_pad,
        )
        axes.tick_params(
            axis="y",
            which="major",
            width=self.scale_artist_size(mpl.rcParams["ytick.major.width"], main_axes),
            length=self.scale_artist_size(mpl.rcParams["ytick.major.size"], main_axes),
            labelsize=fontsize,
            pad=ytick_major_pad,
        )
        axes.tick_params(
            axis="y",
            which="minor",
            width=self.scale_artist_size(mpl.rcParams["ytick.minor.width"], main_axes),
            length=self.scale_artist_size(mpl.rcParams["ytick.minor.size"], main_axes),
            labelsize=fontsize,
            pad=ytick_minor_pad,
        )

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            axes.zaxis.set_tick_params(
                which="major",
                width=self.scale_artist_size(mpl.rcParams["ytick.major.width"], main_axes),
                length=self.scale_artist_size(mpl.rcParams["ytick.major.size"], main_axes),
                labelsize=fontsize,
                pad=ytick_major_pad,
            )
            axes.zaxis.set_tick_params(
                which="minor",
                width=self.scale_artist_size(mpl.rcParams["ytick.minor.width"], main_axes),
                length=self.scale_artist_size(mpl.rcParams["ytick.minor.size"], main_axes),
                labelsize=fontsize,
                pad=ytick_minor_pad,
            )

    def default_annotation_position(self, axes, x, y):
        return (0.0, 10.0)

    def _bind_custom_annotation(self, axes):
        """Bind the custom annotation implementation to an axes instance."""
        if axes is None:
            return
        axes.annotate = MethodType(annotate, axes)

    def connect_gui(self, master):
        
        self.master = master

        # Import Figure into Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, self.master)

        # Bind clicks on canvas widget
        self.release = self.canvas.mpl_connect("button_release_event", self.on_release)
        self.pickevent =  self.canvas.mpl_connect("pick_event", self.on_pick)

        # Setup Toolbar
        self.toolbar = Toolbar(self.canvas, self.master.toolbar_frame, self)

        # Setup for blitting
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)
        self.annotations = []
        self.iannotations = []

        # Setup Selectors for Peak Picking and Integrating
        self._setup_selectors(self.ax)

    # Custom function for canvas drawing and other arugments associated with it
    def draw_canvas(self):

        # Draw the canvas
        self.canvas.draw()

    def _setup_selectors(self, axes):
        """Setup peak picking and integration selectors for the given axes"""
        self.PeakSelector = RectangleSelector(axes, self.pick_peaks,
                                              useblit=True,
                                              button=[1],
                                              minspanx=5, minspany=5,
                                              spancoords="pixels",
                                              interactive=False)

        self.IntegrateSelector = SpanSelector(axes, self.integrate,
                                              direction="horizontal",
                                              useblit=True,
                                              button=[1],
                                              interactive=False)

        self.PeakSelector.set_active(False)
        self.IntegrateSelector.set_active(False)

    def _setup_inset_selector(self, axes):
        self.InsetPeakSelector = RectangleSelector(axes, self.pick_inset_peaks,
                                                   useblit=True,
                                                   button=[1],
                                                   minspanx=5, minspany=5,
                                                   spancoords="pixels",
                                                   interactive=False)
        self.InsetPeakSelector.set_active(False)

    def _update_selectors(self):
        if self.toolbar.mode == _Mode.PEAKS:
            self.PeakSelector.set_active(True)
            self.IntegrateSelector.set_active(False)
            if self.insetplotted:
                self.InsetPeakSelector.set_active(True) 
        elif self.toolbar.mode == _Mode.INT:
            self.IntegrateSelector.set_active(True)
            self.PeakSelector.set_active(False)
            if self.insetplotted:
                self.InsetPeakSelector.set_active(False) 
        else:
            self.PeakSelector.set_active(False)
            self.IntegrateSelector.set_active(False)
            if self.insetplotted:
                self.InsetPeakSelector.set_active(False) 

    def _blit_redraw(self, axes=None, reset_inset=False, updated_fontsize=False):
        if axes == None:
            axes = self.ax
        """Restore the saved background and redraw dynamic artists via blitting."""
        if self.background is None:
            self.draw_canvas()
            return

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            self.draw_canvas()
        else:
            try:
                # Restore the background
                self.canvas.restore_region(self.background)
                if self.figure_boundary_artist1 is not None:
                    self.fig.draw_artist(self.figure_boundary_artist1)
                if self.figure_boundary_artist2 is not None:
                    self.fig.draw_artist(self.figure_boundary_artist2)
                if self.master.plottype not in ["MultiPlot", "Assay"]:
                    plot_data = self.plot_data
                else:
                    plot_data = self.multiplot_data["PlotOptions"]

                if plot_data["show_yticks"] or self.master.plottype == "Kinetics":
                    if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
                        axes.draw_artist(axes.zaxis)
                    else:
                        axes.draw_artist(axes.yaxis)

                if plot_data["show_xticks"] or self.master.plottype == "Kinetics":
                    axes.draw_artist(axes.xaxis)

                if self.master.plottype not in ["MultiPlot", "Assay"]:

                    # Redraw polygons
                    if self.master.plottype == "HPLC" and self.plot_data["plot_integrals"]:

                        for polygon in self.polygons:
                            axes.draw_artist(polygon)

                    if self.master.plottype == "CD" and self.plot_data["show_zero_line"]:
                        axes.draw_artist(self.zero_line)

                    # Redraw simulation
                    for simulation in self.simulation:
                        axes.draw_artist(simulation)

                    if self.insetplotted:
                        for simulation in self.isimulation:
                            axes.inset.draw_artist(simulation)

                    if self.master.plottype == "Tm":
                        # Redraw plot
                        try:
                            if self.plot_data["show_fit"] and self.plot_data["Tm_method"] in ["SCB","SLB","SQB","VHD","EGD"]:
                                axes.draw_artist(self.fit)
                        except Exception as e:
                            if DEBUG: print("Error drawing fit:", e)
                        try:
                            if self.plot_data["show_tm_baselines"] and self.plot_data["Tm_method"] in ["SCB","SLB","SQB"]:
                                for baseline in self.tm_baselines:
                                    axes.draw_artist(baseline)
                        except Exception as e:
                            if DEBUG: print("Error drawing tm baselines:", e)

                    axes.draw_artist(self.line)

                    # refresh annotations
                    for ann in self.annotations:
                        axes.draw_artist(ann)

                    # Draw HPLC baseline and axles if applicable
                    if self.master.plottype == "HPLC" and self.master.HPLC_baseline_visible and axes == self.ax:
                        if not self.skip_HPLC_baseline: axes.draw_artist(self.HPLC_baseline)
                        if self.plot_data["integration_type"] == "manual":
                            for axle in self.manual_HPLC_baseline_axles:
                                axes.draw_artist(axle)

                    if self.insetplotted and self.plot_data["inset"]:

                        if reset_inset:
                            # Calculate the width and height of the insets
                            inset_width = str(self.plot_data["inset_xsize"]) + "%"
                            inset_height = str(self.plot_data["inset_ysize"]) + "%"
                            # Create new locator for the inset axes
                            new_loc = AnchoredSizeLocator(bbox_to_anchor=axes.bbox,
                                                        x_size=inset_width,
                                                        y_size=inset_height,
                                                        loc=self.plot_data["inset_pos"],
                                                        borderpad=self._get_inset_borderpad(axes))
                            
                            # Change locator of the inset axes
                            axes.inset.set_axes_locator(new_loc)

                            # Also update the position of the yaxis
                            axes.inset.yaxis.set_label_position("right" if "left" in self.plot_data["inset_pos"] else "left")
                            if updated_fontsize:
                                font = self.master.plotoptions_data[self.master.plottype]["font"]
                                fontsize = self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes)
                                inset_ylabel = axes.inset.get_ylabel()
                                inset_xlabel = axes.inset.get_xlabel()

                                labelpad = self.scale_artist_size(mpl.rcParams["axes.labelpad"], axes)

                                axes.inset.set_ylabel(inset_ylabel, font=font, fontsize=fontsize, labelpad=labelpad)
                                axes.inset.set_xlabel(inset_xlabel, font=font, fontsize=fontsize, labelpad=labelpad)
                                axes.inset.tick_params(axis="x",
                                                    labelsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                                    labelfontfamily=font)
                                axes.inset.tick_params(axis="y",
                                                    labelsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                                    labelfontfamily=font)

                                for ann in self.iannotations:
                                    ann.set_fontsize(fontsize)

                        axes.draw_artist(axes.inset)
                        
                        for ann in self.iannotations:
                            # Necessary so not every object is unnecessarily drawn twice
                            # Otherwise the moving object disappears during custom blitting
                            if ann._draggable is not None and ann._draggable.got_artist:
                                axes.inset.draw_artist(ann)

                    elif self.insetplotted and not self.plot_data["inset"]:
                        self.InsetPeakSelector.disconnect_events()
                        axes.inset.remove()
                        self.insetplotted = False

                elif self.master.plottype == "Assay":

                    if self.multiplot_data["PlotOptions"]["assay_type"] and self.line is not None:
                        markers, caplines, barlinecols = self.line

                        for barlinecol in barlinecols:
                            axes.draw_artist(barlinecol)
                        for capline in caplines:
                            axes.draw_artist(capline)
                        axes.draw_artist(markers)

                        # Redraw Km rectangle
                        try:
                            if self.multiplot_data["PlotOptions"]["show_Km"] and "popt" in self.multiplot_data["PlotOptions"]["assay_fit"] and self.Km_rectangle is not None:
                                axes.draw_artist(self.Km_rectangle)
                        except Exception as e:
                            if DEBUG: print("Error drawing Km rectangle:", e)

                        # Redraw Vmax constant
                        try:
                            if self.multiplot_data["PlotOptions"]["show_vmax"] and "popt" in self.multiplot_data["PlotOptions"]["assay_fit"] and self.Vmax_constant is not None:
                                axes.draw_artist(self.Vmax_constant)
                        except Exception as e:
                            if DEBUG: print("Error drawing Vmax constant:", e)

                        # Try to draw the params legend
                        try:
                            if self.multiplot_data["PlotOptions"]["show_fit_data"] and "popt" in self.multiplot_data["PlotOptions"]["assay_fit"] and self.fit_params is not None:
                                axes.draw_artist(self.fit_params)
                        except Exception as e:
                            if DEBUG: print("Error drawing fit params legend:", e)

                        # Redraw plot
                        try:
                            if self.multiplot_data["PlotOptions"]["show_assay_fit"] and self.multiplot_data["PlotOptions"]["assay_fit"] and "popt" in self.multiplot_data["PlotOptions"]["assay_fit"]:
                                axes.draw_artist(self.fit)
                        except Exception as e:
                            if DEBUG: print("Error drawing fit:", e)                                
                else:

                    # Redraw lines
                    for line in self.multiplot_lines:
                        axes.draw_artist(self.multiplot_lines[line])

                    # Redraw labels
                    for label in self.multiplot_labels:
                        axes.draw_artist(self.multiplot_labels[label])

                    # Redraw legend
                    if (self.legend and
                        (self.legend._draggable is None or not self.legend._draggable.got_artist)):
                        axes.draw_artist(self.legend)

                for text in self.free_texts.values():
                    if text._draggable is None or not text._draggable.got_artist:
                        axes.draw_artist(text)

                # Update the canvas
                self.canvas.blit(self.fig.bbox)
                
            except Exception as e:
                if DEBUG: print("Blit redraw failed:", e)
                self.draw_canvas()

        if axes is self.ax:
            self._update_selectors()

    def _set_widgets_state(self, widgets, disabled=True):
        """Set state for multiple widgets at once.
        
        Args:
            widgets: List of widget objects or dict of {widget: state_bool}
            disabled: If True, disables widgets; if False, enables them
        """
        state = ["disabled"] if disabled else ["!disabled"]
        
        # Handle list of widgets
        if isinstance(widgets, list):
            for widget in widgets:
                widget.state(state)
        # Handle dict of widgets with custom state per widget
        elif isinstance(widgets, dict):
            for widget, is_disabled in widgets.items():
                s = ["disabled"] if is_disabled else ["!disabled"]
                widget.state(s)

    def _plot_assay_fit_single(self, axes):
        """Plot assay fit for the single-plot case.

        Returns: (plotted_fit: bool, fit_artist)
        """
        plotted_fit = False
        fit_artist = None
        rectangle_artist = None
        constant_artist = None
        params_artist = None

        plot_data = self.multiplot_data["PlotOptions"]

        fit = plot_data.get("assay_fit", {})
        
        if "popt" in fit:
            rectangle_artist = self._plot_assay_Km_rectangle_single(axes)
            constant_artist = self._plot_assay_vmax_constant_single(axes)
            params_artist = self._plot_assay_fit_params_single(axes)

            if plot_data["show_assay_fit"]:
                # Infer the step_size from the range of xpoints to get enough datapoints for a smooth curve
                xlim = axes.get_xlim()
                range_x = xlim[1] - xlim[0]
                step_size = range_x / 1000
                x_fit = np.arange(plot_data["xpoints"].min()-5, plot_data["xpoints"].max()+5, step_size)
                y_fit = michaelis_menten(x_fit, *fit["popt"])

                fit_artist, = axes.plot(x_fit, y_fit,
                                        linewidth=self.scale_artist_size(plot_data["assay_fit_linewidth"], axes),
                                        color=plot_data["assay_fit_color"],
                                        linestyle=plot_data["assay_fit_linestyle"])
                plotted_fit = True

        return plotted_fit, fit_artist, rectangle_artist, constant_artist, params_artist

    def _plot_assay_Km_rectangle_single(self, axes):

        rectangle_artist = None

        plot_data = self.multiplot_data["PlotOptions"]

        fit = plot_data.get("assay_fit", {})

        if "popt" in fit and plot_data["show_Km"]:
            
            Km = fit["popt"][0]
            Vmax = fit["popt"][1]

            rectangle_artist, = axes.plot([-100, Km, Km], [Vmax/2, Vmax/2, -100],
                                            color="gray",
                                            linewidth=self.scale_artist_size(plot_data["assay_fit_linewidth"]/2, axes),
                                            linestyle="--")

        return rectangle_artist
    
    def _plot_assay_vmax_constant_single(self, axes):

        constant_artist = None

        plot_data = self.multiplot_data["PlotOptions"]

        fit = plot_data.get("assay_fit", {})

        if "popt" in fit and plot_data["show_vmax"]:
            
            Vmax = fit["popt"][1]

            constant_artist = axes.axhline(y=Vmax, color="gray", linewidth=self.scale_artist_size(plot_data["assay_fit_linewidth"]/2, axes), linestyle="--")

        return constant_artist

    def _plot_assay_fit_params_single(self, axes):

        """Plot assay fit parameters (Km and Vmax) for the single-plot case.

        Returns: params_artist
        """

        params_artist = None

        plot_data = self.multiplot_data["PlotOptions"]
        
        fit = plot_data.get("assay_fit", {})

        if "popt" in fit and plot_data["show_fit_data"]:

            Km = fit["popt"][0]
            Vmax = fit["popt"][1]
            Km_error, Vmax_error = np.sqrt(np.diag(fit["pcov"]))
            font = self.master.plotoptions_data[self.master.plottype]["font"]
            fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=axes)

            dummy = mpl.lines.Line2D([], [], linestyle="none")

            params_artist = axes.legend([dummy, dummy],
                                        [f"K$_m$ = {Km:.4g} ± {Km_error:.2g} {plot_data['assay_x_unit']}", "V$_{max}$ = "+f"{Vmax:.4g} ± {Vmax_error:.2g} {plot_data['assay_y_unit']}"],
                                        prop={"family": font,
                                              "size": fontsize},
                                        title_fontproperties={"family": font, 
                                                              "size": fontsize},
                                        loc="best",
                                        markerscale=0,
                                        handlelength=0,
                                        handletextpad=0,
                                        linewidth=self.scale_artist_size(mpl.rcParams["legend.linewidth"] if mpl.rcParams["legend.linewidth"] is not None
                                                                         else mpl.rcParams["patch.linewidth"], axes),

                                    )

        return params_artist

    def _plot_tm_fit_single(self, axes):
        """Plot Tm fit and baselines for the single-plot case.

        Returns: (plotted_fit: bool, fit_artist, baselines_list)
        """
        plotted_fit = False
        fit_artist = None
        baselines = []

        tm = self.plot_data.get("Tm_method")
        fits = self.plot_data.get("fits", {})
        if tm in fits and "popt" in fits[tm] and not np.any(np.isnan(fits[tm]["popt"])):
            if self.plot_data["show_fit"]:
                # Infer the step_size from the range of xpoints to get enough datapoints for a smooth curve
                xlim = axes.get_xlim()
                range_x = xlim[1] - xlim[0]
                step_size = range_x / 1000
                x_fit = np.arange(self.plot_data["xpoints"].min()-5, self.plot_data["xpoints"].max()+5, step_size)
                if tm == "SCB":
                    y_fit = sigmoidal_constant_baseline(x_fit, *fits["SCB"]["popt"])
                elif tm == "SLB":
                    y_fit = sigmoidal_linear_baseline(x_fit, *fits["SLB"]["popt"])
                elif tm == "SQB":
                    y_fit = sigmoidal_quadratic_baseline(x_fit, *fits["SQB"]["popt"])
                elif tm == "VHD":
                    y_fit = vant_hoff(x_fit, *fits["VHD"]["popt"])
                elif tm == "EGD":
                    y_fit = gaussian(x_fit, *fits["EGD"]["popt"])

                fit_artist, = axes.plot(x_fit, y_fit,
                                        linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                        color=self.plot_data["fit_color"],
                                        linestyle=self.plot_data["fit_linestyle"])
                plotted_fit = True
            else:
                plotted_fit = False
                fit_artist = None

            if self.plot_data.get("show_tm_baselines") and tm in ["SCB", "SLB", "SQB"]:
                # Infer the step_size from the range of xpoints to get enough datapoints for a smooth curve
                xlim = axes.get_xlim()
                range_x = xlim[1] - xlim[0]
                step_size = range_x / 1000

                if not plotted_fit: 
                    x_fit = np.arange(self.plot_data["xpoints"].min()-5, self.plot_data["xpoints"].max()+5, step_size)

                if tm == "SCB":
                    y_baseline1 = np.full(x_fit.size, fits["SCB"]["popt"][0])
                    y_baseline2 = np.full(x_fit.size, fits["SCB"]["popt"][1])
                elif tm == "SLB":
                    y_baseline1 = fits["SLB"]["popt"][0] * x_fit + fits["SLB"]["popt"][1]
                    y_baseline2 = fits["SLB"]["popt"][2] * x_fit + fits["SLB"]["popt"][3]
                elif tm == "SQB":
                    y_baseline1 = fits["SQB"]["popt"][0] * x_fit**2 + fits["SQB"]["popt"][1] * x_fit + fits["SQB"]["popt"][2]
                    y_baseline2 = fits["SQB"]["popt"][3] * x_fit**2 + fits["SQB"]["popt"][4] * x_fit + fits["SQB"]["popt"][5]
                else:
                    y_baseline1 = np.full(x_fit.size, 0)
                    y_baseline2 = np.full(x_fit.size, 0)


                baseline1, = axes.plot(x_fit, y_baseline1,
                                        linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                        linestyle="--",
                                        color=self.plot_data["fit_color"])
                baseline2, = axes.plot(x_fit, y_baseline2,
                                        linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                        linestyle="--",
                                        color=self.plot_data["fit_color"])
                baselines = [baseline1, baseline2]

        return plotted_fit, fit_artist, baselines

    def _plot_tm_fit_multi(self, axes, plot, iid, min_y=None, max_y=None, normalized=False, plot_offset=False):
        """Plot Tm fit and baselines for a multiplot entry.

        Returns: (plotted_fit: bool, fit_artist, baselines_list)
        """
        plotted_fit = False
        fit_artist = None
        baselines = []

        # Since the difference between MRE and measured ellipticity is just a scaling factor, we can check whether the
        # fit of the iid was calculated using the MRE or measured ellipticity and scale the fit accordingly

        plot_MRE = plot.get("calc_MRE", False)
        multiplot_MRE = self.multiplot_data["PlotOptions"].get("calc_MRE", False)

        if plot_MRE == multiplot_MRE:
            scaling_factor = 1.0
        else:

            conc = plot["concentration"]*10**(-3)
            pathlength = plot["pathlength"]
            num_res = plot["nbr_of_residues"]
            
            MRE_scaling = 1 / (conc*pathlength*num_res) / (10**3)

            if plot_MRE and not multiplot_MRE:
                scaling_factor = 1 / MRE_scaling

            else:
                scaling_factor = MRE_scaling


        tm = self.multiplot_data["PlotOptions"].get("Tm_method")
        fits = plot.get("fits", {})
        if tm in fits and "popt" in fits[tm] and not np.any(np.isnan(fits[tm]["popt"])):
            # Infer the step_size from the range of xpoints to get enough datapoints for a smooth curve
            xlim = axes.get_xlim()
            range_x = xlim[1] - xlim[0]
            step_size = range_x / 1000

            xmin, xmax = plot["xpoints"].min()-5, plot["xpoints"].max()+5

            x_fit = np.arange(xmin, xmax, step_size)

            if tm == "SCB":
                y_fit = sigmoidal_constant_baseline(x_fit, *fits["SCB"]["popt"])
            elif tm == "SLB":
                y_fit = sigmoidal_linear_baseline(x_fit, *fits["SLB"]["popt"])
            elif tm == "SQB":
                y_fit = sigmoidal_quadratic_baseline(x_fit, *fits["SQB"]["popt"])
            elif tm == "VHD":
                y_fit = vant_hoff(x_fit, *fits["VHD"]["popt"])
            elif tm == "EGD":
                y_fit = gaussian(x_fit, *fits["EGD"]["popt"])

            y_fit *= scaling_factor

            fit_clr = self.multiplot_data[iid]["color"]
            fit_alpha = self.multiplot_data[iid]["alpha"]

            # Handle normalization and offsets
            if normalized and min_y is not None and max_y is not None:
                normalized_fit = normalize(y_fit, min_y, max_y)
                if plot_offset:
                    y_fit = normalized_fit + self.multiplot_data[iid]["position"] * 1.05
                else:
                    y_fit = normalized_fit
            else:
                if plot_offset and min_y is not None:
                    y_fit = y_fit + self.multiplot_data[iid]["position"] * 1.05 * (self.multiplot_data["PlotOptions"]["global_max_y"] - self.multiplot_data["PlotOptions"]["global_min_y"]) - min_y

            kwargs = dict()

            if self.multiplot_data["PlotOptions"].get("3D", False):
                kwargs.update({"zs": self.multiplot_data["PlotOptions"]["3D_data"]["offset"]*self.multiplot_data[iid]["position"] + 0.5,
                               "zdir": "y"})

            # Get the limits
            if self.multiplot_data["PlotOptions"].get("3D", False):
                x_min, x_max = axes.get_xlim()
                y_min, y_max = axes.get_zlim()

                fit_mask = (x_fit >= x_min) & (x_fit <= x_max) & \
                            (y_fit >= y_min) & (y_fit <= y_max)

                x_fit_mask, y_fit_mask = x_fit[fit_mask], y_fit[fit_mask]
            
            else:
                x_fit_mask, y_fit_mask = x_fit, y_fit

            fit_artist, = axes.plot(x_fit_mask, y_fit_mask,
                                    linewidth=self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes),
                                    linestyle=self.multiplot_data[iid]["linestyle"],
                                    color=fit_clr,
                                    alpha=fit_alpha,
                                    **kwargs)
            plotted_fit = True

            # Baselines
            if self.multiplot_data["PlotOptions"].get("show_tm_baselines") and tm in ["SCB", "SLB", "SQB"]:
                if tm == "SCB":
                    y_baseline1 = np.full(x_fit.size, fits["SCB"]["popt"][0])
                    y_baseline2 = np.full(x_fit.size, fits["SCB"]["popt"][1])
                elif tm == "SLB":
                    y_baseline1 = fits["SLB"]["popt"][0] * x_fit + fits["SLB"]["popt"][1]
                    y_baseline2 = fits["SLB"]["popt"][2] * x_fit + fits["SLB"]["popt"][3]
                elif tm == "SQB":
                    y_baseline1 = fits["SQB"]["popt"][0] * x_fit**2 + fits["SQB"]["popt"][1] * x_fit + fits["SQB"]["popt"][2]
                    y_baseline2 = fits["SQB"]["popt"][3] * x_fit**2 + fits["SQB"]["popt"][4] * x_fit + fits["SQB"]["popt"][5]

                y_baseline1 *= scaling_factor
                y_baseline2 *= scaling_factor

                y_baselines = [y_baseline1, y_baseline2]
                if normalized and min_y is not None and max_y is not None:
                    for i, baseline in enumerate(y_baselines):
                        normalized_baseline = normalize(baseline, min_y, max_y)
                        if plot_offset:
                            y_baselines[i] = normalized_baseline + self.multiplot_data[iid]["position"] * 1.05
                        else:
                            y_baselines[i] = normalized_baseline
                else:
                    if plot_offset and min_y is not None:
                        for baseline in y_baselines:
                            baseline += self.multiplot_data[iid]["position"] * 1.05 * (self.multiplot_data["PlotOptions"]["global_max_y"] - self.multiplot_data["PlotOptions"]["global_min_y"]) - min_y

                y_baseline1 = y_baselines[0]

                # Get the limits
                if self.multiplot_data["PlotOptions"].get("3D", False):
                    x_min, x_max = axes.get_xlim()
                    y_min, y_max = axes.get_zlim()
    
                    baseline1_mask = (x_fit >= x_min) & (x_fit <= x_max) & \
                                (y_baseline1 >= y_min) & (y_baseline1 <= y_max)
    
                    x_baseline1_mask, y_baseline1_mask = x_fit[baseline1_mask], y_baseline1[baseline1_mask]
                
                else:
                    x_baseline1_mask, y_baseline1_mask = x_fit, y_baseline1

                baseline1, = axes.plot(x_baseline1_mask, 
                                       y_baseline1_mask, 
                                       linewidth=self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes), 
                                       linestyle="--", 
                                       color=fit_clr, 
                                       alpha=self.multiplot_data[iid]["alpha"],
                                       **kwargs)

                y_baseline2 = y_baselines[1]
                
                # Get the limits
                if self.multiplot_data["PlotOptions"].get("3D", False):
                    x_min, x_max = axes.get_xlim()
                    y_min, y_max = axes.get_zlim()
    
                    baseline2_mask = (x_fit >= x_min) & (x_fit <= x_max) & \
                                (y_baseline2 >= y_min) & (y_baseline2 <= y_max)
    
                    x_baseline2_mask, y_baseline2_mask = x_fit[baseline2_mask], y_baseline2[baseline2_mask]
                
                else:
                    x_baseline2_mask, y_baseline2_mask = x_fit, y_baseline2

                baseline2, = axes.plot(x_baseline2_mask, 
                                       y_baseline2_mask, 
                                       linewidth=self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes), 
                                       linestyle="--", 
                                       color=fit_clr, 
                                       alpha=self.multiplot_data[iid]["alpha"],
                                       **kwargs)
                baselines = [baseline1, baseline2]

        return plotted_fit, fit_artist, baselines

    def add_ax(self, fig):

        if not hasattr(self, "master"):
            plot_width, plot_height = fig.get_size_inches()
            padding_left = padding_right = padding_top = padding_bottom = 0.1
        else:
            (
                plot_width,
                plot_height,
                padding_left,
                padding_right,
                padding_bottom,
                padding_top,
            ) = self._get_layout()

        # Setup the divider to get a fixed size for the data inside of the axes
        horiz = [Size.Fixed(padding_left), Size.Fixed(plot_width), Size.Fixed(padding_right)]
        vert = [Size.Fixed(padding_bottom), Size.Fixed(plot_height), Size.Fixed(padding_top)]

        fig.divider = Divider(fig, [0, 0, 1, 1], horiz, vert, aspect=False)

        ax = fig.add_axes(fig.divider.get_position(), axes_locator=fig.divider.new_locator(nx=1, ny=1))

        return ax

    def add_3d_ax(self, fig):
        """Create a 3D axes in the same layout slot as the regular axes."""
        ax = fig.add_axes(fig.divider.get_position(),
                          projection="3d",
                          axes_locator=fig.divider.new_locator(nx=1, ny=1),
                )

        ax.mouse_init(rotate_btn=[], zoom_btn=[], pan_btn=[])  # Disable default mouse rotation to avoid conflicts with custom interactions

        return ax

    def update_fig_size(self, fig):
        renderer = fig.canvas.get_renderer()

        (
            plot_width,
            plot_height,
            padding_left,
            padding_right,
            padding_bottom,
            padding_top,
        ) = self._get_layout()

        # Setup the divider to get a fixed size for the data inside of the axes
        vert = [Size.Fixed(padding_bottom), Size.Fixed(plot_height), Size.Fixed(padding_top)]
        horiz = [Size.Fixed(padding_left), Size.Fixed(plot_width), Size.Fixed(padding_right)]

        fig.divider.set_vertical(vert)
        fig.divider.set_horizontal(horiz)

        columns = [sum(col) for col in fig.divider.get_horizontal_sizes(renderer)]
        rows = [sum(row) for row in fig.divider.get_vertical_sizes(renderer)]

        width = sum(columns)
        height = sum(rows)

        if fig is self.fig:
            # When the fig is actually on the graph, change the size of the ax, to fit properly into the entire fig size
            fig_width, fig_height = fig.get_size_inches()
            width_ratio = fig_width / width
            height_ratio = fig_height / height

            for i, _ in enumerate(vert):
                vert[i] = Size.Fixed(height_ratio * rows[i]) 
            
            for i, _ in enumerate(horiz):
                horiz[i] = Size.Fixed(width_ratio * columns[i])

            fig.divider.set_vertical(vert)
            fig.divider.set_horizontal(horiz)

        else:

            columns = [sum(col) for col in fig.divider.get_horizontal_sizes(renderer)]
            rows = [sum(row) for row in fig.divider.get_vertical_sizes(renderer)]
            width = sum(columns)
            height = sum(rows)

            fig.set_size_inches(width, height)

    def show_visual_border(self):
        # Draw a visual border indicated by two rectangles to show which part of the figure will be visible in the exported figure

        (
            plot_width,
            plot_height,
            padding_left,
            padding_right,
            padding_bottom,
            padding_top,
        ) = self._get_layout()
        width = plot_width + padding_left + padding_right
        height = plot_height + padding_top + padding_bottom
        fig_width, fig_height = self.fig.get_size_inches()
        width_ratio = fig_width / width
        height_ratio = fig_height / height

        patch_width1 = 1
        patch_height1 = 1
        patch_width2 = -1
        patch_height2 = -1
        # This was previously calculated from Axes.get_position() but this does not work properly for Axes3D instances
        # Therefore, calculate this completely from the aspect ratio of the plot and the figure size, as well as the padding
        aspect_ratio = plot_height / plot_width

        if width_ratio <= height_ratio:
            # The divider scales the complete cell independently in each direction. The
            # box-aspect axes are then centered in that cell, so asymmetric padding
            # shifts the visible area away from the center of the figure.
            height_from_aspect = (
                fig_width - width_ratio * (padding_left + padding_right)
            ) * aspect_ratio + width_ratio * (padding_bottom + padding_top)
            delta_height = fig_height - height_from_aspect
            lower_excess = (
                (height_ratio - width_ratio)
                * (padding_bottom + plot_height / 2)
            )
            upper_excess = delta_height - lower_excess
            patch_height1 = lower_excess / fig_height
            patch_height2 = -upper_excess / fig_height

        else:
            # Same calculation when the height is the limiting factor.
            width_from_aspect = (
                fig_height - height_ratio * (padding_bottom + padding_top)
            ) / aspect_ratio + height_ratio * (padding_left + padding_right)
            delta_width = fig_width - width_from_aspect
            left_excess = (
                (width_ratio - height_ratio)
                * (padding_left + plot_width / 2)
            )
            right_excess = delta_width - left_excess
            patch_width1 = left_excess / fig_width
            patch_width2 = -right_excess / fig_width

        if self.figure_boundary_artist1 is None or self.figure_boundary_artist1.get_figure() is not self.fig:
            color = self.master.background_color if self.master._dark else "lightgray"
            # Create the first rectangle to cover the area outside of the plot area. This one is either on the bottom or left-hand side
            self.figure_boundary_artist1 = mpl.patches.Rectangle(
                xy=(0, 0),
                width=patch_width1,
                height=patch_height1,
                transform=self.fig.transFigure,
                fill=True,
                facecolor=color,
                linestyle="None",
                clip_on=False,
                zorder=1000,
            )
            self.fig.add_artist(self.figure_boundary_artist1)

        else:
            self.figure_boundary_artist1.set_width(patch_width1)
            self.figure_boundary_artist1.set_height(patch_height1)

        if self.figure_boundary_artist2 is None or self.figure_boundary_artist2.get_figure() is not self.fig:
            color = self.master.background_color if self.master._dark else "lightgray"
            # Create the second rectangle to cover the area outside of the plot area. Tihs one is either on the top or right-hand side
            self.figure_boundary_artist2 = mpl.patches.Rectangle(
                xy=(1, 1),
                width=patch_width2,
                height=patch_height2,
                transform=self.fig.transFigure,
                fill=True,
                facecolor=color,
                linestyle="None",
                clip_on=False,
                zorder=1000,
            )
            self.fig.add_artist(self.figure_boundary_artist2)

        else:
            self.figure_boundary_artist2.set_width(patch_width2)
            self.figure_boundary_artist2.set_height(patch_height2)

        self.fig.draw_artist(self.figure_boundary_artist1)
        self.fig.draw_artist(self.figure_boundary_artist2)
        
    def plot(self, plot_data):

        # Delete polygons
        try:
            for p in self.polygons:
                p.remove()
        except Exception as e:
            if DEBUG: print("Error removing polygon:", e)

        self.polygons = []

        self.plot_data = plot_data

        # Set Toolbar Mode to none
        self.toolbar.mode = _Mode.NONE

        # Deactivate Selectors at first
        self.PeakSelector.set_active(False)
        self.IntegrateSelector.set_active(False)
        
        # Clear ax and delete old artist
        self.ax.clear()

        self.master.set_blank(skip_save=True)

        # create list to keep track of annotations
        self.annotations = []
        self.iannotations = []  

        # Delete current inset if plotted
        if self.insetplotted:
            # Deactivate RectangleSelector
            self.InsetPeakSelector.disconnect_events()
            # Close Inset Plot
            plt.delaxes(ax=self.ax.inset)
            # Disable all Entries
            if self.master.plottype == "MALDI":
                self.master.xlim_min_inset_entry.state(["disabled"])
                self.master.xlim_max_inset_entry.state(["disabled"])
                self.master.y_height_inset_entry.state(["disabled"])
                self.master.ask_mirror.state(["disabled"])
                self.master.ask_inset_pos.state(["disabled"])
                self.master.inset_vlabel_checkbox.state(["disabled"])
            # Update Variables
            self.insetplotted = False

        ## Initiate all dictionaries and keys for current plot
        
        # Get overall maximum y value, make sure that it is not zero to avoid issues with normalization
        self.max_y_val = np.max([self.plot_data["ypoints"].max(), 10**-20])

        # Setup for blitting
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)

        self.toolbar.update()

        # Check which button should be selected
        self.toolbar._update_buttons_checked()

        # Deactive Buttons that should not be activated
        self.toolbar.check_whether_active()

        # Reactivate all widgets
        self._set_widgets_state([self.master.baseline_entry,
                                self.master.set_blank_btn], disabled=False)

        # Keep one scrolling callback on the long-lived GUI canvas.
        try:
            if self.mousewheel_event is not None:
                self.canvas.mpl_disconnect(self.mousewheel_event)
        except (AttributeError, ValueError):
            pass
        self.mousewheel_event = self.canvas.mpl_connect("scroll_event", self.on_mousewheel)
        
        if not hasattr(self, "resize_event"):
            self.resize_event = self.canvas.mpl_connect("resize_event", self.on_resize)
        if getattr(self.master, "_startup_complete", False):
            self.refresh()
    
    def on_resize(self, event):

        if (not getattr(self.master, "_startup_complete", False)
            or getattr(self.master, "_loading", False)):
            return

        if self.pick_text:
            if getattr(self.pick_text, "free_text_editor", False):
                self.finish_text_edit()
            else:
                self.pick_on_focus_out()
        
        # Cancel previous request if called again
        if self._refresh:
            self.master.after_cancel(self._refresh)

        # Schedule a new resize without saving to the database and without refreshing treeviews
        self._refresh = self.master.after_idle(lambda: self.master.refresh(resize=True, refreshTree=False))

    def multiplot(self, multiplot_data):

        self.multiplot_data = multiplot_data

        if not hasattr(self, "resize_event"):
            self.resize_event = self.canvas.mpl_connect("resize_event", self.on_resize)

        # Empty buffer
        self.polygons = []
        self.multiplot_lines = {}
        self.multiplot_labels = {}
        self.legend = None
        self.annotations = []
        self.iannotations = []
        self.simulation = []
        self.isimulation = []

        # Delete current inset if plotted
        if self.insetplotted:
            # Deactivate RectangleSelector
            self.InsetPeakSelector.disconnect_events()
            # Close Inset Plot
            plt.delaxes(ax=self.ax.inset)
            # Update Variables
            self.insetplotted = False
        
        # Unbind events bound for regular plots
        try:
            self.canvas.mpl_disconnect(self.mousewheel_event)
        except (AttributeError, ValueError):
            pass
        self.mousewheel_event = None
        
        # Set Toolbar Mode to none
        self.toolbar.mode = _Mode.NONE

        # Deactivate Selectors
        self.PeakSelector.set_active(False)
        self.IntegrateSelector.set_active(False)

        # Clear ax and delete old artists
        self.ax.clear()

        self.multiplot_height = 0
        # Setup for blitting
        self.background = self.canvas.copy_from_bbox(self.fig.bbox)

        self.toolbar.update()

        # Check which button should be selected
        self.toolbar._update_buttons_checked()

        # Deactive Buttons that should not be activated
        self.toolbar.check_whether_active()

        # Deactivate all widgets that are not applicable for MultiPlots
        self._set_widgets_state([self.master.baseline_entry,
                                 self.master.set_blank_btn], disabled=True)

        if getattr(self.master, "_startup_complete", False):
            self.refresh()

    def show_assay_file_fit(self, iid, data):

        if "fit_slope" not in self.multiplot_data[iid] or "fit_intercept" not in self.multiplot_data[iid]:
            print(f"No fit data available for file: {self.multiplot_data[iid]['filename']}")
            return

        # First get all important fit data
        slope = self.multiplot_data[iid]["fit_slope"]
        intercept = self.multiplot_data[iid]["fit_intercept"]

        xmin, xmax = data["xpoints"].min(), data["xpoints"].max()
        xrange = xmax - xmin
        # Elongate the minimum and maximum a bit to make it aesthetically more pleasing
        xmin -= 0.05 * xrange
        xmax += 0.05 * xrange
        x_fit = np.array([xmin, xmax])
        y_fit = slope * x_fit + intercept

        # Get the nonlinear fit data
        x_fit_polynomial = np.linspace(xmin, xmax, 100)
        poly_coeffs = self.multiplot_data[iid]["polynomial_coefficients"]
        non_linear_fit = np.polynomial.Polynomial(poly_coeffs)
        y_fit_polynomial = non_linear_fit(x_fit_polynomial)
        polynomial_degree = self.multiplot_data[iid]["polynomial_degree"]

        # Get the corrected baseline ypoints
        if iid not in self.corrected_ypoints:
            self.corrected_ypoints[iid] = self.master.correct_baseline(iid)

        corrected_ypoints = self.corrected_ypoints[iid]

        # Show the source data in a separate, non-blocking Matplotlib window.
        figure, axes = plt.subplots(num=f"Fit for file: {self.multiplot_data[iid]['filename']}", clear=True)
        axes.plot(data["xpoints"], corrected_ypoints, marker="o", linestyle="None", color="black", markersize=4)
        axes.plot(x_fit_polynomial, y_fit_polynomial, linestyle="--", color="#0072B2", linewidth=2)
        axes.plot(x_fit, y_fit, linestyle="-", color="#E69F00", linewidth=2)

        dummy = mpl.lines.Line2D([], [], linestyle="none")
        axes.legend([dummy, dummy, dummy, dummy, dummy],
                    [f"Slope = {slope:.3g}",
                     f"Intercept = {intercept:.3g}",
                     f"R² = {self.multiplot_data[iid]['fit_r_squared']:.4g}",
                     f"Polynomial degree = {polynomial_degree}",
                     f"Rel. nonlinearity = {self.multiplot_data[iid]['relative_data_curvature']:.2%}"],
                    loc="best",
                    markerscale=0,
                    handlelength=0,
                    handletextpad=0,)

        axes.set_xlabel("x")
        axes.set_ylabel("y")
        axes.set_xlim(xmin, xmax)
        axes.set_ylim(data["ypoints"].min(), data["ypoints"].max())
        axes.set_title(f"Fit for file: {self.multiplot_data[iid]['filename']}")
        axes.grid(True, alpha=0.3)
        figure.tight_layout()
        figure.show()
        

    ## Block for functions with specific and singular refresh purposes as called in Root
    ## These functions may also be included into the refresh methods for better code readability

    def update_assay_type(self):

        # Do a blit redraw
        self._blit_redraw()

    def update_assay_fit(self, skip_blit=False):

        self.multiplot_data["PlotOptions"]["show_assay_fit"] = self.master.show_assay_fit.get()

        try:
            self.fit.remove()
        except Exception as e:
            if DEBUG: print("Error removing old assay fit in update_assay_fit method:", e)

        try:
            self.Vmax_constant.remove()
        except Exception as e:
            if DEBUG: print("Error removing old Vmax constant in update_assay_fit method:", e)

        try:
            self.Km_rectangle.remove()
        except Exception as e:
            if DEBUG: print("Error removing old Km rectangle in update_assay_fit method:", e)

        if (self.multiplot_data["PlotOptions"]["show_assay_fit"] and 
            self.multiplot_data["PlotOptions"]["assay_type"] is not None and
            len(self.multiplot_data["PlotOptions"]["assay_fit"]) > 0):

            plotted_fit, fit, rectangle_artist, constant_artist, params_artist = self._plot_assay_fit_single(self.ax)

            if plotted_fit:
                self.fit = fit

            if constant_artist is not None:
                self.Vmax_constant = constant_artist

            if rectangle_artist is not None:
                self.Km_rectangle = rectangle_artist

            if params_artist is not None:
                self.fit_params = params_artist

        # Do a blit redraw
        if not skip_blit:
            self._blit_redraw()

    def update_assay_plot(self, skip_blit=False):

        plot_data = self.multiplot_data["PlotOptions"]

        if plot_data["assay_type"] is None:
            return

        # Small helper function to check whether all keys are inside of the datapoint
        def is_there(dict, keys):
            for key in keys:
                if key not in dict:
                    return False
            return True

        xpoints = [0] + [plot_data["assay_datapoints"][datapoint]["x"] for datapoint in plot_data["assay_datapoints"] if is_there(plot_data["assay_datapoints"][datapoint], ["x", "y", "error"])]
        ypoints = [0] + [plot_data["assay_datapoints"][datapoint]["y"] for datapoint in plot_data["assay_datapoints"] if is_there(plot_data["assay_datapoints"][datapoint], ["x", "y", "error"])]
        y_err = [0] + [plot_data["assay_datapoints"][datapoint]["error"] for datapoint in plot_data["assay_datapoints"] if is_there(plot_data["assay_datapoints"][datapoint], ["x", "y", "error"])]
        sigma = [0] + [plot_data["assay_datapoints"][datapoint]["error"] / np.sqrt(len(plot_data["assay_datapoints"][datapoint]["plots"])) for datapoint in plot_data["assay_datapoints"] if is_there(plot_data["assay_datapoints"][datapoint], ["x", "y", "error"])]

        xpoints = np.array(xpoints)
        ypoints = np.array(ypoints)
        y_err = np.array(y_err)
        sigma = np.array(sigma)

        plot_data["xpoints"] = xpoints
        plot_data["ypoints"] = ypoints
        plot_data["y_err"] = y_err
        plot_data["sigma"] = sigma

        line = self.ax.errorbar(xpoints,
                                ypoints,
                                yerr=y_err,
                                fmt="o",
                                linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), self.ax),
                                markersize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"])*2, self.ax),
                                elinewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"])/2, self.ax),
                                capsize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), self.ax),
                                ecolor="black",
                                color=plot_data["color"]
                            )

        # Remove the old line to avoid ghost lines
        try:
            self.line.remove()
        except Exception as e:
            if DEBUG: print("Error removing old line in update_assay_plot method:", e)
        
        # Save the line as new line
        self.line = line

        # Adjust y axis if necessary, blit redraw will be triggered there
        self.autoadjust_y(skip_blit=skip_blit)

    def update_assay_fit_linewidth(self):

        self.multiplot_data["PlotOptions"]["assay_fit_linewidth"] = float(self.master.assay_fit_linewidth.get())

        try:
            self.fit.set_linewidth(self.scale_artist_size(self.multiplot_data["PlotOptions"]["assay_fit_linewidth"], self.ax))
        except Exception as e:
            if DEBUG: print("Error updating assay fit linewidth:", e)

        try:
            self.Km_rectangle.set_linewidth(self.scale_artist_size(self.multiplot_data["PlotOptions"]["assay_fit_linewidth"]/2, self.ax))
        except Exception as e:
            if DEBUG: print("Error updating Km rectangle linewidth:", e)

        try:
            self.Vmax_constant.set_linewidth(self.scale_artist_size(self.multiplot_data["PlotOptions"]["assay_fit_linewidth"]/2, self.ax))
        except Exception as e:
            if DEBUG: print("Error updating Vmax constant linewidth:", e)

        # Do a blit redraw
        self._blit_redraw()

    def update_assay_fit_linestyle(self):

        plot_data = self.multiplot_data["PlotOptions"]

        changed_linestyle, linestyle = self.check_and_set_linestyle(self.master.assay_fit_linestyle.get(), self.fit)

        if changed_linestyle:
            # If the linestyle was successfully set, update the plot data
            plot_data["assay_fit_linestyle"] = linestyle
            self._blit_redraw()

            return True
        else:
            # If the linestyle could not be set, reset the entry to the previous value
            self.master.assay_fit_linestyle.set(str(plot_data["assay_fit_linestyle"]))

            return False

    def update_assay_fit_color(self):

        self.multiplot_data["PlotOptions"]["assay_fit_color"] = self.master.assay_fit_color

        try:
            self.fit.set_color(self.master.assay_fit_color)
        except Exception as e:
            if DEBUG: print("Error updating assay fit color:", e)

        # Do a blit redraw
        self._blit_redraw()

    def update_vmax_constant(self, *args):

        self.multiplot_data["PlotOptions"]["show_vmax"] = self.master.assay_show_vmax.get()

        try:
            self.Vmax_constant.remove()
        except Exception as e:
            if DEBUG: print("Error removing old Vmax constant in update_vmax_constant method:", e)

        artist = self._plot_assay_vmax_constant_single(self.ax)

        if artist is not None:
            self.Vmax_constant = artist

        self._blit_redraw()

    def update_Km_rectangle(self, *args):

        self.multiplot_data["PlotOptions"]["show_Km"] = self.master.assay_show_Km.get()

        try:
            self.Km_rectangle.remove()
        except Exception as e:
            if DEBUG: print("Error removing old Km rectangle in update_Km_rectangle method:", e)

        artist = self._plot_assay_Km_rectangle_single(self.ax)

        if artist is not None:
            self.Km_rectangle = artist

        self._blit_redraw()

    def update_fit_params_visibility(self, *args):

        self.multiplot_data["PlotOptions"]["show_fit_data"] = self.master.assay_show_fit_data.get()

        try:
            self.fit_params.remove()
        except Exception as e:
            if DEBUG: print("Error removing old fit params in update_fit_params_visibility method:", e)

        artist = self._plot_assay_fit_params_single(self.ax)

        if artist is not None:
            self.fit_params = artist

        self._blit_redraw()

    def update_xlim(self):
        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        else:
            plot_data = self.multiplot_data["PlotOptions"]

        # Update saved data for xlims
        plot_data["x_axis_max"] = self.master.xlim_max.get()
        plot_data["x_axis_min"] = self.master.xlim_min.get()
    
        # Update xlims
        self.ax.set_xlim(right=plot_data["x_axis_max"],
                        left=plot_data["x_axis_min"])

        self.ax.xaxis.set_major_locator(mpl.ticker.AutoLocator())
        major_locator = self.ax.xaxis.get_major_locator()
        tick_values = major_locator()

        offset = tick_values[0]
        if len(tick_values) >= 2:
            distance = abs(tick_values[1] - tick_values[0])
        else:
            distance = abs(plot_data["y_axis_max"] - plot_data["y_axis_min"])

        plot_data["distance_xticks"] = distance
        self.master.distance_xticks.set(distance)

        offset_distance_ratio = abs(offset)/distance
        if offset_distance_ratio.is_integer():
            offset = 0
        else:
            fraction = offset_distance_ratio % 1
            offset = fraction*distance
            
        plot_data["offset_xticks"] = offset
        self.master.offset_xticks.set(offset)

        if self.master.plottype == "MultiPlot":
            self.recompute_multiplot_maxima()
            self.autoadjust_y(skip_blit=True)
            self.update_multiplot_positions()
            self._blit_redraw()

        elif self.master.plottype == "Assay":
            self._blit_redraw()

        else:
            # Check whether y_values need to be adjusted, blitting is done in autoadjust_y
            self.autoadjust_y()

    
    def update_ylim(self, skip_blit=False):

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        else:
            plot_data = self.multiplot_data["PlotOptions"]

        # Update saved data for ylims
        plot_data["y_axis_max"] = self.master.ylim_max.get()
        plot_data["y_axis_min"] = self.master.ylim_min.get()
        plot_data["autoadjust_y"] = self.master.adjust_y.get()
        
        # Update ylims
        if self.master.plottype == "MultiPlot" and plot_data["3D"]:
            self.ax.set_zlim(bottom = plot_data["y_axis_min"], 
                          top = plot_data["y_axis_max"])

            axis = self.ax.zaxis
        else:

            self.ax.set_ylim(top=plot_data["y_axis_max"],
                            bottom=plot_data["y_axis_min"])
            axis = self.ax.yaxis

        axis.set_major_locator(mpl.ticker.AutoLocator())
        major_locator = axis.get_major_locator()
        tick_values = major_locator()

        offset = tick_values[0]
        if len(tick_values) >= 2:
            distance = abs(tick_values[1] - tick_values[0])
        else:
            distance = abs(plot_data["y_axis_max"] - plot_data["y_axis_min"])

        plot_data["distance_yticks"] = distance
        self.master.distance_yticks.set(distance)

        offset_distance_ratio = abs(offset)/distance
        if offset_distance_ratio.is_integer():
            offset = 0
        else:
            fraction = offset_distance_ratio % 1
            offset = fraction*distance

        plot_data["offset_yticks"] = offset
        self.master.offset_yticks.set(offset)

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            self.update_multiplot_positions()

        # Only do a blit redraw
        if not skip_blit:
            self._blit_redraw(self.ax)

    def autoadjust_y(self, axes=None, skip_blit=False):
        
        if not axes:
            axes = self.ax
            
        changed = False

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        else:
            plot_data = self.multiplot_data["PlotOptions"]

        # Update saved data for autoadjust_y
        plot_data["autoadjust_y"] = self.master.adjust_y.get()
        
        if self.master.plottype != "MultiPlot":

            # ylim update logic initially in refresh
            if self.master.plottype == "Tm" and plot_data["Tm_method"] in ["VHD","EGD"]:
                # For these methods, corrected_y_points is not used for the plot, but the derivative of the original y_points,
                # so we need to check whether the y_axis_max and y_axis_min are within the range of the derivative of the 
                # original y_points
                corrected_ypoints = np.gradient(self.corrected_ypoints[self.master.iid],
                                                plot_data["xpoints"])
                xpoints = plot_data["xpoints"]
            elif self.master.plottype != "Assay":
                corrected_ypoints = self.corrected_ypoints[self.master.iid]
                xpoints = plot_data["xpoints"]
            else:
                corrected_ypoints = plot_data["ypoints"] if plot_data["ypoints"].size > 2 else np.array([0, 1])
                xpoints = plot_data["xpoints"] if plot_data["xpoints"].size > 2 else np.array([0, 1])
                y_err = plot_data["y_err"] if plot_data["y_err"].size > 2 else np.array([0, 0])

            # Update y_axis_max_percent based on y_axis_max and update max_y_val based on the current corrected ypoints
            self.max_y_val = np.max([corrected_ypoints.max(), 10**-20])
            plot_data["y_axis_max_percent"] = float(plot_data["y_axis_max"]*100/self.max_y_val)

            if plot_data["autoadjust_y"]:
                # Get lower y-limit of the plot in the visible area
                xmin_vis, xmax_vis = find_indexes(plot_data["x_axis_min"],plot_data["x_axis_max"],xpoints)

                try:
                    
                    if self.master.plottype == "Assay":
                        bottom_ylim_array = corrected_ypoints[xmin_vis:xmax_vis] - y_err[xmin_vis:xmax_vis]
                        bottom_ylim = bottom_ylim_array.min()

                    else:
                        bottom_ylim = corrected_ypoints[xmin_vis:xmax_vis].min()
                    
                except ValueError:
                    bottom_ylim = 0
                
                # Calculate one magnitude for all values
                
                if self.master.plottype == "Assay":
                    top_ylim_array = corrected_ypoints[xmin_vis:xmax_vis] + y_err[xmin_vis:xmax_vis]
                    top_ylim = top_ylim_array.max()

                else:
                    top_ylim = corrected_ypoints[xmin_vis:xmax_vis].max()

                if bottom_ylim == top_ylim:
                    bottom_ylim -= 0.5
                    top_ylim += 0.5

                magnitude = np.floor(np.log10(abs(top_ylim-bottom_ylim))) if top_ylim-bottom_ylim != 0 else 0

                # Round the ylim values to a reasonable number of decimal places based on the magnitude of the values
                # This is to make the plot look cleaner
                if self.master.plottype in ["CD", "Tm", "Assay"]:
                    top_ylim = np.ceil(top_ylim * 10**(-magnitude)) / 10**(-magnitude)
                    bottom_ylim = np.floor(bottom_ylim * 10**(-magnitude)) / 10**(-magnitude)
                
                else:
                    top_ylim = plot_data["y_axis_max_percent"]/100*self.max_y_val

                if self.master.plottype in ["Fluorescence", "UV/vis"]:
                    bottom_ylim = min(0, bottom_ylim)
                
                # Save new limits if there are any changes
                if bottom_ylim != plot_data["y_axis_min"]:
                    self.master.ylim_min.set(bottom_ylim)
                    plot_data["y_axis_min"] = float(bottom_ylim)
                    changed = True

            else:
                bottom_ylim = plot_data["y_axis_min"]
                if self.master.plottype in ["CD", "Tm", "Assay"]:
                    top_ylim = plot_data["y_axis_max"]
                else:
                    top_ylim = plot_data["y_axis_max_percent"]/100*self.max_y_val

            # Save new limits if there are any changes
            if top_ylim != plot_data["y_axis_max"]:
                self.master.ylim_max.set(top_ylim)
                plot_data["y_axis_max"] = float(top_ylim)
                plot_data["y_axis_max_percent"] = float(plot_data["y_axis_max"]*100/self.max_y_val)
                changed = True
                
            # Check whether any of the ylim values are NaN or inf and if so reset them to default values
            if np.isnan(bottom_ylim) or np.isinf(bottom_ylim):
                bottom_ylim = 0
                self.master.ylim_min.set(bottom_ylim)
                plot_data["y_axis_min"] = float(bottom_ylim)
            if np.isnan(top_ylim) or np.isinf(top_ylim):
                top_ylim = self.max_y_val
                self.master.ylim_max.set(top_ylim)
                plot_data["y_axis_max"] = float(top_ylim)
                plot_data["y_axis_max_percent"] = float(plot_data["y_axis_max"]*100/self.max_y_val)

            axes.set_ylim(top=top_ylim,
                          bottom=bottom_ylim)
            
        else:

            # Update saved data for autoadjust_y for multiplots
            old_ylim = (self.master.ylim_min.get(), self.master.ylim_max.get())

            if plot_data["autoadjust_y"]:

                # Calculate the estimated height of the plot
                try:
                    self.multiplot_height = max(values["position"] for iid, values in self.multiplot_data.items() if iid != "PlotOptions" and "position" in values)
                except ValueError:
                    self.multiplot_height = 0
                if DEBUG: print(f"Highest plot: {self.multiplot_height}")

                # Calculate the correct height based on the highest multiplot position
                self.multiplot_height += 1
                if DEBUG: print(f"Added 1: {self.multiplot_height}")
                self.multiplot_height *= 1.05
                if DEBUG: print(f"Multiplied: {self.multiplot_height}")

                if not plot_data["normalization"]:
                    # Calculate which of the multiplots are the plots with the highest and lowest y values in the visible region
                    self.multiplot_height *= plot_data["global_max_y"]
                
                if plot_data["3D"]:
                    if not plot_data["normalization"]:

                        if plot_data["plottype"] in ["CD", "Tm"]:
                            axes.set_zlim(bottom = plot_data["global_min_y"]-(abs(plot_data["global_min_y"])*0.05),
                                            top = plot_data["global_max_y"]*1.05
                                        )
                        else:
                            axes.set_zlim(bottom = -0.05*plot_data["global_max_y"], 
                                            top = plot_data["global_max_y"]*1.05
                                        )
                    else:
                        axes.set_zlim(bottom = 0, top = 1.05)
                    axes.set_ylim(bottom = 0, 
                                    top = len(self.multiplot_data)-1)
                else:
                    if plot_data["plot_offset"]:
                        # Because of the transformation of the plots, the highest point must be adjusted according to the corrected multiplot_max_plot_height if the values are not normalized
                        if not plot_data["normalization"]:

                            self.multiplot_height /= plot_data["global_max_y"]
                            self.multiplot_height *= plot_data["global_max_y"] - plot_data["global_min_y"]
                            
                        axes.set_ylim(bottom = -self.multiplot_height*0.05,
                                        top = self.multiplot_height*1.05)
                    else:
                        if plot_data["normalization"]:
                            axes.set_ylim(bottom= -0.05, top=1.05)

                        else:
                            if plot_data["plottype"] in ["CD", "Tm"]:
                                axes.set_ylim(bottom = plot_data["global_min_y"]-(abs(plot_data["global_min_y"])*0.05),
                                                top = plot_data["global_max_y"]*1.05
                                            )
                            else:
                                axes.set_ylim(bottom = -0.05*plot_data["global_max_y"], 
                                                top = plot_data["global_max_y"]*1.05
                                            )

                if plot_data["3D"]:
                    ylim = axes.get_zlim()
                else:
                    ylim = axes.get_ylim()

                self.master.ylim_min.set(ylim[0])
                self.master.ylim_max.set(ylim[1])
                plot_data["y_axis_min"] = ylim[0]
                plot_data["y_axis_max"] = ylim[1]

            else:
                if plot_data["3D"]:
                    axes.set_zlim(bottom = plot_data["y_axis_min"], 
                                    top = plot_data["y_axis_max"])

                    axes.set_ylim(bottom = 0, 
                                  top = len(self.multiplot_data)-1)

                else:
                    axes.set_ylim(plot_data["y_axis_min"],
                                  plot_data["y_axis_max"])

            new_ylim = axes.get_ylim() if not plot_data["3D"] else axes.get_zlim()

            if old_ylim != new_ylim:
                changed = True
            else:
                changed = False

        # Also now, in case yticks are visible, update major Ticks, to nicely fit the new bounds
        # Only do this, if ylims were changed due to autoadjust_y
        if changed and plot_data["autoadjust_y"] and plot_data["show_yticks"]:

            if self.master.plottype == "MultiPlot" and plot_data["3D"]:
                axis = axes.zaxis
            else:
                axis = axes.yaxis

            axis.set_major_locator(mpl.ticker.AutoLocator())
            major_locator = axis.get_major_locator()
            tick_values = major_locator()

            offset = tick_values[0]
            if len(tick_values) >= 2:
                distance = abs(tick_values[1] - tick_values[0])
            else:
                distance = abs(plot_data["y_axis_max"] - plot_data["y_axis_min"])
                
            plot_data["distance_yticks"] = distance
            self.master.distance_yticks.set(distance)

            offset_distance_ratio = abs(offset)/distance
            if offset_distance_ratio.is_integer():
                offset = 0
            else:
                fraction = offset_distance_ratio % 1
                offset = fraction*distance
            plot_data["offset_yticks"] = offset
            self.master.offset_yticks.set(offset)

        if not skip_blit:
            self._blit_redraw(axes)

    def update_background_correction(self):

        # Baseline correction is only applicable for single plots, not for multiplots
        if self.master.plottype in ["MultiPlot", "Assay"]:
            return

        # First it should be enough to just update self.line

        if self.master.plottype == "Tm" and self.plot_data["Tm_method"] in ["EGD","VHD"]:
            ypoints = np.gradient(self.corrected_ypoints[self.master.iid], self.plot_data["xpoints"])
        else:
            ypoints = self.corrected_ypoints[self.master.iid]

        if hasattr(self, "line") and self.line is not None:
            # Update the line data with the new baseline-corrected ypoints
            self.line.set_ydata(ypoints)

        if self.insetplotted and hasattr(self, "inset_line") and self.inset_line is not None:
            self.inset_line.set_ydata(ypoints)

        # Now update properties that also change with the exact shape of the curve
        if self.master.plottype == "HPLC":
            self.refresh_integration(skip_blit=True)

        # Update the annotations
        self.refresh_annotations(axes=self.ax)

    
        # Adjust the yaxis again
        #self.autoadjust_y()
        self._blit_redraw()

    def update_axis_labels(self, axes=None):

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        else:
            plot_data = self.multiplot_data["PlotOptions"]

        if not axes:
            axes = self.ax

        font = self.master.plotoptions_data[self.master.plottype]["font"]
        fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=axes)

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            labelpad = self.scale_3D_padding(mpl.rcParams["axes.labelpad"], axes)
        else:
            labelpad = self.scale_artist_size(mpl.rcParams["axes.labelpad"], axes)
    
        if self.master.plottype != "MultiPlot":

            if self.master.plottype == "Assay":
                # Update the database
                plot_data["assay_x_label"] = self.master.x_axis_label.get()
                plot_data["assay_y_label"] = self.master.y_axis_label.get()

                if plot_data["assay_type"] is not None:
                    ylabel = plot_data["assay_y_label"]
                    xlabel = plot_data["assay_x_label"]
                    xlabel = xlabel.replace("VAR_x_unit", str(plot_data["assay_x_unit"]))
                    ylabel = ylabel.replace("VAR_y_unit", str(plot_data["assay_y_unit"]))
                else:
                    ylabel = plot_data["assay_y_label"]
                    xlabel = plot_data["assay_x_label"]

            elif self.master.plottype == "Kinetics":
                plot_data["xlabel"] = self.master.kinetics_x_label.get()
                plot_data["ylabel"] = self.master.kinetics_y_label.get()
                xlabel = plot_data["xlabel"]
                ylabel = plot_data["ylabel"]

            else:
                xlabel = self.master.plotoptions_data[self.master.plottype]["xlabel"]
                if self.master.plottype in ["CD", "Tm"] and self.plot_data["calc_MRE"]:
                    ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_MRE"]

                else:
                    # Change Font_Size and set Label
                    ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel"]

            if self.master.plottype == "Tm":

                if self.plot_data["Tm_method"] in ["VHD","EGD"]:

                    if self.plot_data["calc_MRE"]:
                        ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_MRE_derivative"]
                    else:
                        ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_derivative"]
                
                if "{VAR\\_wavelength}" in ylabel:
                    ylabel = ylabel.replace("{VAR\\_wavelength}","{"+str(self.plot_data["wavelength"])+" \\/nm}")

            axes.set_ylabel(ylabel, fontsize=fontsize, font=font, labelpad=labelpad)
            axes.set_xlabel(xlabel, fontsize=fontsize, font=font, labelpad=labelpad)

        else:
            
            # Edit ylabel properly in case of Tm
            ylabel = self.master.plotoptions_data[self.multiplot_data["PlotOptions"]["plottype"]]["ylabel"] if self.multiplot_data["PlotOptions"]["plottype"] != "" else ""

            if self.multiplot_data["PlotOptions"]["plottype"] in ["CD", "Tm"]:
                if self.multiplot_data["PlotOptions"]["calc_MRE"]:
                    ylabel = self.master.plotoptions_data[self.multiplot_data["PlotOptions"]["plottype"]]["ylabel_MRE"]
            if self.multiplot_data["PlotOptions"]["plottype"] == "Tm":

                if self.multiplot_data["PlotOptions"]["Tm_method"] in ["VHD","EGD"]:
                    if self.multiplot_data["PlotOptions"]["calc_MRE"]:
                        ylabel = self.master.plotoptions_data[self.multiplot_data["PlotOptions"]["plottype"]]["ylabel_MRE_derivative"]
                    else:
                        ylabel = self.master.plotoptions_data[self.multiplot_data["PlotOptions"]["plottype"]]["ylabel_derivative"]
                
                if "{VAR\\_wavelength}" in ylabel:
                    # First check whether the wavelength is equal for all loaded plots
                    current_wavelength = None
                    equal_wavelengths = True
                    for iid in self.multiplot_data:
                        if iid != "PlotOptions":
                            plot_data = self.master.get_plot_data(iid)
                            if current_wavelength is None:
                                current_wavelength = plot_data["wavelength"]
                            elif plot_data["wavelength"] != current_wavelength:
                                equal_wavelengths = False
                                ylabel = ylabel.replace("_{VAR\\_wavelength}","")
                                break

                    if equal_wavelengths:
                        self.multiplot_data["PlotOptions"]["wavelength"] = current_wavelength            
                        ylabel = ylabel.replace("{VAR\\_wavelength}","{"+str(self.multiplot_data["PlotOptions"]["wavelength"])+" \\/nm}")
            
            if self.multiplot_data["PlotOptions"]["plottype"] != "":
                if self.multiplot_data["PlotOptions"]["plottype"] != "Assay" and self.multiplot_data["PlotOptions"]["3D"]:
                    axes.zaxis._axinfo["juggled"] = (1, 2, 0)
                    axes.set_zlabel(ylabel, fontsize=fontsize, font=font, labelpad=labelpad)
                else:
                    axes.set_ylabel(ylabel, fontsize=fontsize, font=font, labelpad=labelpad)
                axes.set_xlabel(self.master.plotoptions_data[self.multiplot_data["PlotOptions"]["plottype"]]["xlabel"], fontsize=fontsize, font=font, labelpad=labelpad)

    def update_linestyle(self):

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        elif self.master.plottype == "Assay":
            plot_data = self.multiplot_data["PlotOptions"]

        changed_linestyle, linestyle = self.check_and_set_linestyle(self.master.linestyle.get(), self.line)

        if changed_linestyle:
            # If the linestyle was successfully set, update the plot data
            plot_data["linestyle"] = linestyle
            if self.insetplotted:
                self.inset_line.set_linestyle(plot_data["linestyle"])
                        
            self._blit_redraw()

            return True
        else:
            # If the linestyle could not be set, reset the entry to the previous value
            self.master.linestyle.set(str(plot_data["linestyle"]))

            return False

    def check_and_set_linestyle(self, linestyle, artist):
        # Check whether linestyle is actually a tuple written as string
        str = linestyle

        try:
            tup = ast.literal_eval(str)
            # Check whether tup is actually a tuple and written the way which is necessary for matplotlib
            if isinstance(tup, tuple) and len(tup) == 2 and isinstance(tup[1], tuple) and int(len(tup[1])/2) == len(tup[1])/2:
                linestyle = tup
            else:
                linestyle = str
        except:
            linestyle = str

        try:
            artist.set_linestyle(linestyle)
            changed_linestyle = True
        except Exception as e:
            if DEBUG: print(f"Error setting linestyle {linestyle} for artist {artist}: {e}")
            changed_linestyle = False

        return changed_linestyle, linestyle

    def update_color(self):

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        elif self.master.plottype == "Assay":
            plot_data = self.multiplot_data["PlotOptions"]

        # Get current line_color
        plot_data["color"] = self.master.color
        if self.master.plottype == "Assay":
            markers, _, _ = self.line
            markers.set_color(plot_data["color"])
        else:
            self.line.set_color(plot_data["color"])
        if self.insetplotted:
            self.inset_line.set_color(plot_data["color"])
        self._blit_redraw()

    def update_ticks(self):

        # Check whether values are correct and will not return any errors
        if self.master.show_xticks.get():

            if self.master.distance_xticks.get() < 0:
                self.master.distance_xticks.set(1)
                
            if self.master.num_minor_xticks.get() < 0:
                self.master.num_minor_xticks.set(0)

        if self.master.show_yticks.get():

            if self.master.distance_yticks.get() < 0:
                self.master.distance_yticks.set(1)
                
            if self.master.num_minor_yticks.get() < 0:
                self.master.num_minor_yticks.set(0)

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_data = self.plot_data
        else:
            plot_data = self.multiplot_data["PlotOptions"]

        # Update saved data for ticks
        if self.master.show_xticks.get():
            plot_data["distance_xticks"] = self.master.distance_xticks.get()
            plot_data["offset_xticks"] = self.master.offset_xticks.get()
            plot_data["num_minor_xticks"] = self.master.num_minor_xticks.get()
        if self.master.show_yticks.get():
            plot_data["distance_yticks"] = self.master.distance_yticks.get()
            plot_data["offset_yticks"] = self.master.offset_yticks.get()
            plot_data["num_minor_yticks"] = self.master.num_minor_yticks.get()

        # Update ticks
        if self.master.show_xticks.get():
            x_axis_major_locator = mpl.ticker.MultipleLocator(base=plot_data["distance_xticks"],
                                                            offset=plot_data["offset_xticks"])
            self.ax.xaxis.set_major_locator(x_axis_major_locator)
            self.ax.xaxis.set_minor_locator(mpl.ticker.AutoMinorLocator(plot_data["num_minor_xticks"]+1))

        if self.master.show_yticks.get():
            y_axis_major_locator = mpl.ticker.MultipleLocator(base=plot_data["distance_yticks"],
                                                            offset=plot_data["offset_yticks"])

            if self.master.plottype == "MultiPlot" and plot_data["3D"]:
                axis = self.ax.zaxis
            else:
                axis = self.ax.yaxis

            axis.set_major_locator(y_axis_major_locator)
            axis.set_minor_locator(mpl.ticker.AutoMinorLocator(plot_data["num_minor_yticks"]+1))

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    # switch between horizontal and vertical peak labels
    def update_labels(self):
        # Update saved data for vlabels
        self.plot_data["label_orientation"] = self.master.vlabels.get()

        # Rotate all annotations according to the new label orientation
        for ann in self.annotations:
            ann.set_rotation(self.plot_data["label_orientation"])

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    ## Inset specific settings
    # Update the inset axes, in case size, position, fontsize, borderpad or existence changes
    def update_inset(self, updated_borderpad=False, updated_fontsize=False):
        self.plot_data["inset"] = self.master.inset.get()
        self._set_widgets_state(self.master.inset_widgets, disabled=not self.plot_data["inset"])
        self.plot_data["inset_xsize"] = self.master.xsize_inset.get()
        self.plot_data["inset_ysize"] = self.master.ysize_inset.get()
        self.plot_data["inset_fontsize"] = self.master.inset_fontsize.get()

        if updated_borderpad:

            borderpad = self.master.inset_borderpad.get()

            borderpad_eval = ast.literal_eval(borderpad)
            # Check whether borderpad is a tuple and written the way which is necessary for matplotlib or a float
            if isinstance(borderpad_eval, tuple) and len(borderpad_eval) == 2 and isinstance(borderpad_eval[0], (int, float)) and isinstance(borderpad_eval[1], (int, float)):
                borderpad = borderpad_eval
            elif isinstance(borderpad_eval, (int, float)):
                borderpad = float(borderpad_eval)
            else:
                raise ValueError("Invalid borderpad value. Must be a float or a tuple of two floats.")

            self.plot_data["inset_borderpad"] = borderpad

        if self.plot_data["inset_pos"] != self.master.inset_pos.get():
            self.plot_data["inset_pos"] = self.master.inset_pos.get()
            self.xpos_inset = self.plot_data["inset_pos"]
        
        # Do a full refresh, to reload the inset in case none is drawn and one should be drawn
        if not self.insetplotted and self.plot_data["inset"]:
            self.refresh(mirror=True)
        else:
            # Otherwise do quick blitting
            self._blit_redraw(self.ax, reset_inset = True, updated_fontsize=updated_fontsize)

    # Update the limits of the x-Axis of the inset
    def update_xlim_inset(self):
        self.plot_data["inset_x_axis_min"] = self.master.xlim_min_inset.get()
        self.plot_data["inset_x_axis_max"] = self.master.xlim_max_inset.get()
        # Update xlims
        self.ax.inset.set_xlim(right=self.plot_data["inset_x_axis_max"],
                               left=self.plot_data["inset_x_axis_min"])

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    # Update the limits of the y-Axis of the inset
    def update_ylim_inset(self):
        self.plot_data["inset_y_axis_max_percent"] = self.master.y_height_inset.get()

        # Update ylim
        self.ax.inset.set_ylim(top = self.plot_data["inset_y_axis_max_percent"]/100*self.max_y_val)

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    # Mirror annotations
    def mirror_annotations_to_inset(self):
        self.plot_data["mirror_annotations"] = self.master.mirror_annotations.get()

        if self.plot_data["mirror_annotations"]:
            self.plot_data["inset_peak_dict"] = {
                peak: self.plot_data["inset_peak_dict"].get(peak, self.plot_data["peak_dict"][peak]).copy()
                for peak in self.plot_data["peak_dict"]
            }

        # Create Annotations on Inset
        if self.insetplotted:

            self._migrate_annotation_positions(self.ax, self.plot_data["inset_peak_dict"], "inset_annotation_coordinate_system")

            self.create_annotations(axes = self.ax,
                                    inset = True,
                                    automatic_scripts = self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")
        else:
            for peak in self.iannotations:
                peak.remove()
            self.iannotations = []

        self._blit_redraw(self.ax)

    # switch between horizontal and vertical peak labels in an inset
    def update_inset_labels(self):
        # Update saved data for inset_vlabels
        self.plot_data["inset_label_orientation"] = self.master.inset_vlabels.get()

        # Rotate all inset annotations according to the new label orientation
        for ann in self.iannotations:
            ann.set_rotation(self.plot_data["inset_label_orientation"])

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    def update_simulation(self, axes=None):
        if axes is None:
            axes = self.ax

        # Update all drawn simulations and do a blit redraw
        # delete simulations
        if axes is self.ax:
            for sim in self.simulation + self.isimulation:
                sim.remove()
            self.simulation = []
            self.isimulation = []

        peak_dicts = [self.plot_data["peak_dict"], self.plot_data["inset_peak_dict"]]
        # Get all peaks from the save_data and check whether they should be simulated
        for peak_dict in peak_dicts:
            if peak_dict is self.plot_data["inset_peak_dict"]:
                if hasattr(axes, "inset"):
                    sim_axes = axes.inset
                else:
                    continue
            else:
                sim_axes = axes

            for values in peak_dict.values():
                if values[6] == "Yes":
                    
                    self.simulate_spectrum(chemical_formula=values[4], 
                                            axes=sim_axes, 
                                            intensity=values[7], 
                                            width=values[8], 
                                            charge=values[5])

        if axes is self.ax:
            self._blit_redraw(self.ax)

    ## CD and Tm specific settings

    def update_MRE_settings(self):
        if self.master.plottype in ["CD", "Tm"]:
            self.plot_data["calc_MRE"] = self.master.calc_MRE.get()
            # Update ylabel
            self.update_ylabel(skip_blit=True)
            # Update CD points
            self.update_CD_points()

        elif self.master.plottype == "MultiPlot":
            self.multiplot_data["PlotOptions"]["calc_MRE"] = self.master.calc_MRE.get()

            for iid in self.multiplot_data:
                if iid != "PlotOptions":
                    self.corrected_ypoints[iid] = self.master.correct_baseline(iid)

            self.multiplot_data["PlotOptions"]["autoadjust_y"] = True
            self.master.adjust_y.set(True)
            self.recompute_multiplot_maxima()
            self.update_axis_labels(axes=self.ax)
            
            self.autoadjust_y(skip_blit=True)
            self.update_multiplot_positions()
            self._blit_redraw()

    def update_CD_points(self, autoadjust_y=True):
        # Update saved data for pathlength, concentration, and number of residues
        self.plot_data["pathlength"] = self.master.pathlength.get()
        self.plot_data["concentration"] = self.master.concentration.get()
        self.plot_data["nbr_of_residues"] = self.master.nbr_of_residues.get()
        if autoadjust_y:
            self.plot_data["autoadjust_y"] = True
            self.master.adjust_y.set(True)
        self.corrected_ypoints[self.master.iid] = self.master.correct_baseline(self.master.iid)
    
        if self.master.plottype == "Tm" and self.plot_data["Tm_method"] in ["EGD","VHD"]:
            ypoints = np.gradient(self.corrected_ypoints[self.master.iid], self.plot_data["xpoints"])
        else:
            ypoints = self.corrected_ypoints[self.master.iid]
        # Refresh Plot
        if self.master.plottype == "Tm":
            line, = self.ax.plot(self.plot_data["xpoints"],
                                ypoints,
                                marker="o",
                                markersize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), self.ax),
                                linewidth=0,
                                color=self.plot_data["color"]
                                )
        else:
            line, = self.ax.plot(self.plot_data["xpoints"], self.corrected_ypoints[self.master.iid],
                                 linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), self.ax),
                                 linestyle=self.plot_data["linestyle"],
                                 color=self.plot_data["color"]
                                 )
            
        # Remove the old line to avoid ghost lines
        try:
            self.line.remove()
        except Exception as e:
            if DEBUG: print("Error removing old line in update_CD_points method:", e)
        
        # Save the line as new line
        self.line = line

        # Adjust y axis if necessary, blit redraw will be triggered there
        self.autoadjust_y()

    def update_ylabel(self, skip_blit=False):

        # Change Label
        ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel"]
        # This function will most likely only be called for Tm plots anyway
        if self.master.plottype in ["CD", "Tm"] and self.plot_data["calc_MRE"]:
            ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_MRE"]

        if self.master.plottype == "Tm":

            old_wavelength = self.plot_data["wavelength"]
            # Updating plot_data to reflect the current wavelength selection
            self.plot_data["wavelength"] = self.master.wavelength.get()
            # If wavelength is an integer, save it as an integer to avoid unnecessary decimal points in the label
            if self.plot_data["wavelength"].is_integer():
                self.plot_data["wavelength"] = int(self.plot_data["wavelength"])

            if self.plot_data["Tm_method"] in ["VHD","EGD"]:
                if self.plot_data["calc_MRE"]:
                    ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_MRE_derivative"]
                else:
                    ylabel = self.master.plotoptions_data[self.master.plottype]["ylabel_derivative"]
            
            if "{VAR\\_wavelength}" in ylabel:
                ylabel = ylabel.replace("{VAR\\_wavelength}","{"+str(self.plot_data["wavelength"])+" \\/nm}")

        font = self.master.plotoptions_data[self.master.plottype]["font"]
        fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=self.ax)
        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            labelpad = self.scale_3D_padding(mpl.rcParams["axes.labelpad"], self.ax)
        else:
            labelpad = self.scale_artist_size(mpl.rcParams["axes.labelpad"], self.ax)
        self.ax.set_ylabel(ylabel, fontsize=fontsize, font=font, labelpad=labelpad)

        # When the blank of the current Tm is a CD blank, the CD points also need to be adjusted to the new wavelength, so update the CD points as well
        if self.master.plottype == "Tm" and self.plot_data["baseline_iid"] and self.master.get_plottype(self.plot_data["baseline_iid"]) == "CD" and old_wavelength != self.plot_data["wavelength"]:
            print("Updating CD points due to wavelength change in Tm plot...")
            self.update_CD_points()

        elif not skip_blit:
            # Only do a blit redraw
            self._blit_redraw(self.ax)

    def update_fit(self, skip_blit=False):
        # Update saved data for show_fit
        self.plot_data["show_fit"] = self.master.show_fit.get()
        self.plot_data["show_tm_baselines"] = self.master.show_tm_baselines.get()

        # Remove the old fit, to avoid ghost lines
        try:
            self.fit.remove()
        except Exception as e:
            if DEBUG: print("Error removing old fit in update_fit method:", e)
        # Also remove the old baselines, to avoid ghost lines
        try:
            for baseline in self.tm_baselines:
                baseline.remove()
        except Exception as e:
            if DEBUG: print("Error removing old baseline in update_fit method:", e)

        # Refresh the fit if the option is enabled
        if self.plot_data["show_fit"] or self.plot_data["show_tm_baselines"]:
            # Plot a fit if available (centralized in helper)
            plotted_fit, fit, baselines = self._plot_tm_fit_single(self.ax)

            if plotted_fit:
                self.fit = fit

            if baselines:
                self.tm_baselines = baselines

        # Only do a blit redraw
        if not skip_blit:
            self._blit_redraw(self.ax)

    def toggle_zero_line(self):

        self.plot_data["show_zero_line"] = self.master.show_zero_line.get()

        try:
            self.zero_line.remove()
        except Exception as e:
            if DEBUG: print("Error removing zero line in toggle_zero_line method:", e)

        if self.plot_data["show_zero_line"]:
            self.zero_line = self.ax.axhline(y=0,
                                             color=self.plot_data["zero_line_color"],
                                             linewidth=self.scale_artist_size(self.plot_data["zero_line_linewidth"], self.ax),
                                             linestyle=self.plot_data["zero_line_linestyle"])
            
        self._blit_redraw()

    def update_zero_linestyle(self):

        changed_linestyle, linestyle = self.check_and_set_linestyle(self.master.zero_line_linestyle.get(), self.zero_line)

        if changed_linestyle:
            # If the linestyle was successfully set, update the plot data
            self.plot_data["zero_line_linestyle"] = linestyle
            self._blit_redraw()

            return True
        else:
            # If the linestyle could not be set, reset the entry to the previous value
            self.master.zero_line_linestyle.set(str(self.plot_data["zero_line_linestyle"]))

            return False

    def update_zero_linewidth(self):

        self.plot_data["zero_line_linewidth"] = self.master.zero_line_linewidth.get()

        
        self.zero_line.set_linewidth(self.scale_artist_size(self.plot_data["zero_line_linewidth"], self.ax))
        self._blit_redraw()

    def update_zero_color(self):

        self.plot_data["zero_line_color"] = self.master.zero_line_color

        self.zero_line.set_color(self.plot_data["zero_line_color"])
        self._blit_redraw()

    ## HPLC specific settings
    # toggle integral visibility
    def toggle_integrals(self):
        # Updating saved data for plot_integrals (whether to show polygons or not)
        self.plot_data["plot_integrals"] = self.master.integrated_area.get()

        # Only do a blit redraw
        self._blit_redraw(self.ax)

    def toggle_HPLC_baseline(self, visible=False, skip_blit=False):

        if self.HPLC_baseline:
            try:
                self.HPLC_baseline.remove()
            except Exception as e:
                if DEBUG: print(f"Error removing baseline in toggle_HPLC_baseline: {e}")
            finally:
                self.HPLC_baseline = None

        for axle in self.manual_HPLC_baseline_axles:
            axle.remove()

        self.manual_HPLC_baseline_axles = []

        if visible:

            xpoints = np.array([self.plot_data["xpoints"].min(), self.plot_data["xpoints"].max()])
            # Let the drawn baseline depend on the integration mode
            if self.plot_data["integration_type"] == "linear":

                corrected_ypoints = self.corrected_ypoints[self.master.iid]
                ### Integration is done by assuming a constant baseline from the values entered in the entries
                # Calculate the baseline
                xmin_ind_baseline, xmax_ind_baseline = find_indexes(self.plot_data["integration_info"][self.plot_data["integration_type"]][0],
                                                                    self.plot_data["integration_info"][self.plot_data["integration_type"]][1],
                                                                    self.plot_data["xpoints"])
                xmin_baseline, xmax_baseline = self.plot_data["xpoints"][xmin_ind_baseline], self.plot_data["xpoints"][xmax_ind_baseline]
                ymin_baseline, ymax_baseline = corrected_ypoints[xmin_ind_baseline], corrected_ypoints[xmax_ind_baseline]

                # Calculate a straight function from xmin to xmax (y = mx + b)
                m = (ymax_baseline-ymin_baseline)/(xmax_baseline-xmin_baseline)
                b = ymin_baseline - m * xmin_baseline

                ypoints = m * xpoints + b

            elif self.plot_data["integration_type"] == "constant":
                ypoints = np.full(np.size(xpoints), 
                                  self.plot_data["integration_info"]["constant"])

            elif self.plot_data["integration_type"] == "manual":
                xpoints = self.plot_data["integration_info"][self.plot_data["integration_type"]][0]
                ypoints = self.plot_data["integration_info"][self.plot_data["integration_type"]][1]

            else:
                ypoints = [0, 0]

            color = "#D55E00" if self.master._colorblind else "red"
                        
            self.HPLC_baseline, = self.ax.plot(xpoints, 
                                               ypoints,
                                               linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), self.ax),
                                               color=color,
                                               visible=self.plot_data["integration_type"] != "local"
                                               )
            
            if self.plot_data["integration_type"] == "manual":
                zipped_xy = list(zip(xpoints, ypoints))
                self.HPLC_baseline.set_picker(self._picker_HPLC)

                # Add two points to the HPLC_baseline, one that is always at xmin and one that is always at xmax
                xmin = self.plot_data["xpoints"].min()
                xmax = self.plot_data["xpoints"].max()

                # For the y_coordinate of ymin, take the first and second axle, calculate m and b (y = mx + b)
                (axle_0_x, axle_0_y) = zipped_xy[0]
                (axle_1_x, axle_1_y) = zipped_xy[1]

                m = (axle_1_y-axle_0_y)/(axle_1_x-axle_0_x)
                b = axle_0_y - m * axle_0_x

                ymin = m * xmin + b

                # For the y_coordinate of xmax, take the last and second to last axle, calculate m and b (y = mx + b)
                axle_last_x, axle_last_y = zipped_xy[-1]
                axle_2nd_last_x, axle_2nd_last_y = zipped_xy[-2]

                m = (axle_2nd_last_y-axle_last_y)/(axle_2nd_last_x-axle_last_x)
                b = axle_last_y - m * axle_last_x

                ymax = m * xmax + b

                HPLC_xdata = self.HPLC_baseline.get_xdata()
                HPLC_ydata = self.HPLC_baseline.get_ydata()

                HPLC_xdata = np.insert(HPLC_xdata, 0, xmin)
                HPLC_xdata = np.append(HPLC_xdata, xmax)

                HPLC_ydata = np.insert(HPLC_ydata, 0, ymin)
                HPLC_ydata = np.append(HPLC_ydata, ymax)

                self.HPLC_baseline.set_data(HPLC_xdata, HPLC_ydata)

                for count, (x, y) in enumerate(zipped_xy):
                    axle = self.ax.add_line(custom_Dot([x],
                                                       [y],
                                                       marker="o",
                                                       markersize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"])*8, self.ax),
                                                       markeredgewidth=float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]),
                                                       markerfacecolor="white",
                                                       markeredgecolor="black",
                                                       ))

                    axle.master = self
                    axle.draggable(use_blit=True)
                    axle.set_picker(self._picker_axle)
                    axle.xpoints = xpoints
                    axle.ypoints = ypoints
                    axle.xmin = xmin
                    axle.xmax = xmax

                    self.manual_HPLC_baseline_axles.append(axle)

            if not skip_blit:
                self.ax.draw_artist(self.HPLC_baseline)
                if self.plot_data["integration_type"] == "manual":
                    for axle in self.manual_HPLC_baseline_axles:
                        self.ax.draw_artist(axle)
                # Update the canvas
                self.canvas.blit(self.fig.bbox)
        else:
            if not skip_blit:
                self._blit_redraw(self.ax)

    def _picker_HPLC(self, artist, mouseevent):

        if mouseevent.button == 1 and mouseevent.dblclick:
            return artist.contains(mouseevent)
        return False, {}

    def _picker_axle(self, artist, mouseevent):

        if (mouseevent.button == 1 and not mouseevent.dblclick) or mouseevent.button == 3:
            return artist.contains(mouseevent)
        return False, {}

    # Update the HPLC baselines as soon as changes were made
    def update_HPLC_baseline_mode(self):
        self.plot_data["integration_type"] = self.master.integration_mode.get()
        # Update widgets to fit current integration type              
                        
        if self.plot_data["integration_type"] == "linear":
            self._set_widgets_state({
                self.master.linear_min_entry: False,
                self.master.linear_max_entry: False,
                self.master.constant_entry: True,
            })
        elif self.plot_data["integration_type"] == "constant":
            self._set_widgets_state({
                self.master.linear_min_entry: True,
                self.master.linear_max_entry: True,
                self.master.constant_entry: False,
            })
        else:
            self._set_widgets_state([
                self.master.linear_min_entry,
                self.master.linear_max_entry,
                self.master.constant_entry,
            ], disabled=True)

        self.refresh_integration()

    def update_linear_HPLC_baseline(self):
        self.plot_data["integration_info"]["linear"][0] = self.master.integration_linear_min.get()
        self.plot_data["integration_info"]["linear"][1] = self.master.integration_linear_max.get()
        
        self.refresh_integration()

    def update_constant_HPLC_baseline(self):
        self.plot_data["integration_info"]["constant"] = self.master.integration_constant.get()
        
        self.refresh_integration()

    def refresh_integration(self, skip_blit=False):
        # Redraw polygons
        try:
            for p in self.polygons:
                p.remove()
        except Exception as e:
            if DEBUG: print("Error removing polygon during integration update:", e)
        self.polygons = []
        old_integral_dict = copy.deepcopy(self.plot_data["integral_dict"])
        self.plot_data["integral_dict"] = {}

        self.toggle_HPLC_baseline(self.master.HPLC_baseline_visible, skip_blit=True)

        for peak in old_integral_dict:
            self.integrate(old_integral_dict[peak][0],old_integral_dict[peak][1], color=old_integral_dict[peak][5], skip_save=True)

        self.master.save_to_db()

        # If there is no item in the integral dict, no redraw will take place
        if len(old_integral_dict) == 0 and not skip_blit:
            self._blit_redraw()

    # MultiPlot specific settings
    def apply_colormap(self, skip_blit=False):

        self.multiplot_data["PlotOptions"]["colormap"] = self.master.multiplot_colormap.get()

        # Sort plots according to their position in the plot with the one with the highest position coming first
        sorted_plots = sorted((iid for iid in self.multiplot_data if iid != "PlotOptions"),
                                key=lambda iid: self.multiplot_data[iid]["position"],
                                reverse=True)

        if (not (self.multiplot_data["PlotOptions"]["colormap"] is None or
            self.multiplot_data["PlotOptions"]["colormap"] == "None")) and len(sorted_plots) > 0:

            # Apply the chosen colormap to all plots
            largest_pos = self.multiplot_data[sorted_plots[0]]["position"]
            if largest_pos == 0: largest_pos = 1
            normalized_positions = np.array([self.multiplot_data[iid]["position"]/largest_pos for iid in sorted_plots])
            normalized_positions = 0.05 + 0.9 * normalized_positions # Center the colormap a bit so the edges are not included
            cmap = plt.get_cmap(self.multiplot_data["PlotOptions"]["colormap"])
            colors = cmap(normalized_positions)

            for count, iid in enumerate(sorted_plots):
                self.multiplot_data[iid]["color"] = colors[count]

        if not skip_blit:

            for iid in sorted_plots:
                self.update_multiplot_color(iid, skip_blit=True)
                
            self.update_multiplot_legend()

    def recompute_multiplot_maxima(self):
        self.multiplot_data["PlotOptions"]["global_min_y"] = None
        self.multiplot_data["PlotOptions"]["global_max_y"] = None

        iid_list = list(self.multiplot_data.keys())
        iid_list.remove("PlotOptions")

        for iid in iid_list:
            if self.master.get_plot_data(iid) is None:
                print(f"File with iid {iid} is missing. Removing it from MultiPlot.")
                self.multiplot_data.pop(iid)
            else:

                plot = self.master.get_plot_data(iid)

                if iid not in self.corrected_ypoints:
                    self.corrected_ypoints[iid] = self.master.correct_baseline(iid)

                ypoints = self.corrected_ypoints[iid]

                if self.multiplot_data["PlotOptions"]["plottype"] == "Tm" and self.multiplot_data["PlotOptions"]["show_fit"] and self.multiplot_data["PlotOptions"]["Tm_method"] in ["EGD","VHD"]:
                    ypoints = np.gradient(ypoints, plot["xpoints"])
                else:
                    ypoints = ypoints

                _, max_y = get_maximum(self.multiplot_data["PlotOptions"]["x_axis_min"],
                                        self.multiplot_data["PlotOptions"]["x_axis_max"],
                                        plot["xpoints"],
                                        ypoints)
                _, min_y = get_minimum(self.multiplot_data["PlotOptions"]["x_axis_min"],
                                        self.multiplot_data["PlotOptions"]["x_axis_max"],
                                        plot["xpoints"],
                                        ypoints)
                
                self.multiplot_data[iid]["min_y"] = min_y
                self.multiplot_data[iid]["max_y"] = max_y

                # Now recalculate global values
                if (not self.multiplot_data["PlotOptions"]["global_min_y"]) or min_y < self.multiplot_data["PlotOptions"]["global_min_y"]:
                    self.multiplot_data["PlotOptions"]["global_min_y"] = min_y

                if (not self.multiplot_data["PlotOptions"]["global_max_y"]) or max_y > self.multiplot_data["PlotOptions"]["global_max_y"]:
                    self.multiplot_data["PlotOptions"]["global_max_y"] = max_y

    def update_multiplot_lines(self):

        if self.multiplot_data["PlotOptions"]["plot_offset"] != self.master.multiplot_plot_offset.get() and self.master.multiplot_plot_offset.get():
            if self.multiplot_data["PlotOptions"]["show_yticks"] and not self.multiplot_data["PlotOptions"]["3D"]:
                # Yticks don't really make a lot of sense when using an offset. Therefore if that is done, automatically disable yticks
                self.master.show_yticks.set(False)
                self.multiplot_data["PlotOptions"]["show_yticks"] = False
                yticks_widgets = [self.master.major_ytick_distance_spinbox, 
                                self.master.major_ytick_offset_spinbox,
                                self.master.minor_ytick_spinbox]
                self._set_widgets_state(yticks_widgets, disabled=True)

                # The background needs to be recomputed so the label is there, do this using blitting
                # Restore the background
                self.canvas.restore_region(self.background)
                # Draw only the label
                self.ax.draw_artist(self.ax.yaxis.label)
                # Update the canvas
                self.canvas.blit(self.fig.bbox)

                self.background = self.canvas.copy_from_bbox(self.fig.bbox)  

        self.multiplot_data["PlotOptions"]["plot_offset"] = self.master.multiplot_plot_offset.get()
        self.multiplot_data["PlotOptions"]["normalization"] = self.master.multiplot_normalization.get()

        # Disable and enable specific settings based on whether an offset is plotted and which label type is chosen
        if self.multiplot_data["PlotOptions"]["plot_offset"]:
            self.master.multiplot_labels_combobox["values"] = ["In Axes", "In Legend", "Hide"]
            self.master.adjust_y.set(True)
            
        else:
            if self.multiplot_data["PlotOptions"]["labels"] == "In Axes":
                self.multiplot_data["PlotOptions"]["labels"] = "In Legend"
                self.master.multiplot_labels.set("In Legend")
            self.master.multiplot_labels_combobox["values"] = ["In Legend", "Hide"]

        self.autoadjust_y(skip_blit=True)

        try:
            for plot in self.multiplot_lines:
                self.multiplot_lines[plot].remove()
        except Exception as e:
            if DEBUG: print("Error removing multiplot lines:", e)
        self.multiplot_lines = {}

        try:
            for label in self.multiplot_labels:
                self.multiplot_labels[label].remove()
        except Exception as e:
            if DEBUG: print("Error removing multiplot labels:", e)
        self.multiplot_labels = {}

        # Plot the multiplot lines again
        self.plot_all_multiplot_lines(axes=self.ax)

        self._blit_redraw()

    def plot_multiplot_line(self, iid, axes=None):

        if not axes:
            axes = self.ax

        plotted_fit = False

        font = self.master.plotoptions_data[self.master.plottype]["font"]

        plot = self.master.get_plot_data(iid)
        # Get the corrected baseline ypoints
        if iid not in self.corrected_ypoints:
            self.corrected_ypoints[iid] = self.master.correct_baseline(iid)

        corrected_ypoints = self.corrected_ypoints[iid]

        if self.multiplot_data["PlotOptions"]["plottype"] == "Tm" and self.multiplot_data["PlotOptions"]["show_fit"] and self.multiplot_data["PlotOptions"]["Tm_method"] in ["EGD","VHD"]:
            corrected_ypoints = np.gradient(corrected_ypoints, plot["xpoints"])
    
        if self.multiplot_data["PlotOptions"]["normalization"]:

            min_y = self.multiplot_data[iid]["min_y"]
            max_y = self.multiplot_data[iid]["max_y"]

            # Normalize the y values
            normalized_y = normalize(corrected_ypoints, 
                                        min_y, 
                                        max_y)
            
            # If 3D, all y values are not changed
            if self.multiplot_data["PlotOptions"]["3D"]:
                ypoints = normalized_y
            else:
                # In 2D, the position on the graph is added and calculated *1.05 if offset should be plotted otherwise just take normalized_y
                if self.multiplot_data["PlotOptions"]["plot_offset"]:
                    ypoints = normalized_y+self.multiplot_data[iid]["position"]*1.05
                else:
                    ypoints = normalized_y
        else:

            # If 3D and no normalization, just take the unnormalized ypoints
            if self.multiplot_data["PlotOptions"]["3D"]:
                ypoints = corrected_ypoints
            else:
                # In 2D, add the position on the multiplot*1.05*(the height of the highest plot - the lowest point in all plots), so they are stacked properly
                if self.multiplot_data["PlotOptions"]["plot_offset"]:
                    # Here it is important, that the values are transformed, so that the lowest point in every plot is 0
                    # For this, get the min_y in the visible space and subtract it from ypoints
                    min_y = self.multiplot_data[iid]["min_y"]
                    
                    ypoints = corrected_ypoints + self.multiplot_data[iid]["position"]*1.05*(self.multiplot_data["PlotOptions"]["global_max_y"]-self.multiplot_data["PlotOptions"]["global_min_y"]) - min_y
                else:
                    ypoints = corrected_ypoints
                    
        if self.multiplot_data["PlotOptions"]["3D"]:

            self.recompute_multiplot_maxima()
            self.autoadjust_y(skip_blit=True)

            # Get the limits
            x_min, x_max = axes.get_xlim()
            z_min, z_max = axes.get_zlim()
            
            # Here, a mask for x and y is necessary, so that only values within the limits are visible
            mask = (plot["xpoints"] >= x_min) & (plot["xpoints"] <= x_max) & \
                    (ypoints >= z_min) & (ypoints <= z_max)

            # Get the masked values and switch y and z values
            xpoints_mask, ypoints_mask = plot["xpoints"][mask], ypoints[mask]

        else:
            xpoints_mask, ypoints_mask = plot["xpoints"], ypoints

        if self.multiplot_data["PlotOptions"]["plottype"] != "Tm":
            plot_kwargs = {"linewidth": self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes),
                            "linestyle": self.multiplot_data[iid]["linestyle"],
                            "alpha": self.multiplot_data[iid]["alpha"],
                            "color": self.multiplot_data[iid]["color"],
                            "label": self.multiplot_data[iid]["filename"],
                        }
        else:
            plot_kwargs = {"marker": "o",
                            "markersize": self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes),
                            "linewidth": 0,
                            "alpha": self.multiplot_data[iid]["alpha"],
                            "color": self.multiplot_data[iid]["color"],
                        }

        if self.multiplot_data["PlotOptions"]["3D"]:
            plot_kwargs.update({"zs": self.multiplot_data["PlotOptions"]["3D_data"]["offset"]*self.multiplot_data[iid]["position"] + 0.5,
                                "zdir": "y"})



        line, = axes.plot(xpoints_mask,
                          ypoints_mask,
                          **plot_kwargs
                        )

        
        if self.multiplot_data["PlotOptions"]["plottype"] == "Tm":
            # Plot a fit if fits should be plotted and one has been selected and calculated
            if self.multiplot_data["PlotOptions"]["show_fit"]:
                # Plot a fit for multiplot entry using helper
                plotted_fit, fit, baselines = self._plot_tm_fit_multi(axes, 
                                                                      plot, 
                                                                      iid,
                                                                      min_y=min_y if 'min_y' in locals() else None,
                                                                      max_y=max_y if 'max_y' in locals() else None,
                                                                      normalized=self.multiplot_data["PlotOptions"]["normalization"],
                                                                      plot_offset=(self.multiplot_data["PlotOptions"]["plot_offset"] if not self.multiplot_data["PlotOptions"]["3D"] else False)
                                                                    )
            
            if plotted_fit:
                # If a fit was plotted, plot a marker with a line somewhere outside the visible region to generate a proper label for the legend
                legend_label, = axes.plot([-np.inf, -np.inf],
                                            [-np.inf, -np.inf],
                                            marker="o",
                                            markersize=self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes),
                                            linewidth=self.scale_artist_size(self.multiplot_data[iid]["linewidth"], axes),
                                            linestyle=self.multiplot_data[iid]["linestyle"],
                                            color=self.multiplot_data[iid]["color"],
                                            alpha=self.multiplot_data[iid]["alpha"],
                                            label=self.multiplot_data[iid]["filename"])
            else:
                # Otherwise set a label for the scattered points
                line.set_label(self.multiplot_data[iid]["filename"])

        label_y_position = self.multiplot_data[iid]["position"]*1.05+self.multiplot_data["PlotOptions"]["label_data"]["yposition"] 

        if not self.multiplot_data["PlotOptions"]["normalization"]:
            label_y_position *= abs(self.multiplot_data["PlotOptions"]["global_max_y"] - self.multiplot_data["PlotOptions"]["global_min_y"])  

        label_x_position = (self.multiplot_data["PlotOptions"]["x_axis_min"]+
                            (self.multiplot_data["PlotOptions"]["x_axis_max"]-self.multiplot_data["PlotOptions"]["x_axis_min"])
                            *self.multiplot_data["PlotOptions"]["label_data"]["xposition"])

        plot_label = True
    
        if axes == self.ax:
            
            self.multiplot_lines[iid] = line

            if self.multiplot_data["PlotOptions"]["plottype"] == "Tm" and plotted_fit:
                self.multiplot_lines[f"{iid}_fit"] = fit
                self.multiplot_lines[f"{iid}_legend_label"] = legend_label

                if self.multiplot_data["PlotOptions"]["show_tm_baselines"] and self.multiplot_data["PlotOptions"]["Tm_method"] in ["SCB","SLB","SQB"]:
                    if baselines:
                        self.multiplot_lines[f"{iid}_baseline0"] = baselines[0]
                        self.multiplot_lines[f"{iid}_baseline1"] = baselines[1]
            
            xlim_min, xlim_max = axes.get_xlim()
            ylim_min, ylim_max = axes.get_ylim()

            if not self.multiplot_data["PlotOptions"]["3D"]:

                if label_x_position < xlim_min or label_x_position > xlim_max or label_y_position < ylim_min or label_y_position > ylim_max:
                    plot_label = False

        if plot_label and self.multiplot_data["PlotOptions"]["labels"] == "In Axes":
            if self.multiplot_data["PlotOptions"]["3D"]:
                zlim_min, _ = axes.get_zlim()
                label = axes.text(self.multiplot_data["PlotOptions"]["x_axis_max"]+(self.multiplot_data["PlotOptions"]["x_axis_max"]-self.multiplot_data["PlotOptions"]["x_axis_min"])*0.1,
                                  self.multiplot_data["PlotOptions"]["3D_data"]["offset"]*self.multiplot_data[iid]["position"]+0.5,
                                  zlim_min,
                                  self.multiplot_data[iid]["filename"],
                                  horizontalalignment = "left",
                                  verticalalignment = "center_baseline",
                                  fontsize = self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=axes),
                                  font = font,
                                  color = self.multiplot_data[iid]["color"] if self.multiplot_data["PlotOptions"]["label_data"]["match_color"] else self.master.plotoptions_data["MultiPlot"]["clr"],
                                  alpha = self.multiplot_data[iid]["alpha"]
                                )

            else:
                label = axes.text(label_x_position,
                                  label_y_position,
                                  self.multiplot_data[iid]["filename"],
                                  horizontalalignment = "right" if self.multiplot_data["PlotOptions"]["label_data"]["xposition"] > 0.51 else "left" if self.multiplot_data["PlotOptions"]["label_data"]["xposition"] < 0.49 else "center",
                                  verticalalignment = "center_baseline",
                                  fontsize = self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=axes),
                                  font = font,
                                  color=self.multiplot_data[iid]["color"] if self.multiplot_data["PlotOptions"]["label_data"]["match_color"] else self.master.plotoptions_data["MultiPlot"]["clr"],
                                  alpha = self.multiplot_data[iid]["alpha"]
                                )

            if axes == self.ax:
                self.multiplot_labels[iid] = label

    def plot_all_multiplot_lines(self, axes=None):

        if not axes:
            axes = self.ax

        sorted_plots = sorted((iid for iid in self.multiplot_data if iid != "PlotOptions"),
                              key=lambda iid: self.multiplot_data[iid]["position"],
                              reverse=True)
        
        # Initialize all plots that are supposed to be in the graph
        for iid in sorted_plots:
            self.plot_multiplot_line(iid, axes=axes)

        if self.multiplot_data["PlotOptions"]["labels"] == "In Legend":
            font = self.master.plotoptions_data[self.master.plottype]["font"]
            legend_kwargs = {"prop": {"family": font,
                                       "size": self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=axes)},
                             "markerscale": 2,
                             "handlelength": 1.5,
                             "framealpha": 1-self.multiplot_data["PlotOptions"]["legend_transparency"]}
            if not self.multiplot_data["PlotOptions"]["legend_automatic_placement"]:
                legend_position = self.multiplot_data["PlotOptions"]["legend_position"]
                if legend_position is not None:
                    legend_kwargs["loc"] = tuple(legend_position)
            legend = axes.legend(**legend_kwargs)
            legend.master = self
            legend._draggable = custom_DraggableLegend(legend, use_blit=True)
            if axes == self.ax:
                self.legend = legend
            
    def update_multiplot_labels(self):
        self.multiplot_data["PlotOptions"]["labels"] = self.master.multiplot_labels.get()

        # Update correct visibility of the respective options
        if self.multiplot_data["PlotOptions"]["labels"] == "In Axes":
            label_position_widgets = [
                self.master.multiplot_label_xposition_entry,
                self.master.multiplot_label_xposition_slider,
                self.master.multiplot_label_yposition_entry,
                self.master.multiplot_label_yposition_slider,
            ]
            self._set_widgets_state(label_position_widgets, disabled=False)
        else:
            label_position_widgets = [
                self.master.multiplot_label_xposition_entry,
                self.master.multiplot_label_xposition_slider,
                self.master.multiplot_label_yposition_entry,
                self.master.multiplot_label_yposition_slider,
            ]
            self._set_widgets_state(label_position_widgets, disabled=True)
        
        if self.multiplot_data["PlotOptions"]["labels"] == "In Legend":
            legend_widgets = [
                self.master.multiplot_legend_transparency_entry,
                self.master.multiplot_legend_transparency_slider,
                self.master.multiplot_legend_automatic_placement_checkbox
            ]
            self._set_widgets_state(legend_widgets, disabled=False)
        else:
            legend_widgets = [
                self.master.multiplot_legend_transparency_entry,
                self.master.multiplot_legend_transparency_slider,
                self.master.multiplot_legend_automatic_placement_checkbox
            ]
            self._set_widgets_state(legend_widgets, disabled=True)

        # If labels is not "In Axes" disable match color
        is_not_in_axes = self.multiplot_data["PlotOptions"]["labels"] != "In Axes"
        self._set_widgets_state([self.master.multiplot_label_match_color_checkbox], disabled=is_not_in_axes)

        # If labels are hidden fontsize is deactivated too, otherwise activate it
        if self.multiplot_data["PlotOptions"]["labels"] == "Hide":
            self._set_widgets_state([self.master.multiplot_label_fontsize_spinbox], disabled=True)
            self.master.multiplot_label_settings_frame.grid_remove()
        else:
            self._set_widgets_state([self.master.multiplot_label_fontsize_spinbox], disabled=False)
            self.master.multiplot_label_settings_frame.grid()

        self.update_multiplot_positions()
        self._blit_redraw()

    def update_multiplot_label_color(self):
        self.multiplot_data["PlotOptions"]["label_data"]["match_color"] = self.master.multiplot_label_match_color.get()
        for iid in self.multiplot_labels:
            self.multiplot_labels[iid].set_color(self.multiplot_data[iid]["color"] if self.multiplot_data["PlotOptions"]["label_data"]["match_color"]
                                                 else self.master.plotoptions_data["MultiPlot"]["clr"])

        self.update_multiplot_legend()

    def update_multiplot_legend_placement(self):
        self.multiplot_data["PlotOptions"]["legend_automatic_placement"] = self.master.multiplot_legend_automatic_placement.get()
        self.update_multiplot_legend()

    def update_multiplot_label_xposition(self):
        self.multiplot_data["PlotOptions"]["label_data"]["xposition"] = self.master.multiplot_label_xposition.get()
        label_x_position = (self.multiplot_data["PlotOptions"]["x_axis_min"]+
                            (self.multiplot_data["PlotOptions"]["x_axis_max"]-self.multiplot_data["PlotOptions"]["x_axis_min"])
                            *self.multiplot_data["PlotOptions"]["label_data"]["xposition"])

        xlim_min, xlim_max = self.ax.get_xlim()
        plot_label = True
        if label_x_position < xlim_min or label_x_position > xlim_max:
            plot_label = False
        
        for iid in self.multiplot_labels:
            self.multiplot_labels[iid].set_x(label_x_position)
            self.multiplot_labels[iid].set_horizontalalignment("right" if self.multiplot_data["PlotOptions"]["label_data"]["xposition"] > 0.51 
                                                               else "left" if self.multiplot_data["PlotOptions"]["label_data"]["xposition"] < 0.49 
                                                               else "center")
            self.multiplot_labels[iid].set_visible(plot_label)
        
        self._blit_redraw()

    def update_multiplot_label_yposition(self):
        self.multiplot_data["PlotOptions"]["label_data"]["yposition"] = self.master.multiplot_label_yposition.get()

        for iid in self.multiplot_labels:
            label_y_position = self.multiplot_data[iid]["position"]*1.05+self.multiplot_data["PlotOptions"]["label_data"]["yposition"]

            if not self.multiplot_data["PlotOptions"]["normalization"]:
                label_y_position *= abs(self.multiplot_data["PlotOptions"]["global_max_y"] - self.multiplot_data["PlotOptions"]["global_min_y"])  

            ylim_min, ylim_max = self.ax.get_ylim()
            plot_label = True
            if label_y_position < ylim_min or label_y_position > ylim_max:
                plot_label = False
            
            self.multiplot_labels[iid].set_y(label_y_position)
            self.multiplot_labels[iid].set_visible(plot_label)

        self._blit_redraw()

    def update_multiplot_label_fontsize(self):
        self.multiplot_data["PlotOptions"]["label_data"]["fontsize"] = self.master.multiplot_label_fontsize.get()

        if self.legend:
            fontsize = self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=self.ax)
            labels = [label.get_text() for label in self.legend.get_texts()]
            legend_location = self.legend._loc
            self.legend._fontsize = fontsize
            self.legend.prop.set_size(fontsize)
            handle_markersizes = [handle.get_markersize() for handle in self.legend.legend_handles]
            self.legend._init_legend_box(self.legend.legend_handles, labels)
            # For some reason markersizes get doubled each time init_legend_box is triggered, therefore reset them to the previous values
            for i, handle in enumerate(self.legend.legend_handles):
                handle.set_markersize(handle_markersizes[i])
            self.legend._legend_title_box.set_visible(False)
            self.legend._set_loc(legend_location)
            self._blit_redraw()

        else:   
            for iid in self.multiplot_labels:
                self.multiplot_labels[iid].set_fontsize(self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=self.ax))
            self._blit_redraw()

    def update_multiplot_legend(self):

        self.multiplot_data["PlotOptions"]["legend_transparency"] = self.master.multiplot_legend_transparency.get()

        if self.legend:
            if self.legend._draggable is not None:
                self.legend._draggable.disconnect()
            self.legend.remove()
            self.legend = None

        font = self.master.plotoptions_data[self.master.plottype]["font"]

        if self.multiplot_data["PlotOptions"]["labels"] == "In Legend":
            legend_kwargs = {"prop": {"family": font,
                                       "size": self.scale_artist_size(self.multiplot_data["PlotOptions"]["label_data"]["fontsize"], axes=self.ax)},
                             "markerscale": 2,
                             "handlelength": 1.5,
                             "framealpha": 1-self.multiplot_data["PlotOptions"]["legend_transparency"]}
            if not self.multiplot_data["PlotOptions"]["legend_automatic_placement"]:
                legend_position = self.multiplot_data["PlotOptions"]["legend_position"]
                if legend_position is not None:
                    legend_kwargs["loc"] = tuple(legend_position)
            self.legend = self.ax.legend(**legend_kwargs)
            self.legend.master = self
            self.legend._draggable = custom_DraggableLegend(self.legend, use_blit=True)

        self._blit_redraw()

    def update_multiplot_label(self, iid):
        if iid in self.multiplot_labels:
            self.multiplot_labels[iid].set_text(self.multiplot_data[iid]["filename"])

        if self.multiplot_data["PlotOptions"]["labels"] == "In Legend":
            if self.multiplot_data["PlotOptions"]["plottype"] == "Tm" and self.multiplot_data["PlotOptions"]["show_fit"]:
                legend_label = f"{iid}_legend_label"
                if legend_label in self.multiplot_lines:
                    self.multiplot_lines[legend_label].set_label(self.multiplot_data[iid]["filename"])
            else:
                if iid in self.multiplot_lines:
                    self.multiplot_lines[iid].set_label(self.multiplot_data[iid]["filename"])


        self.update_multiplot_legend()

    def update_multiplot_linewidth(self, iid):

        if self.multiplot_data["PlotOptions"]["plottype"] == "Tm":
            self.multiplot_lines[iid].set_markersize(self.scale_artist_size(self.multiplot_data[iid]["linewidth"], self.ax))
            if self.multiplot_data["PlotOptions"]["show_fit"]:
                for artist in [f"{iid}_legend_label", f"{iid}_fit", f"{iid}_baseline1", f"{iid}_baseline2"]:
                    if artist in self.multiplot_lines:
                        self.multiplot_lines[artist].set_linewidth(self.scale_artist_size(self.multiplot_data[iid]["linewidth"], self.ax))
                        if artist.endswith("_legend_label"):
                            self.multiplot_lines[artist].set_markersize(self.scale_artist_size(self.multiplot_data[iid]["linewidth"], self.ax))

        else:
            self.multiplot_lines[iid].set_linewidth(self.scale_artist_size(self.multiplot_data[iid]["linewidth"], self.ax))

        self.update_multiplot_legend()
    
    def update_multiplot_linestyle(self, iid):

        if self.multiplot_data["PlotOptions"]["plottype"] == "Tm":
            if self.multiplot_data["PlotOptions"]["show_fit"]:
                for artist in [f"{iid}_legend_label", f"{iid}_fit"]:
                    if artist in self.multiplot_lines:
                        self.multiplot_lines[artist].set_linestyle(self.multiplot_data[iid]["linestyle"])

        else:
            self.multiplot_lines[iid].set_linestyle(self.multiplot_data[iid]["linestyle"])

        self.update_multiplot_legend()

    def update_multiplot_alpha(self, iid):
        iid_artists = [key for key in self.multiplot_lines if key.startswith(f"{iid}_")] + [iid]
        if iid in self.multiplot_lines:
            for artist in iid_artists:
                self.multiplot_lines[artist].set_alpha(self.multiplot_data[iid]["alpha"])
        if iid in self.multiplot_labels:
            self.multiplot_labels[iid].set_alpha(self.multiplot_data[iid]["alpha"])

        self.update_multiplot_legend()

    def update_multiplot_color(self, iid, skip_blit=False):
        iid_artists = [key for key in self.multiplot_lines if key.startswith(f"{iid}_")] + [iid]
        if iid in self.multiplot_lines:
            for artist in iid_artists:
                self.multiplot_lines[artist].set_color(self.multiplot_data[iid]["color"])
        if iid in self.multiplot_labels:
            self.multiplot_labels[iid].set_color(self.multiplot_data[iid]["color"])

        if not skip_blit:
            self.update_multiplot_legend()


    def update_multiplot_position(self, iid, skip_blit=False):

        iid_artists = [key for key in self.multiplot_lines if key.startswith(f"{iid}_")] + [iid]
        if iid in self.multiplot_lines:
            for artist in iid_artists:
                self.multiplot_lines[artist].remove()
                self.multiplot_lines.pop(artist)

        if iid in self.multiplot_labels:
            self.multiplot_labels[iid].remove()
            self.multiplot_labels.pop(iid)

        self.plot_multiplot_line(iid, axes=self.ax)

        if not skip_blit:
            self.update_multiplot_legend()

    def update_multiplot_positions(self):
        if self.legend:
            if self.legend._draggable is not None:
                self.legend._draggable.disconnect()
            self.legend.remove()
            self.legend = None

        for artist in self.multiplot_lines.values():
            artist.remove()
        self.multiplot_lines = {}

        for label in self.multiplot_labels.values():
            label.remove()
        self.multiplot_labels = {}

        self.plot_all_multiplot_lines(axes=self.ax)

    def update_multiplot_fit(self):

        self.multiplot_data["PlotOptions"]["show_fit"] = self.master.multiplot_fit.get()

        tm_method = self.master.multiplot_fit_type.get()
        if tm_method == "Sigmoidal + Constant Baseline": tm_method = "SCB"
        elif tm_method == "Sigmoidal + Linear Baseline": tm_method = "SLB"
        elif tm_method == "Sigmoidal + Quadratic Baseline": tm_method = "SQB"
        elif tm_method == "Van't Hoff Derivative": tm_method = "VHD"
        elif tm_method == "Empirical Gauss Derivative": tm_method = "EGD"

        tm_method_changed = self.multiplot_data["PlotOptions"]["Tm_method"] != tm_method

        self.multiplot_data["PlotOptions"]["Tm_method"] = tm_method

        self.multiplot_data["PlotOptions"]["show_tm_baselines"] = self.master.multiplot_show_tm_baselines.get()

        # Only activate all other widgets, if show_fit is True
        fit_widgets = [self.master.multiplot_fit_combobox, self.master.show_tm_baselines_checkbox]
        self._set_widgets_state(fit_widgets, disabled=not self.multiplot_data["PlotOptions"]["show_fit"])

        if tm_method in ["VHD", "EGD"]:
            self._set_widgets_state([self.master.show_tm_baselines_checkbox], disabled=True)

        if tm_method_changed:
            # Set autoadjust_y to True, so that the y-axis is adjusted to the new fit
            self.multiplot_data["PlotOptions"]["autoadjust_y"] = True
            self.master.adjust_y.set(True)
            self.recompute_multiplot_maxima()
            self.update_axis_labels(axes=self.ax)

        self.autoadjust_y(skip_blit=True)
        self.update_multiplot_positions()
        self._blit_redraw()

    #  refresh Graph
    def refresh(self, *args, axes=None, refreshTree=True, mirror=False):
        if DEBUG: print("Refresh...")
        if self._refresh:
            self.master.after_cancel(self._refresh)
        self._refresh = None
        if axes == None: axes = self.ax

        # Before doing anything, check whether it needs to be a 3D or 2D axes
        if self.master.plottype == "MultiPlot":
            self.multiplot_data["PlotOptions"]["3D"] = self.master.multiplot_3D.get()

        if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
            if not isinstance(axes, Axes3D):
                print("Converting to 3D plot")
                
                if axes == self.ax:

                    self.fig.delaxes(ax=axes)
                    axes = self.add_3d_ax(self.fig)
                    self.ax = axes
                    # Disconnect old PeakSelector events
                    self.PeakSelector.disconnect_events()
                    self.IntegrateSelector.disconnect_events()

                else:

                    self.expfig.delaxes(ax=axes)
                    axes = self.add_3d_ax(self.expfig)
                    self.expax = axes

                axes.set_zticks([])

        else:
            if isinstance(axes, Axes3D):
                print("Converting to 2D plot")
                if axes == self.ax:

                    self.fig.delaxes(ax=axes)
                    axes = self.add_ax(self.fig)
                    self.ax = axes
                    # disconnect old Selectors
                    self.PeakSelector.disconnect_events()
                    self.IntegrateSelector.disconnect_events()
                    # Setup Selector for Peak Picking and Integrating
                    self._setup_selectors(self.ax)

                else:

                    self.expfig.delaxes(ax=axes)
                    axes = self.add_ax(self.expfig)
                    self.expax = axes

        self.update_fig_size(axes.figure)

        font = self.master.plotoptions_data[self.master.plottype]["font"]
        fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=axes)

        # Setup mathtext only when the selected font changes.
        if font != self._configured_mathtext_font:
            mpl.rcParams.update({
                                "mathtext.fontset": "custom",
                                "mathtext.rm": font,
                                "mathtext.it": f"{font}:italic",
                                "mathtext.bf": f"{font}:bold",
                                "mathtext.bfit": f"{font}:bold:italic",
                                "mathtext.sf": font,
                                "mathtext.tt": font,
                                "mathtext.cal": font,
                            })
            self._configured_mathtext_font = font


        # Only enable the other options if show_yticks is True
        yticks_widgets = [self.master.major_ytick_distance_spinbox, 
                            self.master.major_ytick_offset_spinbox,
                            self.master.minor_ytick_spinbox]
        self._set_widgets_state(yticks_widgets, disabled=not self.master.show_yticks.get())

        # Only enable the other options if show_xticks is True
        xticks_widgets = [self.master.major_xtick_distance_spinbox, 
                            self.master.major_xtick_offset_spinbox,
                            self.master.minor_xtick_spinbox]
        self._set_widgets_state(xticks_widgets, disabled=not self.master.show_xticks.get())
                
        if self.master.plottype != "MultiPlot":

            if self.master.plottype != "Assay":
                if mirror:
                    if self.plot_data["mirror_annotations"]:
                        self.plot_data["inset_peak_dict"] = {
                            peak: self.plot_data["inset_peak_dict"].get(peak, self.plot_data["peak_dict"][peak]).copy()
                            for peak in self.plot_data["peak_dict"]
                        }

                self.plot_data["show_yticks"] = self.master.show_yticks.get()
                self.plot_data["show_xticks"] = self.master.show_xticks.get()

            else:
                self.multiplot_data["PlotOptions"]["show_yticks"] = self.master.show_yticks.get()
                self.multiplot_data["PlotOptions"]["show_xticks"] = self.master.show_xticks.get()

            self.update_axis_labels(axes=axes)
            self.autoadjust_y(axes=axes, skip_blit=True)

            if axes is self.ax:
                plot_width, plot_height, *_ = self._get_layout()
                aspect_ratio = plot_height / plot_width

                axes.set_box_aspect(aspect_ratio)

        else:
            # Update data
            self.multiplot_data["PlotOptions"]["labels"] = self.master.multiplot_labels.get()
            self.multiplot_data["PlotOptions"]["3D_data"]["elev"] = self.master.multiplot_3D_elev.get()
            self.multiplot_data["PlotOptions"]["3D_data"]["azim"] = self.master.multiplot_3D_azim.get()
            self.multiplot_data["PlotOptions"]["3D_data"]["projection_type"] = "ortho" if self.master.multiplot_3D_projection_type.get() == "Orthographic" else "persp"
            self.multiplot_data["PlotOptions"]["3D_data"]["offset"] = self.master.multiplot_3D_offset.get()

            self.multiplot_data["PlotOptions"]["show_yticks"] = self.master.show_yticks.get()
            self.multiplot_data["PlotOptions"]["show_xticks"] = self.master.show_xticks.get()
            
            if self.multiplot_data["PlotOptions"]["plottype"] == "Tm":

                # Only activate all other widgets, if show_fit is True
                fit_widgets = [self.master.multiplot_fit_combobox, self.master.show_tm_baselines_checkbox]
                self._set_widgets_state(fit_widgets, disabled=not self.multiplot_data["PlotOptions"]["show_fit"])

                if self.multiplot_data["PlotOptions"]["Tm_method"] in ["VHD", "EGD"]:
                    self._set_widgets_state([self.master.show_tm_baselines_checkbox], disabled=True)                

            # If labels is not "In Axes" disable match color
            is_not_in_axes = self.multiplot_data["PlotOptions"]["labels"] != "In Axes"
            self._set_widgets_state([self.master.multiplot_label_match_color_checkbox], disabled=is_not_in_axes)

            # If labels are hidden fontsize is deactivated too, otherwise activate it
            if self.multiplot_data["PlotOptions"]["labels"] == "Hide":
                self._set_widgets_state([self.master.multiplot_label_fontsize_spinbox], disabled=True)
                self.master.multiplot_label_settings_frame.grid_remove()
            else:
                self._set_widgets_state([self.master.multiplot_label_fontsize_spinbox], disabled=False)
                self.master.multiplot_label_settings_frame.grid()

            if self.multiplot_data["PlotOptions"]["3D"]:
                # Add all choices for the label combobox in case they have been removed in a prior step
                self.master.multiplot_labels_combobox["values"] = ["In Axes", "In Legend", "Hide"]
                
                # Enable 3D controls
                enabled_3d_widgets = [
                    self.master.multiplot_elevation_entry,
                    self.master.multiplot_elevation_slider,
                    self.master.multiplot_rotation_entry,
                    self.master.multiplot_rotation_slider,
                    self.master.multiplot_offset_entry,
                    self.master.multiplot_offset_slider,
                    self.master.multiplot_perspective_combobox,
                ]
                self._set_widgets_state(enabled_3d_widgets, disabled=False)
                self.master.multiplot_perspective_combobox.state(["readonly"])
                
                # Disable label and offset widgets in 3D
                disabled_3d_widgets = [
                    self.master.multiplot_plot_offset_checkbox,
                    self.master.multiplot_label_xposition_entry,
                    self.master.multiplot_label_xposition_slider,
                    self.master.multiplot_label_yposition_entry,
                    self.master.multiplot_label_yposition_slider,
                    self.master.multiplot_legend_transparency_entry,
                    self.master.multiplot_legend_transparency_slider,
                ]
                self._set_widgets_state(disabled_3d_widgets, disabled=True)

                # Only show the 3D settings frame just now
                self.master.multiplot_3D_settings_frame.grid()

                axes.view_init(elev=self.multiplot_data["PlotOptions"]["3D_data"]["elev"],
                               azim=-self.multiplot_data["PlotOptions"]["3D_data"]["azim"]-90)

                axes.set_proj_type(self.multiplot_data["PlotOptions"]["3D_data"]["projection_type"])
                
            else:
                # Disable 3D controls for 2D mode
                disabled_3d_widgets = [
                    self.master.multiplot_elevation_entry,
                    self.master.multiplot_elevation_slider,
                    self.master.multiplot_rotation_entry,
                    self.master.multiplot_rotation_slider,
                    self.master.multiplot_offset_entry,
                    self.master.multiplot_offset_slider,
                    self.master.multiplot_perspective_combobox,
                ]
                self._set_widgets_state(disabled_3d_widgets, disabled=True)
                self._set_widgets_state([self.master.multiplot_plot_offset_checkbox], disabled=False)

                # Hide 3D settings frame
                self.master.multiplot_3D_settings_frame.grid_remove()

                # Disable and enable specific settings based on whether an offset is plotted and which label type is chosen
                if self.multiplot_data["PlotOptions"]["plot_offset"]:
                    self.master.multiplot_labels_combobox["values"] = ["In Axes", "In Legend", "Hide"]
                    
                else:
                    if self.multiplot_data["PlotOptions"]["labels"] == "In Axes":
                        self.multiplot_data["PlotOptions"]["labels"] = "In Legend"
                        self.master.multiplot_labels.set("In Legend")
                    self.master.multiplot_labels_combobox["values"] = ["In Legend", "Hide"]

                if self.multiplot_data["PlotOptions"]["labels"] == "In Axes":
                    label_position_widgets = [
                        self.master.multiplot_label_xposition_entry,
                        self.master.multiplot_label_xposition_slider,
                        self.master.multiplot_label_yposition_entry,
                        self.master.multiplot_label_yposition_slider,
                    ]
                    self._set_widgets_state(label_position_widgets, disabled=False)
                else:
                    label_position_widgets = [
                        self.master.multiplot_label_xposition_entry,
                        self.master.multiplot_label_xposition_slider,
                        self.master.multiplot_label_yposition_entry,
                        self.master.multiplot_label_yposition_slider,
                    ]
                    self._set_widgets_state(label_position_widgets, disabled=True)

                if self.multiplot_data["PlotOptions"]["labels"] == "In Legend":
                    legend_widgets = [
                        self.master.multiplot_legend_transparency_entry,
                        self.master.multiplot_legend_transparency_slider,
                        self.master.multiplot_legend_automatic_placement_checkbox
                    ]
                    self._set_widgets_state(legend_widgets, disabled=False)
                else:
                    legend_widgets = [
                        self.master.multiplot_legend_transparency_entry,
                        self.master.multiplot_legend_transparency_slider,
                        self.master.multiplot_legend_automatic_placement_checkbox
                    ]
                    self._set_widgets_state(legend_widgets, disabled=True)
                    
            plot_width, plot_height, *_ = self._get_layout()
            aspect_ratio = plot_height / plot_width

            if isinstance(axes, Axes3D):
                axes.set_box_aspect([1,1,aspect_ratio])
            else:
                axes.set_box_aspect(aspect_ratio)
            global_values_calculated = self.multiplot_data["PlotOptions"]["global_min_y"] and self.multiplot_data["PlotOptions"]["global_max_y"]

            # Already load all plots into memory and delete plots that are not available
            for iid in list(self.multiplot_data.keys()):
                if iid != "PlotOptions":
                    if self.master.get_plot_data(iid) is None:
                        print(f"File with iid {iid} is missing. Removing it from MultiPlot.")
                        self.multiplot_data.pop(iid)
                    else:
                        # Now check whether min_y and max_y have already been calculated (backwards compatibility)
                        if not (self.multiplot_data[iid]["min_y"] and self.multiplot_data[iid]["max_y"]):
                            plot = self.master.get_plot_data(iid)

                            if iid not in self.corrected_ypoints:
                                                
                                self.corrected_ypoints[iid] = self.master.correct_baseline(iid)

                            _, max_y = get_maximum(self.multiplot_data["PlotOptions"]["x_axis_min"],
                                                   self.multiplot_data["PlotOptions"]["x_axis_max"],
                                                   plot["xpoints"],
                                                   self.corrected_ypoints[iid])
                            _, min_y = get_minimum(self.multiplot_data["PlotOptions"]["x_axis_min"],
                                                   self.multiplot_data["PlotOptions"]["x_axis_max"],
                                                   plot["xpoints"],
                                                   self.corrected_ypoints[iid])
                            
                            self.multiplot_data[iid]["min_y"] = min_y
                            self.multiplot_data[iid]["max_y"] = max_y

                        # Now if global values have not been finally calculated yet, calculate them now
                        if not global_values_calculated:
                            if (not self.multiplot_data["PlotOptions"]["global_min_y"]) or min_y < self.multiplot_data["PlotOptions"]["global_min_y"]:
                                self.multiplot_data["PlotOptions"]["global_min_y"] = min_y

                            if (not self.multiplot_data["PlotOptions"]["global_max_y"]) or max_y > self.multiplot_data["PlotOptions"]["global_max_y"]:
                                self.multiplot_data["PlotOptions"]["global_max_y"] = max_y
                
            # Change Font_Size and labels

            self.update_axis_labels(axes=axes)
            self.autoadjust_y(axes=axes, skip_blit=True)

            # In Case of 3D plots, set labels as ticklabels on the yaxis, for this, you need to loop through multiplot_data
            if self.multiplot_data["PlotOptions"]["3D"]:

                y_tick_positions = []
                y_tick_labels = []

                for iid in self.multiplot_data:
                    if iid != "PlotOptions":
                        y_tick_positions.append(self.multiplot_data["PlotOptions"]["3D_data"]["offset"]*self.multiplot_data[iid]["position"]+0.5)
                        y_tick_labels.append(self.multiplot_data[iid]["filename"])

                axes.set_yticks(y_tick_positions)
                axes.set_yticklabels([])
                axes.tick_params(axis="y",labelsize=fontsize,labelfontfamily=font)

        bottom_xlim = float(self.master.xlim_min.get())
        top_xlim = float(self.master.xlim_max.get())
        # Check whether any of the xlim values are NaN or inf and if so reset them to default values
        if np.isnan(bottom_xlim) or np.isinf(bottom_xlim):
            bottom_xlim = 0
            self.master.xlim_min.set(bottom_xlim)
            self.plot_data["x_axis_min"] = float(bottom_xlim)
        if np.isnan(top_xlim) or np.isinf(top_xlim):
            top_xlim = 1
            self.master.xlim_max.set(top_xlim)
            self.plot_data["x_axis_max"] = float(top_xlim)

        # Set limits of axis
        axes.set_xlim(bottom_xlim, 
                      top_xlim
                      )
        
        axes.margins(0)

        if self.master.plottype not in ["MultiPlot", "Assay"]:
            plot_options = self.plot_data
        else:
            plot_options = self.multiplot_data["PlotOptions"]

        self.scale_axes_strokes(axes)

        if plot_options["show_yticks"]:
            if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
                axis = axes.zaxis
            else:
                axis = axes.yaxis
            if DEBUG: print("Showing yticks on regular plot")
            ydistance = plot_options["distance_yticks"]
            if ydistance:
                y_axis_major_locator = mpl.ticker.MultipleLocator(base=ydistance,
                                                                  offset=plot_options["offset_yticks"])
            else:
                y_axis_major_locator = mpl.ticker.AutoLocator()
            axis.set_major_locator(y_axis_major_locator)
            if not ydistance:
                y_tick_vals = y_axis_major_locator()
                yoffset = y_tick_vals[0]
                if len(y_tick_vals) >= 2:
                    ydistance = abs(y_tick_vals[1] - y_tick_vals[0])
                else:
                    ydistance = 10

                if ydistance.is_integer():
                    ydistance = int(ydistance)

                yoffset_ydistance_ratio = abs(yoffset)/ydistance

                if yoffset_ydistance_ratio.is_integer():
                    yoffset = 0
                else:
                    yfraction = yoffset_ydistance_ratio % 1
                    yoffset = yfraction*ydistance

                plot_options["distance_yticks"] = ydistance
                self.master.distance_yticks.set(ydistance)
                plot_options["offset_yticks"] = yoffset
                self.master.offset_yticks.set(yoffset)
                
            axis.set_minor_locator(mpl.ticker.AutoMinorLocator(plot_options["num_minor_yticks"]+1))
            axis.set_tick_params(labelsize=fontsize,labelfontfamily=font)

        elif self.master.plottype != "MultiPlot" or (self.master.plottype == "MultiPlot" and 
                                                     not self.multiplot_data["PlotOptions"]["3D"]):
            if DEBUG:
                print("Showing no yticks on regular plot or regular multiplot without 3D axis")
            axes.set_yticks([])
            axes.set_yticks([], minor=True)


        if plot_options["show_xticks"]:
            if DEBUG: print("Showing xticks on regular plot")
            xdistance = plot_options["distance_xticks"]
            if xdistance:
                x_axis_major_locator = mpl.ticker.MultipleLocator(base=xdistance,
                                                                    offset=plot_options["offset_xticks"])
            else:
                x_axis_major_locator = mpl.ticker.AutoLocator()
            axes.xaxis.set_major_locator(x_axis_major_locator)
            if not xdistance:
                x_tick_vals = x_axis_major_locator()
                xoffset = x_tick_vals[0]
                if len(x_tick_vals) >= 2:
                    xdistance = abs(x_tick_vals[1] - x_tick_vals[0])
                else:
                    xdistance = 10

                if xdistance.is_integer():
                    xdistance = int(xdistance)

                xoffset_xdistance_ratio = abs(xoffset)/xdistance
                
                if xoffset_xdistance_ratio.is_integer():
                    xoffset = 0
                else:
                    xfraction = xoffset_xdistance_ratio % 1
                    xoffset = xfraction*xdistance

                plot_options["distance_xticks"] = xdistance
                self.master.distance_xticks.set(xdistance)
                plot_options["offset_xticks"] = xoffset
                self.master.offset_xticks.set(xoffset)
                
            axes.xaxis.set_minor_locator(mpl.ticker.AutoMinorLocator(plot_options["num_minor_xticks"]+1))
            axes.tick_params(axis="x",labelsize=fontsize,labelfontfamily=font)

        elif self.master.plottype != "MultiPlot" or (self.master.plottype == "MultiPlot" 
                                                    and not self.multiplot_data["PlotOptions"]["3D"]):
            if DEBUG:
                print("Showing no xticks on regular plot or regular multiplot without 3D axis")
            axes.set_xticks([])
            axes.set_xticks([], minor=True)
        

        if self.master.plottype == "MALDI" and self.plot_data["inset"]:
            # Calculate the width and height of the insets
            inset_width = str(self.plot_data["inset_xsize"]) + "%"
            inset_height = str(self.plot_data["inset_ysize"]) + "%"
            # Enable all Entries
            
            self._set_widgets_state(self.master.inset_widgets, disabled=False)
                
            if not self.insetplotted or axes != self.ax:
                           
                # Create Inset
                axes.inset = inset_axes(axes,
                                        width=inset_width, 
                                        height=inset_height, 
                                        loc=self.plot_data["inset_pos"], 
                                        borderpad=self._get_inset_borderpad(axes))

                if not self.initiated and len(self.plot_data["inset_peak_dict"]) == 0:
                    self.plot_data["inset_peak_dict"] = {
                        peak: [self.plot_data["peak_dict"][peak][0],
                               self.plot_data["peak_dict"][peak][1],
                               *self.default_annotation_position(axes.inset, peak, self.plot_data["peak_dict"][peak][1])]
                        for peak in self.plot_data["peak_dict"]
                    }

                if axes is self.ax:
                    self._setup_inset_selector(axes=axes.inset)
                self.insetplotted = True

            self._update_inset_borderpad(axes)
            self.scale_axes_strokes(axes, inset=True)
            axes.inset.xaxis.get_major_locator().set_params(integer=True)
            axes.inset.margins(0,0)
            axes.inset.set_yticks([])

            labelpad = self.scale_artist_size(mpl.rcParams["axes.labelpad"], axes)
            
            axes.inset.set_ylabel(self.master.plotoptions_data[self.master.plottype]["ylabel"],
                                  fontsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                  font = font,
                                  labelpad=labelpad)
            axes.inset.set_xlabel(self.master.plotoptions_data[self.master.plottype]["xlabel"],
                                  fontsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                  font = font,
                                  labelpad=labelpad)
            axes.inset.tick_params(axis="x",
                                   labelsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                   labelfontfamily=font)
            axes.inset.tick_params(axis="y",
                                   labelsize=self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes),
                                   labelfontfamily=font)
            axes.inset.set_xlim(self.master.xlim_min_inset.get(),
                                   self.master.xlim_max_inset.get()
                                   )
            axes.inset.set_ylim(top = self.master.y_height_inset.get()/100*self.max_y_val)

            axes.inset.yaxis.set_label_position("right" if "left" in self.plot_data["inset_pos"] else "left")
            
        elif not self.master.plottype == "MALDI" and self.insetplotted and self.plot_data["inset"]:
            # Disconnect Inset Peak Selector Events
            self.InsetPeakSelector.disconnect_events()
            # Close Inset Plot
            axes.inset.remove()
            # Disable all Entries
            self._set_widgets_state(self.master.inset_widgets, disabled=True)
            # Update Variables
            self.insetplotted = False

        if not self.master.mirror_annotations.get():
            self.initiated = False
        elif self.master.mirror_annotations.get() and self.insetplotted:
            self.initiated = True
    
        if axes == self.ax:
            self.toolbar.home()
            # Refresh Zoom on Toolbar
            self.toolbar.update()
        else:
            self.refresh_for_blitting(axes)

        if refreshTree: self.master.refreshTree()

    def refresh_for_blitting(self, axes):

        if DEBUG: print("Refreshing for blitting on axes:", axes)

        # Remember whether a fit was plotted
        plotted_fit = False
        baselines = None
        fit = None
        line = None
        constant_artist = None
        rectangle_artist = None
        params_artist = None

        if axes == self.ax:
 
            # Clear ax and delete old artist
            try:
                self.figure_boundary_artist1.remove()
                self.figure_boundary_artist2.remove()
            except Exception as e:
                if DEBUG: print("Error removing figure boundary artists:", e)
            try:
                if self.line is not None:
                    self.line.remove()
            except Exception as e:
                if DEBUG: print("Error removing main line:", e)
            try:
                if self.HPLC_baseline is not None:
                    self.HPLC_baseline.remove()
            except Exception as e:
                if DEBUG: print("Error removing HPLC baseline:", e)
            try:
                for axle in self.manual_HPLC_baseline_axles:
                    axle.remove()
            except Exception as e:
                if DEBUG: print("Error removing HPLC baseline axles:", e)
            try:
                self.zero_line.remove()
            except Exception as e:
                if DEBUG: print("Error removing zero line:", e)
            try:
                if self.inset_line is not None:
                    self.inset_line.remove()
            except Exception as e:
                if DEBUG: print("Error removing inset line:", e)
            # Delete old fit
            try:
                if self.fit is not None:
                    self.fit.remove()
            except Exception as e:
                if DEBUG: print("Error removing fit:", e)
            # Delete old Vmax constant and Km rectangle, if they exist
            try:
                if self.Vmax_constant is not None:
                    self.Vmax_constant.remove()
            except Exception as e:
                if DEBUG: print("Error removing old Vmax constant:", e)
            try:
                if self.Km_rectangle is not None:
                    self.Km_rectangle.remove()
            except Exception as e:
                if DEBUG: print("Error removing old Km rectangle:", e)
            try:
                if self.fit_params is not None:
                    self.fit_params.remove()
            except Exception as e:
                if DEBUG: print("Error removing old fit params legend:", e)
            try:
                for baseline in self.tm_baselines or []:
                    baseline.remove()
            except Exception as e:
                if DEBUG: print("Error removing tm baselines:", e)
            # delete simulations
            try:
                for simulation in self.simulation + self.isimulation:
                    simulation.remove()
            except Exception as e:
                if DEBUG: print("Error removing simulations:", e)
            # delete annotations and polygons
            for a in self.annotations + self.iannotations:
                a.remove()
            
            # If the inset is plotted, remove the axes
            if self.insetplotted:
                axes.inset.set_animated(True)
            
            # Delete polygons, needs to be try except, otherwise it will throw an error if p does not exist anymore
            try:
                for p in self.polygons:
                    p.remove()
            except Exception as e:
                if DEBUG: print("Error removing polygons:", e)

            try:
                for plot in self.multiplot_lines:
                    self.multiplot_lines[plot].remove()
            except Exception as e:
                if DEBUG: print("Error removing multiplot lines:", e)

            try:
                for label in self.multiplot_labels:
                    self.multiplot_labels[label].remove()
            except Exception as e:
                if DEBUG: print("Error removing multiplot labels:", e)

            try:
                for text in self.free_texts.values():
                    text.remove()
            except Exception as e:
                if DEBUG: print("Error removing free text artists:", e)

            try:
                if self.legend is not None:
                    if self.legend._draggable is not None:
                        self.legend._draggable.disconnect()
                    self.legend.remove()
                    self.legend = None
            except Exception as e:
                if DEBUG: print("Error removing legend:", e)

            self.multiplot_lines = {}
            self.multiplot_labels = {}
            self.annotations = []
            self.iannotations = []
            self.simulation = []
            self.isimulation = []
            self.manual_HPLC_baseline_axles = []
            self.free_texts = {}
            self.fit = None
            self.Vmax_constant = None
            self.Km_rectangle = None
            self.inset_line = None
            self.fit_params = None

            xtick_labels = self.ax.get_xticklabels()
            xtick_lines = list(self.ax.xaxis.get_ticklines()) + list(self.ax.xaxis.get_minorticklines())
            xtick_artists = [self.ax.xaxis.label] + list(xtick_labels) + list(xtick_lines)

            for artist in xtick_artists:
                artist.set_alpha(0)

            if ((self.master.plottype not in ["MultiPlot", "Assay"] and self.plot_data["show_yticks"]) or 
                (self.master.plottype in ["MultiPlot", "Assay"] and self.multiplot_data["PlotOptions"]["show_yticks"]) or
                self.master.plottype == "Kinetics"):
                # Because in Kinetics the y-axis label can be changed interactively, this needs to be done too

                # In case of 3D, do this for the z-axis instead of the y-axis
                if self.master.plottype == "MultiPlot" and self.multiplot_data["PlotOptions"]["3D"]:
                    ytick_labels = self.ax.get_zticklabels()
                    ytick_lines = list(self.ax.zaxis.get_ticklines()) + list(self.ax.zaxis.get_minorticklines())
                    ytick_artists = [self.ax.zaxis.label] + list(ytick_labels) + list(ytick_lines)

                else:
                    ytick_labels = self.ax.get_yticklabels()
                    ytick_lines = list(self.ax.yaxis.get_ticklines()) + list(self.ax.yaxis.get_minorticklines())
                    ytick_artists = [self.ax.yaxis.label] + list(ytick_labels) + list(ytick_lines)

                for artist in ytick_artists:
                    artist.set_alpha(0)

                self.draw_canvas()
                self.background = self.canvas.copy_from_bbox(self.fig.bbox)

                for artist in ytick_artists:
                    artist.set_alpha(1)

            else:
                self.draw_canvas()
                self.background = self.canvas.copy_from_bbox(self.fig.bbox)

            for artist in xtick_artists:
                artist.set_alpha(1)

            # If the inset is plotted, show it again, so it is properly drawn on zooming and panning, etc
            if self.insetplotted:
                axes.inset.set_animated(False)

        # Here the simulations need to be plotted
        if self.master.plottype == "MALDI":
            self.update_simulation(axes)

        if self.master.plottype != "MultiPlot":

            if self.master.plottype not in ["Tm", "Assay", "Kinetics"]:

                # Draw zero_line if plottype is CD
                if self.master.plottype == "CD" and self.plot_data["show_zero_line"]:

                    zero_line = axes.axhline(y=0,
                                             color=self.plot_data["zero_line_color"],
                                             linewidth=self.scale_artist_size(self.plot_data["zero_line_linewidth"], axes),
                                             linestyle=self.plot_data["zero_line_linestyle"]
                                             )
        
                # Refresh Plot
                line, = axes.plot(self.plot_data["xpoints"], self.corrected_ypoints[self.master.iid],
                                  linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                  linestyle=self.plot_data["linestyle"],
                                  color=self.plot_data["color"]
                                  )

                if self.insetplotted:
                     inset_line, = axes.inset.plot(self.plot_data["xpoints"],
                                                   self.corrected_ypoints[self.master.iid],
                                                   linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                                   linestyle=self.plot_data["linestyle"],
                                                   color=self.plot_data["color"]
                                                   )

            elif self.master.plottype == "Assay":
                                
                if self.multiplot_data["PlotOptions"]["assay_type"] is not None:

                    line = axes.errorbar(self.multiplot_data["PlotOptions"]["xpoints"],
                                         self.multiplot_data["PlotOptions"]["ypoints"],
                                         yerr=self.multiplot_data["PlotOptions"]["y_err"],
                                         fmt="o",
                                         linewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                         markersize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"])*2, axes),
                                         elinewidth=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"])/2, axes),
                                         capsize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                         ecolor="black",
                                         color=self.multiplot_data["PlotOptions"]["color"]
                                        )

                    if self.multiplot_data["PlotOptions"]["show_assay_fit"]:
                        plotted_fit, fit, rectangle_artist, constant_artist, params_artist = self._plot_assay_fit_single(axes)

            else:

                if self.master.plottype == "Tm":
                    # Plot a fit if available (centralized in helper)
                    if self.plot_data["show_fit"] or self.plot_data["show_tm_baselines"]:
                        plotted_fit, fit, baselines = self._plot_tm_fit_single(axes)

                    if self.plot_data["Tm_method"] in ["EGD","VHD"]:
                        ypoints = np.gradient(self.corrected_ypoints[self.master.iid], self.plot_data["xpoints"])
                    else:
                        ypoints = self.corrected_ypoints[self.master.iid]

                else:
                    ypoints = self.corrected_ypoints[self.master.iid]

                # Refresh Plot
                line, = axes.plot(self.plot_data["xpoints"],
                                ypoints,
                                marker="o",
                                markersize=self.scale_artist_size(float(self.master.plotoptions_data[self.master.plottype]["lnwdth"]), axes),
                                linewidth=0,
                                color=self.plot_data["color"]
                                )

            if axes == self.ax:
                if line is not None:
                    self.line = line
                if self.insetplotted:
                    self.inset_line = inset_line
                else:
                    self.inset_line = None
                if plotted_fit:
                    self.fit = fit
                if constant_artist is not None:
                    self.Vmax_constant = constant_artist
                if rectangle_artist is not None:
                    self.Km_rectangle = rectangle_artist
                if params_artist is not None:
                    self.fit_params = params_artist
                if baselines and self.plot_data["show_tm_baselines"]:
                    self.tm_baselines = baselines

                if self.master.plottype == "CD" and self.plot_data["show_zero_line"]:
                    self.zero_line = zero_line

                # Redraw polygons
                self.polygons = []
                
                if self.master.plottype == "HPLC":
                    # Draw HPLC baseline if necessary
                    self.toggle_HPLC_baseline(self.master.HPLC_baseline_visible, skip_blit=True)
                    for peak in self.plot_data["integral_dict"]:
                        self.draw_polygon(self.plot_data["integral_dict"][peak][0],self.plot_data["integral_dict"][peak][1], axes, color=self.plot_data["integral_dict"][peak][5])

                    # Second loop to remove polygons if they should not be visible in the first place
                    if not self.plot_data["plot_integrals"]:
                        for p in self.polygons:
                            p.remove()
            
            else:
                if self.master.plottype == "HPLC" and self.plot_data["plot_integrals"]:
                    for peak in self.plot_data["integral_dict"]:
                        self.draw_polygon(self.plot_data["integral_dict"][peak][0],self.plot_data["integral_dict"][peak][1], axes, color=self.plot_data["integral_dict"][peak][5])

            if self.master.plottype != "Assay":
                self.refresh_annotations(axes)
            self.create_free_texts(axes)

            for text in self.free_texts.values():
                axes.draw_artist(text)

            # Draw inset last so that nothing overlaps the inset
            if self.insetplotted and self.master.plottype != "Assay":
                axes.draw_artist(axes.inset)

        elif self.master.plottype == "MultiPlot":

            self.apply_colormap(skip_blit=True)
            
            self.plot_all_multiplot_lines(axes=axes)
            self.create_free_texts(axes)

        self.show_visual_border()

        self._blit_redraw()

        if DEBUG: print("Done with complete refresh")

    def refresh_annotations(self, axes):

        if axes == self.ax:
            for a in self.annotations:
                a.remove()
            for a in self.iannotations:
                a.remove()
            
            self.annotations = []
            self.iannotations = []

        self._migrate_annotation_positions(axes, self.plot_data["peak_dict"], "annotation_coordinate_system")

        # create annotations from dict
        self.create_annotations(axes = axes,
                                inset = False,
                                automatic_scripts = self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")

        # Create Annotations on Inset
        if self.insetplotted and self.master.mirror_annotations.get():

            self._migrate_annotation_positions(axes, self.plot_data["inset_peak_dict"], "inset_annotation_coordinate_system")

            self.create_annotations(axes = axes,
                                    inset = True,
                                    automatic_scripts = self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")

        # Update canvas
        if axes == self.ax:
            # Update the canvas
            self._blit_redraw()

            # If an annotation is outside of the axes, hide it
            redraw = False

            annotations = self.annotations + self.iannotations if self.insetplotted else self.annotations

            for ann in annotations:
                if not self.is_artist_in_axes(ann, scroll=True): redraw = True
            
            if redraw: self._blit_redraw()

    def _migrate_annotation_positions(self, axes, peak_dict, coordinate_key):
        if self.plot_data.get(coordinate_key, "offset_points") != "axes_fraction":
            return

        conversion_axes = self.ax.inset if (
            coordinate_key == "inset_annotation_coordinate_system"
            and hasattr(self.ax, "inset")
        ) else self.ax
        dpi = conversion_axes.figure.dpi
        for peak, peak_data in peak_dict.items():
            try:
                corrected_ypoints = self.corrected_ypoints[self.master.iid]
                y_position = corrected_ypoints[np.where(self.plot_data["xpoints"] == peak)[0][0]]
            except Exception:
                y_position = peak_data[1]

            anchor_position = conversion_axes.transData.transform((peak, y_position))
            text_position = conversion_axes.transAxes.transform((peak_data[2], peak_data[3]))
            peak_data[2], peak_data[3] = (
                (text_position - anchor_position) * 72 / dpi
            )

        self.plot_data[coordinate_key] = "offset_points"

    def _free_text_data(self):
        if self.master.plottype in ["MultiPlot", "Assay"]:
            return self.multiplot_data["PlotOptions"]["free_text_dict"]
        return self.plot_data["free_text_dict"]

    def _free_text_position(self, axes, text_data):
        if text_data.get("coordinate_system") == "axes_fraction":
            return text_data["x"], text_data["y"]

        figure_position = axes.figure.transFigure.transform((text_data["x"], text_data["y"]))
        axes_position = axes.transAxes.inverted().transform(figure_position)
        text_data["x"], text_data["y"] = map(float, axes_position)
        text_data["coordinate_system"] = "axes_fraction"
        return text_data["x"], text_data["y"]

    def create_free_texts(self, axes=None):
        if axes is None:
            axes = self.ax

        figure = getattr(axes, "figure", self.fig)

        # Remove previously created free-text artists to avoid duplicates on refresh
        for t in list(getattr(figure, "texts", [])):
            if getattr(t, "master", None) is self and getattr(t, "free_text_id", None) is not None:
                t.remove()

        if axes == self.ax:
            self.free_texts = {}

        for text_id, text_data in self._free_text_data().items():

            if text_data["text"].strip() == "":
                self.master.after_idle(self._free_text_data().pop, text_id)
                continue
            
            label = autoscripts(text_data["text"], 
                                self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")

            x_position, y_position = self._free_text_position(axes, text_data)
            text = figure.text(x_position,
                               y_position,
                               label,
                               fontsize=self.scale_artist_size(text_data["fontsize"], axes=axes),
                               font=text_data["font"],
                               color=text_data["color"],
                               horizontalalignment=text_data["alignment"],
                               picker=True,
                               clip_on=True,
                               transform=axes.transAxes,
                               bbox=dict(boxstyle="round,pad=0.4",
                                         facecolor="white",
                                         edgecolor="gray",
                                         linewidth=self.scale_artist_size(1.0, axes=axes),
                                         alpha=text_data["border_alpha"]) if text_data["border"]
                               else None,)
            
            text.master = self
            text.free_text_id = text_id
            
            if axes == self.ax:
                text._draggable = custom_DraggableText(text, use_blit=True)
                self.free_texts[text_id] = text

    def save_free_text_position(self, artist):
        text_data = self._free_text_data()[artist.free_text_id]
        text_data["x"], text_data["y"] = map(float, artist.get_position())
        text_data["coordinate_system"] = "axes_fraction"
        self.master.save_to_db()

    def _create_text_editor(self, artist, text, x_corner, y_corner, *, fontsize, font, color=None, inaxes=None, free_text_editor=False):

        # Hide the original artist while the text field is active to avoid drawing duplicates.
        artist.set_color((0,0,0,0))
        self._blit_redraw()

        if font == "sans serif":
            mpl_font = mpl.font_manager.FontProperties().get_name()
        else:
            mpl_font = font

        mpl_dpi = self.canvas.figure.get_dpi()
        screen_dpi = self.master.winfo_fpixels("1i")
        scaled_font_size = floor(self.scale_artist_size(
            fontsize, axes=inaxes if inaxes is not None else artist.axes
        ) * (mpl_dpi / screen_dpi))

        tk_font = tk.font.Font(family=mpl_font, size=scaled_font_size)
        text_per_line = text.split("\n")
        width = max(1, max(self.calculate_character_size_from_str(tk_font, line) for line in text_per_line))
        height = max(1, len(text_per_line))

        editor = tk.Text(master=self.master.canvas_widget, font=tk_font, height=height)
        editor.font = tk_font
        if color is None:
            color = "black"
        editor.config(width=width, bg="white", fg=color, insertbackground="black",
                      highlightthickness=0, padx=0, pady=0, borderwidth=0)
        
        editor.insert("1.0", text)
        editor.tag_add("alignment", "1.0", "end")

        if free_text_editor:
            alignment = self._free_text_data()[artist.free_text_id]["alignment"]
            editor.tag_configure("alignment", justify=alignment)
            
        else:
            editor.tag_configure("alignment", justify="center")

        editor.min_width = width
        editor.min_height = height
        editor.bind("<Return>", self.pick_on_return)
        editor.bind("<FocusOut>", self.pick_on_focus_out)
        editor.bind("<MouseWheel>", self.pick_on_mousewheel)
        editor.bind("<<Modified>>", self.pick_on_modified)
        editor.finish_text_edit = self.finish_text_edit
        editor.pick_on_modified = self.pick_on_modified
        editor.blit_redraw = self._blit_redraw
        editor.edit_modified(False)
        editor.artist = artist
        editor.inaxes = inaxes if inaxes is not None else getattr(artist, "axes", None)
        editor.free_text_editor = free_text_editor
        editor.focus()
        self.pick_text = editor

        if free_text_editor:
            if self.editor_menu is not None:
                self.editor_menu.destroy()
                self.editor_menu = None

            text_data = self._free_text_data()[artist.free_text_id]

            self.editor_menu = Editor_Menu(self.master, editor, text_data, artist=artist)
            self.editor_menu.center_id = self.editor_menu.after_idle(self.editor_menu.center_on_artist)

            if text == "  ":
                self.master.after_idle(editor.delete, "1.0", "end")

        else:
            
            editor.place(x=x_corner, y=y_corner)

        self.master.unbind_controls()   

        return editor

    def edit_free_text(self, artist):
        if self.pick_text:
            if getattr(self.pick_text, "free_text_editor", False):
                self.finish_text_edit()
            else:
                self.pick_on_focus_out()

        text = artist.get_text()

        text_id = artist.free_text_id
        text_data = self._free_text_data()[text_id]

        fontsize = text_data["fontsize"]
        font = text_data["font"]
        color = text_data["color"]

        self._create_text_editor(artist, text, None, None,
                                fontsize=fontsize, font=font, color=color,
                                inaxes=artist.axes, free_text_editor=True)

    def finish_text_edit(self, event=None):
        
        editor = event.widget if event is not None and hasattr(event, "widget") else self.pick_text
        if editor is None:
            return

        artist = editor.artist
        text = editor.get("1.0", "end-1c")

        if self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True":
            new_text = text.replace("\n", "\\n")

        if getattr(editor, "free_text_editor", False):
            if self.editor_menu is not None:
                self.editor_menu.destroy()
                self.editor_menu = None

            if new_text.strip() == "":
                if DEBUG: print("Free text is only whitespace. Removing free text...")
                self._free_text_data().pop(artist.free_text_id, None)
                self.free_texts.pop(artist.free_text_id, None)
                artist.remove()
                editor.destroy()
                self.pick_text = None
                self.master.bind_controls()
                self.master.save_to_db()
                self._blit_redraw()
                return
            
            self._free_text_data()[artist.free_text_id]["text"] = new_text

        else:
            x, _ = artist.xy
            if new_text == "":
                if DEBUG: print("Reverting to standard content")
                new_text = str(round(float(x), 1))

            if editor.inaxes == self.ax:
                self.plot_data["peak_dict"][x][0] = new_text
            elif self.insetplotted and editor.inaxes == self.ax.inset:
                self.plot_data["inset_peak_dict"][x][0] = new_text

        label = autoscripts(new_text, 
                            self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")
        artist.set_text(label)

        if isinstance(artist, mpl.text.Text) and not isinstance(artist, mpl.text.Annotation):
            artist.set_color(self._free_text_data()[artist.free_text_id]["color"])
            artist.set_fontsize(self.scale_artist_size(self._free_text_data()[artist.free_text_id]["fontsize"], axes=self.ax))
            artist.set_fontfamily(self._free_text_data()[artist.free_text_id]["font"])
            artist.set_ha(self._free_text_data()[artist.free_text_id]["alignment"])
            artist.set_bbox(dict(boxstyle="round,pad=0.4", 
                                 facecolor="white", 
                                 edgecolor="gray",
                                 linewidth=self.scale_artist_size(1.0, axes=self.ax),
                                 alpha=self._free_text_data()[artist.free_text_id]["border_alpha"]) if self._free_text_data()[artist.free_text_id]["border"]
                            else None)
        else:
            artist.set_color((0,0,0,1))

        editor.destroy()
        self.pick_text = None
        self.master.bind_controls()
        if artist in self.annotations + self.iannotations:
            self.master.refreshTree()
        self.master.save_to_db()
        self._blit_redraw()
        
    def create_annotations(self, axes, inset: bool, automatic_scripts: bool):
        if inset:
            peak_dict = self.plot_data["inset_peak_dict"]
            rotation = self.master.inset_vlabels.get()
        else:
            peak_dict = self.plot_data["peak_dict"]
            rotation = self.master.vlabels.get()

        scale = self.get_scale(figure=axes.figure)
        if inset:
            # Scale the fontsize for the inset axes, but the scaling has to be based on the main axes therefore only change to axes.inset after this has been done
            fontsize = self.scale_artist_size(self.plot_data["inset_fontsize"], axes=axes)
            axes = axes.inset
        else:
            fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=axes)

        # Replace annotate method from the axes object with a custom method that uses PeptiXPlots custom blitting logic
        self._bind_custom_annotation(axes)
        
        for annotations in peak_dict:

            try:
                corrected_ypoints = self.corrected_ypoints[self.master.iid]
                ann_y = corrected_ypoints[np.where(self.plot_data["xpoints"] == annotations)[0][0]]
            except Exception as e:
                if DEBUG: print("Error computing annotation y position:", e)
                ann_y = peak_dict[annotations][1]

            label = autoscripts(peak_dict[annotations][0], automatic_scripts)

            default_position = self.default_annotation_position(axes, annotations, ann_y)
            arrowprops = dict(arrowstyle="-", color="gray") if not np.allclose(
                (peak_dict[annotations][2], peak_dict[annotations][3]), default_position
            ) else None

            offset_x, offset_y = scale * peak_dict[annotations][2], scale * peak_dict[annotations][3]
        
            ann = axes.annotate(text=label,
                                xy=(annotations,ann_y), xycoords="data",
                                xytext=(offset_x, offset_y), textcoords="offset points",
                                ha="center",
                                arrowprops=arrowprops,
                                rotation=rotation,
                                fontsize=fontsize,
                                font=self.master.plotoptions_data[self.master.plottype]["font"]
                                )
            
            if axes == self.ax or (inset and axes == self.ax.inset):
                ann.master = self

                # Only make the annotation draggable if the toolbar is not in a picking mode of any kind right now
                if self.toolbar.mode not in [_Mode.PEAKS, _Mode.INT, _Mode.TXT]:
                    ann.draggable(True, use_blit=True)

                if inset: self.iannotations.append(ann)
                else: self.annotations.append(ann)
            
            # In case of the export figure, check for visibility on the current loaded plot
            else:
                visibility = True
                annotation_list = self.iannotations if inset else self.annotations 
                
                for artist in annotation_list:
                    if artist.xy == (annotations,ann_y) and artist.get_text() == label:
                        visibility = artist.get_visible()
                        break
                ann.set_visible(visibility)

        # Callback for Integration Selector
    def integrate(self, xclick, xrelease, color = None, skip_save=False):

        # Return if click and release were at the same position
        if xclick == xrelease: return

        # find indices of the xpositions
        xmin_ind, xmax_ind = find_indexes(xclick,xrelease,self.plot_data["xpoints"])

        # xmin_ind and xmax_ind are fallback values in case x1 and x2 yield the same index in the np.array
        if xmin_ind == 0 and xmax_ind == -1: return

        xmin, xmax, xpoints, ypoints, color = self.draw_polygon(xclick, xrelease, self.ax, color)

        integrated = trapezoid(ypoints, x = xpoints)

        # Calculate the percentage of the areas
        sum_for_area = integrated

        # Make sure that plottype is HPLC
        if self.master.plottype != "HPLC":
            return
        
        for peak in self.plot_data["integral_dict"]:
            # Check whether the peak should be included
            if self.plot_data["integral_dict"][peak][4] == "Yes":
                sum_for_area += self.plot_data["integral_dict"][peak][2]

        # Update all peaks in the dictionary
        for peak in self.plot_data["integral_dict"]:
            # Check whether the peak should be included
            if self.plot_data["integral_dict"][peak][4] == "Yes":
                self.plot_data["integral_dict"][peak][3] = self.plot_data["integral_dict"][peak][2]/sum_for_area*100
            elif self.plot_data["integral_dict"][peak][4] == "No":
                self.plot_data["integral_dict"][peak][3] = float(0.00)
    
        #save Information for integration in dictionary with following format:
        # center of peak: (X1, X2, Area, Percentage, Include?)
        self.plot_data["integral_dict"].update({str((xmax+xmin)/2):[xmin, xmax, integrated, integrated/sum_for_area*100, "Yes", color]})

        if not skip_save: self.master.save_to_db()

        # This needs to be done so that there are no weird artifacts of the selectors
        # Update the canvas, but only using after, as to not trigger too many unnecessary redraws
        # Cancel previous request if called again
        if self._blit:
            self.master.after_cancel(self._blit)
        # Schedule a new blit-based redraw
        self._blit = self.master.after(25, lambda: [self.master.refreshTree(), self._blit_redraw(), self.IntegrateSelector.set_active(self.toolbar.mode == _Mode.INT)])
        
        
    def draw_polygon(self, x1, x2, axes, color = None):

        corrected_ypoints = self.corrected_ypoints[self.master.iid]

        if self.plot_data["integration_type"] not in ["linear","constant","manual"]:
            approximate_baseline = True
        else:
            approximate_baseline = False

        # find indices of the xpositions
        xmin_ind, xmax_ind = find_indexes(x1,x2,self.plot_data["xpoints"])

        # xmin_ind and xmax_ind are fallback values in case x1 and x2 yield the same index in the np.array
        if xmin_ind == 0 and xmax_ind == -1: return
            
        xmin, xmax = self.plot_data["xpoints"][xmin_ind], self.plot_data["xpoints"][xmax_ind]
        ymin, ymax = corrected_ypoints[xmin_ind], corrected_ypoints[xmax_ind]

        if not approximate_baseline:

            # get np_arrays for x and ypoints with just the important data points
            xpoints = self.plot_data["xpoints"][xmin_ind:xmax_ind+1].copy()
            ypoints = corrected_ypoints[xmin_ind:xmax_ind+1].copy()

            if self.plot_data["integration_type"] == "linear":

                ### Integration is done by assuming a constant baseline from 5 to 40
                # Calculate the baseline
                xmin_ind_baseline, xmax_ind_baseline = find_indexes(self.plot_data["integration_info"][self.plot_data["integration_type"]][0],
                                                                    self.plot_data["integration_info"][self.plot_data["integration_type"]][1],
                                                                    self.plot_data["xpoints"])
                xmin_baseline, xmax_baseline = self.plot_data["xpoints"][xmin_ind_baseline], self.plot_data["xpoints"][xmax_ind_baseline]
                ymin_baseline, ymax_baseline = corrected_ypoints[xmin_ind_baseline], corrected_ypoints[xmax_ind_baseline]

                # Calculate a straight function from xmin to xmax (y = mx + b)
                m = (ymax_baseline-ymin_baseline)/(xmax_baseline-xmin_baseline)
                b = ymin_baseline - m * xmin_baseline

            elif self.plot_data["integration_type"] == "manual":
                # Check which axles belong to the selected region
                x_data_baseline = self.plot_data["integration_info"][self.plot_data["integration_type"]][0]
                y_data_baseline = self.plot_data["integration_info"][self.plot_data["integration_type"]][1]
                left_boundary = bisect_right(x_data_baseline, x1)
                right_boundary = bisect_left(x_data_baseline, x2)
                # Keep track whether the left-most or right-most axle is already important. If so, extrapolate from the left-most and 2nd left-most axle and the same for the right-most axle 
                left_most = False
                right_most = False
                if left_boundary > 0: 
                    left_boundary -= 1
                else:
                    left_most = True

                if right_boundary < len(x_data_baseline):
                    right_boundary += 1
                else:
                    right_most = True

                x_data_baseline_selected = x_data_baseline[left_boundary:right_boundary]
                y_data_baseline_selected = y_data_baseline[left_boundary:right_boundary]

                # get np_arrays for x and ypoints with just the important data points
                xpoints = self.plot_data["xpoints"][xmin_ind:xmax_ind+1].copy()

                if left_most and x_data_baseline[1] not in x_data_baseline_selected:
                    x_data_baseline_selected.insert(1, x_data_baseline[1])
                    y_data_baseline_selected.insert(1, y_data_baseline[1])

                if right_most and x_data_baseline[-2] not in x_data_baseline_selected:
                    x_data_baseline_selected.insert(-2, x_data_baseline[1])
                    y_data_baseline_selected.insert(-2, y_data_baseline[1])

                # Now different cases are necessary, if x_data_baseline_selected only has two items, this is basically the regular linear case
                # Because of how left_most and right_most are handled, this ideally should always have at least two list items
                if len(x_data_baseline_selected) == 2:

                    x1_baseline, x2_baseline = x_data_baseline_selected[0], x_data_baseline_selected[1]
                    y1_baseline, y2_baseline = y_data_baseline_selected[0], y_data_baseline_selected[1]

                    # Calculate a straight function from xmin to xmax (y = mx + b)
                    m = (y2_baseline-y1_baseline)/(x2_baseline-x1_baseline)
                    b = y1_baseline - m * x1_baseline

                    xpoints = np.concatenate(([xmin],xpoints,[xmax]))
                    # Correct ypoints for the baseline
                    ypoints = np.concatenate(([m*xmin + b],ypoints,[m*xmax + b]))
                    ypoint_integration_correction = (m * xpoints + b)

                # This should be the only other possible case
                elif len(x_data_baseline_selected) > 2:

                    # Find all indices in the xpoints array to make the correct split
                    indices = np.searchsorted(xpoints, x_data_baseline_selected)
                    x_sections = [array for array in np.split(xpoints, indices) if array.size > 0]

                    y_sections_correction = []
                    xpoint_list = [xpoints]
                    ypoint_list = [ypoints]

                    for count, section in enumerate(x_sections):

                        x1_baseline, x2_baseline = x_data_baseline_selected[count], x_data_baseline_selected[count+1]
                        y1_baseline, y2_baseline = y_data_baseline_selected[count], y_data_baseline_selected[count+1]
    
                        # Calculate a straight function from xmin to xmax (y = mx + b)
                        m = (y2_baseline-y1_baseline)/(x2_baseline-x1_baseline)
                        b = y1_baseline - m * x1_baseline

                        y_sections_correction.append(m*section+b)

                        # The axles for each section should be x_data_baseline_selected[count] and count+1
                        if count == 0:
                            # Because of how selection is done, the first section must be the one relevant for the bottom-left integration point
                            xpoint_list.insert(0, [xmin])
                            ypoint_list.insert(0, [m*xmin + b])
                            y_sections_correction.insert(0, [m*xmin + b])

                        elif count == len(x_sections)-1:
                            # Because of how selection is done, the last section must be the one relevant for the bottom-right integration point
                            xpoint_list.append([xmax])
                            ypoint_list.append([m*xmax + b])
                            y_sections_correction.append([m*xmax + b])

                        if count < len(x_sections)-1:
                            xpoint_list.insert(0, [x_data_baseline_selected[count+1]])
                            ypoint_list.insert(0, [y_data_baseline_selected[count+1]])
                            y_sections_correction.insert(0, [y_data_baseline_selected[count+1]])

                    ypoint_integration_correction = np.concatenate(y_sections_correction)
                    xpoints = np.concatenate(xpoint_list)
                    ypoints = np.concatenate(ypoint_list)
                # Fallback so that there are no weird errors in case something is not like it should be
                else:
                    m = 0
                    b = 0

                    xpoints = np.concatenate(([xmin],xpoints,[xmax]))
                    # Correct ypoints for the baseline
                    ypoints = np.concatenate(([m*xmin + b],ypoints,[m*xmax + b]))
                    ypoint_integration_correction = (m * xpoints + b)

            elif self.plot_data["integration_type"] == "constant":
                m = 0
                b = self.plot_data["integration_info"]["constant"]

            if self.plot_data["integration_type"] != "manual":
                xpoints = np.concatenate(([xmin],xpoints,[xmax]))
                # Correct ypoints for the baseline
                ypoints = np.concatenate(([m*xmin + b],ypoints,[m*xmax + b]))
                ypoint_integration_correction = (m * xpoints + b)

        else:
            
            ### Integration is done in a straight line
            
            # get np_arrays for x and ypoints with just the important data points
            xpoints = self.plot_data["xpoints"][xmin_ind:xmax_ind].copy()
            ypoints = corrected_ypoints[xmin_ind:xmax_ind].copy()

            # Calculate a straight function from xmin to xmax (y = mx + b)
            m = (ymax-ymin)/(xmax-xmin)
            b = ymin - m * xmin

            ypoint_integration_correction = (m * xpoints + b)

        # Correct ypoints to start on y=0, so that integration is done properly
        ypoints_corrected = ypoints - ypoint_integration_correction

        # Draw a polygon where the integration was done
        polygon, = axes.fill(xpoints, ypoints, rasterized=True)

        if axes == self.ax:
            self.polygons.append(polygon)

        if color == None:

            if DEBUG: print("None")
            
            color = polygon.get_fc()
        elif color == "no color" and len(self.plot_data["integral_dict"][str((xmax+xmin)/2)]) < 6:

            if DEBUG: print("no color")
            color = polygon.get_fc()
            self.plot_data["integral_dict"][str((xmax+xmin)/2)].append(color)
        else:

            if DEBUG: print("Color known")
            polygon.set_fc(color)

        if axes == self.ax:
            # Update the canvas, but only using after, as to not trigger too many unnecessary redraws
            # Cancel previous request if called again
            if self._blit:
                self.master.after_cancel(self._blit)
            # Schedule a new blit-based redraw
            self._blit = self.master.after(25, lambda: self._blit_redraw())

        return xmin, xmax, xpoints, ypoints_corrected, color

    def simulate_spectrum(self, chemical_formula, axes, intensity=100, width=0.1, charge=1):

        chemical_formula = self.master.check_if_peptide(chemical_formula)

        # Convert the entered formula into a chemical Formula
        f = Formula(chemical_formula)
        spectrum = f.spectrum(min_intensity=0.01)

        # Add them all together as one dictionary
        spect_dict = spectrum.asdict()

        # Get the xpoints of the current spectrum to calculate the ypoints for the simulated spectrum
        width = float(width)
        step = width / 10

        x_point_arrays = []

        # The limit how far away from the center in multiples of the fwhm the simulation should be calculated
        limit = np.arctan(10)

        for peak in spect_dict:
            x0 = spect_dict[peak][0] / abs(int(charge))
            u = np.linspace(-limit, limit, 100)
            arr = x0 + width * np.tan(u)
            x_point_arrays.append(arr)

        # Combine all xpoint arrays
        xpoints = np.unique(np.concatenate(x_point_arrays))
        xpoints.sort()
        ypoints = np.zeros_like(xpoints)

        # Always put intensity relative to the maximum intensity of the plot
        for key in spect_dict:
            ypoints += lorentzian(xpoints, float(intensity)/100*self.max_y_val*spect_dict[key][2]/100, spect_dict[key][0]/abs(int(charge)), width/2)
            
        simulation, = axes.plot(xpoints, 
                                ypoints,
                                linewidth=self.scale_artist_size(float(self.master.plotoptions_data["MALDI"]["lnwdth"]), axes),
                                color=self.master.plotoptions_data["MALDI"]["simulation_clr"],
                                )

        if axes is self.ax:
            self.simulation.append(simulation)
        elif hasattr(self.ax, "inset") and axes is self.ax.inset:
            self.isimulation.append(simulation)

    # set a Callback for Line Selection for Peak Picking
    def pick_peaks(self, eclick, erelease, inset=False):

        #get cursor positions for click and release
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata

        max_x_val, max_y_val = get_maximum(x1, x2, self.plot_data["xpoints"], self.corrected_ypoints[self.master.iid])

        #check whether maximum is in the boundaries of the marked rectangle
        if max_y_val >= y1 and max_y_val <= y2:

            if not inset:
                #save List in dictionary with following format:
                # x-value of peak: (Label [Standard: x-value rounded to one decimal point], y-value of peak, offset x, offsety)
                if not isinstance(self.plot_data["peak_dict"], dict): self.plot_data["peak_dict"] = dict(self.plot_data["peak_dict"])
                main_position = self.default_annotation_position(self.ax, max_x_val, max_y_val)
                self.plot_data["peak_dict"].update({max_x_val:[str(round(max_x_val,1)),max_y_val,*main_position]})
                if self.insetplotted and self.plot_data["mirror_annotations"]:
                    inset_position = self.default_annotation_position(self.ax.inset, max_x_val, max_y_val)
                    self.plot_data["inset_peak_dict"].update({max_x_val:[str(round(max_x_val,1)),max_y_val,*inset_position]})
                
            else:
                inset_position = self.default_annotation_position(self.ax.inset, max_x_val, max_y_val)
                self.plot_data["inset_peak_dict"].update({max_x_val:[str(round(max_x_val,1)),max_y_val,*inset_position]})
        
            self.master.refreshTree()

            self.refresh_annotations(self.ax)

            # This needs to be done so that there are no weird artifacts of the selectors
            self._blit_redraw(self.ax)
            self.PeakSelector.set_active(True)
            if self.insetplotted:
                self.InsetPeakSelector.set_active(True)

    def pick_inset_peaks(self, eclick, erelease):
        self.pick_peaks(eclick=eclick, erelease=erelease, inset=True)

    def on_mousewheel(self, event):

        if self.pick_text:
            if getattr(self.pick_text, "free_text_editor", False):
                self.master.after_idle(self.finish_text_edit)
            else:
                self.master.after_idle(self.pick_on_focus_out)

        scroll = event.step/20

        inset_axes = getattr(self.ax, "inset", None)
        if self.insetplotted and event.inaxes == self.ax.inset:
            # Change scale on scrolling when hovering over the inset
            self.plot_data["inset_y_axis_max_percent"] *= (1 - scroll)
            # Get current ylim of inset_axis 
            bot, top = self.ax.inset.get_ylim()
            # Modify it according to scroll
            top *= (1-scroll)
            # Set the ylim according to the modified value
            self.ax.inset.set_ylim(top=top)
            # Reset the y_height variable
            self.master.y_height_inset.set(self.plot_data["inset_y_axis_max_percent"])
            
        else:
            # Change scale on scrolling
            self.plot_data["y_axis_max_percent"] *= (1 - scroll)
            bot, top = self.ax.get_ylim()

            # Do the calculation of the ylim based on the current bounds, to make this work together with zooming
            top *= (1 - scroll)
            if self.master.plottype == "CD" or self.master.plottype == "Tm":
                bot *= (1 - scroll)
                # Change autoadjust to false
                self.plot_data["autoadjust_y"] = False
                self.master.adjust_y.set(False)
            self.ax.set_ylim(bottom=bot, top=top)

            # Reset the ylim spans
            if self.toolbar.is_home:
                self.master.ylim_min.set(bot)
                self.master.ylim_max.set(top)

                self.plot_data["y_axis_min"] = float(bot)
                self.plot_data["y_axis_max"] = float(top)

            # Update the yticks
            if self.plot_data["show_yticks"]:
                self.ax.yaxis.set_major_locator(mpl.ticker.AutoLocator())
                major_locator = self.ax.yaxis.get_major_locator()
                tick_values = major_locator()

                offset = tick_values[0]
                if len(tick_values) >= 2:
                    distance = abs(tick_values[1] - tick_values[0])
                else:
                    distance = abs(self.plot_data["y_axis_max"] - self.plot_data["y_axis_min"])

                self.plot_data["distance_yticks"] = distance
                self.master.distance_yticks.set(distance)

                offset_distance_ratio = abs(offset)/distance
                if offset_distance_ratio.is_integer():
                    offset = 0
                else:
                    fraction = offset_distance_ratio % 1
                    offset = fraction*distance
                self.plot_data["offset_yticks"] = offset
                self.master.offset_yticks.set(offset)

                major_locator = mpl.ticker.MultipleLocator(base=self.plot_data["distance_yticks"],
                                                            offset=self.plot_data["offset_yticks"])

        self._blit_redraw()

        # If an annotation or free text is outside of the axes, move it back inside or hide it and schedule another blit_redraw
        redraw = False

        annotations = self.annotations + self.iannotations if self.insetplotted else self.annotations

        for ann in annotations:
            if not self.is_artist_in_axes(ann, scroll=True): redraw = True

        if redraw: self._blit_redraw()

        # Save information to database after some time
        # Cancel previous request if called again
        if self._save:
            self.master.after_cancel(self._save)

        # Schedule a new save request
        self._save = self.master.after(500, self.master.save_to_db)

    def is_artist_in_axes(self, artist, scroll=False):
    # Check whether the annotation artist is inside the axes, if not move it back inside

        inside = True
        updated = False

        # Artist needs to be visible so the calculation is accurate
        if (artist.axes == self.ax or
            (self.insetplotted and artist.axes == self.ax.inset)) and not artist.get_visible():

            artist.set_visible(True)

            artist.axes.draw_artist(artist)
            # Update the canvas
            self.canvas.blit(self.fig.bbox)

        # Get the limits of the current axes
        xmin, xmax = artist.axes.get_xlim()
        ymin, ymax = artist.axes.get_ylim()

        # Create a virtual text on the plot, to get the exact size of the text in data coordinates
        fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=self.ax)
        font = self.master.plotoptions_data[self.master.plottype]["font"]
        # Create a text to get the exact bbox of the annotation text
        text_object = artist.axes.text(x=0, y=0,
                                       s=artist.get_text(), 
                                       fontsize=fontsize, 
                                       font=font, 
                                       color="white", 
                                       horizontalalignment="left", 
                                       verticalalignment="bottom",
                                       rotation=artist.get_rotation())
        
        text_bbox = text_object.get_tightbbox()
        text_object.remove()

        text_width, text_height = text_bbox.x1, text_bbox.y1

        # x1 and y1 give the correct width in data coordinates since x0 and y0 are 0, perform transform
        text_width, text_height = artist.axes.transData.inverted().transform((text_width, text_height))

        # Change the limits to account for the size of the text, so the entire annotation stays inside at all times
        xmin += text_width/2
        xmax -= text_width/2
        ymax -= text_height
        
        # Get the x and y coordinates of the artist in display coordinates
        anchor_position = artist.axes.transData.transform(artist.xy)
        text_offset = np.asarray(artist.xyann) * artist.figure.dpi / 72
        x_offset, y_offset = anchor_position + text_offset
        
        # Convert to data coordinates
        x, y = artist.axes.transData.inverted().transform((x_offset, y_offset))
        
        # Keep it inbetween min and max
        x_enforced = max(min(x, xmax), xmin)
        y_enforced = max(min(y, ymax), ymin)

        if not scroll:
            if x != x_enforced or y != y_enforced:
                inside = False
                if DEBUG: print("Annotation out of bounds. Moving back into axes.")
        else:
            if y != y_enforced:
                inside = False
                if DEBUG: print("Annotation out of bounds. Hiding annotation.")
        
        # Convert to display coordinates
        x_enforced, y_enforced = artist.axes.transData.transform((x_enforced, y_enforced))
        # Convert to the format necessary for xyann
        x_offset, y_offset = (
            np.asarray((x_enforced, y_enforced)) - anchor_position
        ) * 72 / artist.figure.dpi
        
        # Do not replace the offset if the cause for moving outside of the axes is scrolling
        if not scroll:
            # Get the scale of the axes to scale the offset accordingly
            scale = self.get_scale(figure=artist.axes.figure)
            x_offset /= scale
            y_offset /= scale

            # However, scale the offset again here because otherwise the artist gets displaced every time it is moved
            artist.xyann = (x_offset * scale, y_offset * scale)

        # Check whether ann is in self.ax or self.ax.inset
        if artist.axes == self.ax:
            peak_dict = self.plot_data["peak_dict"]
            annotations = self.annotations
        elif artist.axes == self.ax.inset:
            peak_dict = self.plot_data["inset_peak_dict"]
            annotations = self.iannotations

        
        artist_x, _ = artist.xy

        if not scroll:

            # check whether the annotation has actually been moved
            # When scrolling there is some error in the later digits, therefore round all values to the 10th decimal digit
            if round(x_offset, 10) != round(peak_dict[artist_x][2], 10) or round(y_offset, 10) != round(peak_dict[artist_x][3], 10):
                # Update the dictionary
                needs_redraw = False

                default_position = self.default_annotation_position(artist.axes, *artist.xy)
                if np.allclose(peak_dict[artist_x][2:4], default_position):
                    ann = artist.axes.annotate(text=artist.get_text(),
                                               xy=artist.xy, xycoords="data",
                                               xytext=artist.xyann, textcoords="offset points",
                                               ha=artist.get_ha(),
                                               arrowprops=dict(arrowstyle="-", color="gray"),
                                               rotation=artist.get_rotation(),
                                               fontsize=artist.get_fontsize(),
                                               font=artist.get_font()
                                        )
                    
                    artist.remove()
                    annotations.remove(artist)
                    annotations.append(ann)
                
                    ann.master = self
                    ann.draggable(True, use_blit=True)
                    needs_redraw = True

                peak_dict[artist_x][2] = x_offset
                peak_dict[artist_x][3] = y_offset
                updated = True

                if needs_redraw: 
                    if self._blit:
                        self.master.after_cancel(self._blit)
                    # Schedule a new blit-based redraw
                    self._blit = self.master.after(25, lambda: self._blit_redraw())

        else:
            if inside:
                if not artist.get_visible():
                    artist.set_visible(True)
            else:
                artist.set_visible(False)

        if updated:
            # Save information to database after some time
            # Cancel previous request if called again
            if self._save:
                self.master.after_cancel(self._save)

            # Schedule a new save request
            self._save = self.master.after(2500, self.master.save_to_db)

        return inside

    def on_pick(self, event):

        if event.artist == self.HPLC_baseline and event.mouseevent.inaxes:

            x, y = event.mouseevent.xdata, event.mouseevent.ydata

            self.plot_data["integration_info"]["manual"][0].append(x)
            self.plot_data["integration_info"]["manual"][1].append(y)

            pairs = sorted(zip(self.plot_data["integration_info"]["manual"][0],
                               self.plot_data["integration_info"]["manual"][1]))

            xpoints_sorted, ypoints_sorted = map(list, zip(*pairs))

            self.plot_data["integration_info"]["manual"][0] = xpoints_sorted
            self.plot_data["integration_info"]["manual"][1] = ypoints_sorted

            self.refresh_integration()

        elif event.artist in self.manual_HPLC_baseline_axles:

            self.picked_axle = True
            # Find the point closest to the click event
            x, y = event.mouseevent.xdata, event.mouseevent.ydata

            if y is None or x is None: return

            distance = np.inf
            closest_x = None
            closest_y = None

            for x_data, y_data in zip(self.plot_data["integration_info"]["manual"][0], self.plot_data["integration_info"]["manual"][1]):
                y_diff = y_data - y
                x_diff = x_data - x

                new_distance = np.sqrt(x_diff**2 + y_diff**2)

                if new_distance < distance:
                    distance = new_distance
                    closest_x = x_data
                    closest_y = y_data

            if closest_x is None or closest_y is None: return

            # Right click is used to remove axles again, therefore find the point closest to the click event
            if event.mouseevent.button == 3:
                # Only remove the axle if there are more than just two axles
                if len(self.plot_data["integration_info"]["manual"][0]) > 2:
                    if DEBUG: print("Removing axle")
                    self.plot_data["integration_info"]["manual"][0].remove(closest_x)
                    self.plot_data["integration_info"]["manual"][1].remove(closest_y)

                    self.refresh_integration()
                else:
                    if DEBUG: print("At least two axles must remain")

        else:

            if (event.mouseevent.button == 1 and event.mouseevent.dblclick and
                    event.artist in self.free_texts.values()):
                self.master.after_idle(self.edit_free_text, event.artist)
                return

            if event.mouseevent.button == 1 and event.mouseevent.dblclick != True and isinstance(event.artist, mpl.text.Annotation):
                self.selected_artist = event.artist
                return
            elif event.mouseevent.button != 1 or event.mouseevent.dblclick != True:
                self.selected_artist = None
                return
            
            if self._pick:
                self.master.after_cancel(self._pick)

            self._pick = self.master.after_idle(self.on_pick_after, event)

    # After method, to be triggered in on_pick to make sure, that one double click does not cause two entries to appear
    def on_pick_after(self, event):

        self._pick = None
        self.selected_artist = None
        artist = event.artist
        if isinstance(artist, mpl.legend.Legend): return
        text = artist.get_text()

        axes = artist.axes

        bbox = artist.get_tightbbox()
        # Get annotation position in fig coordinates
        x, y = axes.transData.transform(artist.xy)

        # Get the canvas height
        canvas_height = event.canvas.figure.bbox.height

        # This needs to be scaled once here so that the text_object for the calculation of the correct position is correct
        fontsize = self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=axes)
        font = self.master.plotoptions_data[self.master.plottype]["font"]

        # Create a text to get the exact bbox of the annotation text
        text_object = mpl.text.Text(x=0, y=0, text=text, fontsize=fontsize, font=font)
        text_object.set_figure(self.fig)
        text_bbox = text_object.get_tightbbox()

        text_width, text_height = text_bbox.width, text_bbox.height

        x0 = bbox.x0
        x1 = bbox.x1
        y0 = bbox.y0
        y1 = bbox.y1

        # First check which value is further from the anchor of the annotation
        diffx0 = abs(x-x0)
        diffx1 = abs(x-x1)
        diffy0 = abs(y-y0)
        diffy1 = abs(y-y1)
        
        if diffx0 > diffx1:
            x_corner = x0
        else:
            x_corner = x1

        if diffy0 > diffy1:
            y_corner = y0
        else:
            y_corner = y1

        # Top right if x_corner and y_corner are larger than x and y
        # Bottom right, if x_corner larger than x and y_corner smaller than y
        # Top left if x_corner smaller than x and y_corner larger than y

        if x_corner > x:
            x_corner -= text_width/2
            if y_corner > y:
                y_corner -= text_height
                
        else:
            x_corner += text_width/2
            if y_corner > y:
                y_corner -= text_height
                
        y_corner_inverted = canvas_height - y_corner

        # Remove LaTeX Formula from text
        text = autoscripts_reverse(text, self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")

        # Get the regular fontsize again as there is scaling in create_text_editor
        fontsize = self.master.plotoptions_data[self.master.plottype]["fontsize"]

        self._create_text_editor(artist, text, x_corner, y_corner_inverted,
                                 fontsize=fontsize, font=font,
                                 color=None, inaxes=event.mouseevent.inaxes, free_text_editor=False)

    def on_release(self, event):

        if self.toolbar.mode == _Mode.TXT:
            self.toolbar.mode = _Mode.NONE

            self.toolbar.update()
            # Check which button should be selected
            self.toolbar._update_buttons_checked()

            fig_x, fig_y = self.ax.transAxes.inverted().transform((event.x, event.y))
            text = self.fig.text(x=fig_x,
                                y=fig_y,
                                s="  ",
                                fontsize=self.scale_artist_size(self.master.plotoptions_data[self.master.plottype]["fontsize"], axes=self.ax),
                                font=self.master.plotoptions_data[self.master.plottype]["font"],
                                horizontalalignment="center",
                                animated=False,
                                visible=True,
                                clip_on=True,
                                transform=self.ax.transAxes)
            
            text_id = str(uuid.uuid4())
            self._free_text_data()[text_id] = {"text": text.get_text(),
                                               "x": float(fig_x),
                                               "y": float(fig_y),
                                               "font": text.get_font().get_name(),
                                               "fontsize": float(self.master.plotoptions_data[self.master.plottype]["fontsize"]),
                                               "color": text.get_color(),
                                               "border": False,
                                               "border_alpha": 1,
                                               "alignment": text.get_ha(),
                                               "coordinate_system": "axes_fraction",
                                               }
            text.master = self
            text.free_text_id = text_id
            text._draggable = custom_DraggableText(text, use_blit=True)
            self.free_texts[text_id] = text
            self.master.save_to_db()

            # Update the canvas
            self.ax.draw_artist(text)
            self.canvas.blit(self.fig.bbox)

            self.master.after_idle(self.edit_free_text, text)

        if self.legend is not None and self.legend._draggable is not None and self.legend._draggable.got_artist:
            self.legend._draggable.on_release(event)
            self.multiplot_data["PlotOptions"]["legend_position"] = tuple(self.legend._loc)
            self.multiplot_data["PlotOptions"]["legend_automatic_placement"] = False
            self.master.multiplot_legend_automatic_placement.set(False)

            self.master.save_to_db()

        # Update annotation dictionary according to new position of annotations
        if self.selected_artist is not None:
            if not self.is_artist_in_axes(artist=self.selected_artist):
                if self._blit:
                    self.master.after_cancel(self._blit)
                # Schedule a new blit-based redraw
                self._blit = self.master.after(0, lambda: self._blit_redraw())

            self.selected_artist = None

        if self.picked_axle:
            self.refresh_integration()
            self.picked_axle = False

    def pick_on_mousewheel(self, event):
        # Small function to give correct functionality to scrolling when hovering over a pick_text
        event.step = event.delta/120
        event.inaxes = event.widget.artist.axes

        self.on_mousewheel(event)

    def pick_on_return(self, event):

        if event.state & 0x0001:
            # Skip custom logic if Shift is pressed
            return

        else:
            # Otherwise go on with the same logic as in on_focus_out
            self.pick_on_focus_out(event, backspace=True)

    def pick_on_focus_out(self, event=None, backspace=False):
        if backspace: return self.finish_text_edit(event)

        self.master.after_idle(self.pick_on_focus_out_idle, event)

    def pick_on_focus_out_idle(self, event=None):

        focused = self.editor_menu.focus_get() if self.editor_menu is not None else None
        if DEBUG: print(f"Pick_focus_out: {focused}")

        if focused is None:
            focused = self.master.focus_get()
        if focused is None:
            self.finish_text_edit(event)
            return

        if self.editor_menu is not None and focused not in (self.editor_menu, self.editor_menu.focus_get()):
            self.finish_text_edit(event)
            return

        current = focused
        while current is not None:
            if current is self.pick_text or (self.editor_menu is not None and current is self.editor_menu):
                return
            current = getattr(current, "master", None)

        self.finish_text_edit(event)

    def pick_on_modified(self, event):

        skip_finally = False
        if DEBUG:
            print("Called pick_on_modified")
            try:
                print(event)
            except:
                print("Called pick_on_modified without event")
        text = event.widget

        # Unbind to prevent recursive calls
        text.unbind("<<Modified>>")

        try:
            # Get current content        
            content = text.get("1.0", "end-1c")
            text_per_line = content.split("\n")

            # Tag needs to be added again in case the entire text is deleting, so always add the tag again,
            # as soon as there is just 1 character in content
            if len(content) == 1:
                text.tag_add("alignment", "1.0", "end")

            old_height = text.winfo_height()
            old_width = text.winfo_width()

            if text.free_text_editor:

                text.config(height=max(len(text_per_line),
                                        1),
                            width=max(max([self.calculate_character_size_from_str(text.font, line) for line in text_per_line]),
                                    2)
                        )

            else:

                text.config(height=max(len(text_per_line),
                                        text.min_height),
                            width=max(max([self.calculate_character_size_from_str(text.font, line) for line in text_per_line]),
                                    text.min_width)
                        )

            text.update_idletasks()

            # After doing text.update_idletasks, the existance of the windows is updated and therefore must be checked here
            # to prevent errors because of stale references to the non-existing toplevel
            if text.free_text_editor:
                if text is None or self.editor_menu is None or not self.editor_menu.winfo_exists() or not text.winfo_exists():
                    if DEBUG: print("Editor or menu does not exist, aborting pick_on_modified")
                    skip_finally = True
                    return
                
            new_height = text.winfo_height()
            new_width = text.winfo_width()

            if new_height != old_height:
                height_difference = old_height - new_height
                y = text.winfo_y() + height_difference
                text.place_configure(y=y)
                if self.editor_menu is not None:
                    if self.editor_menu.center_id is None:
                        self.editor_menu.center_id = self.editor_menu.after_idle(self.editor_menu.center_on_artist)

            if new_width != old_width:
                width_difference = old_width - new_width
                x = text.winfo_x() + width_difference/2
                text.place_configure(x=x)
                if self.editor_menu is not None:
                    if self.editor_menu.center_id is None:
                        self.editor_menu.center_id = self.editor_menu.after_idle(self.editor_menu.center_on_artist)

            if text.free_text_editor:
                if self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True":
                    new_text = content.replace("\n", "\\n")
                else:
                    new_text = content

                label = autoscripts(new_text, 
                                    self.master.plotoptions_data[self.master.plottype]["automatic_scripts"]=="True")

                if label == "":
                    label = "  "

                text.artist.set_text(label)

                self._blit_redraw()

        finally:
            if skip_finally: return
            # Always rebind, even if an error occurs
            text.bind("<<Modified>>", self.pick_on_modified)
            text.edit_modified(False)

        if DEBUG: print("Done picking on modified")

    def calculate_character_size_from_str(self, font, string):

        string = str(string)

        avg_width = font.measure("0")
        string_width = font.measure(string)

        return max(1, ceil(string_width/avg_width))


    def export(self, *args):
        ## Create seperate export figure so that all figures are identical

        if getattr(self, "expfig", None) is None:
            self.expfig = plt.figure(dpi=self.fig.get_dpi())
        else:
            self.expfig.clear()
        self.expax = None

        self.expax = self.add_ax(self.expfig)

        self.refresh(axes = self.expax, refreshTree=False, mirror=False)

        if self.master.plottype == "MALDI" and self.plot_data["inset"] and hasattr(self.expax, "inset"):

            # Just to make sure, sync the ticks from the inset axes in the GUI to the expax
            major_locator = self.ax.inset.xaxis.get_major_locator()
            tick_values = major_locator()
    
            offset = tick_values[0]
            if len(tick_values) >= 2:
                distance = abs(tick_values[1] - tick_values[0])
            else:
                distance = abs(self.plot_data["inset_x_axis_max"] - self.plot_data["inset_x_axis_min"])
    
            offset_distance_ratio = abs(offset)/distance
            if offset_distance_ratio.is_integer():
                offset = 0
            else:
                fraction = offset_distance_ratio % 1
                offset = fraction*distance

            inset_x_axis_major_locator = mpl.ticker.MultipleLocator(base=distance,
                                                                    offset=offset)
            self.expax.inset.xaxis.set_major_locator(inset_x_axis_major_locator)

            # Get ylim from current plot
            inset_bot, inset_top = self.ax.inset.get_ylim()
            self.expax.inset.set_ylim(bottom=inset_bot, top=inset_top)

        # Just to make sure, sync the legend location
        self._sync_export_legend_location()