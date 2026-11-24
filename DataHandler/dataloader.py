import tkinter as tk
import tkinter.font as tkfont
import ttkbootstrap as ttk
from tkinter import filedialog as fd
from tkinter import messagebox, simpledialog
import csv
from io import StringIO
from sys import maxsize as symaxsize
from os.path import exists
import numpy as np
import pandas as pd
from tksheet import Sheet

DEBUG = False

class ImportHandler(tk.Toplevel):

    _instance = None

    def __init__(self, master, config, database):

        if ImportHandler._instance is not None:
            master.after_idle(lambda: (ImportHandler._instance.lift(), ImportHandler._instance.focus_force()))
            return
        
        super().__init__(master=master)
        ImportHandler._instance = self

        self.title("Import Settings")

        self.master = master

        self.config = config

        self.db = database

        self.plottypes = self.master.plottypes

        self.plottype = tk.StringVar(self, value=sorted(self.plottypes)[0])
        
        self.resizable(False, False)

        self.settings = (
            "delimiter",
            "decimaldelimiter",
            "linevaluestart",
            "linevalueend",
            "endatvalue",
        )

        self.import_presets = self.db.load_import_presets()
        self.selected_presets = {}
        self.preset_dirty = {}
        self.preset_base_names = {}
        self.preset_edit_names = {}
        self._updating_preset = False

        self.import_data = {}
        for plottype in self.plottypes:
            self.import_data[plottype] = {}
            for setting in self.settings:
                self.import_data[plottype][setting] = tk.StringVar(self, self.config.import_data[plottype][setting])

            self.import_presets.setdefault(plottype, {})
            self.import_presets[plottype]["Default"] = self._get_default_preset(plottype)
            self.selected_presets[plottype] = tk.StringVar(self, value="Default")
            self.preset_dirty[plottype] = False
            self.preset_base_names[plottype] = "Default"
            self.preset_edit_names[plottype] = None

        self.__create_widgets()
        for plottype in self.plottypes:
            for setting in self.settings:
                self.import_data[plottype][setting].trace_add(
                    "write",
                    lambda *_args, plot_type=plottype: self._mark_preset_dirty(plot_type),
                )

        # Dictionary for saving imported data
        self.imported_data = {}

        self.protocol("WM_DELETE_WINDOW", self.__close)
        
    def __create_widgets(self):

        #Radiobuttons for plottype
        self.radioframe = ttk.Frame(self)

        plottypes = list(self.plottypes)
        plottypes.sort()

        for plottype in plottypes:
            radiobtn = ttk.Radiobutton(self.radioframe, text=plottype, value=plottype, variable=self.plottype, command=self.__update_plottype)
            radiobtn.pack(side=tk.LEFT, expand=True, pady=10)

        self.radioframe.grid(column=0, row=0, sticky=tk.EW)

        self.notebook = ttk.Notebook(self)

        self.basic_frame = ttk.Frame(self.notebook, padding=8)
        self.advanced_frame = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.basic_frame, text="Basic Settings")
        self.notebook.add(self.advanced_frame, text="Advanced Settings")
        self.notebook.grid(column=0, row=1, sticky=tk.NSEW)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        self.__build_basic_settings()
        self.__build_advanced_settings()
        self.__build_advanced_settings_confirm_frame()
        self.__update()
        self.bind("<Button-1>", self.__clear_checkbox_focus, add="+")

    def __clear_checkbox_focus(self, event):
        checkbox_widgets = (
            self.askendatvalue,
            self.advanced_transpose_chkbtn,
            self.add_suffix_chkbtn,
        )
        if event.widget in checkbox_widgets:
            return

        focused_widget = self.focus_get()
        if focused_widget in checkbox_widgets:
            self.focus_set()

    def __build_basic_settings(self):
        # Configure grid
        self.basic_frame.columnconfigure(0, weight=1)
        self.basic_frame.columnconfigure(1, weight=1)
        self.basic_frame.rowconfigure(6, weight=1)

        # Get the currently selected plottype to use for the textvariables of the widgets
        plottype = self.plottype.get()

        # LabelFrame for all preset options
        self.preset_labelframe = ttk.LabelFrame(self.basic_frame, text="Preset:")
        self.preset_labelframe.grid(column=0, row=0, columnspan=2, sticky=tk.NSEW, pady=(0, 10))
        self.preset_labelframe.grid_columnconfigure(0, weight=1)

        self.preset_frame = ttk.Frame(self.preset_labelframe)
        self.preset_frame.grid(column=0, row=0, sticky=tk.NSEW, pady=10, padx=10)

        # All preset specific widgets
        self.preset_combo = ttk.Combobox(
            self.preset_frame,
            textvariable=self.selected_presets[plottype],
            values=tuple(self.import_presets[self.plottype.get()]),
            state="normal",
            validate="key",
            validatecommand=(self.register(self.__validate_preset_name), "%P"),
        )
        
        self.preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.preset_combo.bind("<<ComboboxSelected>>", self.__load_preset)
        self.preset_combo.bind("<FocusIn>", self.__focus_preset)
        self.preset_combo.bind("<KeyRelease>", self.__preview_preset_rename)
        self.preset_combo.bind("<Return>", self.__rename_preset)
        self.preset_combo.bind("<FocusOut>", self.__rename_preset)

        preset_buttons = ttk.Frame(self.preset_frame)
        preset_buttons.pack(side=tk.RIGHT)
        self.save_preset_btn = ttk.Button(preset_buttons, text="Save", command=self.__save_preset, padding=5)
        self.save_preset_btn.pack(side=tk.LEFT, padx=2)
        self.save_preset_as_btn = ttk.Button(
            preset_buttons,
            text="Save as...",
            command=self.__save_preset_as,
            padding=5,
        )
        self.save_preset_as_btn.pack(side=tk.LEFT, padx=2)
        self.delete_preset_btn = ttk.Button(preset_buttons, text="Delete", command=self.__delete_preset, padding=5)
        self.delete_preset_btn.pack(side=tk.LEFT, padx=2)

        self._preset_regular_font = tkfont.nametofont("TkDefaultFont").copy()
        self._preset_bold_font = self._preset_regular_font.copy()
        self._preset_bold_font.configure(weight="bold")

        # Delimiter Combobox
        ttk.Label(self.basic_frame, text="Separator:", padding=5).grid(column=0, row=1, sticky=tk.W)
        self.delimiter = ttk.Combobox(self.basic_frame, textvariable = self.import_data[plottype]["delimiter"] ,width=20)
        self.delimiter["values"]=(";",","," ","Tab","Backspace")
        self.delimiter["state"]="readonly"
        self.delimiter.grid(column=1, row=1, sticky=tk.E, pady=3)
        
        # Decimal Delimiter Combobox
        ttk.Label(self.basic_frame, text="Decimal delimiter:", padding=5).grid(column=0, row=2, sticky=tk.W)
        self.decimaldelimiter = ttk.Combobox(self.basic_frame, textvariable=self.import_data[plottype]["decimaldelimiter"] ,width=20)
        self.decimaldelimiter["values"]=(",",".")
        self.decimaldelimiter["state"]="readonly"
        self.decimaldelimiter.grid(column=1, row=2, sticky=tk.E, pady=3)
        
        #Linestart Spinbox
        ttk.Label(self.basic_frame, text="Values start in line:", padding=5).grid(column=0, row=3, sticky=tk.W)
        self.linevaluestart = ttk.Spinbox(self.basic_frame, from_=1, to=1000, textvariable=self.import_data[plottype]["linevaluestart"],width=21)
        self.linevaluestart.grid(column=1, row=3, sticky=tk.E, pady=3)
        
        # Ask whether to end at a specific line
        ttk.Label(self.basic_frame, text="End at a specific line:", padding=5).grid(column=0, row=4, sticky=tk.W)
        self.askendatvalue = ttk.Checkbutton(self.basic_frame, text="", command=self.__update, variable=self.import_data[plottype]["endatvalue"], onvalue="True", offvalue="False")
        self.askendatvalue.grid(column=1, row=4, sticky=tk.E, pady=3)
        
        # Ask at which line to end
        ttk.Label(self.basic_frame, text="Values end in line:", padding=5).grid(column=0, row=5, sticky=tk.W)
        self.linevalueend = ttk.Spinbox(self.basic_frame, from_=1, to=symaxsize , textvariable=self.import_data[plottype]["linevalueend"],width=21)
        self.linevalueend.grid(column=1, row=5, sticky=tk.E, pady=3)
        
        #Import File(s) Button
        self.import_btn = ttk.Button(self.basic_frame, text="Choose Files", command=self.close)
        
        self.import_btn.grid(column=0, columnspan=2, row=6, sticky="sew")

    def __build_advanced_settings(self):

        # Configure grid for advanced settings
        self.advanced_frame.columnconfigure(1, weight=1)
        self.advanced_frame.rowconfigure(8, weight=1)

        # Configure tk_variables for advanced settings
        self.advanced_filename = tk.StringVar(self)
        self.advanced_sheet = tk.StringVar(self)
        self.advanced_transpose = tk.BooleanVar(self, value=False)

        plottype = self.plottype.get()
        self.advanced_sep = self.import_data[plottype]["delimiter"]
        self.advanced_decimal = self.import_data[plottype]["decimaldelimiter"]

        # Entry and Button for the selection of a file for the preview
        ttk.Label(self.advanced_frame, text="Preview File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.filename_entry = ttk.Entry(self.advanced_frame, 
                                        textvariable=self.advanced_filename, 
                                        state="readonly", 
                                        width=45)
        self.filename_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=3)
        self.filename_btn = ttk.Button(self.advanced_frame, 
                                       text="Choose File", 
                                       command=self.__choose_advanced_file)
        self.filename_btn.grid(row=0, column=3, padx=5, pady=3)

        # Combobox for the selection of a datasheet in case of an Excel file
        ttk.Label(self.advanced_frame, text="Datasheet:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.advanced_sheet_combo = ttk.Combobox(self.advanced_frame, 
                                                 textvariable=self.advanced_sheet, 
                                                 state="disabled", 
                                                 width=18)
        self.advanced_sheet_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        self.advanced_sheet_combo.bind("<<ComboboxSelected>>", self.__load_advanced_preview)

        # Comboboxes for the selection of the separator
        ttk.Label(self.advanced_frame, text="Separator:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.advanced_sep_combo = ttk.Combobox(self.advanced_frame, 
                                               textvariable=self.advanced_sep, 
                                               width=18, 
                                               state="readonly")
        self.advanced_sep_combo["values"] = (";", ",", " ", "Tab", "Backspace")
        self.advanced_sep_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        self.advanced_sep_combo.bind("<<ComboboxSelected>>", self.__load_advanced_preview)

        # Combobox for the selection of the Decimal Delimiter
        ttk.Label(self.advanced_frame, text="Decimal:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.advanced_decimal_combo = ttk.Combobox(self.advanced_frame, 
                                                   textvariable=self.advanced_decimal, 
                                                   width=18, 
                                                   state="readonly")
        self.advanced_decimal_combo["values"] = (",", ".")
        self.advanced_decimal_combo.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        self.advanced_decimal_combo.bind("<<ComboboxSelected>>", self.__load_advanced_preview)

        # Checkbutton whether to transpose the dataframe or not
        self.advanced_transpose_chkbtn = ttk.Checkbutton(self.advanced_frame, 
                                                         text="Transpose Dataframe",
                                                         variable=self.advanced_transpose,
                                                         command=self.__load_advanced_preview)
        self.advanced_transpose_chkbtn.grid(row=4, column=0, columnspan=4, sticky=tk.W, padx=5, pady=3)

        # Label to show the status of the preview (e.g. number of rows and columns loaded, errors, etc.)
        self.advanced_status = ttk.Label(self.advanced_frame, text="Choose a file to preview it.")
        self.advanced_status.grid(row=5, column=0, columnspan=4, sticky=tk.W, padx=5, pady=3)

        # Frame for the preview of the selected file
        sheet_frame = ttk.Frame(self.advanced_frame)
        sheet_frame.grid(row=6, column=0, columnspan=4, sticky=tk.NSEW, padx=5, pady=3)
        sheet_frame.rowconfigure(0, weight=1)
        sheet_frame.columnconfigure(0, weight=1)

        # Sheet for the preview of the selected file
        self.preview_sheet = Sheet(sheet_frame, 
                                   width=760, 
                                   height=300,
                                   show_x_scrollbar=True, 
                                   show_y_scrollbar=True,
                                   expand_sheet=True)
        self.preview_sheet.grid(row=0, column=0, sticky=tk.NSEW)

        # Match the style of the preview sheet to the rest of the application, otherwise because of ttkbootstrap
        # This will not fit the rest of the application and look out of place
        self.__style_preview_sheet(sheet_obj=self.preview_sheet)

        # Only enable different selection modes and resizing for the preview sheet, "disable" everything else
        self.preview_sheet.enable_bindings(("single_select",
                                            "drag_select",
                                            "select_all",
                                            "column_select",
                                            "row_select",
                                            "arrowkeys",
                                            "column_width_resize",
                                            "double_click_column_resize",
                                            "row_width_resize",
                                            "column_height_resize",
                                            "row_height_resize",
                                            "double_click_row_resize",
                                            "ctrl_select",
                                            ), menu=False)

        self.confirm_advanced_btn = ttk.Button(self.advanced_frame, text="Confirm Selection", command=self.__confirm_selection)
        self.confirm_advanced_btn.grid(row=7, column=0, columnspan=4, sticky=tk.EW, padx=5, pady=3)
        self.confirm_advanced_btn.configure(state=tk.DISABLED)
        # Setup after method so this is not called too often when the user is selecting multiple boxes
        self._selection_update_after = None
        self.preview_sheet.extra_bindings("all_select_events", 
                                           self.__update_confirm_advanced_button)

    def __build_advanced_settings_confirm_frame(self):
        self.confirmed_advanced_settings_frame = ttk.Frame(self)

        # Add a label showing the user what the current file would be named and what the current plottype is
        self.current_file_label = ttk.Label(self.confirmed_advanced_settings_frame, text="Current File: | Current Plot Type: ")
        self.current_file_label.grid(row=0, column=0, columnspan=3, sticky=tk.W, padx=5, pady=3)

        self.add_suffix = tk.BooleanVar(self, value=False)

        # Add a checkbutton whether to add a custom suffix to the filename or not, and an entry for the suffix
        self.add_suffix_chkbtn = ttk.Checkbutton(self.confirmed_advanced_settings_frame,
                                                 text="Add Suffix to Filename", 
                                                 variable=self.add_suffix, 
                                                 command=self.__toggle_suffix_entry)
        self.add_suffix_chkbtn.grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)

        self.suffix = tk.StringVar(self, value="")
        self.suffix.trace_add("write", self.__update_display_filename)

        self.suffix_entry = ttk.Entry(self.confirmed_advanced_settings_frame, 
                                      textvariable=self.suffix,
                                      state="disabled", 
                                      width=20)
        self.suffix_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        # Add a button that allows the user to switch the x and y axes of the selected data
        self.switch_axes_btn = ttk.Button(self.confirmed_advanced_settings_frame, text="Switch Axes", command=self.__switch_axes)
        self.switch_axes_btn.grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)

        self.switched_axes = False

        # Add the tksheet, that shows the current dataframe, now clearly label the first column as x and the second column as y
        self.final_preview_sheet = Sheet(self.confirmed_advanced_settings_frame,
                                         show_x_scrollbar=True,
                                         show_y_scrollbar=True,
                                         expand_sheet=True,
                                         header=["x Values", "y Values"])
        self.final_preview_sheet.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW, padx=5, pady=3)

        self.final_preview_sheet.enable_bindings(("arrowkeys",
                                                  "column_width_resize",
                                                  "double_click_column_resize",
                                                  "row_width_resize",
                                                  "column_height_resize",
                                                  "row_height_resize",
                                                  "double_click_row_resize",
                                                  ), menu=False)

        # Match the style of the preview sheet to the rest of the application, otherwise because of ttkbootstrap
        # This will not fit the rest of the application and look out of place
        self.__style_preview_sheet(sheet_obj=self.final_preview_sheet)

        # Add a button that allows the user to go back to the advanced settings and change the selection
        self.back_to_advanced_btn = ttk.Button(self.confirmed_advanced_settings_frame, text="Back", command=self.__back)
        self.back_to_advanced_btn.grid(row=4, column=0, sticky=tk.EW, padx=5, pady=3)

        # Add a button that allows the user to confirm the selection and continue to import multiple files using the same settings
        self.import_multiple_advanced_btn = ttk.Button(self.confirmed_advanced_settings_frame, 
                                                       text="Import Multiple Files", 
                                                       command=self.close_multiple_advanced)
        
        self.import_multiple_advanced_btn.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=3)

        # Add a button that allows the user to confirm the selection and continue to import a single file using the same settings
        self.import_single_advanced_btn = ttk.Button(self.confirmed_advanced_settings_frame,
                                                     text="Import File", 
                                                     command=self.close_single_advanced)

        self.import_single_advanced_btn.grid(row=4, column=2, sticky=tk.EW, padx=5, pady=3)


    def __back(self):
        self.confirmed_advanced_settings_frame.grid_forget()
        self.radioframe.grid()
        self.notebook.grid()

    def __continue_to_advanced_settings_confirm_frame(self):

        self.final_preview_sheet.set_sheet_data(self.final_preview_df.astype(str).values.tolist(),
                                                reset_col_positions=True,
                                                reset_row_positions=True)

        self.switched_axes = False

        self.__update_display_filename()

        self.confirmed_advanced_settings_frame.grid(row=0, column=0, sticky=tk.NSEW)
        self.radioframe.grid_forget()
        self.notebook.grid_forget()

    def __switch_axes(self):
        if self.final_preview_df is not None:
            self.final_preview_df = self.final_preview_df.iloc[:, ::-1]
            self.switched_axes = not self.switched_axes
            self.final_preview_sheet.set_sheet_data(self.final_preview_df.astype(str).values.tolist(),
                                                    reset_col_positions=True,
                                                    reset_row_positions=True)

    def __toggle_suffix_entry(self):
        if self.add_suffix.get():
            self.suffix_entry.configure(state="normal", cursor="xterm")
        else:
            self.suffix_entry.configure(state="disabled", cursor="arrow")

        self.__update_display_filename()

    def __update_display_filename(self, *args):
        advanced_filename = self.advanced_filename.get()
        
        display_filename = advanced_filename[advanced_filename.rfind("/")+1:advanced_filename.rfind(".")]

        if self.add_suffix.get() and self.suffix.get():
            display_filename += f"_{self.suffix.get()}"

        self.current_file_label.configure(text=f"Current File: {display_filename} | Current Plot Type: {self.plottype.get()}")

    def __update_confirm_advanced_button(self, event=None):
        if self._selection_update_after is not None:
            self.after_cancel(self._selection_update_after)
        self._selection_update_after = self.after(25, self.__apply_confirm_advanced_button_state)

    def __apply_confirm_advanced_button_state(self):
        self._selection_update_after = None

        # Already check whether the selection also satisfies the necessary criteria
        selection_boxes = self.preview_sheet.get_all_selection_boxes()

        if not selection_boxes:
            self.confirm_advanced_btn.configure(state=tk.DISABLED)
            return

        if len(selection_boxes) >= 1:
            box_dict = {}
            for box in selection_boxes:
                box_dict[box] = {"columns": list(range(box.from_c, box.upto_c)),
                                    "rows": list(range(box.from_r, box.upto_r))}

            # There are now a few possible cases for how this selection was made in a logic way:
            # Either both x and y axes have been selected in two selection boxes, giving them two different columns, but the same amount of rows
            # Theoretically it could also be that the user selected two boxes that both contain the same x and y axes but different rows of those
            # For more selection boxes than two, it would also be either of these special cases

            # Perhaps both cases can be solved as following:
            # Reorganizing the data in a way, so that we have a dictionary such as {column_index: [list of rows]}
            self.column_dict = {}

            for box in box_dict:
                for column in box_dict[box]["columns"]:
                    if column not in self.column_dict:
                        self.column_dict[column] = []
                    self.column_dict[column].extend(box_dict[box]["rows"])

            # Now compare, in the end the dictionary should have exactly two columns and their list of rows should match
            # This match should not just be in length but also in actual row indices, because it can be expected from csv files
            # that x and y values are in the same row, so if the user selects two boxes that have different rows for the same column, it should be considered an error
            if len(self.column_dict) != 2:
                if DEBUG: print("The selection does not contain exactly two columns for x and y axis data.")
                self.confirm_advanced_btn.configure(state=tk.DISABLED)
                return

            self.column_dict_values = list(self.column_dict.values())
            if self.column_dict_values[0] != self.column_dict_values[1]:
                if DEBUG: print("The selection does not contain matching rows for the two columns.")
                self.confirm_advanced_btn.configure(state=tk.DISABLED)
                return

        if DEBUG: print("The selection is valid.")
        self.confirm_advanced_btn.configure(state=tk.NORMAL)

    def __confirm_selection(self):
        selection_boxes = sorted(self.preview_sheet.get_all_selection_boxes())
        if DEBUG: print("Current selection boxes:", selection_boxes)

        if len(selection_boxes) == 0:
            if DEBUG: print("No selection has been made.")
            return

        # Found a solution for all cases (singular and multiple selections)
        if len(selection_boxes) >= 1:
            box_dict = {}
            for box in selection_boxes:
                box_dict[box] = {"columns": list(range(box.from_c, box.upto_c)),
                                 "rows": list(range(box.from_r, box.upto_r))}

            # There are now a few possible cases for how this selection was made in a logic way:
            # Either both x and y axes have been selected in two selection boxes, giving them two different columns, but the same amount of rows
            # Theoretically it could also be that the user selected two boxes that both contain the same x and y axes but different rows of those
            # For more selection boxes than two, it would also be either of these special cases

            # Perhaps both cases can be solved as following:
            # Reorganizing the data in a way, so that we have a dictionary such as {column_index: [list of rows]}
            self.column_dict = {}

            for box in box_dict:
                for column in box_dict[box]["columns"]:
                    if column not in self.column_dict:
                        self.column_dict[column] = []
                    self.column_dict[column].extend(box_dict[box]["rows"])

            # Now compare, in the end the dictionary should have exactly two columns and their list of rows should match
            # This match should not just be in length but also in actual row indices, because it can be expected from csv files
            # that x and y values are in the same row, so if the user selects two boxes that have different rows for the same column, it should be considered an error
            if len(self.column_dict) != 2:
                if DEBUG: print("The selection does not contain exactly two columns for x and y axis data.")
                return

            self.column_dict_values = list(self.column_dict.values())
            if self.column_dict_values[0] != self.column_dict_values[1]:
                if DEBUG: print("The selection does not contain matching rows for the two columns.")
                return

            if DEBUG:
                print("The selection contains two columns with matching rows. The data can be imported.")
                print("Selected columns:", list(self.column_dict.keys()))
                print("Selected rows:", self.column_dict_values[0])

                print("Preview DataFrame:")
                print(self.advanced_preview_df)

            # Now import the data from the selected columns and rows into a pandas dataframe and then allow the user to continue to a different frame
            # That frame should just have new sheet which shows x and y as the two columns and the user has the possibility to switch x and y axis

            self.final_preview_df = self.advanced_preview_df.loc[self.column_dict_values[0], list(self.column_dict.keys())].reset_index(drop=True)

            if DEBUG:
                print("Excerpt of the selected data:")
                print(self.final_preview_df)

            self.__continue_to_advanced_settings_confirm_frame()

    def __style_preview_sheet(self, sheet_obj=None):
        style = ttk.Style()
        dark = getattr(self.master, "_dark", False)
        frame_bg = style.lookup("TFrame", "background") or ("#222222" if dark else "#ffffff")
        table_bg = style.lookup("TEntry", "fieldbackground") or ("#343a40" if dark else "#ffffff")
        table_fg = style.lookup("TLabel", "foreground") or ("#f8f9fa" if dark else "#212529")
        accent = style.lookup("TButton", "background") or ("#375a7f" if dark else "#2c3e50")
        grid = "#4b5563" if dark else "#d6d9dc"
        selected_bg = "#28527a" if dark else "#dbeafe"
        selected_fg = "#ffffff" if dark else "#172033"

        if sheet_obj is None:
            sheet_obj = self.preview_sheet

        sheet_obj.set_options(
            frame_bg=frame_bg,
            table_bg=table_bg,
            table_fg=table_fg,
            table_editor_bg=table_bg,
            table_editor_fg=table_fg,
            table_editor_select_bg=accent,
            table_editor_select_fg="#ffffff",
            table_grid_fg=grid,
            header_bg=frame_bg,
            header_fg=table_fg,
            header_grid_fg=grid,
            header_border_fg=grid,
            index_bg=frame_bg,
            index_fg=table_fg,
            index_grid_fg=grid,
            index_border_fg=grid,
            table_selected_cells_bg=selected_bg,
            table_selected_cells_fg=selected_fg,
            table_selected_rows_bg=selected_bg,
            table_selected_rows_fg=selected_fg,
            table_selected_columns_bg=selected_bg,
            table_selected_columns_fg=selected_fg,
            header_selected_columns_bg=accent,
            header_selected_columns_fg="#ffffff",
            index_selected_rows_bg=accent,
            index_selected_rows_fg="#ffffff",
            vertical_scroll_background=table_bg,
            horizontal_scroll_background=table_bg,
            vertical_scroll_troughcolor=frame_bg,
            horizontal_scroll_troughcolor=frame_bg,
            rounded_boxes=False,
        )

    def __choose_advanced_file(self):
        filename = fd.askopenfilename(parent=self, 
                                      title="Select a file to preview",
                                      filetypes=(("Data files", "*.csv *.txt *.ctx *.xlsx *.xls"), ("All files", "*.*")))
        if not filename:
            return
        self.advanced_filename.set(filename)
        if filename.lower().endswith((".xls", ".xlsx")):
            try:
                sheets = pd.ExcelFile(filename).sheet_names
                self.advanced_sheet_combo.configure(values=sheets, state="readonly")
                self.advanced_sheet.set(sheets[0])
            except (OSError, ValueError, ImportError) as error:
                self.advanced_sheet_combo.configure(values=(), state="disabled")
                self.advanced_status.configure(text=f"Could not read Excel sheets: {error}")
                return
        else:
            self.advanced_sheet_combo.configure(values=(), state="disabled")
            self.advanced_sheet.set("")
        self.__load_advanced_preview()

    def __load_advanced_preview(self, *args):
        filename = self.advanced_filename.get()
        if not filename:
            return

        try:
            dataframe = self.__load_advanced_file(filename)

            self.advanced_preview_df = dataframe
            self.preview_sheet.set_sheet_data(dataframe.astype(str).values.tolist(),
                                                reset_col_positions=True,
                                                reset_row_positions=True)
            self.__update_confirm_advanced_button()

            self.advanced_status.configure(
                text=f"Loaded {len(dataframe)} rows and {len(dataframe.columns)} columns"
                        + (" (transposed)." if self.advanced_transpose.get() else "."))
        except Exception as error:
            self.advanced_status.configure(text=f"Could not load file: {error}")

    def __load_advanced_file(self, filename, *args):

        kwargs = {"decimal": self.advanced_decimal.get(),
                  "skiprows": 0,
                  "header": None,
                  "na_filter": False}
        if filename.lower().endswith((".xls", ".xlsx")):
            kwargs["sheet_name"] = self.advanced_sheet.get()
            dataframe = pd.read_excel(filename, **kwargs)
        else:
            kwargs["sep"] = self.advanced_sep.get()
            kwargs["skip_blank_lines"] = False
            if kwargs["sep"] == "Tab":
                kwargs["sep"] = "\t"
            elif kwargs["sep"] == "Backspace":
                kwargs["sep"] = "\b"
            dataframe = self.__read_flexible_csv(filename, kwargs)
        if self.advanced_transpose.get():
            dataframe = dataframe.transpose().reset_index(drop=True)
        dataframe = dataframe.fillna("")

        return dataframe

    def __read_flexible_csv(self, filename, kwargs):
        """Read CSV rows with varying field counts into a rectangular dataframe."""
        separator = kwargs["sep"]

        with open(filename, "r", newline="", encoding="utf-8-sig", errors="replace") as file:
            rows = list(csv.reader(file, delimiter=separator))

        max_fields = max((len(row) for row in rows), default=0)

        if max_fields == 0:
            return pd.DataFrame()

        normalized_rows = [row[:max_fields] + [""] * (max_fields - len(row)) for row in rows]
        normalized_file = StringIO()
        csv.writer(normalized_file, delimiter=separator, lineterminator="\n").writerows(normalized_rows)
        normalized_file.seek(0)

        read_kwargs = kwargs.copy()
        read_kwargs.update({"engine": "python", "names": list(range(max_fields)), "header": None})
        dataframe = pd.read_csv(normalized_file, **read_kwargs)
        # Make NaN values appear as empty strings
        dataframe = dataframe.fillna("")
        # Remove the last column if it is empty (all values are empty strings)
        if dataframe.shape[1] and dataframe.iloc[:, -1].astype("string").str.strip().eq("").all():
            dataframe = dataframe.iloc[:, :-1]

        return dataframe
        

    def close(self):
        self.__update()

        self.__close()

        #clarify file types in file browser
        filetypes = (
            ("Text/ CTX/ CSV Files", "*.txt *.ctx *.csv"),
            ("All Files", "*.*"),
        )

        plottype = self.plottype.get()

        # Open the same folder that was opened before during the current runtime
        initialdir = self.master.last_import_folder[plottype]

        # Fallback if no initialdir is known or it does not exist
        if initialdir is None or not exists(initialdir):
            initialdir = ".."

        # open file Browser for multiple files
        filepaths = fd.askopenfilenames(parent=self.master,
                                             title=f"Select {plottype} Files",
                                             initialdir=initialdir,
                                             filetypes=filetypes)
        if filepaths == "":
            return

        # Save the new initialdir
        self.master.last_import_folder[plottype] = filepaths[0][:filepaths[0].rfind("/")]

        selection = self.master.browser.selection()

        if len(selection) == 1:
            parent = selection[0]

            # Check whether the parent is a project or a graph object by checking the tags and if they are not a project, get their parent
            if not self.master.browser.tag_has("Project", item=parent):
                parent = self.master.browser.parent(parent)

        else:
            parent = ""
        

        #define converter for different decimal delimiters
        convertfunc = lambda x: float(x.replace(self.import_data[plottype]["decimaldelimiter"].get(),"."))

        decimal = self.import_data[plottype]["decimaldelimiter"].get()

        delimiter = self.import_data[plottype]["delimiter"].get()

        if delimiter == "Tab":
            delimiter = "\t"
        elif delimiter == "Backspace":
            delimiter = "\b"

        for filepath in filepaths:
            filename = filepath[filepath.rfind("/")+1:filepath.rfind(".")]
            
            print("Importing "+filename+" as "+plottype+" plot...")

            try:
                
                # Check whether to read the entire file or just a part of it
                if self.import_data[plottype]["endatvalue"].get() == "False":
                    try:
                        data = pd.read_csv(filepath,
                                           delimiter=delimiter,
                                           decimal=decimal,
                                           skiprows=int(self.import_data[plottype]["linevaluestart"].get())-1,
                                           header=None,
                                           usecols=[0,1])

                        xpoints, ypoints = data.to_numpy(dtype=np.float64).T # Get two arrays, one per column
                        
                    except: #Genfromtxt as fallback
                        print("There were issues importing the file with pandas. Using numpy's genfromtxt as fallback.")
                        #get values from txt
                        xpoints, ypoints = np.genfromtxt(filepath, unpack=True,
                                                         delimiter=delimiter,
                                                         skip_header=int(self.import_data[plottype]["linevaluestart"].get())-1,
                                                         encoding=None,
                                                         converters={0: convertfunc,
                                                                     1: convertfunc},
                                                         usecols=(0,1)
                                                         )
                else:
                    try:
                        data = pd.read_csv(filepath,
                                           delimiter=delimiter,
                                           decimal=decimal,
                                           skiprows=int(self.import_data[plottype]["linevaluestart"].get())-1,
                                           header=None,
                                           nrows=int(self.import_data[plottype]["linevalueend"].get())-int(self.import_data[plottype]["linevaluestart"].get())+1,
                                           usecols=[0,1])

                        xpoints, ypoints = data.to_numpy(dtype=np.float64).T # Get two arrays, one per column
                    except: #Genfromtxt as fallback
                        print("There were issues importing the file with pandas. Using numpy's genfromtxt as fallback.")
                        #get values from txt
                        xpoints, ypoints = np.genfromtxt(filepath, unpack=True,
                                                         delimiter=delimiter,
                                                         skip_header=int(self.import_data[plottype]["linevaluestart"].get())-1,
                                                         max_rows=int(self.import_data[plottype]["linevalueend"].get())-int(self.import_data[plottype]["linevaluestart"].get())+1,
                                                         encoding=None,
                                                         converters={0: convertfunc,
                                                                     1: convertfunc},
                                                         usecols=(0,1)
                                                         )
                        
                # Check whether any of the values is NaN and if so, skip remaining logic
                for array in [xpoints, ypoints]:

                    if np.any(~np.isfinite(array)):
                        raise ValueError("NaN value found in import. Please check the line numbers as well as the delimiters again.")

                if np.unique(xpoints).size != xpoints.size:
                    raise ValueError("Duplicate x-values found in import. Please check the line numbers as well as the delimiters again.")

                # Sort the xpoints and ypoints by xpoints in ascending order
                sort_indices = np.argsort(xpoints)
                xpoints = xpoints[sort_indices]
                ypoints = ypoints[sort_indices]

                save_dict = {"filename": filename, #filename
                             "plottype": plottype, #plottype
                             "xpoints": xpoints,  #points on x-axis
                             "ypoints": ypoints,  #points on y-axis
                             }

                new_item = self.db.add_new_save()

                self.master.browser.insert(parent, tk.END, iid=new_item, text=filename, values=[plottype,], tags=[plottype,"Plot"])
                
                self.imported_data.update({new_item: save_dict})

            except Exception as e:
                print(f"An error occured during import.\n{e}\nSkipping current file")

        if len(self.imported_data) > 0:
            self.master.add_imported_data(self.imported_data)

    def close_multiple_advanced(self):
        self.__update()
        self.__close()

        # Get the file type of the previewed advanced file
        advanced_filename = self.advanced_filename.get()

        current_filetype = advanced_filename[advanced_filename.rfind(".")+1:].lower()

        #clarify file types in file browser
        filetypes = (
            (f"{current_filetype.upper()} Files", f"*.{current_filetype}"),
        )

        plottype = self.plottype.get()

        # open file Browser for multiple files
        filepaths = fd.askopenfilenames(parent=self.master,
                                             title=f"Select {plottype} Files",
                                             filetypes=filetypes)
        
        if filepaths == "":
            filepaths = []

        filepaths = list(filepaths) # Convert to a list, so changing it later is possible

        # Add the previewed file to the list of files to import, in case it is not already included
        if advanced_filename not in filepaths:
            filepaths.append(advanced_filename)  

        # Get the parent item in the browser where the new items will be inserted

        selection = self.master.browser.selection()

        if len(selection) == 1:
            parent = selection[0]

            # Check whether the parent is a project or a graph object by checking the tags and if they are not a project, get their parent
            if not self.master.browser.tag_has("Project", item=parent):
                parent = self.master.browser.parent(parent)

        else:
            parent = ""

        for filepath in filepaths:

            filename = filepath[filepath.rfind("/")+1:filepath.rfind(".")]

            if self.add_suffix.get() and self.suffix.get():
                filename += f"_{self.suffix.get()}"
                        
            print("Importing "+filename+" as "+plottype+" plot...")

            try:

                # Insert a quick check in case of excel files, to check whether sheet names match the one of the previewed file
                if filepath.lower().endswith((".xls", ".xlsx")):
                    sheets = pd.ExcelFile(filepath).sheet_names

                    if self.advanced_sheet.get() not in sheets:
                        raise ValueError(f"The selected file '{filename}' does not contain the sheet '{self.advanced_sheet.get()}' that was used for the previewed file.")

                # Load the dataframe and treat it exactly like the single advanced file, but now for multiple files
                dataframe = self.__load_advanced_file(filepath)

                finalized_dataframe = dataframe.loc[self.column_dict_values[0], list(self.column_dict.keys())].reset_index(drop=True)

                if self.switched_axes:
                    finalized_dataframe = finalized_dataframe.iloc[:, ::-1]
            
                xpoints, ypoints = finalized_dataframe.to_numpy(dtype=np.float64).T # Get two arrays, one per column
    
                # Check whether any of the values is NaN and if so, skip remaining logic
                for array in [xpoints, ypoints]:

                    if np.any(~np.isfinite(array)):
                        raise ValueError("NaN value found in import. Please check the line numbers as well as the delimiters again.")

                if np.unique(xpoints).size != xpoints.size:
                    raise ValueError("Duplicate x-values found in import. Please check the line numbers as well as the delimiters again.")

                # Sort the xpoints and ypoints by xpoints in ascending order
                sort_indices = np.argsort(xpoints)
                xpoints = xpoints[sort_indices]
                ypoints = ypoints[sort_indices]
    
                save_dict = {"filename": filename, #filename
                             "plottype": plottype, #plottype
                             "xpoints": xpoints,  #points on x-axis
                             "ypoints": ypoints,  #points on y-axis
                        }
    
                new_item = self.db.add_new_save()
    
                self.master.browser.insert(parent, tk.END, iid=new_item, text=filename, values=[plottype,], tags=[plottype,"Plot"])
                
                self.imported_data.update({new_item: save_dict})
                
            except Exception as e:
                print(f"An error occured during import.\n{e}\nSkipping file.")

        if len(self.imported_data) > 0:
            self.master.add_imported_data(self.imported_data)            

    def close_single_advanced(self):
        self.__update()
        self.__close()

        plottype = self.plottype.get()

        advanced_filename = self.advanced_filename.get()
                
        filename = advanced_filename[advanced_filename.rfind("/")+1:advanced_filename.rfind(".")]

        if self.add_suffix.get() and self.suffix.get():
            filename += f"_{self.suffix.get()}"

        print("Importing "+filename+" as "+plottype+" plot...")

        selection = self.master.browser.selection()

        if len(selection) == 1:
            parent = selection[0]

            # Check whether the parent is a project or a graph object by checking the tags and if they are not a project, get their parent
            if not self.master.browser.tag_has("Project", item=parent):
                parent = self.master.browser.parent(parent)

        else:
            parent = ""

        try:

            xpoints, ypoints = self.final_preview_df.to_numpy(dtype=np.float64).T # Get two arrays, one per column

            # Check whether any of the values is NaN and if so, skip remaining logic
            for array in [xpoints, ypoints]:

                if np.any(~np.isfinite(array)):
                    raise ValueError("NaN value found in import. Please check the line numbers as well as the delimiters again.")

            if np.unique(xpoints).size != xpoints.size:
                raise ValueError("Duplicate x-values found in import. Please check the line numbers as well as the delimiters again.")

            # Sort the xpoints and ypoints by xpoints in ascending order
            sort_indices = np.argsort(xpoints)
            xpoints = xpoints[sort_indices]
            ypoints = ypoints[sort_indices]

            save_dict = {"filename": filename, #filename
                         "plottype": plottype, #plottype
                         "xpoints": xpoints,  #points on x-axis
                         "ypoints": ypoints,  #points on y-axis
                    }

            new_item = self.db.add_new_save()

            self.master.browser.insert(parent, tk.END, iid=new_item, text=filename, values=[plottype,], tags=[plottype,"Plot"])
            
            self.imported_data.update({new_item: save_dict})

            self.master.add_imported_data(self.imported_data)
        
        except Exception as e:
            print(f"An error occured during import.\n{e}\nSkipping file.")

    def _get_default_preset(self, plottype):
        return {
            setting: self.config.import_data[plottype][setting]
            for setting in self.settings
        }

    def _get_current_preset(self, plottype):
        return {
            setting: self.import_data[plottype][setting].get()
            for setting in self.settings
        }

    def _apply_preset(self, plottype, preset):
        self._updating_preset = True
        try:
            for setting in self.settings:
                if setting not in preset:
                    raise ValueError(f"Preset is missing '{setting}' for plot type '{plottype}'.")
                self.import_data[plottype][setting].set(str(preset[setting]))
        finally:
            self._updating_preset = False

        self.__update(sync_config=False)
        self.preset_dirty[plottype] = False
        self._update_preset_display()

    def _selected_preset_name(self, plottype=None):
        plottype = plottype or self.plottype.get()
        return (
            self.preset_edit_names[plottype]
            or self.preset_base_names[plottype]
        )

    def _update_preset_display(self):
        plottype = self.plottype.get()
        name = self._selected_preset_name(plottype)
        display_name = f"{name} *" if self.preset_dirty[plottype] else name
        self._updating_preset = True
        try:
            self.selected_presets[plottype].set(display_name)
            self.preset_combo.configure(
                values=tuple(self.import_presets[plottype]),
                font=self._preset_bold_font if self.preset_dirty[plottype] else self._preset_regular_font,
            )
            self.save_preset_btn.configure(
                state="normal" if self._can_save_preset(plottype) else "disabled"
            )
            self.delete_preset_btn.configure(
                state="disabled" if self.preset_base_names[plottype] == "Default" else "normal"
            )
            if self.preset_dirty[plottype]:
                self.preset_combo.icursor(max(0, len(display_name) - 2))
        finally:
            self._updating_preset = False

    def _can_save_preset(self, plottype, entered_name=None):
        if entered_name is not None:
            entered_name = entered_name.removesuffix(" *").strip()
            if entered_name != self.preset_base_names[plottype]:
                return (
                    self.preset_base_names[plottype] != "Default"
                    and bool(entered_name)
                )
        if not self.preset_dirty[plottype]:
            return False
        if self.preset_base_names[plottype] != "Default":
            return True
        if self.preset_edit_names[plottype] is not None:
            return False
        return entered_name in (None, "Default")

    def _mark_preset_dirty(self, plottype):
        if self._updating_preset:
            return
        self.preset_dirty[plottype] = True
        self._update_preset_display()

    def __focus_preset(self, event=None):
        if self._updating_preset:
            return

        plottype = self.plottype.get()
        if self.preset_dirty[plottype]:
            name = self._selected_preset_name(plottype)
            self._updating_preset = True
            try:
                self.selected_presets[plottype].set(name)
                self.preset_combo.icursor(tk.END)
            finally:
                self._updating_preset = False

    def __validate_preset_name(self, proposed_name):
        return "*" not in proposed_name

    def __preview_preset_rename(self, event=None):
        if self._updating_preset:
            return

        plottype = self.plottype.get()
        entered_name = self.selected_presets[plottype].get().removesuffix(" *").strip()
        is_renamed = bool(entered_name) and entered_name != self.preset_base_names[plottype]
        if is_renamed or self.preset_dirty[plottype]:
            self.preset_combo.configure(font=self._preset_bold_font)
        else:
            self.preset_combo.configure(font=self._preset_regular_font)
        self.save_preset_btn.configure(
            state="normal" if self._can_save_preset(plottype, entered_name) else "disabled"
        )

    def __load_preset(self, event=None):
        plottype = self.plottype.get()
        name = self.selected_presets[plottype].get().removesuffix(" *")

        try:
            self._sync_default_config(plottype)
            self._apply_preset(plottype, self.import_presets[plottype][name])
            self.preset_base_names[plottype] = name
            self.preset_edit_names[plottype] = None
            self._update_preset_display()
        
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Load preset", str(error), parent=self)
            self.selected_presets[plottype].set("Default")
            self._apply_preset(plottype, self.import_presets[plottype]["Default"])

    def __save_preset(self):
        self.__update()
        plottype = self.plottype.get()
        old_name = self.preset_base_names[plottype]
        name = self._selected_preset_name(plottype)

        if name != old_name and name in self.import_presets[plottype]:
            if not messagebox.askyesno("Rename preset", f"Overwrite preset '{name}'?", parent=self):
                return

        preset = self._get_current_preset(plottype)
        try:
            self.db.save_import_preset(plottype, name, preset)
            if name != old_name:
                self.db.delete_import_preset(plottype, old_name)
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Save preset", str(error), parent=self)
            return

        if name != old_name:
            del self.import_presets[plottype][old_name]
        self.import_presets[plottype][name] = preset
        self.preset_base_names[plottype] = name
        self.preset_edit_names[plottype] = None
        self.preset_dirty[plottype] = False
        self._update_preset_display()

    def __rename_preset(self, event=None):
        if self._updating_preset:
            return

        plottype = self.plottype.get()
        entered_name = self.selected_presets[plottype].get().strip()
        base_name = self.preset_base_names[plottype]

        if not entered_name:
            return

        self.preset_edit_names[plottype] = (
            entered_name if entered_name != base_name else None
        )
        self.preset_dirty[plottype] = (
            self.preset_edit_names[plottype] is not None
            or self.preset_dirty[plottype]
        )
        self._update_preset_display()

    def __save_preset_as(self):
        plottype = self.plottype.get()
        edited_name = self.selected_presets[plottype].get().removesuffix(" *").strip()
        base_name = self.preset_base_names[plottype]
        if edited_name and edited_name != base_name:
            name = edited_name
        else:
            name = simpledialog.askstring("Save import preset as", "Preset name:", parent=self)
            if name is None:
                return

        name = name.strip()
        if not name or name == "Default":
            messagebox.showerror("Save preset", "Choose a non-empty name other than 'Default'.", parent=self)
            return
        if name in self.import_presets[plottype] and not messagebox.askyesno(
            "Save preset",
            f"Overwrite preset '{name}'?",
            parent=self,
        ):
            return

        preset = self._get_current_preset(plottype)
        try:
            self.db.save_import_preset(plottype, name, preset)
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Save preset", str(error), parent=self)
            return

        self.import_presets[plottype][name] = preset
        self.selected_presets[plottype].set(name)
        self.preset_base_names[plottype] = name
        self.preset_edit_names[plottype] = None
        self.preset_dirty[plottype] = False
        self._update_preset_display()

    def __delete_preset(self):
        plottype = self.plottype.get()
        name = self.preset_base_names[plottype]
        if name == "Default":
            return

        if not messagebox.askyesno("Delete preset", f"Delete preset '{name}'?", parent=self):
            return

        try:
            self.db.delete_import_preset(plottype, name)
        except (KeyError, OSError, ValueError) as error:
            messagebox.showerror("Delete preset", str(error), parent=self)
            return

        preset_names = list(self.import_presets[plottype])
        preset_index = preset_names.index(name)
        del self.import_presets[plottype][name]
        remaining_names = list(self.import_presets[plottype])
        next_name = remaining_names[min(preset_index, len(remaining_names) - 1)]
        self.selected_presets[plottype].set(next_name)
        self.preset_base_names[plottype] = next_name
        self.preset_edit_names[plottype] = None
        self._apply_preset(plottype, self.import_presets[plottype][next_name])

    def __update(self, sync_config=True):

        if sync_config:
            for plot in self.import_data:
                self._sync_default_config(plot)

        plottype = self.plottype.get()
        state = "disabled"
        if self.import_data[plottype]["endatvalue"].get() == "True": state = "enabled"
        self.delimiter.config(textvariable = self.import_data[plottype]["delimiter"])
        self.decimaldelimiter.config(textvariable = self.import_data[plottype]["decimaldelimiter"])
        self.advanced_sep = self.import_data[plottype]["delimiter"]
        self.advanced_decimal = self.import_data[plottype]["decimaldelimiter"]
        self.advanced_sep_combo.config(textvariable=self.advanced_sep)
        self.advanced_decimal_combo.config(textvariable=self.advanced_decimal)
        self.linevaluestart.config(textvariable = self.import_data[plottype]["linevaluestart"])
        self.askendatvalue.config(variable = self.import_data[plottype]["endatvalue"])
        self.linevalueend.config(textvariable = self.import_data[plottype]["linevalueend"], state=state)
        self.preset_combo.config(textvariable=self.selected_presets[plottype])
        self._update_preset_display()
        
        self.update()
        self.config.update()

    def _sync_default_config(self, plottype):
        if (
            self.preset_base_names[plottype] != "Default"
            or self.preset_edit_names[plottype] is not None
        ):
            return
        for key in self.import_data[plottype]:
            self.config.import_data[plottype].update(
                {key: self.import_data[plottype][key].get()}
            )

    def __update_plottype(self):
        self._update_preset_display()
        self.__update()
        if self.notebook.select() == str(self.advanced_frame) and self.advanced_filename.get():
            self.__load_advanced_preview()

    def __close(self):
        ImportHandler._instance = None
        self.destroy()
