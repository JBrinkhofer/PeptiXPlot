import orjson
import zstandard as zstd
import numpy as np
import pandas as pd
import sqlite3
from copy import deepcopy
from pathlib import Path

DEBUG = False

folder_icon = "\U0001F4C1"
graph_icon = "\U0001F4C8"

# Serialize pandas DataFrames
def pandas_handler(obj):
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="split")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _new_dict():
    return {}


def _new_list():
    return []


_MULTIPLOT_BASE_DEFAULTS = {
    "legend_transparency": lambda: 0.2,
    "legend_automatic_placement": lambda: True,
    "legend_position": lambda: None,
    "autoadjust_y": lambda: True,
    "y_axis_min": lambda: 0.0,
    "y_axis_max": lambda: 1.0,
    "notepad_text": lambda: "",
    "show_xticks": lambda: True,
    "distance_xticks": lambda: None,
    "offset_xticks": lambda: 0,
    "num_minor_xticks": lambda: 0,
    "show_yticks": lambda: False,
    "distance_yticks": lambda: None,
    "offset_yticks": lambda: 0,
    "num_minor_yticks": lambda: 4,
    "free_text_dict": _new_dict,
}

_MULTIPLOT_PLOTINFO_DEFAULTS = {
    "linestyle": lambda: "solid",
    "alpha": lambda: 1.0,
    "min_y": lambda: None,
    "max_y": lambda: None,
}

_SINGLE_BASE_DEFAULTS = {
    "linestyle": lambda: "solid",
    "autoadjust_y": lambda: True,
    "y_axis_max_percent": lambda: 100,
    "label_orientation": lambda: "horizontal",
    "peak_dict": _new_dict,
    "annotation_coordinate_system": lambda: "offset_points",
    "baseline_iid": lambda: None,
    "baseline_in": _new_list,
    "aspect_ratio": lambda: None,
    "show_xticks": lambda: True,
    "distance_xticks": lambda: None,
    "offset_xticks": lambda: 0,
    "num_minor_xticks": lambda: 0,
    "show_yticks": lambda: False,
    "distance_yticks": lambda: None,
    "offset_yticks": lambda: 0,
    "num_minor_yticks": lambda: 4,
    "notepad_text": lambda: "",
    "free_text_dict": _new_dict,
    "smoothing_method": lambda: "None",
    "background_correction_method": lambda: "None",
    "background_correction": lambda: np.array([], dtype=np.float64),
}

_SINGLE_MALDI_DEFAULTS = {
    "inset": lambda: False,
    "inset_pos": lambda: "upper right",
    "inset_y_axis_max_percent": lambda: 100,
    "inset_xsize": lambda: 40,
    "inset_ysize": lambda: 40,
    "inset_borderpad": lambda: 2.0,
    "mirror_annotations": lambda: True,
    "inset_label_orientation": lambda: "horizontal",
    "inset_peak_dict": _new_dict,
    "inset_annotation_coordinate_system": lambda: "offset_points",
}

_SINGLE_CD_DEFAULTS = {
    "show_zero_line": lambda: False,
    "zero_line_color": lambda: "black",
    "zero_line_linestyle": lambda: "dotted",
}

_SINGLE_CD_TM_DEFAULTS = {
    "pathlength": lambda: 1,
    "concentration": lambda: 0.05,
    "nbr_of_residues": lambda: 1,
    "show_yticks": lambda: True,
    "calc_MRE": lambda: True,
}

_SINGLE_TM_DEFAULTS = {
    "wavelength": lambda: 228,
    "fits": _new_dict,
    "Tm_method": lambda: "SCB",
    "show_tm_baselines": lambda: False,
    "show_fit": lambda: True,
    "fit_linestyle": lambda: "solid",
}

_SINGLE_HPLC_DEFAULTS = {
    "integration_type": lambda: "local",
    "integral_dict": _new_dict,
    "plot_integrals": lambda: False,
}


class DatabaseHandler:
    def __init__(self, DEBUG, config):

        DEBUG = DEBUG
        
        self.config = config
        db_path = Path(__file__).resolve().parent.parent / "assets" / "saves.db"
        self.conn = sqlite3.connect(db_path)
        
        # Dictionary that contains all necessary information for the graphs loaded to memory
        self.save_data = {}

        # Dictionary that contains all necessary information for the multiplot saves
        self.multiplot_save_data = {}

        # Keep track of Browser Information
        self.browser_saves = {} # {iid: {filename: str, plottype: str, folder: bool}}
        self.multiplot_browser_saves = {} # {iid: {filename: str, plottype: str, folder: bool}}

        # Setup compressor context
        self.cctx = zstd.ZstdCompressor(level=3)
        self.dctx = zstd.ZstdDecompressor()

    def close(self):
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    def prepare_saves(self):

        cursor = self.conn.cursor()

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS trees (
                    type TEXT PRIMARY KEY,
                    data BLOB
                )
            """)
        
        #Generate empty saves
        saves = [[],[],[],[],[],[]]
        
        json_saves = orjson.dumps(saves)
        compressed_saves = self.cctx.compress(json_saves)
        
        # Add empty saves so browsers can be initialized properly
        for browser_type in {"plot","multiplot"}:
            
            cursor.execute(f"""
                INSERT OR IGNORE INTO trees (type, data)
                VALUES (?,?)
            """, (browser_type, compressed_saves))
        self.conn.commit()

    def setup_import_preset_table(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_presets (
                plottype TEXT NOT NULL,
                name TEXT NOT NULL,
                data BLOB NOT NULL,
                PRIMARY KEY (plottype, name)
            )
        """)
        self.conn.commit()

    def save_import_preset(self, plottype, name, data):

        cursor = self.conn.cursor()
        compressed_data = self.cctx.compress(orjson.dumps(data))
        cursor.execute(
            "INSERT OR REPLACE INTO import_presets (plottype, name, data) VALUES (?, ?, ?)",
            (plottype, name, compressed_data),
        )
        self.conn.commit()

    def load_import_presets(self):
        cursor = self.conn.cursor()

        cursor.execute("SELECT plottype, name, data FROM import_presets ORDER BY plottype, name")
        rows = cursor.fetchall()

        presets = {}
        for plottype, name, data in rows:
            presets.setdefault(plottype, {})[name] = orjson.loads(self.dctx.decompress(data))
        return presets

    def delete_import_preset(self, plottype, name):
        if not name or name == "Default":
            raise ValueError("The Default preset cannot be deleted.")

        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM import_presets WHERE plottype = ? AND name = ?",
            (plottype, name),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()

        if not deleted:
            raise KeyError(f"No import preset named '{name}' exists.")

    def save_browser(self, browser_type, saves):
        # Browser type is either plot or multiplot
        if browser_type not in {"plot","multiplot"}: return

        cursor = self.conn.cursor()
        json_saves = orjson.dumps(saves)
        compressed_saves = self.cctx.compress(json_saves)
        # Insert or Replace the info in the database
        cursor.execute(f"""
            INSERT OR REPLACE INTO trees (type, data)
            VALUES (?,?)
        """, (browser_type, compressed_saves))
        
        self.conn.commit()

    def load_browser(self, browser_type):
        # Browser type is either plot or multiplot

        if browser_type not in {"plot","multiplot"}: return

        cursor = self.conn.cursor()

        cursor.execute("SELECT data FROM trees WHERE type = ?", (browser_type,))
        row = cursor.fetchone()

        if row is not None:
            compressed_saves = row[0]
        else:
            print("No such file in the database.")
            return

        # Decompress data
        json_saves = self.dctx.decompress(compressed_saves)

        (widgets, text, values, parent, indices, tags) = orjson.loads(json_saves)

        return widgets, text, values, parent, indices, tags

    def add_new_save(self):

        cursor = self.conn.cursor()

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS saves (
                    iid INTEGER PRIMARY KEY AUTOINCREMENT,
                    data BLOB
                )
            """)

        # Create empty entry
        cursor.execute("INSERT INTO saves (data) VALUES (NULL)")
        self.conn.commit()

        # Get iid of newest entry
        iid = cursor.lastrowid

        return str(iid)
        

    def save(self, iid, MultiPlot=False):

        if DEBUG: print(f"Saving {iid} with MultiPlot={MultiPlot}")

        cursor = self.conn.cursor()

        cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS saves (
                    iid INTEGER PRIMARY KEY AUTOINCREMENT,
                    data BLOB
                )
            """)

        # Check if a table with the plottype has already been created
        if not MultiPlot:

            export_data = dict(self.save_data[iid])

            # The keys in the dictionaries need to be converted back to strings
            self.convert_dict_keys_to_str(export_data, "peak_dict")

            self.convert_dict_keys_to_str(export_data, "inset_peak_dict")

            # Serialize the data with orjson
            data = orjson.dumps(export_data,
                                option=orjson.OPT_SERIALIZE_NUMPY,
                                default=pandas_handler,
            )
            
        else:

            # Serialize the data with orjson
            data = orjson.dumps(self.multiplot_save_data[iid], 
                                option=orjson.OPT_SERIALIZE_NUMPY, 
                                default=pandas_handler)

        # Compress data before saving using zstandard
        compressed_data = self.cctx.compress(data)

        # Insert or Replace the info in the database
        cursor.execute("""
            INSERT OR REPLACE INTO saves (iid, data)
            VALUES (?,?)
        """, (iid, compressed_data))

        self.conn.commit()

    def format_linestyle(self, dict, key):

        if key in dict:
            # Here check whether linestyle is a tuple like it should be, when it is possible
            linestyle = dict[key]

            if (not isinstance(linestyle, str)) and len(linestyle) == 2:
                try:
                    linestyle[1] = tuple(linestyle[1])
                    linestyle = tuple(linestyle)
                except:
                    linestyle = "solid"

            dict[key] = linestyle

    # Function to load the right iid into memory
    def load(self, iid, MultiPlot: bool = False, delete=False):
        # Adding MultiPlot to differentiate regular plots and multiplots
        # Delete is used to not check for deprecated saves for files that should be deleted because this is unnecessary

        if DEBUG: print(f"Loading {iid} with MultiPlot={MultiPlot} and delete={delete}")

        if iid not in self.browser_saves | self.multiplot_browser_saves:
            print(f"Selected iid {iid} is invalid.")
            return False

        if MultiPlot:
            plottype = "MultiPlot"
            filename = self.multiplot_browser_saves[iid]["filename"]
            if iid in self.multiplot_save_data:
                self.initiated = True
                return True

        else:
            plottype = self.browser_saves[iid]["plottype"]
            filename = self.browser_saves[iid]["filename"]
            if iid in self.save_data:
                self.initiated = True
                return True
            
        cursor = self.conn.cursor()

        self.initiated = False
        
        print(f"Loading {plottype} plot \"{filename}\"")

        cursor.execute("SELECT data FROM saves WHERE iid = ?", (iid,))
        row = cursor.fetchone()

        if row is not None:
            json_data = row[0]
        else:
            print("No such file in the database.")
            return False

        if json_data is not None:

            # Decompress
            decompressed_data = self.dctx.decompress(json_data)

            # Unserialize the json data
            data = orjson.loads(decompressed_data)

            if MultiPlot:

                if not delete:

                    # Check data for backwards compatibility
                    data, up_to_date = self.backwards_compatibility(data, MultiPlot=True)

                    # Convert the xpoints and ypoints of the dictionary back to NumPy arrays, in case of an assay
                    if data["PlotOptions"]["plottype"] == "Assay":
                        data["PlotOptions"]["xpoints"] = np.array(data["PlotOptions"]["xpoints"],dtype=np.float64)
                        data["PlotOptions"]["ypoints"] = np.array(data["PlotOptions"]["ypoints"],dtype=np.float64)
                        data["PlotOptions"]["x_err"] = np.array(data["PlotOptions"]["x_err"],dtype=np.float64)
                        data["PlotOptions"]["y_err"] = np.array(data["PlotOptions"]["y_err"],dtype=np.float64)
                        data["PlotOptions"]["sigma"] = np.array(data["PlotOptions"]["sigma"],dtype=np.float64)

                        self.format_linestyle(data["PlotOptions"], "assay_fit_linestyle")


                    for plot_iid in data:
                        if plot_iid != "PlotOptions":

                            self.format_linestyle(data[plot_iid], "linestyle")
                    
                    self.multiplot_save_data.update({iid:data})

                    if not up_to_date: self.save(iid, MultiPlot=True)
                
                else:
                    self.multiplot_save_data.update({iid:data})

            else:

                if not delete:

                    # Check data for backwards compatibility
                    data, up_to_date = self.backwards_compatibility(data, plottype=plottype, MultiPlot=False)

                    # Convert the xpoints and ypoints of the dictionary back to NumPy arrays 
                    data["xpoints"] = np.array(data["xpoints"],dtype=np.float64)
                    data["ypoints"] = np.array(data["ypoints"],dtype=np.float64)
                    data["background_correction"] = np.array(data["background_correction"],dtype=np.float64)
                    
                    # Convert the string keys of the dictionaries back to floats
                    peak_dict = {}
                    ipeak_dict = {}
                    for key, value in data["peak_dict"].items():
                        peak_dict[float(key)] = value
                    
                    if "inset_peak_dict" in data:
                        for key, value in data["inset_peak_dict"].items():
                            ipeak_dict[float(key)] = value
                        data["inset_peak_dict"] = ipeak_dict
                    
                    data["peak_dict"] = peak_dict

                    for linestyle_key in ["linestyle", "zero_line_linestyle"]:

                        self.format_linestyle(data, linestyle_key)

                    if "inset_borderpad" in data:

                        # Also check whether borderpad is a tuple like it should be, when it is possible
                        borderpad = data["inset_borderpad"]

                        if (not isinstance(borderpad, (str, int, float))) and len(borderpad) == 2:
                            try:
                                borderpad = tuple(borderpad)
                            except:
                                borderpad = 2.0

                        data["inset_borderpad"] = borderpad

                    self.save_data.update({iid:data})

                    if not up_to_date: self.save(iid, MultiPlot=False)
                
                else:
                    self.save_data.update({iid:data})

            return True
                
        else:
            
            print("No such file in the database.")
            
            return False

    def unload(self, iid, MultiPlot: bool = False):
        if MultiPlot:
            if iid in self.multiplot_save_data:
                self.multiplot_save_data.pop(iid)
        else:
            if iid in self.save_data:
                self.save_data.pop(iid)

    def export(self, iid_dict:dict, export_filename):
        # Iid_dict should be a dict with tuples with {iid:str: (MultiPlot:bool, folder:bool)}
            
        # Extended_iid_dict is the dict resulting from all checks whether even more iids need to be exported than selected
        extended_iid_dict = deepcopy(iid_dict)

        # The export dictionary which will be converted to a json and compressed
        export_dict = {"browser": {"widgets": [],
                                   "text": [],
                                   "values": [],
                                   "parent": [],
                                   "indices": [],
                                   "tags": [],
                                },
                       "multiplot_browser": {"widgets": [],
                                             "text": [],
                                             "values": [],
                                             "parent": [],
                                             "indices": [],
                                             "tags": [],
                                        },
                       "saves": {},
                       }

        # First load all relevant MultiPlots
        for iid, (MultiPlot, folder) in iid_dict.items():
            # Load all dependent plots for the MultiPlots
            if MultiPlot and not folder:
                self.load(iid=iid, MultiPlot=MultiPlot)

                for plot_iid in self.multiplot_save_data[iid]:
                    if plot_iid != "PlotOptions":
                        if self.load(iid=plot_iid, MultiPlot=False):
                            extended_iid_dict[plot_iid] = (False, False)

        iid_dict = deepcopy(extended_iid_dict)
        # Now load all regular plots and their respective baselines/blanks. 
        for iid, (MultiPlot, folder) in iid_dict.items():
            if (not MultiPlot) and (not folder):
                if self.load(iid=iid, MultiPlot=MultiPlot):
                    baseline_iid = self.save_data[iid]["baseline_iid"]
                    if baseline_iid:
                        if self.load(iid=baseline_iid, MultiPlot=False):
                            extended_iid_dict[baseline_iid] = (False, False)

        iid_dict = deepcopy(extended_iid_dict)

        widgets, text, values, parent, indices, tags = self.load_browser("plot")
        # Get all current saves from the browser
        browser = {"widgets": widgets,
                   "text": text,
                   "values": values,
                   "parent": parent,
                   "indices": indices,
                   "tags": tags}
        
        # Get all current saves from the multiplot browser
        widgets, text, values, parent, indices, tags = self.load_browser("multiplot")
        multiplot_browser = {"widgets": widgets,
                             "text": text,
                             "values": values,
                             "parent": parent,
                             "indices": indices,
                             "tags": tags}

        print("Preparing files for export...")
        # Now add all those saves to the export_dict
        for iid, (MultiPlot, folder) in iid_dict.items():
            print(f"Preparing {iid} for export...\nMultiPlot: {MultiPlot}. Folder: {folder}")
            if not folder:
                export_dict["saves"][iid] = deepcopy(self.multiplot_save_data[iid] if MultiPlot else self.save_data[iid])

                if not MultiPlot:

                    # Convert the dict keys to strings
                    self.convert_dict_keys_to_str(export_dict["saves"][iid], "peak_dict")

                    self.convert_dict_keys_to_str(export_dict["saves"][iid], "inset_peak_dict")

            # Add the necessary browser saves to browser or multiplot_browser
            if MultiPlot:
                browser_save = multiplot_browser
                browser_str = "multiplot_browser"
            else:
                browser_save = browser
                browser_str = "browser"

            index = browser_save["widgets"].index(iid)

            # Add the actual browser save to the list in case it has not yet been added by any other logic
            if browser_save["widgets"][index] not in export_dict[browser_str]["widgets"]:
                for key in export_dict[browser_str]:
                    export_dict[browser_str][key].append(browser_save[key][index])

                parent = browser_save["parent"][index]

                # Check whether it has a parent, iteratively
                while parent:
                    parent_index = browser_save["widgets"].index(parent)

                    if browser_save["widgets"][parent_index] not in export_dict[browser_str]["widgets"]:
                        for key in export_dict[browser_str]:
                            # To be sure, parents should always be inserted in the front so they are always before their respective children
                            export_dict[browser_str][key].insert(0, browser_save[key][parent_index])
                    parent = browser_save["parent"][parent_index]

        print("Done.")
        print("Serializing...")
        # Serialize the data with orjson
        data = orjson.dumps(export_dict, 
                            option=orjson.OPT_SERIALIZE_NUMPY, 
                            default=pandas_handler)
        print("Done.")
        print("Compressing...")
        # Compress data at a higher level than usual
        compressed_export_data = zstd.compress(data=data, level=10)
        print("Done.")
        print("Writing to file...")
        with open(file=export_filename, mode="wb") as f:
            f.write(compressed_export_data)

        print("Export done.")

    def decompress_import(self, compressed_data):

        print("Decompressing...")
        data = self.dctx.decompress(compressed_data)
        print("Done.")

        print("Deserializing...")
        import_dict = orjson.loads(data)
        print("Done.")
    
        return import_dict

    def delete_save(self, iid, MultiPlot: bool = False):
        
        cursor = self.conn.cursor()
    
        if MultiPlot:

            filename = self.multiplot_browser_saves[iid]["filename"]
            if self.multiplot_browser_saves[iid]["plottype"] == "Assay":
                plottype = "Assay"
            else:
                plottype = "MultiPlot"

            # If the file is a folder, return
            if self.multiplot_browser_saves[iid]["folder"]: return

            # If the file is currently loaded, unload it
            if iid in self.multiplot_save_data: self.multiplot_save_data.pop(iid)
            
        else:

            plottype = self.browser_saves[iid]["plottype"]
            filename = self.browser_saves[iid]["filename"]

            # If the file is a folder, return
            if self.browser_saves[iid]["folder"]: return

            # If there is an error in how the data is saved, this bit keeps the user from deleting corrupted saves

            try:
                # Load plot first if necessary
                if iid not in self.save_data:
                    self.load(iid, delete=True)

                # Check whether this file is a baseline for another file
                if self.save_data[iid]["baseline_in"]: self.remove_baseline_from_plots(iid, self.save_data[iid]["baseline_in"])

                # unload the file
                self.save_data.pop(iid)
                
            except: pass

        print(f"Deleting {plottype} plot \"{filename}\"")

        cursor.execute(f"DELETE FROM saves WHERE iid = ?", (iid,))

        self.conn.commit()

    def check_vacuum(self):
        # Check whether the database has large empty rows and if so, vacuum the database
        
        cursor = self.conn.cursor()

        # Number of unused pages
        cursor.execute("PRAGMA freelist_count")
        free_pages = cursor.fetchone()[0]

        # Total number of pages
        cursor.execute("PRAGMA page_count")
        total_pages = cursor.fetchone()[0]

        ratio = free_pages / total_pages if total_pages else 0

        # If more than 33% of the database are unused, vacuum the database
        if ratio > 0.33:
            print("Compacting the database...")
            cursor.execute("VACUUM")
            print("Done.")

    def remove_baseline_from_plots(self, baseline_iid: str, plot_iids: list):

        # Iterate through all plots that have baseline_iid as their baseline
        for iid in plot_iids:

            # Load the plot if necessary
            if iid not in self.save_data:
                self.load(iid)

            # Check whether the baseline_iid of the loaded object is actually the one expected, if true set it to None
            if self.save_data[iid]["baseline_iid"] == baseline_iid:
                
                self.save_data[iid]["baseline_iid"] = None
                self.save(iid, MultiPlot=False)

    def convert_dict_keys_to_str(self, export_dict, dict_key):

        # Check whether this dictionary is actually in export_dict

        if dict_key in export_dict:
                
                new_dict = {}
                
                if not isinstance(export_dict[dict_key], dict):
                    export_dict[dict_key] = dict(export_dict[dict_key])
                    
                for key, value in export_dict[dict_key].items():
                    for count, item in enumerate(value):
                        if type(item) == np.float64:
                            value[count] = float(item)
                    new_dict[str(key)] = value

                export_dict[dict_key] = new_dict

    def backwards_compatibility(self, data_dict, iid=None, MultiPlot=False, plottype=None, skip_msg=False):        

        # Remember whether the data was up-to-date, if not save the loaded data immediately after updating it
        up_to_date = True

        if MultiPlot:

            plotoptions = data_dict["PlotOptions"]
            plottype = "MultiPlot"

            # In initial versions "PlotOptions" is a list, in that case, convert it to a dictionary
            if isinstance(plotoptions, list):
                print("Found deprecated state of \"PlotOptions\", converting to dictionary...")
                plotoptions_dict= {"filename": plotoptions[0],
                                   "x_axis_min": plotoptions[1],
                                   "x_axis_max": plotoptions[2],
                                   "plottype": plotoptions[3]
                }

                plotoptions = plotoptions_dict

            # In versions before v0.6.2, all other iid entries in the data_dict were lists, convert them to dictionaries and also check whether they are correct for backwards compatibility
            for iid in data_dict:
                if iid != "PlotOptions":
                    if isinstance(data_dict[iid], list):
                        print(f"Found deprecated state of MultiPlot plotinfo for {iid}, converting to dictionary...")

                        data_dict[iid] = {"filename": data_dict[iid][0],
                                          "linewidth": data_dict[iid][1],
                                          "color": data_dict[iid][2],
                                          "position": data_dict[iid][3],
                                          }
                
            plotoptions_structure = dict(_MULTIPLOT_BASE_DEFAULTS)
            if plotoptions["plottype"] != "Assay":
                plotoptions_structure.update({"normalization": lambda: True,
                                              "plot_offset": lambda: True,
                                              "labels": lambda: "In Axes",
                                              "label_data": lambda: {"match_color": True,
                                                                     "xposition": 0.99,
                                                                     "yposition": 0.525,
                                                                     "fontsize": self.config.config[plottype]["fontsize"]},
                                              "global_min_y": lambda: None, # Keep track of the global minimum y value
                                              "global_max_y": lambda: None, # Keep track of the global maximum y value
                                              "colormap": lambda: None, # Keep track of the colormap that should be used
                                              "3D": lambda: False,
                                              "3D_data": lambda: {"elev": 30,
                                              "azim": -30,
                                              "projection_type": "persp",
                                              "offset": 1.0},
                    })

            if plotoptions["plottype"] == "Tm":
                plotoptions_structure.update({"wavelength": lambda: 228, # Wavelength at which Tm was measured
                                              "show_fit": lambda: True, # Whether to show the fit
                                              "Tm_method": lambda: "SCB", # Method that is supposed to be shown in the graph
                                              "show_tm_baselines": lambda: False, # Whether to show the baselines in the plot
                    })

            if plotoptions["plottype"] in ["CD","Tm"]:
                plotoptions_structure.update({"show_yticks": lambda: True, # Whether to show ticks on the yaxis or not
                                              "calc_MRE": lambda: True, # Whether to calculate MRE or show measured ellipticity
                    })

            if plotoptions["plottype"] == "Assay":
                plotoptions_structure.update({"xpoints": lambda: np.array([]), # The xpoints of the assay plot
                                              "ypoints": lambda: np.array([]), # The ypoints of the assay plot
                                              "x_err": lambda: np.array([]), # The x error of the assay plot
                                              "y_err": lambda: np.array([]), # The y error of the assay plot
                                              "sigma": lambda: np.array([]), # The sigma of the assay plot
                                              "color": lambda: self.config.config[plottype]["clr"], # The color of the markers
                                              "linestyle": lambda: "solid", # The linestyle of the markers
                                              "show_yticks": lambda: True, # Show y-ticks by default
                                              "y_axis_max_percent": lambda: 100, #Height of y-axis in percent
                                              "assay_plottypes": lambda: None, # The kind of plottype the plots have that can be added to the assay, so only fitting plottypes can be added
                                              "assay_type": lambda: None, # Which kind of assay is plotted, e.g. "Michaelis-Menten", "Hill", "Binding"
                                              "assay_fit": lambda: {}, # Dictionary to hold information about fitting params
                                              "show_assay_fit": lambda: True, # Whether to show the fit in the plot
                                              "assay_fit_color": lambda: self.config.config["Assay"]["fit_clr"], # The color of the fit
                                              "assay_fit_linestyle": lambda: "solid", # The linestyle of the fit
                                              "assay_fit_linewidth": lambda: float(self.config.config["Assay"]["fit_linewidth"]), # The linewidth of the fit
                                              "assay_datapoints": lambda: {}, # Dictionary to keep track of the actual datapoints to show on the assay plot. {name: {plots, x, y, error,}}
                                              "assay_x_unit": lambda: "M", # The unit of the x-axis in the assay plot
                                              "assay_y_unit": lambda: "M/s", # The unit of the y-axis in the assay plot
                                              "molar_absorption_coefficient": lambda: 1, # The molar absorption coefficient of the protein/peptide in M/cm
                                              "assay_x_label": lambda: "", # The label of the x-axis in the assay plot
                                              "assay_y_label": lambda: "", # The label of the y-axis in the assay plot
                                              "show_vmax": lambda: False, # Whether to show the vmax in the assay plot
                                              "show_Km": lambda: False, # Whether to show the km in the assay plot
                                              "show_fit_data": lambda: False, # Whether to show the data in the fit in the assay plot
                                              "autosort_files": lambda: True, # Whether to guess the x-Coordinate from the filename and add 
                                            })

                plotinfo_structure = {}

            # Also check the plotinfo structure for all the single plot settings inside of a MultiPlot, if they are not present, add them with default values
            if plotoptions["plottype"] != "Assay":
                plotinfo_structure = _MULTIPLOT_PLOTINFO_DEFAULTS

        else:

            if iid is not None and plottype is None:
                # Check whether plottype is already in data_dict
                if "plottype" not in data_dict:
                    data_dict["plottype"] = self.browser_saves[iid]["plottype"]

            elif plottype is not None:
                if "plottype" not in data_dict:
                    data_dict["plottype"] = plottype

            plottype = data_dict["plottype"]

            #Only check for things that might not exist in previous versions. Filename, xpoints and ypoints definitely exist, all other things
            #Lambda functions are used, so that no unnecessary computation is involved

            data_structure = dict(_SINGLE_BASE_DEFAULTS)
            data_structure.update({
                "x_axis_min": lambda: float(data_dict["xpoints"].min()),
                "x_axis_max": lambda: float(data_dict["xpoints"].max()),
                "y_axis_min": lambda: float(data_dict["ypoints"].min()),
                "y_axis_max": lambda: float(data_dict["ypoints"].max()),
                "color": lambda: self.config.config[plottype]["clr"],
            })

            if plottype == "MALDI":
                data_structure.update(_SINGLE_MALDI_DEFAULTS)
                data_structure.update({
                    "inset_x_axis_min": lambda: float(data_dict["xpoints"].min()),
                    "inset_x_axis_max": lambda: float(data_dict["xpoints"].max()),
                    "inset_fontsize": lambda: self.config.config[plottype]["fontsize"],
                })

            if plottype == "CD":
                data_structure.update(_SINGLE_CD_DEFAULTS)
                data_structure["zero_line_linewidth"] = lambda: self.config.config[plottype]["lnwdth"]

            if plottype in ["CD", "Tm"]:
                data_structure.update(_SINGLE_CD_TM_DEFAULTS)

            if plottype == "Tm":
                data_structure.update(_SINGLE_TM_DEFAULTS)
                data_structure["fit_color"] = lambda: self.config.config[plottype]["fit_clr"]

            if plottype == "HPLC":
                data_structure.update(_SINGLE_HPLC_DEFAULTS)
                data_structure["integration_info"] = lambda: {
                    "linear": [
                        float(data_dict["xpoints"].min())
                        + (float(data_dict["xpoints"].max()) - float(data_dict["xpoints"].min())) / 10,
                        float(data_dict["xpoints"].max())
                        - (float(data_dict["xpoints"].max()) - float(data_dict["xpoints"].min())) / 5,
                    ],
                    "constant": float(data_dict["ypoints"].min()),
                    "manual": [
                        [float(data_dict["xpoints"].min()), float(data_dict["xpoints"].max())],
                        [float(data_dict["ypoints"].min()), float(data_dict["ypoints"].max())],
                    ],
                }

            if plottype == "Kinetics":
                data_structure.update({"xlabel": lambda: self.config.config[plottype]["xlabel"], # The label of the x-axis in the kinetics plot
                                       "ylabel": lambda: self.config.config[plottype]["ylabel"], # The label of the y-axis in the kinetics plot
                    })
            

        if MultiPlot:

            if not skip_msg:
                missing_keys = []
                filename = plotoptions["filename"]
            else:
                missing_keys = None
                filename = None
            # Check whether data is in the dictionary
            for key, func in plotoptions_structure.items():
                if key not in plotoptions:
                    if missing_keys is not None:
                        missing_keys.append(key)
                    plotoptions[key] = func()
                    up_to_date = False

            # Check whether data in the remaining plotinfo is okay
            for plot_iid, plotinfo in data_dict.items():
                if plot_iid != "PlotOptions":
                    for key, func in plotinfo_structure.items():
                        if key not in plotinfo:
                            if missing_keys is not None:
                                missing_keys.append(f"{plotinfo['filename']}: {key}")
                            plotinfo[key] = func()
                            up_to_date = False

            if missing_keys is not None:
                if len(missing_keys) == 1:
                    print(f"Recognized missing key in {filename}. Adding {missing_keys[0]} to data")
                elif len(missing_keys) > 1:
                    print(f"Recognized missing keys in {filename}. Adding {missing_keys} to data")
            

        else:

            if not skip_msg:
                missing_keys = []
                filename = data_dict["filename"]
            else:
                missing_keys = None
                filename = None
                
            # Check whether data is in the dictionary
            for key, func in data_structure.items():
                if key not in data_dict:
                    if missing_keys is not None:
                        missing_keys.append(key)
                    data_dict[key] = func()
                    up_to_date = False


            if missing_keys is not None:
                if len(missing_keys) == 1:
                    print(f"Recognized missing key in {filename}. Adding {missing_keys[0]} to data")
                elif len(missing_keys) > 1:
                    print(f"Recognized missing keys in {filename}. Adding {missing_keys} to data")

            # Some changes now rightfully turned two keys from strings into booleans, this should be checked and updated properly:
            if plottype in ["HPLC", "MALDI"]:
                updated_keys = []

                if plottype == "MALDI":
                    
                    if type(data_dict["inset"]) == str:
                        data_dict["inset"] = True if data_dict["inset"] == "True" else False
                        updated_keys.append("inset")
                    if type(data_dict["mirror_annotations"]) == str:
                        data_dict["mirror_annotations"] = True if data_dict["mirror_annotations"] == "True" else False
                        updated_keys.append("mirror_annotations")

                # Also update HPLC manual two have two lists, xpoints and ypoints to make sure that this integration works properly
                elif plottype == "HPLC":
                    if len(data_dict["integration_info"]["manual"]) < 2 or sum(isinstance(x, list) for x in data_dict["integration_info"]["manual"]) != 2:
                        data_dict["integration_info"]["manual"] = [[float(data_dict["xpoints"].min()),float(data_dict["xpoints"].max())],
                                                                [float(data_dict["ypoints"].min()),float(data_dict["ypoints"].max())]]
                        updated_keys.append("integration_info[\"manual\"]")

                if not skip_msg:
                    if len(updated_keys) == 1:
                        print(f"Recognized deprecated key in {filename}. Updating {updated_keys[0]}")
                        up_to_date = False
                    elif len(updated_keys) > 1:
                        print(f"Recognized deprecated keys in {filename}. Updating {updated_keys}")
                        up_to_date = False

        return data_dict, up_to_date
            
            
