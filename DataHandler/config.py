import tkinter as tk
import ttkbootstrap as ttk
from tkinter.colorchooser import askcolor
from tkinter import filedialog as fd
import orjson
from os import mkdir
from os import remove as os_remove
from os.path import exists
import matplotlib as mpl
from pathlib import Path


DEBUG = False


class ConfigHandler:

    def __init__(self, DEBUG):

        # Save all the plottypes
        self.plottypes = {"Assay", "CD", "Fluorescence", "HPLC", "Kinetics", "MALDI", "Tm", "UV/vis", "MultiPlot"}
        # For assay-specific changes to the settings, there need to be some advancements in the config code
        self.assaytypes = {"Michaelis-Menten",}
        self.config_keys = {plottype: set() for plottype in self.plottypes}
        # Keep track of all general and specific keys
        self.config_keys.update({"General": {"lnwdth",
                                             "clr",
                                             "fontsize",
                                             "font",
                                             "dpi",
                                             "xlabel",
                                             "ylabel",
                                             "filetype",
                                             "transparent",
                                             "automatic_scripts",
                                             "allow_duplicates",
                                             "expdir",
                                             "plot_width",
                                             "plot_height",
                                             "padding_left",
                                             "padding_right",
                                             "padding_top",
                                             "padding_bottom",
                                             "dark",
                                             "colorblind"},
                                 "Assay": {"fit_clr",
                                           "fit_linestyle",
                                           "fit_linewidth"},
                                 "CD": {"ylabel_MRE"},
                                 "MALDI": {"simulation_clr"},
                                 "Tm": {"ylabel_derivative",
                                        "ylabel_MRE",
                                        "ylabel_MRE_derivative",
                                        "fit_clr"},
                            })

        # Also add all assaytypes to the config_keys["Assay"] set, so that they can be used in the settings window
        self.config_keys["Assay"] |= self.assaytypes

        # Setup the dictionary to keep track of all information
        self.config = {}
        for key in {"General"} | self.plottypes:
            self.config[key] = {}
            for nested_key in self.config_keys["General"] | self.config_keys[key]:
                if key == "Assay" and nested_key in self.assaytypes:
                    self.config[key][nested_key] = {"xlabel": "",
                                                    "ylabel": ""}
                else:
                    self.config[key][nested_key] = ""

        # Initialize import_data, data necessary for importing plots into the program, nested dictionary to differentiate between plottypes
        self.import_data = {"CD":{
                                "delimiter": "Tab",
                                "decimaldelimiter": ",",
                                "linevaluestart": "22",
                                "linevalueend": "622",
                                "endatvalue": "True",
                                },
                            "Fluorescence":{
                                "delimiter": "Tab",
                                "decimaldelimiter": ".",
                                "linevaluestart": "4",
                                "linevalueend": "1",
                                "endatvalue": "False",
                                },
                            "HPLC":{
                                "delimiter": ";",
                                "decimaldelimiter": ".",
                                "linevaluestart": "39",
                                "linevalueend": "1",
                                "endatvalue": "False",
                                },
                            "Kinetics":{
                                "delimiter": "Tab",
                                "decimaldelimiter": ".",
                                "linevaluestart": "1",
                                "linevalueend": "1",
                                "endatvalue": "False",
                                },
                            "MALDI":{
                                "delimiter": " ",
                                "decimaldelimiter": ".",
                                "linevaluestart": "1",
                                "linevalueend": "1",
                                "endatvalue": "False",
                                },
                            "Tm":{
                                "delimiter": "Tab",
                                "decimaldelimiter": ",",
                                "linevaluestart": "17",
                                "linevalueend": "115",
                                "endatvalue": "True",
                                },
                            "UV/vis":{
                                "delimiter": "Tab",
                                "decimaldelimiter": ".",
                                "linevaluestart": "1",
                                "linevalueend": "1",
                                "endatvalue": "False",
                                },
                            }

        self.assets_path = Path(__file__).resolve().parent.parent / "assets"
        if not exists(self.assets_path / "config.json"):
            if not exists(self.assets_path):
                mkdir(self.assets_path)
            self.setup_config()

        else:
            self.load_config()


    def connect_gui(self, master):
        
        self.master = master

    def setup_config(self):
    # Called whenever no config file was found or the config file was found to be corrupted
    
        config_standard_dict = {"General": {"lnwdth": "0.5",
                                            "clr": "black",
                                            "fontsize": "14",
                                            "font": "sans serif",
                                            "dpi": "600",
                                            "filetype": ".png",
                                            "transparent": "True",
                                            "automatic_scripts": "True",
                                            "allow_duplicates": "True",
                                            "plot_width": "5.6",
                                            "plot_height": "3.7744",
                                            "padding_left": "0.4",
                                            "padding_right": "0.3",
                                            "padding_top": "0.1",
                                            "padding_bottom": "0.6",
                                            "dark": "False",
                                            "colorblind": "False",
                                            },
                                "Assay": {"lnwdth": "2.0",
                                          "xlabel": "",
                                          "ylabel": "",
                                          "expdir": "./Export/Assay",
                                          "fit_clr": "red",
                                          "fit_linestyle": "-",
                                          "fit_linewidth": "2.0",
                                          "padding_left": "0.7",
                                          "Michaelis-Menten": {"xlabel": "c(S) [VAR_x_unit]",
                                                               "ylabel": "$v_0 \\/ \\/ \\left[VAR_y_unit\\right]$",
                                                               },
                                          },
                                "CD": {"xlabel": "$\\lambda \\/ \\mathrm{[nm]}$",
                                       "ylabel": "$\\Theta \\/ \\/  \\left[mdeg\\right]$",
                                       "ylabel_MRE": "$[\\Theta] \\/ \\/  \\left[\\/ 10^3 \\/ \\cdot \\mathrm{\\frac{deg \\/ \\cdot \\/ cm^2}{dmol \\/ \\cdot \\/ res}} \\/ \\right]$",
                                       "padding_left": "1.15",
                                       "expdir": "./Export/CD", 
                                       },
                                "Fluorescence": {"xlabel": "$\\lambda \\/ \\mathrm{[nm]}$",
                                                 "ylabel": "Fluorescence",
                                                 "expdir": "./Export/Fluorescence",
                                                },
                                "HPLC": {"xlabel": "Time [min]",
                                         "ylabel": "Absorbance",
                                         "expdir": "./Export/HPLC",
                                         },
                                "Kinetics": {"lnwdth": "2.0",
                                             "xlabel": "Time [s]",
                                             "ylabel": "Signal",
                                             "expdir": "./Export/Kinetics",
                                             },
                                "MALDI": {"xlabel": "m/z",
                                          "ylabel": "Intensity",
                                          "expdir": "./Export/MALDI",
                                          "simulation_clr": "red",
                                          },
                                "Tm": {"lnwdth": "2.0",
                                       "xlabel": "T [°C]",
                                       "ylabel": "$\\Theta_{VAR\\_wavelength} \\/ \\/  \\left[mdeg\\right]$",
                                       "ylabel_derivative": "$\\frac{d\\Theta_{VAR\\_wavelength}}{dT} \\/ \\/  \\left[mdeg\\right]$",
                                       "ylabel_MRE": "$[\\Theta]_{VAR\\_wavelength} \\/ \\/  \\left[\\/ 10^3 \\/ \\cdot \\mathrm{\\frac{deg \\/ \\cdot \\/ cm^2}{dmol \\/ \\cdot \\/ res}} \\/ \\right]$",
                                       "ylabel_MRE_derivative": "$\\frac{d[\\Theta]_{VAR\\_wavelength}}{dT} \\/ \\/  \\left[\\/ 10^3 \\/ \\cdot \\mathrm{\\frac{deg \\/ \\cdot \\/ cm^2}{dmol \\/ \\cdot \\/ res \\/ \\cdot \\/ K}} \\/ \\right]$",
                                       "padding_left": "1.15",
                                       "fit_clr": "red",
                                       "expdir": "./Export/Tm",
                                       },
                                "UV/vis": {"xlabel": "$\\lambda \\/ \\mathrm{[nm]}$",
                                           "ylabel": "Absorbance",
                                           "expdir": "./Export/UV_vis",
                                           },
                                "MultiPlot": {"xlabel": "",
                                              "ylabel": "",
                                              "expdir": "./Export/MultiPlot",
                                              },
                                }
    
        with open(self.assets_path / "config.json","wb") as config:

            config.write(orjson.dumps(config_standard_dict | {"import_data": self.import_data},option = orjson.OPT_INDENT_2))
            config.close()

        for plottype in self.plottypes | {"General"}:
            config_standard_dict[plottype] = config_standard_dict["General"] | config_standard_dict[plottype]
            for key in config_standard_dict[plottype]:
                self.config[plottype][key] = config_standard_dict[plottype][key]

        self._normalize_colors()

    def _normalize_colors(self):
        for plottype in self.config:
            for key in ("clr", "fit_clr"):
                if key in self.config[plottype]:
                    try:
                        self.config[plottype][key] = mpl.colors.to_hex(self.config[plottype][key])
                    except (TypeError, ValueError):
                        self.config[plottype][key] = mpl.colors.to_hex("black")

    def load_config(self):
    # Called to load the current config values into memory
        up_to_date = True

        # Check whether it has all necessary keys inside and if it is readable
        try:
            with open(self.assets_path / "config.json","rb") as config:
                config_dict = orjson.loads(config.read())
                
                # Check whether the config is up-to-date
                # First check whether the necessary top_level keys are there
                if set(config_dict.keys()) == self.plottypes | {"import_data", "General"}:
                    if DEBUG: print("First check o.k.")
                    # Then check whether all necessary nested_keys are there, for this, "import_data" and everything else needs to be treated differently
                    if all(set(self.config[key].keys()) == set(config_dict[key].keys()) | set(config_dict["General"].keys()) for key in self.plottypes):
                        if DEBUG: print("Second check o.k.")
                        # Check the same for the nested values in "import_data", also checks whether all keys are in import_data that should be there
                        # Additionally check whether all infos for the assays are there as they should be
                        if (all(self.import_data[key].keys() == config_dict["import_data"][key].keys() for key in self.plottypes if key not in ["MultiPlot", "Assay"]) and
                            all(self.config["Assay"][assaytype].keys() == config_dict["Assay"][assaytype].keys() for assaytype in self.assaytypes)):
                            if DEBUG: print("Third check o.k.")
                        else: raise KeyError()

                    else: raise KeyError()

                else: raise KeyError()

                for plottype in config_dict:
                    if plottype != "import_data":
                        config_dict[plottype] = config_dict["General"] | config_dict[plottype]
                        for key in config_dict[plottype]:
                            self.config[plottype][key] = config_dict[plottype][key]
                    else:
                        for import_key in config_dict[plottype]:
                            self.import_data.update({import_key:config_dict[plottype][import_key]})

                # Also load general seperately
                for key in config_dict["General"]:
                    self.config["General"][key] = config_dict["General"][key]
                
                config.close()
                    
        except:
            if exists(self.assets_path / "config.json"):
                os_remove(self.assets_path / "config.json")
                up_to_date = False

                print("Config is out-dated or corrupted.")
                print("Creating new config...")
            else:
                print("There seems to be an issue with the config.json file which cannot be resolved.")
                print("A complete reinstallation of the application is recommended.")
        
        if not up_to_date: self.setup_config()
        else: self._normalize_colors()

    def update(self):        

        with open(self.assets_path / "config.json","wb") as f:
            config_dict = {}
            for plottype in self.config:
                config_dict[plottype] = {}
                for key in self.config[plottype]:
                    if plottype != "General":
                        if key in self.config["General"]:
                            if self.config[plottype][key] == self.config["General"][key]: continue
                    config_dict[plottype][key] = self.config[plottype][key]
              
            config_dict["import_data"] = self.import_data
            f.write(orjson.dumps(config_dict, option = orjson.OPT_INDENT_2))
            f.close()

    def open_settings(self):
        settingswindow = SettingsWindow(self.master, self)


class SplitButton(ttk.Frame):
    def __init__(self, master, root, **kw):
        super().__init__(master, **kw)

        self.root = root
        self.__create_buttons()

    def __create_buttons(self):

        # Create an Apply Button
        self.apply_button = ttk.Button(self, text="Apply", command=self.root.apply)
        self.apply_button.grid(column=0, row=0, stick=tk.W, padx=tk.font.Font().measure("▼")*2.1)
        
        # Create menu
        self.apply_menu = ttk.Button(self, text="▼", width=-1, command=self.__show_menu, bootstyle="secondary-outline")
        self.apply_menu.grid(column=0, row=0, stick=tk.E, padx=0)
        
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Apply changes in general to all", command=lambda: self.root.apply(overwrite=True))

    def __show_menu(self):
        x = self.apply_button.winfo_rootx()
        y = self.apply_button.winfo_rooty() + self.apply_button.winfo_height()
        self.menu.post(x, y)

class SettingsWindow(tk.Toplevel):
    _instance = None

    def __init__(self, master, config):

        if SettingsWindow._instance is not None:
            master.after_idle(lambda: (SettingsWindow._instance.lift(), SettingsWindow._instance.focus_force()))
            return
        
        super().__init__(master=master)
        SettingsWindow._instance = self

        self.title("Settings")

        self.master = master # Main Window

        self.config = config # Config

        self.resizable(False, False)

        # Setup dictionary to keep track of StringVariables for each entry
        self.config_variables = {}

        self.filetypes = [".png",".pdf",".svg",".eps",".ps",".jpg",".tiff",".webp", ".raw", ".rgba", ".pgf"]

        # Keep track of the assaytype
        self.assaytype = tk.StringVar(self, sorted(list(self.config.assaytypes))[0])
        self.color_images = {}

        for plottype in self.config.config:
            self.config_variables[plottype] = {}
            for key in self.config.config[plottype]:
                # Special case, in assays there is the possibility to change the label for each assay specifically, thus the variables need to be
                # setup here as well
                if plottype == "Assay" and key in self.config.assaytypes:
                    self.config_variables[plottype][key] = {}
                    for nested_key in ["xlabel", "ylabel"]:
                        self.config_variables[plottype][key][nested_key] = tk.StringVar(self, self.config.config[plottype][key][nested_key])
                else:
                    self.config_variables[plottype][key] = tk.StringVar(self, self.config.config[plottype][key])

        self.__create_widgets()

        self.protocol("WM_DELETE_WINDOW", self.close)

    def _create_color_button(self, parent, plottype, key):
        color = mpl.colors.to_hex(self.config_variables[plottype][key].get())
        image = tk.PhotoImage(width=24, height=24)
        image.put("darkgray", to=(0, 0, 24, 24))
        image.put(color, to=(1, 1, 23, 23))
        self.color_images[(plottype, key)] = image

        button = tk.Label(parent, image=image, bd=0, highlightthickness=0, cursor="hand2")
        button.bind("<Button-1>", lambda event, p=plottype, k=key: self._choose_color(p, k))
        return button

    def _choose_color(self, plottype, key):
        variable = self.config_variables[plottype][key]
        color = askcolor(color=variable.get(), parent=self)[1]
        if color is None:
            return

        color = mpl.colors.to_hex(color)
        variable.set(color)
        image = self.color_images[(plottype, key)]
        image.put(color, to=(1, 1, 23, 23))

    def __create_widgets(self):

        # Create notebook
        self.setup_notebook()
        # Pack Notebook
        self.notebook.pack(side=tk.TOP, expand=True, fill=tk.BOTH)

        ## Setup buttons
        self.button_frame = ttk.Frame(self)
        self.button_frame.pack(side=tk.BOTTOM, anchor=tk.E, fill=tk.X, padx=5, pady=5)

        # Cancel Button
        self.cancel_button = ttk.Button(self.button_frame, text="Cancel", command=self.close, bootstyle="danger")
        self.cancel_button.pack(side=tk.RIGHT, padx=1)

        # Ok button
        self.ok_button = ttk.Button(self.button_frame, text="Ok", command=self.ok)
        self.ok_button.pack(side=tk.RIGHT, padx=1)

        # Apply button
        self.apply_button = SplitButton(self.button_frame, self)
        self.apply_button.pack(side=tk.RIGHT, padx=1)
        
        # Reset Button
        self.reset_button = ttk.Button(self.button_frame, text="Reset", command=self.reset_config, bootstyle="warning")
        self.reset_button.pack(side=tk.LEFT, padx=1)

        vcmd = (self.register(self.validate_callback))
        vcmd_float = (self.register(self.validate_floats))

        self.widgets = {}

        for plottype in {"General"} | self.config.plottypes:


            frame = self.notebook_frames[plottype]
            for i in range(2):
                frame.columnconfigure(i, weight=1)
            self.widgets[plottype] = {}
    
            row = 0

            # Entries for the plot size
            ttk.Label(frame, text="Plot size [in]:", padding=5).grid(row=row, column=0, sticky=tk.W)
            plot_size_entry_frame = ttk.Frame(frame)
            plot_size_entry_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
            self.widgets[plottype]["plot_width"] = ttk.Entry(plot_size_entry_frame, 
                                                             textvariable=self.config_variables[plottype]["plot_width"], 
                                                             validate="all", 
                                                             validatecommand=(vcmd_float, "%P"),
                                                             width=5)
            self.widgets[plottype]["plot_width"].grid(row=0, column=0, sticky=tk.EW)
            ttk.Label(plot_size_entry_frame, text=" x ", padding=5).grid(row=0, column=1)
            self.widgets[plottype]["plot_height"] = ttk.Entry(plot_size_entry_frame, 
                                                              textvariable=self.config_variables[plottype]["plot_height"], 
                                                              validate="all", 
                                                              validatecommand=(vcmd_float, "%P"),
                                                              width=5)
            self.widgets[plottype]["plot_height"].grid(row=0, column=2, sticky=tk.EW)

            for i in [0,2]:
                plot_size_entry_frame.columnconfigure(i, weight=1)

            # Next row
            row += 1

            # Entries for the edge padding
            ttk.Label(frame, text="Edge padding [in]:", padding=5).grid(row=row, column=0, sticky=tk.W)
            plot_pad_entry_frame = ttk.Frame(frame)
            plot_pad_entry_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
            for i, (label, key) in enumerate([("Left:", "padding_left"), ("Right:", "padding_right"), ("Bottom:", "padding_bottom"), ("Top:", "padding_top")]):
                ttk.Label(plot_pad_entry_frame, text=label, padding=5).grid(row=0, column=2*i, sticky=tk.E)
                self.widgets[plottype][key] = ttk.Entry(plot_pad_entry_frame, 
                                                        textvariable=self.config_variables[plottype][key], 
                                                        validate="all", 
                                                        validatecommand=(vcmd_float, "%P"),
                                                        width=3)
                self.widgets[plottype][key].grid(row=0, column=2*i+1, sticky=tk.EW)

            for i in range(4):
                plot_pad_entry_frame.columnconfigure(2*i+1, weight=1)

            # Assay type specific settings
            if plottype == "Assay":
                
                # Next row
                row += 1

                # Combobox to choose the assaytype
                ttk.Label(frame, text="Assay type:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["Assay_type"] = ttk.Combobox(frame, textvariable = self.assaytype, values=list(self.config.assaytypes), state="readonly")
                self.widgets[plottype]["Assay_type"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)
                self.widgets[plottype]["Assay_type"].bind("<<ComboboxSelected>>", self.update_assay_type)

            # Next row
            row += 1

            if plottype == "Assay":
                xlabel_var = self.config_variables[plottype][self.assaytype.get()]["xlabel"]
            else:
                xlabel_var = self.config_variables[plottype]["xlabel"]

            # Xlabel
            ttk.Label(frame, text="Label on x-axis:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["xlabel"] = ttk.Entry(frame, textvariable = xlabel_var)
            self.widgets[plottype]["xlabel"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)

            # Next row
            row += 1

            if plottype == "Assay":
                ylabel_var = self.config_variables[plottype][self.assaytype.get()]["ylabel"]
            else:
                ylabel_var = self.config_variables[plottype]["ylabel"]

            # Ylabel
            ttk.Label(frame, text="Label on y-axis:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["ylabel"] = ttk.Entry(frame, textvariable = ylabel_var)
            self.widgets[plottype]["ylabel"].grid(row=row, column=1, columnspan=2, sticky=tk.EW)

            if plottype in ["CD", "Tm"]:

                # Next row
                row += 1
                
                ttk.Label(frame, text="MRE label on y-axis:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["ylabel_derivative"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["ylabel_MRE"])
                self.widgets[plottype]["ylabel_derivative"].grid(row=row, column=1, columnspan=2, sticky=tk.EW)

            if plottype == "Tm":

                # Next row
                row += 1
                
                ttk.Label(frame, text="Derivative label on y-axis:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["ylabel_derivative"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["ylabel_derivative"])
                self.widgets[plottype]["ylabel_derivative"].grid(row=row, column=1, columnspan=2, sticky=tk.EW)

                # Next row
                row += 1
                
                ttk.Label(frame, text="MRE derivative label on y-axis:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["ylabel_derivative"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["ylabel_MRE_derivative"])
                self.widgets[plottype]["ylabel_derivative"].grid(row=row, column=1, columnspan=2, sticky=tk.EW)

            # Next row
            row += 1
            
            # Linewidth Entry
            ttk.Label(frame, text="Linewidth:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Linewidth"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["lnwdth"], validate="all", validatecommand=(vcmd_float, "%P"))
            self.widgets[plottype]["Linewidth"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)

            # Next row
            row += 1

            # Color picker
            ttk.Label(frame, text="Color:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Color"] = self._create_color_button(frame, plottype, "clr")
            self.widgets[plottype]["Color"].grid(row=row, column=2, sticky=tk.E, padx= (0, 9))

            if plottype in ["Assay", "Tm"]:

                #Next row
                row += 1

                # Fit color picker
                ttk.Label(frame, text="Color of fit:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["Fit_Color"] = self._create_color_button(frame, plottype, "fit_clr")
                self.widgets[plottype]["Fit_Color"].grid(row=row, column=2, sticky=tk.E, padx= (0, 9))

            if plottype == "MALDI":

                # Next row
                row += 1
                # Simulation color picker
                ttk.Label(frame, text="Color of simulation:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["Simulation_Color"] = self._create_color_button(frame, plottype, "simulation_clr")
                self.widgets[plottype]["Simulation_Color"].grid(row=row, column=2, sticky=tk.E, padx= (0, 9))

            # Next row
            row += 1
        
            # Font Combobox
            ttk.Label(frame, text="Font:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Font"] = ttk.Combobox(frame, textvariable = self.config_variables[plottype]["font"], values = sorted(mpl.font_manager.get_font_names()))
            self.widgets[plottype]["Font"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)
                    
            # Next row
            row += 1

            # Fontsize Entry
            ttk.Label(frame, text="Fontsize:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Fontsize"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["fontsize"], validate="all", validatecommand=(vcmd_float, "%P"))
            self.widgets[plottype]["Fontsize"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)

            # Next row
            row += 1
            
            # Automatic_scripts Checkbox
            ttk.Label(frame, text="Recognize super- and subscripts:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Automatic_scripts"] = ttk.Checkbutton(frame, variable = self.config_variables[plottype]["automatic_scripts"], onvalue="True", offvalue="False")
            self.widgets[plottype]["Automatic_scripts"].grid(row=row, column=2, sticky=tk.E)

            # Next row
            row += 1

            # DPI Entry
            ttk.Label(frame, text="DPI:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["DPI"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["dpi"], validate="all", validatecommand=(vcmd_float, "%P"))
            self.widgets[plottype]["DPI"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)

            # Next row
            row += 1

            # Filetype Combobox
            ttk.Label(frame, text="Filetype:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Filetype"] = ttk.Combobox(frame, textvariable = self.config_variables[plottype]["filetype"], values = sorted(self.filetypes))
            self.widgets[plottype]["Filetype"].grid(row=row, column=1, columnspan=2,  sticky=tk.EW)

            # Next row
            row += 1

            # Transparent Checkbox
            ttk.Label(frame, text="Transparent:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Transparent"] = ttk.Checkbutton(frame, variable = self.config_variables[plottype]["transparent"], onvalue="True", offvalue="False")
            self.widgets[plottype]["Transparent"].grid(row=row, column=2, sticky=tk.E)

            # Next row
            row += 1

            # Allow Duplicates Checkbox
            ttk.Label(frame, text="Allow duplicates on export:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["Allow_duplicates"] = ttk.Checkbutton(frame, variable = self.config_variables[plottype]["allow_duplicates"], onvalue="True", offvalue="False")
            self.widgets[plottype]["Allow_duplicates"].grid(row=row, column=2, sticky=tk.E)

            # Next row
            row += 1

            # Export Directory
            ttk.Label(frame, text="Export directory:", padding=5).grid(row=row, column=0, sticky=tk.W)
            self.widgets[plottype]["export_directory"] = ttk.Entry(frame, textvariable = self.config_variables[plottype]["expdir"])
            self.widgets[plottype]["export_directory"].grid(row=row, column=1, sticky=tk.EW, padx=1)

            # Export Directory button
            self.widgets[plottype]["export_directory_btn"] = ttk.Button(frame, text = "...", command=lambda p=plottype: self.pick_export_dir(p), width=0, bootstyle="secondary")
            self.widgets[plottype]["export_directory_btn"].grid(row=row, column=2, padx=0, pady=0, sticky=tk.EW)

            # Next row
            row += 1

            # Dark mode button
            if plottype == "General":
                
                ttk.Label(frame, text="Enable dark mode:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["dark_mode_btn"] = ttk.Checkbutton(frame, variable = self.config_variables[plottype]["dark"], onvalue="True", offvalue="False")
                self.widgets[plottype]["dark_mode_btn"].grid(row=row, column=2, sticky=tk.EW)

                # Next row
                row += 1

            # Colorblind mode button
            if plottype == "General":

                ttk.Label(frame, text="Enable color-blind mode:", padding=5).grid(row=row, column=0, sticky=tk.W)
                self.widgets[plottype]["colorblind_mode_btn"] = ttk.Checkbutton(frame, variable = self.config_variables[plottype]["colorblind"], onvalue="True", offvalue="False")
                self.widgets[plottype]["colorblind_mode_btn"].grid(row=row, column=2, sticky=tk.EW)

                # Next row
                row += 1

            # Bind to events to Combobox
            for events in ["<<ComboboxSelected>>", "<FocusOut>", "<Return>"]:
                self.widgets[plottype]["Color"].bind(events, self.validate_combobox)
                self.widgets[plottype]["Font"].bind(events, self.validate_combobox)
                self.widgets[plottype]["Filetype"].bind(events, self.validate_combobox)

    def validate_floats(self, value):
        try:
            float(value)
            return True
        except:
            if value == "": return True
            else: return False

    def validate_callback(self, value):
        return True

    def update_assay_type(self, event):
        # Update the xlabel and ylabel StringVars to the new assaytype
        new_assaytype = self.assaytype.get()
        self.widgets["Assay"]["xlabel"].config(textvariable = self.config_variables["Assay"][new_assaytype]["xlabel"])
        self.widgets["Assay"]["ylabel"].config(textvariable = self.config_variables["Assay"][new_assaytype]["ylabel"])

    def pick_export_dir(self, plottype):
        
        initialdir = self.config_variables[plottype]["expdir"].get()

        if not exists(initialdir):
            initialdir = "."

        directory = fd.askdirectory(parent=self,
                                    title="Choose Export Directory",
                                    initialdir=initialdir,
                                    mustexist=False
                                    )

        if directory == "": return

        self.config_variables[plottype]["expdir"].set(directory)

    def validate_combobox(self, event):
        # Get the widget because for some reason event.widget becomes a string
        widget = None
        current_key = None

        for plottype in self.widgets:
            for key in self.widgets[plottype]:
                if str(self.widgets[plottype][key]) == event.widget:
                    widget = self.widgets[plottype][key]
                    current_key = key
                    break
            if widget is not None: break

        if widget is None:
            if isinstance(event.widget, str):
                return
            else:
                widget = event.widget
        
        value = widget.get()

        if current_key == "Color":
            if value not in set(mpl.colors.CSS4_COLORS.keys()):
                widget.set("black")
            else: return
        elif current_key == "Font":
            if value not in set(mpl.font_manager.get_font_names()) | {"sans serif"}:
                widget.set("sans serif")
            else: return
        elif current_key == "Filetype":
            if value not in self.filetypes:
                widget.set(".png")
            else: return
        else: return

        print("Assumed illegal value. Returning to default.")

    def setup_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook_frames = {}

        for plottype in ["General"] + sorted(self.config.plottypes):
            self.notebook_frames[plottype] = ttk.Frame(self.notebook)
            self.notebook_frames[plottype].pack(fill="both", expand=True)
            self.notebook.add(self.notebook_frames[plottype], text=plottype)


    def close(self):
        SettingsWindow._instance = None
        self.destroy()

    def ok(self):

        self.apply()

        self.config.update()
        self.close()


    def apply(self, overwrite=False):

        if overwrite:
            print("Overwrite")
            for plottype in self.config.config:
                # Change general last
                if plottype != "General":
                    # Loop through all keys
                    for key in self.config.config[plottype]:
                        # If General and the plottype are equal, change both if general has changed, for this also check whether the key exists in general
                        if key in self.config.config["General"] and self.config.config["General"][key] != self.config_variables["General"][key].get():
                            self.config.config[plottype][key] = self.config_variables["General"][key].get()
                            self.config_variables[plottype][key].set(self.config.config[plottype][key])
                        else:
                            self.config.config[plottype][key] = self.config_variables[plottype][key].get()

        else:
            for plottype in self.config.config:
                # Change general last
                if plottype != "General":
                    # Loop through all keys
                    for key in self.config.config[plottype]:
                        # If General and the plottype are equal, change both if general has changed, for this also check whether the key exists in general
                        if key in self.config.config["General"] and self.config.config[plottype][key] == self.config.config["General"][key]:
                            # Check whether general changed
                            if self.config.config["General"][key] != self.config_variables["General"][key].get():
                                # Check whether the plottype has also changed, this has higher priority then
                                if self.config.config[plottype][key] != self.config_variables[plottype][key].get():
                                    self.config.config[plottype][key] = self.config_variables[plottype][key].get()
                                else:
                                    self.config.config[plottype][key] = self.config_variables["General"][key].get()
                                    self.config_variables[plottype][key].set(self.config.config[plottype][key])
                            else:
                                self.config.config[plottype][key] = self.config_variables[plottype][key].get()
                        else:
                            # In case of assays, the labels can be changed assay-dependent. This key is not part of General thus it will always be executed 
                            # within this code block. Modification is necessary, otherwise .get() will throw a TypeError because it is a dictionary and not a StringVar. 
                            # Thus, check whether the plottype is Assay and the key is one of the assaytypes, then loop through the nested keys and set them accordingly
                            if plottype == "Assay" and key in self.config.assaytypes:
                                for nested_key in ["xlabel", "ylabel"]:
                                    self.config.config[plottype][key][nested_key] = self.config_variables[plottype][key][nested_key].get()
                            else:
                                self.config.config[plottype][key] = self.config_variables[plottype][key].get()
                            
        # Now save general
        for key in self.config.config["General"]:
            self.config.config["General"][key] = self.config_variables["General"][key].get()

        dark = self.config_variables["General"]["dark"].get() == "True"
        if self.master._dark != dark:
            self.master._dark = dark

            info = tk.messagebox.showinfo(title="Restart necessary", message="Please restart the application for all UI changes to take effect.", parent=self)

        colorblind = self.config_variables["General"]["colorblind"].get() == "True"
        self.master._colorblind = colorblind
        
        self.config.update()
        self.master.refresh()

    def reset_config(self):
        config_path = Path(__file__).resolve().parent.parent / "assets" / "config.json"
        if exists(config_path):
            os_remove(config_path)

        self.config.setup_config()

        for plottype in self.config.config:
            for key in self.config.config[plottype]:
                if plottype == "Assay" and key in self.config.assaytypes:
                    for nested_key in self.config_variables[plottype][key]:
                        self.config_variables[plottype][key][nested_key].set(self.config.config[plottype][key][nested_key])
                else:
                    self.config_variables[plottype][key].set(self.config.config[plottype][key])

        self.master.refresh()


        
        
