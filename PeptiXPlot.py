import ast
import re
import tkinter as tk
import ttkbootstrap as ttk
from tkinter.colorchooser import askcolor
from ttkbootstrap.widgets import scrolled
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from difflib import SequenceMatcher
from natsort import natsorted, natsort_keygen, ns
from decimal import Decimal
import webbrowser

natural_keygen = natsort_keygen(alg=ns.REAL)

mpl.use("TkAgg")
mpl.rcParams["mathtext.default"]="rm"
from os import makedirs, mkdir
from os.path import exists
from molmass import Formula, from_peptide
from math import ceil
from sys import exit as syexit
from scipy.optimize import curve_fit
from scipy.stats import linregress
from scipy.signal import savgol_filter
from copy import deepcopy
from filelock import FileLock, Timeout

# Part of this application
from DataHandler.DBhandler import DatabaseHandler
from DataHandler.dataloader import ImportHandler
from DataHandler.baselines import BlankHandler
from DataHandler.config import ConfigHandler
from PlotHandler.Plotter import CanvasPlot
from HelperScripts.formats import normalize_rgb_tuple, return_regular_rgb_tuple
from HelperScripts.math import sigmoidal_constant_baseline, sigmoidal_linear_baseline, sigmoidal_quadratic_baseline, vant_hoff, gaussian, michaelis_menten, R_square, return_fit_param, get_maximum, get_minimum, emancipator_kroll_nonlinearity, smooth_signal, get_baseline
from GUI.Widgets import CollapsibleFrame

# Necessary for custom images
from pathlib import Path

DEBUG = False

search_icon = "\U0001F50D"

if DEBUG: print("Font:",mpl.rcParams["font.family"][0])

assets_path = Path(__file__).resolve().parent / "assets"

if not exists(assets_path):
    mkdir(assets_path)

lock = FileLock(assets_path / "PeptiXPlot.lock", timeout=0)

try:
    lock.acquire()
except Timeout:
    print("Another instance of PeptiXPlot is already running. Please close it before starting a new one.")
    from time import sleep
    sleep(3)
    raise SystemExit(1)

class ImageEntry(tk.Frame):
    def __init__(self, master=None, image=None, **kwargs):
        super().__init__(master, **kwargs)
        self.master = master
        self.image = image

        # ImageLabel for putting next to the entry
        self.image_label = ttk.Label(self, image=image)
        self.image_label.pack(side="left", padx=0, ipadx=0)

        # Actual entry
        self.entry = tk.Entry(self)
        self.entry.pack(side="left", expand=True, fill="both", padx=0, ipadx=0)

        self.configure(borderwidth=self.entry.cget("borderwidth"),
                       relief=self.entry.cget("relief"),
                       cursor=self.entry.cget("cursor"))

        self.entry.configure(border=0, 
                             borderwidth=0, 
                             background=self.cget("background"))
        
        self._destroying = False
        self._entry_destroy = self.entry.destroy
        
        self.entry.destroy = self.safe_entry_destroy
        
        
 
    def safe_entry_destroy(self, *args, **kwargs):
        if self._destroying:
            return self._entry_destroy(*args, **kwargs)

        self._destroying = True
        try:
            self._entry_destroy(*args, **kwargs)
        finally:
            self.destroy()

    # Overwrite widget methods to focus on the actual entry
    def focus(self):
        self.entry.focus()

    def insert(self, index, string: str):
        self.entry.insert(index=index, string=string)

    def select_range(self, start, end):
        self.entry.select_range(start, end)

    def get(self):
        return self.entry.get()
    
    def bind_to_all(self, *args, **kwargs):
        for widget in [self] + self.winfo_children():
            widget.bind(*args, **kwargs)
    
class BrowserBase(ttk.Treeview):
    def __init__(self, master, root, **kw):
        super().__init__(master, **kw)

        self.bind("<Delete>", self.on_delete)
        self.bind("<Button-3>", self.popup)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Double-1>", self.on_double_click)
        self.bind("<MouseWheel>", self.on_mousewheel, add="+")
        self.bind("<Control-x>", self.cut)
        self.bind("<Control-c>", self.copy)
        self.bind("<Control-v>", self.paste)

        self.root = root
        self.master = master
        self.widget_edit = None
        self.popup_coords = None
        self.browser_type = None

        # Iids to cut, or copy
        self.cut_iids = []
        self.copy_iids = []

        # Remember whether a selection has been made for pasting. Clicking into "nothing" is understood as selecting root ("")
        self.paste_selection = False

        self.watermark_label = ttk.Label(self,
                                         text="",
                                         font=("TkDefaultFont", 20, "bold"),
                                         justify="center",
                                         foreground="lightgray" if config.config["General"]["dark"] == "True" else "gray",
                                         background=self.root.tree_bg
                                         )    

        # Separator widget, that is supposed to indicate where a file is dropped inside a browser treeview
        self.drop_separator = ttk.Separator(self)                 

        if self.root._dark:
            self.tag_configure("move", foreground="#f2f2f2", background="#595959")
            self.tag_configure("cut", foreground="#cccccc", background="#3F3F3F")
        else:
            self.tag_configure("move", foreground="#595959", background="#f2f2f2")
            self.tag_configure("cut", foreground="#A8A8A8", background="#ebebeb")
        self.tag_configure("edited_last", background="#F6A854")
        self.tag_configure("Project_empty", image=self.root.folder_empty_image)
        self.tag_configure("Project_filled", image=self.root.folder_filled_image)
        self.tag_configure("Plot", image=self.root.plot_image)

        self.plottypes = set()
        self.plottypes.update(self.root.plottypes)
        self.plottypes.update({"MultiPlot", "Assay"})

        self.treeview_saves = {}

    def show_watermark(self):

        if not self.get_children():
            self.watermark_label.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.watermark_label.place_forget()

    def insert(self, parent, index, iid=None, **kwargs):
        iid = super().insert(parent, index, iid, **kwargs)

        if parent and not self.tag_has(tagname="Project_filled", item=parent):
            taglist = list(self.item(item=parent, option="tags"))
            if "Project_empty" in taglist:
                taglist.remove("Project_empty")
            taglist.append("Project_filled")
            self.item(item=parent, tags=taglist)

        self.show_watermark()
            
        return iid
    
    def move(self, item, parent, index):

        # Get the previous parent
        old_parent = self.parent(item)

        super().move(item, parent, index)
        
        for parent in [old_parent, parent]:
            taglist = list(self.item(item=parent, option="tags"))
            if self.get_children(parent) and (not "Project_filled" in taglist):
                if "Project_empty" in taglist:
                    taglist.remove("Project_empty")
                taglist.append("Project_filled")
                
            elif (not self.get_children(parent)) and (not "Project_empty" in taglist):
                if "Project_filled" in taglist:
                    taglist.remove("Project_filled")
                taglist.append("Project_empty")

            else: 
                continue

            self.item(item=parent, tags=taglist)

    def cut(self, *args):

        selection = self.selection()
        
        # First remove all items that have the cut tag
        for iid in self.tag_has("cut"):
            tags = list(self.item(item=iid, option="tags"))
            tags.remove("cut")
            self.item(item=iid, tags=tags)

        if len(selection) == 0:
            self.copy_iids = []
            self.cut_iids = []
            return
        
        self.cut_iids = list(selection)
        self.copy_iids = []

        for iid in selection:
            self.cut_iids.extend(self.get_all_children(iid))

        # Every item should only be in the list once, for this create a dict from keys and convert that to a list again. This ensures proper order
            self.cut_iids = list(dict.fromkeys(self.cut_iids))

        # Add all selected items and their children to cut
        for iid in self.cut_iids:
            
            tags = list(self.item(item=iid, option="tags"))
            tags.append("cut")
            self.item(item=iid, tags=tags)

        self.selection_set()
        self.paste_selection = False

    def copy(self, *args):

        selection = self.selection()
        
        # First remove all items that have the move tag
        for iid in self.tag_has("cut"):
            tags = list(self.item(item=iid, option="tags"))
            tags.remove("cut")
            self.item(item=iid, tags=tags)

        if len(selection) == 0:
            self.copy_iids = []
            self.cut_iids = []
            return
        
        self.cut_iids = []
        self.copy_iids = list(selection)

        for iid in selection:
            self.copy_iids.extend(self.get_all_children(iid))

        # Every item should only be in the list once, for this create a dict from keys and convert that to a list again. This ensures proper order
        self.copy_iids = list(dict.fromkeys(self.copy_iids))

        self.selection_set()
        self.paste_selection = False
    
    def paste(self, *args):

        # First remove all items that have the cut tag
        for iid in self.tag_has("cut"):
            tags = list(self.item(item=iid, option="tags"))
            tags.remove("cut")
            self.item(item=iid, tags=tags)

        if (not self.cut_iids) and (not self.copy_iids): return

        if not self.paste_selection:
            self.copy_iids = []
            self.cut_iids = []
            return

        # Check some things about where to move the things, similarly to the entry_on_release method
        # Get the current selection
        selection = self.selection()
        self.selection_set()
        moved_iid = None

        # If no selection has been made move to root
        if len(selection) == 0:
            moved_iid = ""
        
        elif len(selection) == 1:
            
            moved_iid = selection[0]
            # Check whether the moved_iid is a project folder, if not get its parent
            if not self.tag_has(tagname="Project", item=moved_iid):
                moved_iid = self.parent(moved_iid)
            else:
                self.item(item=moved_iid, open=True)
        # If the selection encompasses multiple items, check whether all items share the same parent
        elif len(selection) > 1:
            parent = self.parent(selection[0])
        
            if (not all(parent == self.parent(iid) for iid in selection)):
                self.cut_iids = []
                self.copy_iids = []
                return

            else:
                moved_iid = parent

        if moved_iid is None:
            self.cut_iids = []
            self.copy_iids = []
            return

        if self.cut_iids:
            # Return if the item it was moved to is part of the selection or already has the same parent
            if moved_iid in self.cut_iids or all(moved_iid == self.parent(iid) for iid in self.cut_iids):
                self.cut_iids = []
                self.copy_iids = []
                return
            
            # Otherwise move all items and update them
            for iid in self.cut_iids:

                # Don't move the children out of the parent if parent and its children were selected
                if self.parent(iid) in self.cut_iids: continue

                self.move(iid, moved_iid, tk.END)
                self.selection_add(iid)
                self.changed_item(iid, moved=True)

            changed_iids = self.cut_iids

        elif self.copy_iids:

            MultiPlot = self == self.root.multiplot_browser

            if MultiPlot:
                save_data = db.multiplot_save_data
            else:
                save_data = db.save_data

            copy_dict = {} # {New_iid: save_data}

            iid_map_dict = {} # {old_iid: new_iid}
            # Copy all iids one after the other
            for iid in self.copy_iids:

                # Get all important info for the browser from the widget
                new_text = self.item(item=iid, option="text")
                # If iid is already a child of moved_iid add copy to the name
                if iid in self.get_children(moved_iid):
                    new_text += " - Copy"
                new_values = self.item(item=iid, option="values")
                new_tags = list(self.item(item=iid, option="tags"))

                if "edited_last" in new_tags:
                    new_tags.remove("edited_last")

                # Get the initial parent of the file
                parent = self.parent(iid)

                # Check whether it is a folder
                if self.tag_has(tagname="Project", item=iid):
                    # Add a new entry and catch the iid
                    new_iid = self.insert(iid_map_dict[parent] if parent in self.copy_iids else moved_iid,
                                          tk.END,
                                          text = new_text,
                                          open = self.item(item=iid, option="open"),
                                          tags = ["Project","Project_empty"])
                    iid_map_dict[iid] = new_iid
                    self.add_item(new_iid)

                else:
                    if db.load(iid = iid, MultiPlot = MultiPlot):
                        # Add a new save to the database
                        new_iid = db.add_new_save()
                        # Map the old iid to the new iid
                        iid_map_dict[iid] = new_iid

                        # Check whether the parent was copied as well, otherwise moved_iid will be parent
                        self.insert(iid_map_dict[parent] if parent in self.copy_iids else moved_iid,
                                    tk.END, 
                                    iid = new_iid, 
                                    text = new_text,
                                    values = new_values,
                                    tags = new_tags)
                        
                        copy_dict[new_iid] = deepcopy(save_data[iid])
                        if MultiPlot:
                            copy_dict[new_iid]["PlotOptions"]["filename"] = new_text
                        else:
                            copy_dict[new_iid]["filename"] = new_text
                    else:
                        iid_map_dict[iid] = iid

            if not MultiPlot:
                self.root.add_imported_data(copy_dict)
            else:
                for key in copy_dict:
                    save_data.update({key:copy_dict[key]})

                    self.add_item(key)
                    self.see(key)
                    self.selection_add(key)

                    db.save(key, MultiPlot=True)
                
                key = next(iter(copy_dict))

                parent = self.parent(key)

                if parent != "":
                    self.changed_item(parent)
                
                self.save()

            changed_iids = [iid_map_dict[iid] for iid in self.copy_iids]

        # Only sort the item it was moved to, everything else is probably unnecessary
        self.sort_treeview(parent=moved_iid, recursive=False)

        iid_with_highest_index = None
        index = -1
        # Get the indices
        for iid in changed_iids:
            if self.index(iid) > index:
                index = self.index(iid)
                iid_with_highest_index = iid

        self.see(iid_with_highest_index)

        self.cut_iids = []
        self.copy_iids = []
        self.paste_selection = False

    def delete(self, *items):
        # Get all parents from the selected items
        parents = [self.parent(iid) for iid in items]

        super().delete(*items)

        # Check whether the parents still have contents, if not, then change their tag from Project_filled to Project_empty
        for parent in parents:
            if not self.get_children(parent):
                taglist = list(self.item(item=parent, option="tags"))
                if "Project_filled" in taglist:
                    taglist.remove("Project_filled")
                taglist.append("Project_empty")
                self.item(item=parent, tags=taglist)
        
        self.show_watermark()

    def popup(self, event):
        # Identify the region that was clicked
        region_clicked = self.identify_region(event.x, event.y)
        
        # Only cells are interesting
        if region_clicked not in ("nothing"):
            # Here logic needs to be expanded to create actual user-friendly behavior

            # First check whether a selection already has been made
            current_selection = self.selection()

            # Get the iid
            selected_iid = self.identify_row(event.y)

            # In case no selection has been made yet, select the item that was right-clicked
            if not current_selection:
                self.selection_set(selected_iid)

            # In case there already was a selection, check whether the right-clicked item is part of the selection, if not change the selection to the right-clicked item
            else:
                if selected_iid not in current_selection:
                    self.selection_set(selected_iid)

            self.open_popup("selection", event.x_root, event.y_root)

        else:
            self.open_popup("nothing", event.x_root, event.y_root)

    def load(self):

        if self.browser_type:    
            # browser_type is either multiplot, or plot
            widgets, text, values, parent, indices, tags = db.load_browser(self.browser_type)

            # Save current information in dictionary
            self.treeview_saves["widgets"] = widgets
            self.treeview_saves["text"] = text
            self.treeview_saves["values"] = values
            self.treeview_saves["parent"] = parent
            self.treeview_saves["indices"] = indices
            self.treeview_saves["tags"] = tags

            self.insert_all()

    def remove_popup_coords(self):
        self.popup_coords = None

    def on_click(self, event):

        self.paste_selection = True

        # Checking if Ctrl or shift key is pressed
        if event.state & 0x0004:
            # Skip custom logic if Ctrl is pressed
            return  

        if event.state & 0x0001:
            # Skip custom logic if Shift is pressed
            return

        x = event.x
        y = event.y
        
        # Save current selection
        current_selection = self.selection()

        #identify region clicked
        region_clicked = self.identify_region(x, y)
    
        if region_clicked in ("nothing","heading"):
            #remove all selections when clicking into nothing
            self.selection_remove(current_selection)

        if region_clicked in ("cell","tree"):

            # Identify clicked item
            column = self.identify_column(x)
            column_index = int(column[1:]) - 1

            # Check whether it is first or second column, else return
            if column_index >= 1:
                return

            # get iid of clicked item
            selected_iid = self.identify_row(y)

            # get the values of the currently clicked cell
            if region_clicked in ["cell", "tree"]:
                
                selected_values = self.item(selected_iid).get("text")

            else:
                selected_values = ""

            if selected_values == "":
                return

            self.root.create_moving_entry(self, selected_iid, "#0", current_selection, selected_values, x, y)
                           
    def on_double_click(self, event):
        """Placeholder double-click handler on base class.
        Subclasses override this to implement specific behavior. Having
        this stub keeps the bind in __init__ valid for static analysis
        and runtime.
        """
        return
    
    def _place_widget_edit(self, column="#0", x_offset=12):

        iid = self.widget_edit.entry.editing_item_iid

        # Get the bbox
        column_bbox = self.bbox(iid, column)
        # If there is no column_bbox or when the item is actually on the bottom of the treeview where no item is visible
        if column_bbox and not (self.winfo_y()+self.winfo_height()-(column_bbox[1]+column_bbox[3])<=column_bbox[3]*1.2):
            self.widget_edit.place(
                x=column_bbox[0] + x_offset,
                y=column_bbox[1],
                width=max(column_bbox[2] - x_offset, 1),
                height=column_bbox[3],
            )
        else:
            self.widget_edit.place_forget()

    def rename(self, *args): #*args because it can also be used as a hotkey

        selection = self.selection()
        if len(selection) > 1:
            try:
                if self.popup_coords:
                    x, y = self.popup_coords
                    selected_iid = self.identify_row(y-self.winfo_rooty())
                else:
                    selected_iid = self.identify_row(self.winfo_pointery()-self.winfo_rooty())
                if selected_iid not in selection:
                    selected_iid = self.selection()[0]
            except:
                selected_iid = self.selection()[0]
        elif len(selection) == 1:
            selected_iid = self.selection()[0]
        else:
            return

        text = self.item(selected_iid).get("text")
        project = self.tag_has(tagname="Project", item=selected_iid)
        
        if project:

            rename_type = "Project"

            if self.tag_has(tagname="Project_filled", item=selected_iid):
                image = self.root.folder_filled_image
            else:
                image = self.root.folder_empty_image

        else:

            rename_type = "Graph"
            image = self.root.plot_image

        # create entry over selected position
        widget_edit = ImageEntry(self, image=image)
        self.widget_edit = widget_edit
        widget_edit.entry.type = rename_type
            
        column_index = -1

        widget_edit.entry.bind("<Return>", self.on_backspace)
        widget_edit.entry.bind("<FocusOut>", self.on_backspace)
        widget_edit.bind_to_all("<MouseWheel>", lambda e: (self.yview_scroll(-1 if e.delta > 0 else 1, "units"),
                                                           self.on_mousewheel(e)))

        # Record the column index and item iid
        widget_edit.entry.editing_column_index = column_index
        widget_edit.entry.editing_item_iid = selected_iid

        widget_edit.insert(0, text)
        widget_edit.select_range(0, tk.END)

        widget_edit.focus()

        self._place_widget_edit()
        
        
    # Method to bind scrolling of the widget_edit to the mouse when the mouse entered the treeview
    def on_mousewheel(self, event):
        if self.widget_edit:
            self.after_idle(self._place_widget_edit)
        
    def on_focus_out(self, event):
        self.widget_edit.destroy()
        self.widget_edit = None
    
    def get_all_children(self, iid):
        # Get all children and sub-children for a specific iid
        result = []

        # Make sure, that the children of each child come first in the resulting list
        for child in self.get_children(iid):
            result.extend(self.get_all_children(child))
            result.append(child)

        return result

    def on_delete(self, *args):

        selection = list(self.selection())

        if len(selection)==0: return

        if not tk.messagebox.askokcancel(title="Are you sure?", message="Deleting the selected items is irreversible", icon=tk.messagebox.WARNING):
            return

        # Check whether any of the selected items has children and add them to the list, however children 
        children = []
        
        for iid in selection:
            children.extend(self.get_all_children(iid))
        
        selection = list(dict.fromkeys(children + selection))

        if DEBUG: print("Selected for Deleting: ",selection)
        
        for count, selected_item in enumerate(selection):

            if DEBUG:
                print("Count: ",count)
                print("Item: ",selected_item)

            # Delete item from treeview and update all dictionaries and save files
            db.delete_save(selected_item, MultiPlot = self == self.root.multiplot_browser)

            # Delete Item from TreeView
            self.remove_item(selected_item)
                
        self.save()

        # Check whether the database needs to be vacuumed
        db.check_vacuum()

    def add_item(self, iid:str):
        iid = str(iid)

        # If iid is already in widgets, don't add it again
        if iid in self.treeview_saves["widgets"]:
            print(f"{iid} is already saved. Skipping...")
            return

        # iid needs to be appended to self.treeview_saves["widgets"]
        self.treeview_saves["widgets"].append(iid)

        # Then get all the information such as text, values, parent, indices and tags
        text = self.item(iid, option="text")
        values = self.item(iid, option="values")
        index = self.index(iid)
        parent = self.parent(iid)
        tags = self.item(iid, option="tags")
        children = self.get_children(iid)

        # Add them to the nested lists in the dictionary
        self.treeview_saves["text"].append(text)
        self.treeview_saves["values"].append(values)
        self.treeview_saves["parent"].append(parent)
        self.treeview_saves["indices"].append(index)
        self.treeview_saves["tags"].append(tags)
        self.treeview_saves["children"].append(children)

        self.change_browser_saves(iid=iid, text=text, values=values, tags=tags, removed=False)

    def changed_item(self, iid:str, moved:bool = False):
        iid = str(iid)

        # When an item is changed, get the correct new values and change them in the save list
        # First get the index in the list
        item_index = self.treeview_saves["widgets"].index(iid)

        # Then get all the information such as text, values, parent, indices and tags
        text = self.item(iid, option="text")
        values = self.item(iid, option="values")
        index = self.index(iid)
        parent = self.parent(iid)
        tags = self.item(iid, option="tags")
        children = self.get_children(iid)

        # If the parent has changed, the item needs to be moved inside of the list according to its parent and index, so that there are no issues with the order in which things are inserted into the treeview
        # Also update if the list index of the parent is suddenly after the list index of the child
        if moved and (self.treeview_saves["parent"][item_index] != parent or self.treeview_saves["indices"][item_index] != index or (parent != "" and self.treeview_saves["widgets"].index(parent)>=item_index)):
            # Get the list index of the parent, if there is one
            if parent != "":
                parent_index = self.treeview_saves["widgets"].index(parent)

                # Add the child to the children list of the parent
                parent_children = list(self.treeview_saves["children"][parent_index])
                if iid not in parent_children:
                    parent_children.append(iid)
                    self.treeview_saves["children"][parent_index] = tuple(parent_children)
            else:
                # If it is placed on root, it needs to be moved accordingly
                parent_index = -1

            # Remove the child out of the children list of the old parent, if there was one
            if self.treeview_saves["parent"][item_index] != "":
                old_parent_index = self.treeview_saves["widgets"].index(self.treeview_saves["parent"][item_index])
                old_parent_children = list(self.treeview_saves["children"][old_parent_index])
                if iid in old_parent_children:
                    old_parent_children.remove(iid)
                    self.treeview_saves["children"][old_parent_index] = tuple(old_parent_children)

            new_item_index = parent_index + index + 1

            # Now insert all values at the new position
            self.treeview_saves["widgets"].insert(new_item_index, iid)
            self.treeview_saves["text"].insert(new_item_index, text)
            self.treeview_saves["values"].insert(new_item_index, values)
            self.treeview_saves["indices"].insert(new_item_index, index)
            self.treeview_saves["parent"].insert(new_item_index, parent)
            self.treeview_saves["tags"].insert(new_item_index, tags)
            self.treeview_saves["children"].insert(new_item_index, children)

            # If the new_item_index is smaller than or equal to the older one, it moves the older one further up by 1, adjust for that
            if new_item_index <= item_index:
                item_index += 1

            # Remove the values at the old item_index
            self.treeview_saves["widgets"].pop(item_index)
            self.treeview_saves["text"].pop(item_index)
            self.treeview_saves["values"].pop(item_index)
            self.treeview_saves["indices"].pop(item_index)
            self.treeview_saves["parent"].pop(item_index)
            self.treeview_saves["tags"].pop(item_index)
            self.treeview_saves["children"].pop(item_index)

            self.save()

            # If the moved item has children, they also have to be moved in the list
            for child in children:
                self.changed_item(child, moved=True)
            
        else:

            # Now change all list values
            self.treeview_saves["text"][item_index] = text
            self.treeview_saves["values"][item_index] = values
            self.treeview_saves["tags"][item_index] = tags
            self.treeview_saves["children"][item_index] = children

        self.change_browser_saves(iid=iid, text=text, values=values, tags=tags, removed=False)

    def remove_item(self, iid:str):
        iid = str(iid)

        # Whenever an item is removed, get its index inside of the saves
        item_index = self.treeview_saves["widgets"].index(iid)

        # Remove the values with that index out of all nested lists
        self.treeview_saves["widgets"].pop(item_index)
        self.treeview_saves["text"].pop(item_index)
        self.treeview_saves["values"].pop(item_index)
        # Also delete it out of children from the parent, for this get the parent id
        parent_iid = self.treeview_saves["parent"][item_index]
        self.treeview_saves["parent"].pop(item_index)
        self.treeview_saves["indices"].pop(item_index)
        self.treeview_saves["tags"].pop(item_index)
        self.treeview_saves["children"].pop(item_index)

        # Get the index of the parent, if the parent is not ""
        if parent_iid != "":
            parent_index = self.treeview_saves["widgets"].index(parent_iid)

            children = list(self.treeview_saves["children"][parent_index])
            children.remove(iid)
        
            # children is a tuple so it needs to be converted to a list and then back to a tuple
            self.treeview_saves["children"][parent_index] = tuple(children)

        self.change_browser_saves(iid=iid, text="", values="", tags="", removed=True)

        # Now delete the item
        self.delete(iid)

    def insert_all(self):

        widgets = self.treeview_saves["widgets"]
        text = self.treeview_saves["text"]
        values = self.treeview_saves["values"]
        parent = self.treeview_saves["parent"]
        indices = self.treeview_saves["indices"]
        tags = self.treeview_saves["tags"]

        children = []

        # Update the Browser Treeview to fit new format
        for count, widget in enumerate(widgets):

            if "Project" in tags[count]:
                # This does not work if the parent is missing, therefore check if it exists and else put it on root
                if self.exists(parent[count]):
                    self.insert(parent[count],indices[count], iid=widget, text=text[count], tags = tags[count])
                else:
                    parent[count] = ""
                    self.insert("",tk.END, iid=widget, text=text[count], tags = tags[count])

                plottype = ""

            else: 
                for tag in tags[count]:
                    if tag in self.plottypes: 
                        plottype = tag
                        if values[count] == "":
                            values[count] = plottype

                # Add the "Plot keyword if it does not exist"
                if not "Plot" in tags[count]:
                    tags[count].append("Plot")

                # This does not work if the parent is missing, therefore check if it exists and else put it on root
                if self.exists(parent[count]):
                    self.insert(parent[count],indices[count], iid=widget, text=text[count], values=values[count], tags = tags[count])
                else:
                    parent[count] = ""
                    self.insert("",tk.END, iid=widget, text=text[count], values=values[count], tags = tags[count])

            widget_save_dict = {"filename":text[count],
                                "plottype":plottype,
                                "folder": "Project" in tags[count]}

            if self.browser_type == "plot":
                db.browser_saves[widget] = widget_save_dict

            elif self.browser_type == "multiplot":
                db.multiplot_browser_saves[widget] = widget_save_dict

        # Now get all the children of each item
        for widget in widgets:
            widget_children = self.get_children(widget)
            if widget_children:
                if self.tag_has(tagname="Project", item=widget):
                    tag_list = list(self.item(item=widget, option="tags"))
                    if not "Project_filled" in tag_list:
                        tag_list.append("Project_filled")
                        self.item(item=widget, tags=tuple(tag_list))
            else:
                tag_list = list(self.item(item=widget, option="tags"))
                if ("Project" in tag_list) and (not "Project_empty" in tag_list):
                    tag_list.append("Project_filled")
                elif (not "Project" in tag_list) and (not "Plot" in tag_list):
                    tag_list.append("Plot")

                self.item(item=widget, tags=tuple(tag_list))

            children.append(widget_children)

        # Check whether any of the child widget has the tag move and then remove it
        has_tag_move = self.tag_has("move")
        
        for iid in has_tag_move:

            current_tags = list(self.item(iid, "tags"))

            # Remove move if in tags
            current_tags.remove("move")

            # Update the item
            self.item(iid, tags=tuple(current_tags))

        self.treeview_saves["text"] = text
        self.treeview_saves["tags"] = tags
        self.treeview_saves["children"] = children

        # Sort the treeview alphabetically
        self.sort_treeview()

    def change_browser_saves(self, iid, text, values, tags, removed:bool):

        if not removed:
            browser_saves = {}

            if len(values) >= 1:
                browser_saves[iid] = {"filename":text,
                                       "plottype":values[0],
                                       "folder": "Project" in tags}
            else:
                browser_saves[iid] = {"filename":text,
                                       "plottype":"",
                                       "folder": "Project" in tags}

            if self.browser_type == "plot":
                db.browser_saves |= browser_saves
            elif self.browser_type == "multiplot":
                db.multiplot_browser_saves |= browser_saves

        else:

            if self.browser_type == "plot":
                db.browser_saves.pop(iid)
            elif self.browser_type == "multiplot":
                db.multiplot_browser_saves.pop(iid)
                            
    def save(self):
        # Saving the saves dictionary as a list, with only the important information
        self.saves = (self.treeview_saves["widgets"],
                      self.treeview_saves["text"],
                      self.treeview_saves["values"],
                      self.treeview_saves["parent"],
                      self.treeview_saves["indices"],
                      self.treeview_saves["tags"])

        db.save_browser(self.browser_type, self.saves)

    def open_popup(self, region, x, y):

        # Define which popups belong to the current browser
        if self.browser_type == "plot":
            popup_1 = self.root.popup_1
            popup_2 = self.root.popup_2
        elif self.browser_type == "multiplot":
            popup_1 = self.root.popup_3
            popup_2 = self.root.popup_4

        if self.cut_iids or self.copy_iids:
            state = "normal"
        else:
            state = "disabled"

        for popup in [popup_1, popup_2]:
            popup.entryconfig("Paste", state=state)

        if region == "selection":

            # In case of of browser_type plot, check whether addition of blanks via right_click menu is possible
            # Check whether all entries have the same plottype, or whether an entry is a folder and then dynamically disable/enable Choose Blank
            if self.browser_type == "plot":
                selection = self.selection()
                if len(selection) != 0:
                    tags = self.item(selection[0], option="tags")
                    plottype = None
                    
                    for tag in tags:
                        if tag in self.plottypes: plottype = tag
    
                    if ((not plottype) or 
                        any(self.tag_has(tagname="Project", item=iid) for iid in selection) or 
                        not all(self.tag_has(tagname=plottype, item=iid) for iid in selection)):
    
                        popup_2.entryconfig("Choose Blank", state="disabled")
                    
                    else:
                        popup_2.entryconfig("Choose Blank", state="normal")
    
                else:
                    popup_2.entryconfig("Choose Blank", state="disabled") 

            try:
                self.popup_coords = (x,y)
                popup_2.tk_popup(x, y, 0)
            finally:
                self.after_idle(self.remove_popup_coords)
        else:
            self.selection_set()
            popup_1.tk_popup(x, y, 0)

    def on_double_click(self, event):

        region_clicked = self.identify_region(event.x, event.y)

        if region_clicked in ("nothing", "heading"):
            return

        selection = self.selection()
        # To Fix Bug where self.selection() is a tuple with no items, even though a selection clearly was made
        if len(selection) >= 1:
            iid = selection[0]
        else:
            iid = self.identify_row(event.y)

        if self.tag_has(tagname="Project", item=iid): return
        if iid == "": return

        if self.browser_type == "plot":
            db.load(iid)
            self.root.plot(iid)

        elif self.browser_type == "multiplot":

            db.load(iid, MultiPlot = True)
            self.root.init_multiplot(iid)

    def on_backspace(self, event):

        widget = event.widget
        new_text = widget.get()
        selected_iid = widget.editing_item_iid
        
        old_text = self.item(item=selected_iid, option="text")

        if new_text == "" or new_text == old_text:
            widget.destroy()
            self.widget_edit = None
            return

        self.item(selected_iid, text = new_text)

        self.widget_edit.destroy()
        self.widget_edit = None

        MultiPlot = self.browser_type == "multiplot"

        if widget.type == "Graph":

            db.load(selected_iid, MultiPlot = MultiPlot)

            if MultiPlot:
                db.multiplot_save_data[selected_iid]["PlotOptions"]["filename"] = new_text
            else:
                db.save_data[selected_iid].update({"filename":new_text})

            db.save(iid=selected_iid, MultiPlot = MultiPlot)

        self.item(selected_iid, text = new_text)
        widget.destroy()
        self.widget_edit = None

        self.changed_item(selected_iid)

        parent = self.parent(selected_iid)

        self.sort_treeview(parent=parent, recursive=False)
            
        self.save()

        # Update project label and plot label
        self.root.update_datakey_and_project()

        if self.browser_type == "plot":
            # Also check whether selected_iid is the currently loaded baseline_iid
            if selected_iid != self.root.iid and self.root.plottype not in ["MultiPlot", "Assay"] and db.load(self.root.iid) and db.save_data[self.root.iid]["baseline_iid"] == selected_iid:
                self.root.baseline_filename.set(db.browser_saves[selected_iid]["filename"])

    # Recursive function that calls itself
    def get_treeview_items(self, parent=""):

        # This list will hold all items ids
        items = []

        # Get the children of the current node (parent)
        children = self.get_children(parent)

        for child in children:
            # Add each child ID to the list
            items.append(child)

            # Recursively get all the children of this child
            items.extend(self.get_treeview_items(child))

        return items

    # Sort Items Alphabetically
    def sort_treeview(self, parent="", recursive=True):
        
        # Retrieve all children of the current parent node
        children = []

        # Get the correct list indexes of the all widgets that have the parent "parent"
        children_indexes = [i for i, val in enumerate(self.treeview_saves["parent"]) if str(val) == str(parent)]
        
        for child_index in children_indexes:
            # Get item text
            text = self.treeview_saves["text"][child_index]
            
            # Check whether it is a folder
            if "Project" in self.treeview_saves["tags"][child_index]:
                is_file = False
            else:
                is_file = True
            # Append item with flag indicating if text was originally empty
            children.append((text, is_file, child_index))
        
            # Sort by:
            # 1. Whether it is a folder or a file (is_file)
            # 2. Alphabetical order within each group.
            children.sort(key=lambda item: (item[1], natural_keygen(item[0])))

        # Move each child to the correct position within the parent
        for index, (text, is_file, child_index) in enumerate(children):
            
            child_iid = self.treeview_saves["widgets"][child_index]
            
            # Move child to the new position if child and parent exist
            if self.exists(child_iid) and self.exists(parent):
                self.move(child_iid, parent, index)
                # Save new index
                self.treeview_saves["indices"][child_index] = index

            if recursive:
                # Recursive call to sort the sub-children of each child
                self.sort_treeview(child_iid)

        if (not parent) or (not recursive):

            child_widgets = []

            for widget in self.treeview_saves["widgets"]:
                child_widgets.append(self.get_children(widget))

            self.treeview_saves["children"] = child_widgets
            self.save()

class BrowserTreeview(BrowserBase):
    def __init__(self, master, root, **kw):
        super().__init__(master, root, **kw)

        self.treeview_saves = {}
        self.browser_type = "plot"

        label = "Load experimental file to start\n".replace(" ", "\n") + "(File > Open Files)\n[Ctrl+O]"

        self.watermark_label.configure(text=label)

        self.watermark_label.bind("<Button-3>", self.popup)

        self.load()

        self.show_watermark()

class MultiPlotTreeview(BrowserBase):
    def __init__(self, master, root, **kw):
        super().__init__(master, root, **kw)

        self.treeview_saves = {}
        self.browser_type = "multiplot"

        label = "Create a new MultiPlot to start\n".replace(" ", "\n") + "(File > New MultiPlot)\n[Ctrl+Shift+N]"

        self.watermark_label.configure(text=label)

        self.watermark_label.bind("<Button-3>", self.popup)

        self.load()

        self.show_watermark()

# Editable Treeview
class TreeviewEdit(ttk.Treeview):
    def __init__(self, frame, master, treetype, **kw):
        super().__init__(frame, **kw)
        self.master = master
        self.bind("<Double-1>", self.on_double_click)
        self.bind("<Delete>", self.on_delete)
        self.bind("<MouseWheel>", self.on_mousewheel, add="+")
        self.treetype = treetype
        self.widget_edit = None

        if treetype in ["assay", "multiplot"]:
            self.watermark_label = ttk.Label(self,
                                             text="--- Drop experimental files here ---",
                                             font=("TkDefaultFont", 20, "bold"),
                                             foreground="lightgray" if config.config["General"]["dark"] == "True" else "gray",
                                             background=self.master.tree_bg)
            
            self.bind("<Button-1>", self.on_click)

            if self.master._dark:
                self.tag_configure("move", foreground="#f2f2f2", background="#595959")
            else:
                self.tag_configure("move", foreground="#595959", background="#f2f2f2")

        if treetype == "assay":
            self.popup = tk.Menu(self.master, tearoff=False)
                
            self.popup.add_command(label="New Datapoint",
                                   command = self.add_datapoint
                                )

            self.popup.add_command(label="Delete",
                                   accelerator="Del",
                                   command = self.on_delete
                                )
            self.bind("<Button-3>", self.open_popup)

        if treetype == "Tm":
            self.tag_configure("current", background="#F6A854")

        self.color_images = {} # Keep track of images that show color inside of the Treeview
    
        self.edit_entries = []
        self.drop_separator = ttk.Separator(self) 

    def show_watermark(self):

        if self.treetype in ["assay", "multiplot"]:
            if not self.get_children():
                self.watermark_label.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.watermark_label.place_forget()

    def open_popup(self, event):
        # Identify the region that was clicked
        region_clicked = self.identify_region(event.x, event.y)
        
        # Only cells are interesting
        if region_clicked not in ("nothing"):
            # Here logic needs to be expanded to create actual user-friendly behavior

            # First check whether a selection already has been made
            current_selection = self.selection()

            # Get the iid
            selected_iid = self.identify_row(event.y)

            # In case no selection has been made yet, select the item that was right-clicked
            if not current_selection:
                self.selection_set(selected_iid)

            # In case there already was a selection, check whether the right-clicked item is part of the selection, if not change the selection to the right-clicked item
            else:
                if selected_iid not in current_selection:
                    self.selection_set(selected_iid)

        else:
            self.selection_set()

        # Now check the selection again
        current_selection = self.selection()

        # Only enable "Delete", if there is a selection, otherwise disable it
        if current_selection:
            self.popup.entryconfig("Delete", state="normal")
        else:
            self.popup.entryconfig("Delete", state="disabled")

        self.popup.tk_popup(event.x_root, event.y_root, 0)

    def insert(self, *args, **kwargs):
        iid = super().insert(*args, **kwargs)

        if self.treetype in ["assay", "multiplot"]:
            self.show_watermark()
            
        return iid

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        if self.treetype in ["assay", "multiplot"]:
            self.show_watermark()

    def destroy(self):

        for entry in self.edit_entries:
            entry.destroy()

        self.edit_entries = []

        super().destroy()

    def _bind_edit_scroll(self, widget_edit):
        widget_edit.bind("<MouseWheel>", lambda e: (self.yview_scroll(-1 if e.delta > 0 else 1, "units"),
                                                    self.on_mousewheel(e)))
        self.widget_edit = widget_edit

    def on_mousewheel(self, event):
        if self.widget_edit:
            self.after_idle(self._place_edit_entries)

    def _place_edit_entries(self):
        for widget_edit in self.edit_entries:
            if not widget_edit.winfo_exists():
                continue

            column_index = widget_edit.editing_column_index
            column = f"#{column_index + 1}"
            column_box = self.bbox(widget_edit.editing_item_iid, column)

            if column_box:
                x_offset = 12 if column_index == -1 else 0
                widget_edit.place(x=column_box[0] + x_offset,
                                  y=column_box[1],
                                  w=max(column_box[2] - x_offset, 1),
                                  h=column_box[3])
            else:
                widget_edit.place_forget()

    def add_datapoint(self):

        new_datapoint_iid = "New"

        if self.exists(new_datapoint_iid):
            # If the new datapoint already exists, find a unique name by appending a number
            counter = 1
            while self.exists(f"{new_datapoint_iid}_{counter}"):
                counter += 1
            new_datapoint_iid = f"{new_datapoint_iid}_{counter}"

        # Add the new datapoint to assay_datapoints
        cp.multiplot_data["PlotOptions"]["assay_datapoints"][new_datapoint_iid] = {"plots": [], "x": 0.0}

        # Insert the new datapoint into the Treeview
        self.insert("",
                    0, 
                    iid=new_datapoint_iid, 
                    text=new_datapoint_iid, 
                    values=("",
                            f"{cp.multiplot_data['PlotOptions']['assay_datapoints'][new_datapoint_iid]['x']} {cp.multiplot_data['PlotOptions']['assay_x_unit']}", 
                            )
                )

        self.see(new_datapoint_iid)

        self.focus(new_datapoint_iid)

        # Since adding a new datapoint will not work with the autosort function, disable it
        self.master.autosort_files.set(False)
        self.master.update_autosort_files()

        self.after_idle(self.rename_datapoint, new_datapoint_iid)

    def on_click(self, event):
        # Checking if Ctrl or shift key is pressed
        if event.state & 0x0004:
            # Skip custom logic if Ctrl is pressed
            return  

        if event.state & 0x0001:
            # Skip custom logic if Shift is pressed
            return
        
        column = "#0"
        x, y = event.x, event.y
        # Identify the region that was clicked
        region_clicked = self.identify_region(x, y)

        # Only cells and tree are interesting
        if region_clicked not in ("tree","cell"):
            return

        selected_iid = self.identify_row(y)
        if self.treetype == "multiplot":
            current_selection = (selected_iid,)

        elif self.treetype == "assay":
            current_selection = self.selection()
            current_selection = [iid for iid in current_selection if self.item(iid).get("text") == ""]

        # get the values of the currently clicked cell
        if region_clicked in ["cell", "tree"]:

            if self.treetype == "multiplot":
                selected_values = self.item(selected_iid).get("text")
            elif self.treetype == "assay":
                selected_values = self.item(selected_iid).get("values")[0]
                column = "#1"
            else:
                selected_values = ""

        else:
            selected_values = ""

        if selected_values == "":
            return

        self.master.create_moving_entry(self, selected_iid, column, current_selection, selected_values, x, y)

    def on_double_click(self, event):

        # Identify the region that was clicked
        region_clicked = self.identify_region(event.x, event.y)
            
        # Only cells and tree are interesting
        if region_clicked not in ("tree","cell"):
            return

        # Identify clicked item
        column = self.identify_column(event.x)

        column_index = int(column[1:]) - 1

        selected_iid = self.focus()

        if selected_iid == "":
            return
        
        # Remove all current edit entries
        for entry in self.edit_entries:
            entry.destroy()

        self.edit_entries = []
        
        if self.treetype == "peaks":
                 
            # create entry over selected position
            if column_index in [1,2,4,6,7]:
                if column_index in [6,7]:
                    if self.item(selected_iid).get("values")[4] == "No":
                        return

                selected_values = self.item(selected_iid).get("values")[column_index]
                column_box = self.bbox(selected_iid, column)

                widget_edit = ttk.Entry(self)
                widget_edit.bind("<Return>", self.on_select)
                widget_edit.bind("<FocusOut>", self.on_select)
                self._bind_edit_scroll(widget_edit)

                # Record the column index and item iid
                widget_edit.editing_column_index = column_index
                widget_edit.editing_item_iid = selected_iid

                widget_edit.insert(0, selected_values)
                widget_edit.select_range(0, tk.END)

                widget_edit.focus()

                widget_edit.place(x=column_box[0],
                                    y=column_box[1],
                                    w=column_box[2],
                                    h=column_box[3])
                
                self.edit_entries.append(widget_edit)

            if column_index == 5:

                current_values = self.item(selected_iid).get("values")
                selected_value = current_values[column_index]

                if selected_value == "Yes":
                    current_values[column_index] = "No"

                elif selected_value == "No":
                    current_values[column_index] = "Yes"
                    if current_values[6] == "0.0":
                        current_values[6] = "100"
                    if current_values[7] == "0.0":
                        current_values[7] = "0.1"
                    
                else:
                    print("\"Simulate?\" has assumed an illegal value, returning to default")
                    current_values[column_index] = "No"

                if current_values[2] == "":
                    print("\nSimulation not possible!\nPlease enter a chemical formula first.\n")
                    return

                self.item(selected_iid, values=current_values)

                # pass the simulate value to master
                
                if current_values[0].startswith("i:"):
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][6]=current_values[column_index]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][7]=current_values[6]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][8]=current_values[7]
                    
                else:
                    cp.plot_data["peak_dict"][float(current_values[0])][6]=current_values[column_index]
                    cp.plot_data["peak_dict"][float(current_values[0])][7]=current_values[6]
                    cp.plot_data["peak_dict"][float(current_values[0])][8]=current_values[7]

                # Refresh the graph
                self.master.refresh(cp.ax, refreshTree=False)
                            
                # Reselect clicked row
                self.selection_set(self.identify_row(event.y))
                
        elif self.treetype == "integrals":
            
            if column_index != 5:
                return

            selected_values = self.item(selected_iid).get("values")[column_index]
            current_values = self.item(selected_iid).get("values")

            if selected_values == "Yes":
                current_values[column_index] = "No"

            elif selected_values == "No":
                current_values[column_index] = "Yes"
                
            else:
                print("\"Include?\" has assumed an illegal value, returning to default")
                current_values[column_index] = "Yes"

            self.item(selected_iid, values=current_values)


            if DEBUG: print("Selected Item: ", self.identify_row(event.y))
            # pass the include value to master
            cp.plot_data["integral_dict"][str(self.item(selected_iid).get("text"))][4] = current_values[column_index]
        
            # Now recalculate the percentage for every item
            self.master.refresh_integration_percentages()

            # Reselect clicked row
            self.selection_set(self.identify_row(event.y))

        elif self.treetype == "multiplot":

            if column_index in range(0,5):
                
                column_box = self.bbox(selected_iid, column)

                widget_edit = ttk.Entry(self)
                widget_edit.bind("<Return>", self.on_select)
                widget_edit.bind("<FocusOut>", self.on_select)
                self._bind_edit_scroll(widget_edit)

                # Record the column index and item iid
                widget_edit.editing_column_index = column_index
                widget_edit.editing_item_iid = selected_iid

                selected_values = self.item(selected_iid).get("values")[column_index]
                widget_edit.insert(0, selected_values)
                widget_edit.select_range(0, tk.END)

                widget_edit.focus()

                widget_edit.place(x=column_box[0],
                                    y=column_box[1],
                                    w=column_box[2],
                                    h=column_box[3])
                
                self.edit_entries.append(widget_edit)


            if region_clicked == "tree":

                old_color = return_regular_rgb_tuple(cp.multiplot_data[selected_iid]["color"])

                if old_color and len(old_color) == 4:
                    old_color = old_color[0:3]

                color = askcolor(color=old_color, title="Color Picker")[0]

                if color is not None:
                    # Update the data of that item with the new color
                    cp.multiplot_data[selected_iid]["color"] = normalize_rgb_tuple(color)
                    cp.multiplot_data["PlotOptions"]["colormap"] = None
                    self.master.multiplot_colormap.set(None)

                    self.master.update_multiplot_color(selected_iid)
                    self.master.refreshTree()

        elif self.treetype == "Tm":

            has_tag = self.tag_has("current")

            # Remove previous current tags
            for iid in has_tag:
                self.item(iid, tags=[])

            # Modify the selected value to have the current tag
            self.item(selected_iid, tags=["current"])

            selected_values = self.item(selected_iid).get("values")[0]

            if selected_values == "Sigmoidal + Constant Baseline": tm_method = "SCB"
            elif selected_values == "Sigmoidal + Linear Baseline": tm_method = "SLB"
            elif selected_values == "Sigmoidal + Quadratic Baseline": tm_method = "SQB"
            elif selected_values == "Van't Hoff Derivative": tm_method = "VHD"
            elif selected_values == "Empirical Gauss Derivative": tm_method = "EGD"
                
            #Check whether the new Tm method type has changed from the former
            old_tm_type = "derivative" if cp.plot_data["Tm_method"] in ["VHD", "EGD"] else "normal"
            new_tm_type = "derivative" if tm_method in ["VHD", "EGD"] else "normal"
            
            # If the type changes, the y axis scaling needs to change accordingly
            if old_tm_type != new_tm_type:
                # It doesn't matter what the old and what the new type is
                # The calculation should be the same

                normal_ypoints = self.master.correct_baseline(self.master.iid)

                derivative_ypoints = np.gradient(normal_ypoints,
                                                 cp.plot_data["xpoints"])
                
                # Get the y-limits
                ylim_min_old, ylim_max_old = cp.ax.get_ylim()
                # Get the maximum and minimum in data points
                if old_tm_type == "normal":
                    ymin_old = normal_ypoints.min()
                    ymax_old = normal_ypoints.max()
                    ymin_new = derivative_ypoints.min()
                    ymax_new = derivative_ypoints.max()
                else:
                    ymin_old = derivative_ypoints.min()
                    ymax_old = derivative_ypoints.max()
                    ymin_new = normal_ypoints.min()
                    ymax_new = normal_ypoints.max()
                
                # Calculate the ratio between extremum and limit as a fraction of ymax-ymin
                old_lower_ratio = (ylim_min_old - ymin_old) / (ymax_old - ymin_old)
                old_upper_ratio = (ylim_max_old - ymax_old) / (ymax_old - ymin_old)
                
                # Use it to calculate the proper distance between extremum and y limit
                ylim_min_new = old_lower_ratio * (ymax_new - ymin_new) + ymin_new
                ylim_max_new = old_upper_ratio * (ymax_new - ymin_new) + ymax_new

                self.master.ylim_min.set(ylim_min_new)
                self.master.ylim_max.set(ylim_max_new)
                
            cp.plot_data["Tm_method"] = tm_method

            self.master.update_ylim(change_adjust_y=False, skip_blit=True)
            self.master.update_fit(skip_blit=True)
            self.master.update_CD_points(autoadjust_y=False)

        elif self.treetype == "assay":
            # When clicking column 0, and when clicking a file and not a datapoint, this is supposed to show how the data was fit in a new window
            if column_index == 0:
                # Get the values of the selected item and check whether it has a parent (if not it is a datapoint and should not be clickable like this)
                if self.parent(selected_iid) != "":
                    value = self.item(selected_iid, option="values")[column_index]
                    if value != "":
                        self.master.show_assay_file_fit(selected_iid)

            # For column indices -1 and 1, create an entry over selected position
            if column_index in [-1,1]:
                # Either changes on these columns are for datapoints so check whether a datapoint is actually selected
                if selected_iid not in cp.multiplot_data["PlotOptions"]["assay_datapoints"]:
                    return
                # Since double click changes the "open" state of an item, get the current state and reset that state after idle
                # This is only relevant when clicking on column_index 1 basically
                currently_open = self.item(selected_iid).get("open")
                self.after_idle(lambda: self.item(selected_iid, open=currently_open))

                if column_index == 1:
                    selected_values = cp.multiplot_data["PlotOptions"]["assay_datapoints"][selected_iid]["x"]
                elif column_index == -1:
                    selected_values = self.item(selected_iid).get("text")
                     
                column_box = self.bbox(selected_iid, column)

                widget_edit = ttk.Entry(self)
                widget_edit.bind("<Return>", self.on_select)
                widget_edit.bind("<FocusOut>", self.on_select)
                self._bind_edit_scroll(widget_edit)

                # Record the column index and item iid
                widget_edit.editing_column_index = column_index
                widget_edit.editing_item_iid = selected_iid

                widget_edit.insert(0, selected_values)
                widget_edit.select_range(0, tk.END)

                widget_edit.focus()

                if column_index == -1:
                    # Use the offset of 12 pixels to account for the indentation of the text in the first column
                    widget_edit.place(x=column_box[0] + 12,
                                      y=column_box[1],
                                      w=max(column_box[2] - 12, 1),
                                      h=column_box[3])

                else:

                    widget_edit.place(x=column_box[0],
                                      y=column_box[1],
                                      w=column_box[2],
                                      h=column_box[3])
                
                self.edit_entries.append(widget_edit)

    def rename_datapoint(self, iid):
        if self.treetype == "assay":
            column = "#0"
            column_index = -1
            # Make sure that a datapoint is actually selected
            if iid not in cp.multiplot_data["PlotOptions"]["assay_datapoints"]:
                return

            selected_values = self.item(iid).get("text")
                    
            column_box = self.bbox(iid, column)

            widget_edit = ttk.Entry(self)
            widget_edit.bind("<Return>", self.on_select)
            widget_edit.bind("<FocusOut>", self.on_select)
            self._bind_edit_scroll(widget_edit)

            # Record the column index and item iid
            widget_edit.editing_column_index = column_index
            widget_edit.editing_item_iid = iid

            widget_edit.insert(0, selected_values)
            widget_edit.select_range(0, tk.END)

            widget_edit.focus()

            # Use the offset of 12 pixels to account for the indentation of the text in the first column
            widget_edit.place(x=column_box[0] + 12,
                                y=column_box[1],
                                w=max(column_box[2] - 12, 1),
                                h=column_box[3])

            
            self.edit_entries.append(widget_edit)
            
    def on_select(self, event):

        new_text = event.widget.get()
        event.widget.destroy()
        self.widget_edit = None

        column_index = event.widget.editing_column_index
        selected_iid = event.widget.editing_item_iid

        if self.treetype == "peaks":
            
            # In case of columns 4,6 and 7, test whether the correct input has been made
            if column_index == 4:
                try:
                    int(new_text)
                except:
                    print("Bad input. Charge must be an integer.")
                    return
            
            if column_index in [6,7]:
                try:
                    float(new_text)
                except:
                    print("Bad input. Intensity and FWHM must be floats.")
                    return

            current_values = self.item(selected_iid).get("values")

            if column_index == 2:
                if new_text == "":
                    current_values[3] = 0.0
                    current_values[5] = "No"
                    current_values[6] = "0.0"
                    current_values[7] = "0.0"
                else:
                    formula_string = self.master.check_if_peptide(new_text)
                    try:
                        f = Formula(formula_string)
                        current_values[3] = f.monoisotopic_mass
                        # If the Formula column was previously empty set "Simulate?" to Yes
                        if current_values[2] == "":
                            current_values[5] = "Yes"
                            current_values[6] = "100"
                            current_values[7] = "0.1"

                    except:
                        return
                    
            current_values[column_index] = new_text
                        
            self.item(selected_iid, values=current_values)
            
            # pass current row values back to master, only update first and forth value of list
            # as well as all things for simulation of mass spectra
            if len(current_values) > 2:
                if current_values[0].startswith("i:"):
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][0]=current_values[1]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][4]=current_values[2]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][5]=current_values[4]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][6]=current_values[5]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][7]=current_values[6]
                    cp.plot_data["inset_peak_dict"][float(current_values[0][2:])][8]=current_values[7]
                else:
                    cp.plot_data["peak_dict"][float(current_values[0])][0]=current_values[1]
                    cp.plot_data["peak_dict"][float(current_values[0])][4]=current_values[2]
                    cp.plot_data["peak_dict"][float(current_values[0])][5]=current_values[4]
                    cp.plot_data["peak_dict"][float(current_values[0])][6]=current_values[5]
                    cp.plot_data["peak_dict"][float(current_values[0])][7]=current_values[6]
                    cp.plot_data["peak_dict"][float(current_values[0])][8]=current_values[7]
            else:
                cp.plot_data["peak_dict"][float(current_values[0])][0]=current_values[1]
                                
            #refresh annotations in master
            if column_index == 1:
                self.master.refresh_annotations()

            elif column_index in [2,4,6,7]:
                self.master.update_simulation()

        elif self.treetype == "multiplot":

            current_values = self.item(selected_iid).get("values")
            current_values[column_index] = new_text

            if column_index == 0:

                # Return if no text was entered
                if new_text == "": return

                # Update the data of that item with the new name
                cp.multiplot_data[selected_iid]["filename"] = new_text
                self.master.update_multiplot_label(selected_iid)
                

            elif column_index == 1:

                # Check whether the value is a float, otherwise return
                try:
                    new_text = float(new_text)
                except:
                    print("Entered value is incompatible. Please enter a float value")
                    return

                # Update the data of that item with the new linewidth
                cp.multiplot_data[selected_iid]["linewidth"] = new_text
                self.master.update_multiplot_linewidth(selected_iid)

            elif column_index == 2:

                # Check whether the linestyle is supported
                if new_text not in ["-", "--", "-.", ":", "none", "solid", "dashed", "dashdot", "dotted"]:
                    # If the new_text is not a shorthand value, check whether it is the tuple representation of a dash sequence
                    try:

                        tup = ast.literal_eval(new_text)
                        # Check whether tup is actually a tuple and written the way which is necessary for matplotlib
                        if isinstance(tup, tuple) and len(tup) == 2 and isinstance(tup[1], tuple) and int(len(tup[1])/2) == len(tup[1])/2:
                            new_text = tup
                        else:
                            print("Entered value is incompatible. Please enter a valid linestyle.")
                            return
                    except:
                        print("Entered value is incompatible. Please enter a valid linestyle.")
                        return

                # Update the data of that item with the new linewidth
                cp.multiplot_data[selected_iid]["linestyle"] = new_text
                self.master.update_multiplot_linestyle(selected_iid)

            elif column_index == 3:
                # Check whether the value is a float, otherwise return
                try:
                    new_text = float(new_text)
                    # Check whether the value is between 0 and 1, otherwise return
                    if new_text < 0 or new_text > 1:
                        print("Entered value is incompatible. Please enter a float value between 0 and 1")
                        return
                except:
                    print("Entered value is incompatible. Please enter a float value")
                    return

                # Update the data of that item with the new linewidth
                cp.multiplot_data[selected_iid]["alpha"] = new_text
                self.master.update_multiplot_alpha(selected_iid)

            elif column_index == 4:

                # Check whether the value is an integer, otherwise return
                try:
                    new_text = int(new_text)
                except:
                    print("Entered value is incompatible. Please enter an integer")
                    return

                # Update the data of that item with the new linewidth
                cp.multiplot_data[selected_iid]["position"] = new_text
                self.master.autoadjust_y(skip_blit=True)
                self.master.update_multiplot_position(selected_iid, skip_blit=True)
                self.master.apply_colormap()
                
                return
            
            else:
                return

            self.item(selected_iid, values=current_values)

        elif self.treetype == "assay":

            if column_index == -1:

                old_item = self.item(selected_iid)

                if new_text == old_item["text"]:
                    return

                # Before doing anything, check whether an item with this name already exists
                if self.exists(new_text):
                    print("A datapoint with this name already exists. Please choose a different name.")
                    return

                if new_text == "":
                    print("Please enter a valid name for the datapoint.")
                    return

                # Update the selected item, since in case of the datapoint names which are edited herein, the entire item is changing
                old_index = self.index(selected_iid)
                old_children = self.get_children(selected_iid)

                self.insert("",
                            index=old_index,
                            iid=new_text,
                            text=new_text,
                            values=old_item["values"],
                            tags=old_item["tags"],
                            open=old_item["open"])

                for child in old_children:
                    self.move(child, new_text, "end")
        
                self.delete(selected_iid)

                # Update the data to reflect the new name
                cp.multiplot_data["PlotOptions"]["assay_datapoints"][new_text] = cp.multiplot_data["PlotOptions"]["assay_datapoints"].pop(selected_iid)

                # Also loop through all children of that datapoint and update their parent value in the data
                if "plots" in cp.multiplot_data["PlotOptions"]["assay_datapoints"][new_text]:
                    for plot_iid in cp.multiplot_data["PlotOptions"]["assay_datapoints"][new_text]["plots"]:
                        if plot_iid in cp.multiplot_data:
                            cp.multiplot_data[plot_iid]["parent"] = new_text

                # If a change has actually been made, this is a deviation from the automatic sorting, thus disable it
                self.master.autosort_files.set(False)
                self.master.update_autosort_files()

            elif column_index == 1:

                old_item = self.item(selected_iid)

                new_text = new_text.strip()

                try:
                    new_text = float(new_text)
                except:
                    print("Entered value is incompatible. Please enter a float value")
                    return

                # Update the data to reflect the new value
                cp.multiplot_data["PlotOptions"]["assay_datapoints"][selected_iid]["x"] = new_text

                # Create a string that shows the value with the correct units
                new_text = f"{new_text} {cp.multiplot_data['PlotOptions']['assay_x_unit']}"

                if new_text == old_item["text"]:
                    return

                current_values = self.item(selected_iid).get("values")
                current_values[column_index] = new_text

                # Update the item with the new value
                self.item(selected_iid, values=current_values)

                # Sort the treeview again
                self.sort_treeview()

                # This actually changes something in the plot, therefore the plot needs to be updated including the fit
                self.master.update_assay_plot(skip_save=True, skip_blit=True)
                self.master.perform_assay_fit()

                # If a change has actually been made, this is a deviation from the automatic sorting, thus disable it
                self.master.autosort_files.set(False)
                self.master.update_autosort_files()

    def on_focus_out(self, event):
        event.widget.destroy()

    def on_delete(self, *args):
        if self.treetype == "peaks":
            for selected_item in self.selection():
                # Delete Item from Peak Dictionary
                if self.item(selected_item).get("values")[0].startswith("i:"):
                    cp.plot_data["inset_peak_dict"].pop(float(self.item(selected_item).get("values")[0][2:]))
                else:
                    cp.plot_data["peak_dict"].pop(float(self.item(selected_item).get("values")[0]))
                    
                # Delete Item from TreeView
                self.delete(selected_item)
            # Refresh Annotations in master
            self.master.refresh_annotations()

        elif self.treetype == "integrals":
            for selected_item in self.selection():
                # Delete Item from Int Dictionary
                cp.plot_data["integral_dict"].pop(str(self.item(selected_item).get("text")))

                # Delete Item from TreeView
                self.delete(selected_item)
                
            # Refresh graph
            cp.refresh_integration()

            # Refresh Percentages
            self.master.refresh_integration_percentages()

        elif self.treetype == "multiplot":
            for selected_item in self.selection():
                # Delete item from Multiplot data
                cp.multiplot_data.pop(selected_item)

                # Delete item from TreeView
                self.delete(selected_item)

            # Sort the treeview again
            iids = list(cp.multiplot_data.keys())
            iids.remove("PlotOptions")
            positions = [cp.multiplot_data[iid]["position"] for iid in iids]
            # Sort the items
            iids_sorted = [iid for _, iid in sorted(zip(positions, iids))]

            
            for count, iid in enumerate(iids_sorted):
                cp.multiplot_data[iid]["position"] = count

            self.master.autoadjust_y(skip_blit=True)

            self.master.update_multiplot_positions()

            self.master.apply_colormap()

        elif self.treetype == "assay":

            selection = self.selection()

            if len(selection) == 0:
                return

            # Set autosort files to False and update the value accordingly when a change is being made to the assay data
            self.master.autosort_files.set(False)
            self.master.update_autosort_files()

            # Because of all the changes caused by this, the tree is always refreshed completely. 
            # To make the user feel this less, open all the datapoints that were open before this.
            open_root_items = self.get_open_root_items()

            plot_data = cp.multiplot_data
            for selected_item in selection:

                # First check whether the selected item is a datapoint or a file
                datapoint = (self.parent(selected_item) == "" and 
                             self.item(item=selected_item, option="values")[0] == "" and
                             self.item(item=selected_item, option="text") != "")

                if datapoint:
                    # First get the iids of the plots associated with this datapoint
                    plots = plot_data["PlotOptions"]["assay_datapoints"][selected_item]["plots"]
                    # Delete the datapoint from the assay data
                    plot_data["PlotOptions"]["assay_datapoints"].pop(selected_item)

                    # For all plot_iids in plots, check whether they still exist and if so, remove selected_item as their "parent"
                    for plot_iid in plots:
                        if plot_iid in plot_data:
                            if plot_data[plot_iid]["parent"] == selected_item or not "parent" in plot_data[plot_iid]:
                                plot_data[plot_iid]["parent"] = None

                else:
                    # Delete the plot from the assay data and out of its parent
                    if "parent" in plot_data[selected_item]:
                        parent_iid = plot_data[selected_item]["parent"]
                    else:
                        parent_iid = None

                    # Delete the plot from the assay data
                    plot_data.pop(selected_item)

                    # If there is a parent_iid, remove it from the datapoint
                    if parent_iid is not None and parent_iid in plot_data["PlotOptions"]["assay_datapoints"]:
                        if selected_item in plot_data["PlotOptions"]["assay_datapoints"][parent_iid]["plots"]:
                            plot_data["PlotOptions"]["assay_datapoints"][parent_iid]["plots"].remove(selected_item)

            # Now there need to be some larger updates to the assay data, because the deletion of a datapoint or a plot can have consequences for the rest of the assay data
            
            # Update only the datapoints now not everything all the time
            if plot_data["PlotOptions"]["assay_type"] is not None:
                for datapoint in plot_data["PlotOptions"]["assay_datapoints"]:
                    self.master.update_assay_y_for_datapoint(datapoint, skip_save=True)

                self.master.update_assay_plot(skip_save=True, skip_blit=True)
                self.master.perform_assay_fit()
    
            self.master.refreshTree()

            # Loop through open root items and open those items if they exist on the refreshed Tree
            refreshed_root_items = self.get_children("")
            for item in open_root_items:
                if item in refreshed_root_items:
                    self.item(item, open=True)

    def get_open_root_items(self):
        open_root_items = []

        for item in self.get_children(""):
            if self.item(item, "open"):
                open_root_items.append(item)

        return open_root_items

        # Sort Items Alphabetically
    def sort_treeview(self):
        
        # Retrieve all children of the current parent node
        children = []
        
        for child in self.get_children(""):
            # Get item text and first value column if text is empty
            
            values = self.item(child, "values")

            if self.treetype == "assay" and len(values) > 1 and child in cp.multiplot_data["PlotOptions"]["assay_datapoints"]:
                text = values[1]
            else:
                text = values[0]
            
            # Append item with flag indicating if text was originally empty
            children.append((text, child))
    
        # Sort by:
        # 1. Items with non-empty `text` come first (`is_text_empty` is False).
        # 2. Alphabetical order within each group.
        children.sort(key=lambda item: natural_keygen(item[0]))
            
        # Move each child to the correct position within the parent
        for index, (text, child_id) in enumerate(children):
            self.move(child_id, "", index)  # Moves child to the new position

# Root window
class Root(ttk.Window):
    def __init__(self, theme):
        icon = self._get_data_path(image="PeptiXPlot_icon.png")
        super().__init__(themename=theme, iconphoto=icon)

        if theme == "darkly":
            self._dark = True
        else:
            self._dark = False

        self._colorblind = config.config["General"]["colorblind"] == "True"

        self.title("PeptiXPlot v0.8.3")

        screenwidth = self.winfo_screenwidth()
        screenheight = self.winfo_screenheight()

        self.geometry(f"{ceil(0.8*screenwidth)}x{ceil(0.8*screenheight)}+{ceil(0.1*screenwidth)}+{ceil(0.05*screenheight)}")

        # Flag to prohibit plot and multiplot to be called before the previous iteration has finished
        self._loading = False
        self._startup_complete = False
        self._startup_iid = None
        self._startup_multiplot_iid = None

        self.plottypes = {"CD", "Fluorescence", "HPLC", "Kinetics", "MALDI", "Tm", "UV/vis"}
        self.assaytypes = {'Michaelis-Menten',}

        # Keep track of the last opened folder for importing
        self.last_import_folder = dict.fromkeys(self.plottypes)
        
        # Create images for folders and plots in root
        
        self.folder_empty_image = tk.PhotoImage(file=self._get_data_path(image="folder_empty.png"))
        self.folder_filled_image = tk.PhotoImage(file=self._get_data_path(image="folder_with_plots.png"))
        self.plot_image = tk.PhotoImage(file=self._get_data_path(image="plots.png"))

        self.plottype = None
        self.last_plottype = None

        # Change the style of the treeview to increase the row height, this is necessary because otherwise on some devices the icons look very squeezed
        style = ttk.Style()
        self.scaling = float(self.tk.call("tk","scaling"))
        self.scrollbar_width = ceil(8.4 * self.scaling) 

        new_rowheight = ceil(18.75*self.scaling)

        self.control_widths = {
            "entry": 12,
            "long_entry": 20,
            "spinbox": 10,
            "combobox": 18,
            "long_combobox": 30,
        }

        self.widget_pady = ceil(2 * self.scaling)
        
        style.configure("Treeview", rowheight=new_rowheight)
        style.configure("Treeview.Heading", padding=(8, 4))
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("TButton", padding=(10, 5))
        style.configure("TCheckbutton", padding=(4, 4))
        style.configure("TRadiobutton", padding=(4, 4))
        style.configure("TEntry", padding=(6, 4), width=self.control_widths["entry"])
        style.configure("TCombobox", padding=(6, 4), width=self.control_widths["combobox"])
        style.configure("TSpinbox", padding=(6, 4), width=self.control_widths["spinbox"])
        style.configure("TLabel", padding=(5, 4))

        self.option_add("*TEntry.width", self.control_widths["entry"])
        self.option_add("*TSpinbox.width", self.control_widths["spinbox"])
        self.option_add("*TCombobox.width", self.control_widths["combobox"])

        def style_value(style_name, option, fallback):
            return style.lookup(style_name, option) or fallback

        frame_background = style_value("TFrame", "background", style.colors.bg)
        label_foreground = style_value("TLabel", "foreground", style.colors.fg)
        entry_background = style_value("TEntry", "fieldbackground", frame_background)
        entry_foreground = style_value("TEntry", "foreground", label_foreground)
        insert_color = style_value("TEntry", "insertcolor", entry_foreground)
        select_background = style_value("TEntry", "selectbackground", style.colors.primary)
        select_foreground = style_value("TEntry", "selectforeground", style.colors.selectfg)
        button_background = style_value("secondary.TButton", "background", style.colors.secondary)
        button_foreground = style_value("secondary.TButton", "foreground", style.colors.fg)
        active_background = style_value("secondary.TButton", "background", style.colors.secondary)
        active_foreground = style_value("secondary.TButton", "foreground", button_foreground)

        self.background_color = frame_background

        common = {
            "highlightBackground": frame_background,
            "highlightColor": frame_background,
        }
        widget_options = {
            "Button": {
                "background": button_background,
                "foreground": button_foreground,
                "activeBackground": active_background,
                "activeForeground": active_foreground,
                **common,
            },
            "Checkbutton": {
                "background": style_value("TCheckbutton", "background", frame_background),
                "foreground": style_value("TCheckbutton", "foreground", label_foreground),
                "activeBackground": frame_background,
                "activeForeground": label_foreground,
                "selectColor": select_background,
                **common,
            },
            "Entry": {
                "background": entry_background,
                "foreground": entry_foreground,
                "insertBackground": insert_color,
                "selectBackground": select_background,
                "selectForeground": select_foreground,
                **common,
            },
            "Spinbox": {
                "background": entry_background,
                "foreground": entry_foreground,
                "insertBackground": insert_color,
                "selectBackground": select_background,
                "selectForeground": select_foreground,
                **common,
            },
            "Label": {"background": frame_background, "foreground": label_foreground, **common},
            "Frame": {"background": frame_background, **common},
            "LabelFrame": {"background": frame_background, "foreground": label_foreground, **common},
            "Text": {
                "background": entry_background,
                "foreground": entry_foreground,
                "insertBackground": insert_color,
                "selectBackground": select_background,
                "selectForeground": select_foreground,
                **common,
            },
            "Listbox": {
                "background": entry_background,
                "foreground": entry_foreground,
                "selectBackground": select_background,
                "selectForeground": select_foreground,
                **common,
            },
            "Menu": {
                "background": frame_background,
                "foreground": label_foreground,
                "activeBackground": active_background,
                "activeForeground": active_foreground,
            },
            "Scale": {"background": frame_background, "troughColor": entry_background, **common},
            "Canvas": {"background": frame_background, **common},
            "Toplevel": {"background": frame_background, **common},
        }
        for widget_class, options in widget_options.items():
            for option, value in options.items():
                self.option_add(f"*{widget_class}.{option}", value)

        tree_bg = style.lookup("Treeview", "background")
        if not tree_bg:
            tree_bg = style.lookup("Treeview", "fieldbackground")
        if not tree_bg:
            try:
                tmp = ttk.Treeview(self)
                tree_bg = tmp.cget("background")
                tmp.destroy()
            except:
                pass

        if tree_bg:
            self.tree_bg = tree_bg
        else:
            self.tree_bg = "white" if self._dark else "darkgray"

        self._plotprops_title_font = tk.font.Font(size=20, weight="bold")
        self._plotprops_project_font = tk.font.Font(size=11, slant="italic")
        self._tk_font = tk.font.Font()

        # save all floating entries so they can always be destroyed
        self.floating_entries = []

        # Keep track of plotprops widgets
        self.plotprops_widgets = []
        self.plotprops_frames = {}
        self.plotprops_states = {}

        # Store Limits of x-Axis in Variable 
        self.xlim_min = tk.DoubleVar(self)
        self.xlim_max = tk.DoubleVar(self)

        # Store Limits of y-Axis in Variable
        self.ylim_min = tk.DoubleVar(self)
        self.ylim_max = tk.DoubleVar(self)

        # Line settings
        self.linestyle = tk.StringVar(self)
        self.color = mpl.colors.to_hex("black")

        # Smoothing and baseline correction methods
        self.smoothing_method = tk.StringVar(self)
        self.background_correction_method = tk.StringVar(self)

        # BoolVariable to store whether to show ticks
        self.show_xticks = tk.BooleanVar(self)
        self.show_yticks = tk.BooleanVar(self)

        # Store number of ticks
        self.distance_xticks = tk.DoubleVar(self)
        self.offset_xticks = tk.DoubleVar(self)
        self.num_minor_xticks = tk.IntVar(self)
        self.distance_yticks = tk.DoubleVar(self)
        self.offset_yticks = tk.DoubleVar(self)
        self.num_minor_yticks = tk.IntVar(self)

        # Store value whether to adjust yaxis or not
        self.adjust_y = tk.BooleanVar(self)

        # Store CD specific parameters
        self.pathlength = tk.DoubleVar(self)
        self.concentration = tk.DoubleVar(self)
        self.nbr_of_residues = tk.IntVar(self)
        self.wavelength = tk.DoubleVar(self)
        self.show_tm_baselines = tk.BooleanVar(self)
        self.show_zero_line = tk.BooleanVar(self)
        self.zero_line_color = mpl.colors.to_hex("black")
        self.color_image = None
        self.zero_line_color_image = None
        self.zero_line_linestyle = tk.StringVar(self)
        self.zero_line_linewidth = tk.DoubleVar(self)
        self.show_fit = tk.BooleanVar(self)
        self.calc_MRE = tk.BooleanVar(self)

        # Store Vertical Labels
        self.vlabels = tk.StringVar(self)

        # create inset variable to keep track of whether an inset should be drawn or not and where
        self.inset = tk.BooleanVar(self)
        self.inset_pos = tk.StringVar(self)
        
        # Create all other variables needed for drawing the inset
        self.xlim_min_inset = tk.DoubleVar(self)
        self.xlim_max_inset = tk.DoubleVar(self)
        self.y_height_inset = tk.DoubleVar(self)
        self.xsize_inset = tk.IntVar(self)
        self.ysize_inset = tk.IntVar(self)
        self.inset_borderpad = tk.StringVar(self)
        self.inset_fontsize = tk.DoubleVar(self)

        # Variable for Mirroring Annotations on Inset
        self.mirror_annotations = tk.BooleanVar(self)
        self.inset_vlabels = tk.StringVar(self)

        # Variables for kinetics
        self.kinetics_x_label = tk.StringVar(self)
        self.kinetics_y_label = tk.StringVar(self)

        # Assay-specific variables
        self.assay_type = tk.StringVar(self)
        self.show_assay_fit = tk.BooleanVar(self)
        self.assay_fit_color = mpl.colors.to_hex("#D55E00" if self._colorblind else "red")
        self.assay_fit_color_image = None
        self.assay_fit_linestyle = tk.StringVar(self)
        self.assay_fit_linewidth = tk.DoubleVar(self)
        self.assay_absorption_coefficient = tk.DoubleVar(self)
        self.x_axis_unit = tk.StringVar(self)
        self.y_axis_unit = tk.StringVar(self)
        self.assay_fit_vmax = tk.StringVar(self, "0")
        self.assay_fit_Km = tk.StringVar(self, "0")
        self.assay_fit_r2 = tk.StringVar(self, "0")
        self.x_axis_label = tk.StringVar(self)
        self.y_axis_label = tk.StringVar(self)
        self.assay_show_vmax = tk.BooleanVar(self)
        self.assay_show_Km = tk.BooleanVar(self)
        self.assay_show_fit_data = tk.BooleanVar(self)
        self.autosort_files = tk.BooleanVar(self)
        
        # Variables for Multiplots
        self.multiplot_normalization = tk.BooleanVar(self)
        self.multiplot_plot_offset = tk.BooleanVar(self)
        self.multiplot_3D = tk.BooleanVar(self)
        self.multiplot_3D_elev = tk.DoubleVar(self)
        self.multiplot_3D_azim = tk.DoubleVar(self)
        self.multiplot_3D_projection_type = tk.StringVar(self)
        self.multiplot_3D_offset = tk.DoubleVar(self)
        self.multiplot_labels = tk.StringVar(self)
        self.multiplot_colormap = tk.StringVar(self)
        self.multiplot_label_match_color = tk.BooleanVar(self)
        self.multiplot_label_xposition = tk.DoubleVar(self)
        self.multiplot_label_yposition = tk.DoubleVar(self)
        self.multiplot_label_fontsize = tk.DoubleVar(self)
        self.multiplot_legend_transparency = tk.DoubleVar(self)
        self.multiplot_legend_automatic_placement = tk.BooleanVar(self)
        self.multiplot_fit = tk.BooleanVar(self)
        self.multiplot_fit_type = tk.StringVar(self)
        self.multiplot_show_tm_baselines = tk.BooleanVar(self)

        # Variable to keep track of whether the integrated area should be shown                
        self.integrated_area = tk.BooleanVar(self)

        # Variable to keep track of the integration mode
        self.integration_mode = tk.StringVar(self)

        # Variable to keep track of the linear positions in case of linear integration mode
        self.integration_linear_min = tk.DoubleVar(self)
        self.integration_linear_max = tk.DoubleVar(self)

        # Variable to keep track of the constant in case of constant integration mode
        self.integration_constant = tk.DoubleVar(self)

        # Remember whether HPLC baseline should be visible, this should always be reset when switching between plots
        self.HPLC_baseline_visible = False

        # Store Maximum y value for later offset calculation
        self.y_height = 100

        # Keep track of after methods to avoid multiple calls of the same function
        self._lazy_refresh = None
        self._save_to_db = None
        self._idle_refreshTree = None
        self._idle_adjust_assay_xlim = None
        self._plotprops_scrolling_disabled = False
        self._plotprops_scrollbar_update_id = None
        
        # Bind own close function to closing the window
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _get_data_path(self, image):
        # Return the absolute path to the ./icons folder
        return Path(__file__).resolve().parent / "icons" / image

    def _update_plotprops_width(self, event=None):
        if (not self.plotprops_initialized
                or not self.plotprops.winfo_exists()
                or not self.plotprops_sf.winfo_exists()):
            return

        self.plotprops_sf.update_idletasks()
        child_widths = [
            child.winfo_reqwidth()
            for child in self.plotprops.winfo_children()
            if child.winfo_manager() == "grid"
        ]
        padding = self.plotprops.cget("padding")
        if isinstance(padding, str):
            padding = tuple(padding.split())
        horizontal_padding = int(padding[0]) * 2
        requested_width = max(
            self.plotprops.winfo_reqwidth(),
            max(child_widths, default=0),
        )
        self.columnconfigure(
            5,
            minsize=requested_width + horizontal_padding + self.scrollbar_width,
        )
        self.after_idle(self.update_datakey_and_project)

    def _schedule_plotprops_width(self, event=None):
        self.after_idle(self._update_plotprops_width)

    def _bind_plotprops_scroll_to_widgets(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, ttk.Combobox) or isinstance(widget, ttk.Spinbox):
                widget.bind("<Enter>", self.on_enter)
            self._bind_plotprops_scroll_to_widgets(widget)

    def create_widgets(self):

        # Initialize plotoptions_data
        config.connect_gui(self)
        self.plotoptions_data = config.config
        self.import_data = config.import_data

        self.assay_fit_color = mpl.colors.to_hex(self.plotoptions_data["Assay"]["fit_clr"])

        # prepare sharable dictionaries
        cp.plot_data = {}

        # create and read saves
        db.prepare_saves()
        db.setup_import_preset_table()

        self.columnconfigure(3, weight=5)
        self.columnconfigure(5, weight=1)

        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=100)
        self.rowconfigure(5, weight=33)

        ## Create Menubar
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Create File Menu
        file_menu = tk.Menu(menubar, tearoff=False)

        # Add menu items to File Menu
        file_menu.add_command(label="New Project",
                              accelerator="Ctrl+N",
                              command = self.new_project
                              )
        
        file_menu.add_command(label="New MultiPlot",
                              accelerator="Ctrl+Shift+N",
                              command = self.new_multiplot
                              )

        file_menu.add_command(label="New Assay",
                              command = self.new_assay
                              )


        file_menu.add_command(label="Open Files",
                              accelerator="Ctrl+O",
                              command = self.open_files
                              )


        file_menu.add_separator()

        file_menu.add_command(label="Save",
                              accelerator="Ctrl+S",
                              command = self.save_current_img)

        file_menu.add_command(label="Save as...",
                              command = self.save_img_as)

        file_menu.add_command(label="Save all",
                              command = self.save_all_imgs)

        file_menu.add_separator()

        file_menu.add_command(label="Import PeptiXPlot Files",
                                      command = self.import_pxp_files)

        file_menu.add_command(label="Export Selected Plots",
                              command = self.export_pxp_files)

        file_menu.add_separator()

        file_menu.add_command(label="Settings",
                              command = config.open_settings)


        # Create Help Menu
        help_menu = tk.Menu(menubar, tearoff=False)

        # Add menu items to Help Menu

        help_menu.add_command(label="Open Documentation",
                              state=tk.DISABLED
                              )

        help_menu.add_command(label="Open GitHub Repository",
                              command = lambda: webbrowser.open("https://github.com/JBrinkhofer/PeptiXPlot"))
        
        # Add Menus to menubar
        menubar.add_cascade(
            label="File",
            menu=file_menu
        )

        menubar.add_cascade(
            label="Help",
            menu=help_menu
        )

        ## Create Data Browser on the left
        
        # Organized as a notebook to allow for single and layered plotting
        self.__init_notebook()

        # Initialize Treeview for File Browser
        self.__init_browser()

        # Initialize Treeview for Layered Graphs
        self.__init_multiplot_browser()
             
        self.notebook.grid(column=0, columnspan=2, row=1, rowspan=5, sticky=tk.NSEW)

        # Create Right Click Menues
        self.popup_1 = tk.Menu(self, tearoff=False)
        
        self.popup_1.add_command(label="New Project",
                                 accelerator="Ctrl+N",
                                 command = self.new_project
                                 )

        self.popup_1.add_command(label="Open Files",
                                 accelerator="Ctrl+O",
                                 command = self.open_files)
        
        self.popup_1.add_separator()
        
        self.popup_1.add_command(label="Paste",
                                 accelerator="Ctrl+V",
                                 command = self.browser.paste,
                                 state="disabled")


        self.popup_2 = tk.Menu(self, tearoff=False)

        self.popup_2.add_command(label="New Project",
                                 accelerator="Ctrl+N",
                                 command = self.new_project
                                 )


        self.popup_2.add_command(label="Open Files",
                                 accelerator="Ctrl+O",
                                 command = self.open_files)

        self.popup_2.add_separator()

        self.popup_2.add_command(label="Rename",
                                 accelerator="F2",
                                 command = self.browser.rename)

        self.popup_2.add_separator()

        self.popup_2.add_command(label="Choose Blank",
                                 accelerator="Ctrl+B",
                                 command = lambda: self.get_blank(selection=self.browser.selection()))
        
        self.popup_2.add_separator()

        self.popup_2.add_command(label="Cut",
                                 accelerator="Ctrl+X",
                                 command = self.browser.cut)

        self.popup_2.add_command(label="Copy",
                                 accelerator="Ctrl+C",
                                 command = self.browser.copy)
        
        self.popup_2.add_command(label="Paste",
                                 accelerator="Ctrl+V",
                                 command = self.browser.paste,
                                 state="disabled")
        
        self.popup_2.add_separator()

        self.popup_2.add_command(label="Delete",
                                 accelerator="Del",
                                 command = self.browser.on_delete)

        # MultiPlot Popup Menus
        
        self.popup_3 = tk.Menu(self, tearoff=False)

        self.popup_3.add_command(label="New Project",
                                 accelerator="Ctrl+N",
                                 command = self.new_project
                                 )

        self.popup_3.add_command(label="New MultiPlot",
                                 accelerator="Ctrl+Shift+N",
                                 command = self.new_multiplot
                                 )

        self.popup_3.add_command(label="New Assay",
                                 command = self.new_assay
                                 )
        
        self.popup_3.add_separator()
        
        self.popup_3.add_command(label="Paste",
                                 accelerator="Ctrl+V",
                                 command = self.multiplot_browser.paste,
                                 state="disabled")

        self.popup_4 = tk.Menu(self, tearoff=False)

        self.popup_4.add_command(label="New Project",
                                 accelerator="Ctrl+N",
                                 command = self.new_project
                                 )

        self.popup_4.add_command(label="New MultiPlot",
                                 accelerator="Ctrl+Shift+N",
                                 command = self.new_multiplot
                                 )

        self.popup_4.add_command(label="New Assay",
                                 command = self.new_assay
                                 )

        self.popup_4.add_separator()

        self.popup_4.add_command(label="Rename",
                                 accelerator="F2",
                                 command = self.multiplot_browser.rename)

        self.popup_4.add_separator()

        self.popup_4.add_command(label="Cut",
                                 accelerator="Ctrl+X",
                                 command = self.multiplot_browser.cut)

        self.popup_4.add_command(label="Copy",
                                 accelerator="Ctrl+C",
                                 command = self.multiplot_browser.copy)
        
        self.popup_4.add_command(label="Paste",
                                 accelerator="Ctrl+V",
                                 command = self.multiplot_browser.paste,
                                 state="disabled")
        
        self.popup_4.add_separator()

        self.popup_4.add_command(label="Delete",
                                 accelerator="Del",
                                 command = self.multiplot_browser.on_delete)

        # Create separator between Plot and Browser
        sep_main = ttk.Separator(self, orient="vertical")
        sep_main.grid(column=2, row=0, rowspan=6, sticky=tk.NS, padx=2)

        ## Insert Plot on the right

        # Initialize plot

        self.iid = None
        self.toolbar_frame = ttk.Frame(self)
        cp.connect_gui(self)
        
        # Pack Toolbar and Figure
        self.canvas_widget = cp.canvas.get_tk_widget()
        self.canvas_widget.grid(column=3, row=2, rowspan=2, sticky=tk.NSEW)
        self.init_toolbar_row(column=3, row=1)

        # Create Separator between Table below and Plot
        sep_sec = ttk.Separator(self, orient="horizontal")
        sep_sec.grid(column=2, row=4, columnspan=5, sticky=tk.EW, pady=2)

        # Create Separator between Plot Props and Plot
        sep_tert = ttk.Separator(self, orient="vertical")
        sep_tert.grid(column=4, row=1, rowspan=4, sticky=tk.NS, padx=2)

        # Store in a variable whether plottype-specific plotinfo have already been initialized, so they can be deleted prior to new initialization
        self.plotinfo_initialized = False

        # Store in a variable whether plottype-specific plotprops have already been initialized, so they can be deleted prior to new initialization
        self.plotprops_initialized = False

        # Bind all hotkeys for menus
        self.bind_controls()

        edited_last = self.browser.tag_has("edited_last")
        edited_last_multiplot = self.multiplot_browser.tag_has("edited_last")

        try:
            # Check which plot was opened last
            if len(edited_last) == 1:
                iid = edited_last[0]
                self.browser.see(iid)
                self.browser.selection_set(iid)
                if not self.browser.tag_has("Project", item=iid):
                    db.load(iid)
                    self.plottype = db.save_data[iid]["plottype"]
                    # Pack Treeview for Plotinfo on Bottom
                    self.init_plotinfo(self.plottype)
                    
                    # Pack Frame for Plot Properties on the right
                    self.init_plotprops(self.plottype)
                    self._startup_iid = iid

            elif len(edited_last_multiplot) == 1:
                iid = edited_last_multiplot[0]
                self.notebook.select(self.notebook_frame2)
                self.multiplot_browser.see(iid)
                self.multiplot_browser.selection_set(iid)
                if not self.multiplot_browser.tag_has("Project", item=iid):
                    db.load(iid, MultiPlot=True)
                    self.plottype = "MultiPlot"
                    # Pack Treeview for Plotinfo on Bottom
                    self.init_plotinfo(self.plottype)
                    
                    # Pack Frame for Plot Properties on the right
                    self.init_plotprops(self.plottype)
                    self._startup_multiplot_iid = iid
        except Exception as e:
            if DEBUG: print(f"Exception occured during startup: {e}")

        if not self.plotinfo_initialized or not self.plotprops_initialized:
            # Pack Treeview for Plotinfo on Bottom
            self.init_plotinfo(self.plottype)
            
            # Pack Frame for Plot Properties on the right
            self.init_plotprops(self.plottype)

        # Give the dimensions of the height of the notebook to the browser
        self.notebook_tab_height = self.notebook.winfo_height()-self.browser.winfo_height()
        self.after(50, self._finish_startup)

    def _finish_startup(self):
        self.update_idletasks()
        if self._startup_iid is not None:
            self.plot(self._startup_iid)
        elif self._startup_multiplot_iid is not None:
            self.init_multiplot(self._startup_multiplot_iid)
        self.update_idletasks()
        if self.iid is not None:
            self.refresh(resize=True, refreshTree=True)
        else:
            cp.update_fig_size(cp.fig)
            cp.scale_axes_strokes(cp.ax)
            cp.draw_canvas()
            cp.background = cp.canvas.copy_from_bbox(cp.fig.bbox)
        self.after(250, lambda: setattr(self, "_startup_complete", True))


    def init_toolbar_row(self, column, row):
        # Function for the initiation of the row above the plot including the toolbar and select baseline feature

        cp.toolbar.grid(row=0, column=0, sticky=tk.EW)

        # Setup a label for the import of baselines
        ttk.Label(self.toolbar_frame, text="Blank:").grid(row=0, column=1, sticky=tk.E)

        # Setup a string variable for the current baseline
        self.baseline_filename = tk.StringVar(self)

        # Setup an entry that shows the current baseline
        self.baseline_entry = ttk.Entry(self.toolbar_frame, textvariable=self.baseline_filename, state="readonly")
        self.baseline_entry.grid(row=0, column=2, sticky=tk.EW)
        self.baseline_entry.bind("<Button-1>", self.get_blank)

        # Setup a button for the setup of baselines

        self.set_blank_btn = ttk.Button(self.toolbar_frame, text="Choose blank", command=self.get_blank)
        self.set_blank_btn.grid(row=0, column=3, sticky=tk.E)

        self.toolbar_frame.grid(column=column, row=row, sticky=tk.EW)
        self.toolbar_frame.columnconfigure(0, weight=3)
        self.toolbar_frame.columnconfigure(2, weight=1)

    def get_blank(self, event=None, selection=None):
        if event and event.widget.instate(["disabled",]):
            return
        
        if selection:
            # Check whether the current treeview is the normal browser, otherwise return
            if not str(self.notebook.select()) == str(self.notebook_frame1):
                return

            # Check whether a project has also been selected, if so, don't do anything
            if any(self.browser.tag_has(tagname="Project", item=iid) for iid in selection):
                return

            # Get the plottype
            iid = selection[0]
            
            plottypes = set(self.browser.plottypes)
            tags = set(self.browser.item(iid, option="tags"))

            plottype_list = list(plottypes.intersection(tags))

            if len(plottype_list) > 0:
                plottype = plottype_list[0]
            else:
                return
            
            # Check whether all plots have the same plottype
            if not all(self.browser.tag_has(tagname=plottype, item=iid) for iid in selection):
                return

            # Check whether plottype is the same for all iids
            for iid in selection:
                tags = self.browser.item(iid, option="tags")

                if not (plottype in tags):
                    return

        else:
            plottype = self.plottype

        # For this to work, this function needs to open a dialog that allows for the selection of a blank from available Files
        if DEBUG: print("Setting blank")

        blankhandler = BlankHandler(self, cp, db, selection=selection, plottype=plottype)

    def set_blank(self, selection=None, skip_save=False):

        if not selection:
            current_iids = [self.iid,]
        else:
            current_iids = selection

        if DEBUG: print("Setting blank for selection:", selection)

        blank_iid = db.save_data[current_iids[0]]["baseline_iid"]

        for iid in current_iids:

            if not db.load(iid): continue

            if blank_iid is None:
                if (selection and self.iid in selection) or not selection: self.baseline_filename.set(None)
                cp.corrected_ypoints[iid] = self.correct_baseline(iid)
                continue

            # Load baseline if not done yet
            if not db.load(blank_iid):
                print("Blank file could not be found, removing blank.")
                cp.plot_data["baseline_iid"] = None
                if (selection and self.iid in selection) or not selection: self.baseline_filename.set(None)
                cp.corrected_ypoints[iid] = self.correct_baseline(iid)
                continue
                      
            # Check whether the current plot iid is already saved in "baseline_in"
            if iid not in db.save_data[blank_iid]["baseline_in"]:
                if DEBUG: print(f"Adding {iid} to baseline_in of {blank_iid}")
                db.save_data[blank_iid]["baseline_in"].append(iid)
                db.save(blank_iid, MultiPlot=False)
            
            if (selection and self.iid in selection) or not selection: self.baseline_filename.set(db.browser_saves[blank_iid]["filename"])

            # Calculate the corrected ypoints
            cp.corrected_ypoints[iid] = self.correct_baseline(iid)

            if not skip_save:
                db.save(iid, MultiPlot=False)

    def remove_blank(self, selection=None):

        if selection:
            current_iids = selection
        else:
            current_iids = [self.iid,]

        for iid in current_iids:

            if db.load(iid):
                blank_iid = db.save_data[iid]["baseline_iid"]
                if blank_iid and db.load(blank_iid):
                    if iid in db.save_data[blank_iid]["baseline_in"]:
                        db.save_data[blank_iid]["baseline_in"].remove(iid)
                        db.save(blank_iid, MultiPlot=False)

                db.save_data[iid]["baseline_iid"] = None
                
                if (selection and self.iid in selection) or not selection: self.baseline_filename.set(None)

                cp.corrected_ypoints[iid] = self.correct_baseline(iid)

            db.save(iid, MultiPlot=False)

    def plot(self, iid):
        if self._loading:
            return

        self._loading = True
        try:
            self._plot(iid)
        finally:
            self._loading = False

    def _plot(self, iid):
        if DEBUG: print(f"Plotting iid {iid}")

        # Seperate graphical plot settings handled in CanvasPlot, calls to database and other settings handled in Root
        if self.iid is not None:
            # Do not save if there is a key error, which happens when the currently running plot was deleted
            try:
                self.save_to_db(immediate=True)
            except KeyError as e:
                print(f"File was not found: {e}\nSkipping save.")

        self.iid = iid

        self.update_edited_last(MultiPlot=False)

        self.last_plottype = self.plottype
                
        self.plottype = db.browser_saves[iid]["plottype"]

        # Deactivate baseline visibility by default
        self.HPLC_baseline_visible = False

        # Revert variables to cp.plot_data and plotoptions_data
        self.vlabels.set(db.save_data[iid]["label_orientation"])

        # Inset Variables are only for MALDI
        if self.plottype == "MALDI":
            self.inset_vlabels.set(db.save_data[iid]["inset_label_orientation"])
            # update inset variable to keep track of whether an inset should be drawn or not and where
            self.inset.set(db.save_data[iid]["inset"])
            self.inset_pos.set(db.save_data[iid]["inset_pos"])
            
            # update all other variables needed for drawing the inset
            self.xlim_min_inset.set(db.save_data[iid]["inset_x_axis_min"])
            self.xlim_max_inset.set(db.save_data[iid]["inset_x_axis_max"])
            self.y_height_inset.set(db.save_data[iid]["inset_y_axis_max_percent"])
            self.xsize_inset.set(db.save_data[iid]["inset_xsize"])
            self.ysize_inset.set(db.save_data[iid]["inset_ysize"])
            self.inset_borderpad.set(str(db.save_data[iid]["inset_borderpad"]))
            self.inset_fontsize.set(db.save_data[iid]["inset_fontsize"])

            # Variable for Mirroring Annotations on Inset
            self.mirror_annotations.set(db.save_data[iid]["mirror_annotations"])

        # Update variables
        # Store Limits of x-Axis in Variable 
        self.xlim_min.set(db.save_data[iid]["x_axis_min"])
        self.xlim_max.set(db.save_data[iid]["x_axis_max"])

        # Store Limits of y-Axis
        self.ylim_min.set(db.save_data[iid]["y_axis_min"])
        self.ylim_max.set(db.save_data[iid]["y_axis_max"])
        self.adjust_y.set(db.save_data[iid]["autoadjust_y"])

        # Setup line settings
        self.linestyle.set(str(db.save_data[iid]["linestyle"]))
        self.color = mpl.colors.to_hex(db.save_data[iid]["color"])
        if hasattr(self, "color_btn") and self.color_btn.winfo_exists():
            size = self.color_image.width()
            self.color_image = self.create_color_image(size=size, color=self.color)
            self.color_btn.configure(image=self.color_image)

        # Update the smoothing and baseline correction methods
        self.smoothing_method.set(db.save_data[iid]["smoothing_method"])
        self.background_correction_method.set(db.save_data[iid]["background_correction_method"])

        if self.plottype == "Kinetics":
            self.kinetics_x_label.set(db.save_data[iid]["xlabel"])
            self.kinetics_y_label.set(db.save_data[iid]["ylabel"])

        # Store CD specific data
        if self.plottype in ["CD","Tm"]:
            self.calc_MRE.set(db.save_data[iid]["calc_MRE"])
            self.pathlength.set(db.save_data[iid]["pathlength"])
            self.concentration.set(db.save_data[iid]["concentration"])
            self.nbr_of_residues.set(db.save_data[iid]["nbr_of_residues"])
            if self.plottype == "Tm":
                self.wavelength.set(db.save_data[iid]["wavelength"])
                self.show_tm_baselines.set(db.save_data[iid]["show_tm_baselines"])
                self.show_fit.set(db.save_data[iid]["show_fit"])
            elif self.plottype == "CD":
                self.show_zero_line.set(db.save_data[iid]["show_zero_line"])
                self.zero_line_color = mpl.colors.to_hex(db.save_data[iid]["zero_line_color"])
                if hasattr(self, "zero_line_color_btn") and self.zero_line_color_btn.winfo_exists():
                    size = self.zero_line_color_image.width()
                    self.zero_line_color_image = self.create_color_image(size=size, color=self.zero_line_color)
                    self.zero_line_color_btn.configure(image=self.zero_line_color_image)
                self.zero_line_linestyle.set(str(db.save_data[iid]["zero_line_linestyle"]))
                self.zero_line_linewidth.set(db.save_data[iid]["zero_line_linewidth"])

        # Store information about yticks
        self.show_xticks.set(db.save_data[iid]["show_xticks"])
        self.distance_xticks.set(db.save_data[iid]["distance_xticks"])
        self.offset_xticks.set(db.save_data[iid]["offset_xticks"])
        self.num_minor_xticks.set(db.save_data[iid]["num_minor_xticks"])

        self.show_yticks.set(db.save_data[iid]["show_yticks"])
        self.distance_yticks.set(db.save_data[iid]["distance_yticks"])
        self.offset_yticks.set(db.save_data[iid]["offset_yticks"])
        self.num_minor_yticks.set(db.save_data[iid]["num_minor_yticks"])

        # Update integration mode
        if self.plottype == "HPLC":
            self.integration_mode.set(db.save_data[iid]["integration_type"])
            self.integration_linear_min.set(db.save_data[iid]["integration_info"]["linear"][0])
            self.integration_linear_max.set(db.save_data[iid]["integration_info"]["linear"][1])
            self.integration_constant.set(db.save_data[iid]["integration_info"]["constant"])
            self.integrated_area.set(db.save_data[iid]["plot_integrals"])

        # Update the notepad
        # Flush notepad
        self.notepad.delete("1.0", tk.END)
        # Insert new values
        self.notepad.insert("1.0", db.save_data[iid]["notepad_text"])

        # Initiate plotrelated informations
        # Only reload if the plottype actually changes
        if self.plottype != self.last_plottype:
            self.init_plotinfo(self.plottype)
            self.init_plotprops(self.plottype)
        else:
            # Change only datakey and project label
            self.update_datakey_and_project()

        cp.plot(db.save_data[iid])

    def refresh_integration_percentages(self):
        # Refresh Percentages in Tree
        sum_for_area = 0
        
        for peak in cp.plot_data["integral_dict"]:
            # Check whether the peak should be included
            if cp.plot_data["integral_dict"][peak][4] == "Yes":
                sum_for_area += cp.plot_data["integral_dict"][peak][2]

        # Update all peaks in the dictionary
        for peak in cp.plot_data["integral_dict"]:
            # Check whether the peak should be included
            if cp.plot_data["integral_dict"][peak][4] == "Yes":
                cp.plot_data["integral_dict"][peak][3] = cp.plot_data["integral_dict"][peak][2]/sum_for_area*100
            elif cp.plot_data["integral_dict"][peak][4] == "No":
                cp.plot_data["integral_dict"][peak][3] = float(0.00)

        self.refreshTree()

    def init_multiplot(self, iid):
        if self._loading:
            return

        self._loading = True
        try:
            self._init_multiplot(iid)
        finally:
            self._loading = False

    def _init_multiplot(self, iid):
        if DEBUG: print("Initiating MultiPlot/Assay")

        # Do not save if there is a key error, which happens when the currently running plot was deleted
        if self.iid is not None:
            try:
                self.save_to_db(immediate=True)
            except KeyError:
                pass
                
        self.iid = iid

        self.update_edited_last(MultiPlot=True)

        self.multiplot_iid = iid

        self.last_plottype = self.plottype

        if DEBUG: print(self.last_plottype)

        # Deactivate baseline visibility by default
        self.HPLC_baseline_visible = False

        # Get all general information for the plot
        self.multiplot_plotoptions = db.multiplot_save_data[iid]["PlotOptions"]

        if self.multiplot_plotoptions["plottype"] == "Assay":
            self.plottype = "Assay"

            # Assay-specific variables
            self.assay_fit_color = self.multiplot_plotoptions["assay_fit_color"]
            if hasattr(self, "assay_fit_color_btn") and self.assay_fit_color_btn.winfo_exists():
                size = self.assay_fit_color_image.width()
                self.assay_fit_color_image = self.create_color_image(size=size, color=self.assay_fit_color)
                self.assay_fit_color_btn.configure(image=self.assay_fit_color_image)
            self.assay_type.set(self.multiplot_plotoptions["assay_type"])
            self.assay_fit_linestyle.set(str(self.multiplot_plotoptions["assay_fit_linestyle"]))
            self.assay_fit_linewidth.set(self.multiplot_plotoptions["assay_fit_linewidth"])
            self.show_assay_fit.set(self.multiplot_plotoptions["show_assay_fit"])
            self.assay_absorption_coefficient.set(self.multiplot_plotoptions["molar_absorption_coefficient"])
            self.x_axis_unit.set(self.multiplot_plotoptions["assay_x_unit"])
            self.y_axis_unit.set(self.multiplot_plotoptions["assay_y_unit"])
            self.x_axis_label.set(self.multiplot_plotoptions["assay_x_label"])
            self.y_axis_label.set(self.multiplot_plotoptions["assay_y_label"])
            self.assay_show_vmax.set(self.multiplot_plotoptions["show_vmax"])
            self.assay_show_Km.set(self.multiplot_plotoptions["show_Km"])
            self.assay_show_fit_data.set(self.multiplot_plotoptions["show_fit_data"])
            self.autosort_files.set(self.multiplot_plotoptions["autosort_files"])

            if (self.multiplot_plotoptions["assay_fit"] and 
                "popt" in self.multiplot_plotoptions["assay_fit"] and 
                len(self.multiplot_plotoptions["assay_fit"]["popt"]) == 2):

                km_error, vmax_error = np.sqrt(np.diag(self.multiplot_plotoptions["assay_fit"]["pcov"]))

                self.assay_fit_Km.set(f"{self.multiplot_plotoptions['assay_fit']['popt'][0]:.4g} ± {km_error:.2g} {self.multiplot_plotoptions['assay_x_unit']}")
                self.assay_fit_vmax.set(f"{self.multiplot_plotoptions['assay_fit']['popt'][1]:.4g} ± {vmax_error:.2g} {self.multiplot_plotoptions['assay_y_unit']}")
                self.assay_fit_r2.set(f"{self.multiplot_plotoptions['assay_fit']['r_squared']:.4g}")

            else:
                self.assay_fit_Km.set(f"0 {self.multiplot_plotoptions['assay_x_unit']}")
                self.assay_fit_vmax.set(f"0 {self.multiplot_plotoptions['assay_y_unit']}")
                self.assay_fit_r2.set("0")
            
        else:
            self.plottype = "MultiPlot"

        if DEBUG: print(self.plottype)
        # Initiate plotrelated informations
        # Only reload if the plottype actually changes
        if self.plottype != self.last_plottype:
            if DEBUG: print("Different plottype, reinitializing plotinfo and plotprops")
            self.init_plotinfo(self.plottype)
            self.init_plotprops(self.plottype)
        else:
            if DEBUG: print("Same plottype, not reinitializing plotinfo and plotprops")
            # Change only datakey and project label
            self.update_datakey_and_project()

        ## Initiate all dictionaries and keys for current plot
        if self.plottype == "MultiPlot":
            # Multiplot-specific variables
            self.multiplot_normalization.set(self.multiplot_plotoptions["normalization"])
            self.multiplot_plot_offset.set(self.multiplot_plotoptions["plot_offset"])
            self.multiplot_labels.set(self.multiplot_plotoptions["labels"])
            self.multiplot_label_match_color.set(self.multiplot_plotoptions["label_data"]["match_color"])
            self.multiplot_label_xposition.set(self.multiplot_plotoptions["label_data"]["xposition"])
            self.multiplot_label_yposition.set(self.multiplot_plotoptions["label_data"]["yposition"])
            self.multiplot_label_fontsize.set(self.multiplot_plotoptions["label_data"]["fontsize"] if self.multiplot_plotoptions["label_data"]["fontsize"] is not None else self.plotoptions_data["MultiPlot"]["fontsize"])
            self.multiplot_legend_transparency.set(self.multiplot_plotoptions["legend_transparency"])
            self.multiplot_legend_automatic_placement.set(self.multiplot_plotoptions["legend_automatic_placement"])
    
            self.multiplot_colormap.set(self.multiplot_plotoptions["colormap"])
    
            self.multiplot_3D.set(self.multiplot_plotoptions["3D"])
            self.multiplot_3D_elev.set(self.multiplot_plotoptions["3D_data"]["elev"])
            self.multiplot_3D_azim.set(self.multiplot_plotoptions["3D_data"]["azim"])
            self.multiplot_3D_projection_type.set("Orthographic" if self.multiplot_plotoptions["3D_data"]["projection_type"]=="ortho" else "Perspective")
            self.multiplot_3D_offset.set(self.multiplot_plotoptions["3D_data"]["offset"])
    
            # Tm-specific
            if self.multiplot_plotoptions["plottype"] == "Tm":
                    
                self.multiplot_fit.set(self.multiplot_plotoptions["show_fit"])
                tm_method = self.multiplot_plotoptions["Tm_method"]
                if tm_method == "SCB": tm_method = "Sigmoidal + Constant Baseline"
                elif tm_method == "SLB": tm_method = "Sigmoidal + Linear Baseline"
                elif tm_method == "SQB": tm_method = "Sigmoidal + Quadratic Baseline"
                elif tm_method == "VHD": tm_method = "Van't Hoff Derivative"
                elif tm_method == "EGD": tm_method = "Empirical Gauss Derivative"

                self.multiplot_fit_settings_frame.grid()
                self.multiplot_fit_type.set(tm_method)
                self.multiplot_show_tm_baselines.set(self.multiplot_plotoptions["show_tm_baselines"])
    
            elif self.multiplot_plotoptions["plottype"] != "Assay":
                self.multiplot_fit_settings_frame.grid_remove()
    
            if self.multiplot_plotoptions["plottype"] in ["CD","Tm"]:
                # Store information about yticks
                self.calc_MRE_label.grid()
                self.calc_MRE_checkbox.grid()
                self.calc_MRE.set(self.multiplot_plotoptions["calc_MRE"])
    
                if self._lazy_refresh:
                    self.after_cancel(self._lazy_refresh)
                    self._lazy_refresh = None
    
            elif self.multiplot_plotoptions["plottype"] != "Assay":
                self.calc_MRE_label.grid_remove()
                self.calc_MRE_checkbox.grid_remove()

        # Store Limits of x-Axis in Variable 
        self.xlim_min.set(self.multiplot_plotoptions["x_axis_min"])
        self.xlim_max.set(self.multiplot_plotoptions["x_axis_max"])

        # Store Limits of y-Axis in Variable 
        self.ylim_min.set(self.multiplot_plotoptions["y_axis_min"])
        self.ylim_max.set(self.multiplot_plotoptions["y_axis_max"])
        self.adjust_y.set(self.multiplot_plotoptions["autoadjust_y"])

        # Tick settings
        self.show_xticks.set(self.multiplot_plotoptions["show_xticks"])
        self.distance_xticks.set(self.multiplot_plotoptions["distance_xticks"])
        self.offset_xticks.set(self.multiplot_plotoptions["offset_xticks"])
        self.num_minor_xticks.set(self.multiplot_plotoptions["num_minor_xticks"])
        
        self.show_yticks.set(self.multiplot_plotoptions["show_yticks"])
        self.distance_yticks.set(self.multiplot_plotoptions["distance_yticks"])
        self.offset_yticks.set(self.multiplot_plotoptions["offset_yticks"])
        self.num_minor_yticks.set(self.multiplot_plotoptions["num_minor_yticks"])

        # Variable for Mirroring Annotations on Inset
        self.mirror_annotations.set(True)

        # Update the notepad
        # Flush notepad
        self.notepad.delete("1.0", tk.END)
        # Insert new values
        self.notepad.insert("1.0", self.multiplot_plotoptions["notepad_text"])      

        cp.multiplot(db.multiplot_save_data[iid])

    def add_to_multiplot(self, iid, position=None):

        number_of_plots = len(db.multiplot_save_data[self.multiplot_iid]) - 1
        
        # Check whether the added multiplot is the first multiplot
        if number_of_plots == 0:

            for key in ["show_xticks", "distance_xticks", "offset_xticks", "num_minor_xticks", 
                        "show_yticks", "distance_yticks", "offset_yticks", "num_minor_yticks", 
                        "x_axis_min", "x_axis_max", "plottype"]:
                
                self.multiplot_plotoptions[key] = db.save_data[iid][key]

            if self.multiplot_plotoptions["plottype"] == "Tm":
                for key in ["wavelength", "show_fit", "Tm_method", "show_tm_baselines"]:
                    self.multiplot_plotoptions[key] = db.save_data[iid][key]

                self.multiplot_fit_settings_frame.grid()

                self.multiplot_fit.set(self.multiplot_plotoptions["show_fit"])
                tm_method = self.multiplot_plotoptions["Tm_method"]
                if tm_method == "SCB": tm_method = "Sigmoidal + Constant Baseline"
                elif tm_method == "SLB": tm_method = "Sigmoidal + Linear Baseline"
                elif tm_method == "SQB": tm_method = "Sigmoidal + Quadratic Baseline"
                elif tm_method == "VHD": tm_method = "Van't Hoff Derivative"
                elif tm_method == "EGD": tm_method = "Empirical Gauss Derivative"
            
                self.multiplot_fit_type.set(tm_method)
                self.multiplot_show_tm_baselines.set(self.multiplot_plotoptions["show_tm_baselines"])

            if self.multiplot_plotoptions["plottype"] in ["CD","Tm"]:
                    
                self.multiplot_plotoptions["calc_MRE"] = db.save_data[iid]["calc_MRE"]

                self.calc_MRE_label.grid()
                self.calc_MRE_checkbox.grid()
                # Store information about yticks
                
                self.calc_MRE.set(self.multiplot_plotoptions["calc_MRE"])

                # Additionally in case of CD or Tm, Min-Max Normalization and Plot Offset are not really logical options
                # Therefore they should be disabled by default
                self.multiplot_normalization.set(False)
                self.multiplot_plot_offset.set(False)
                
            if self._lazy_refresh:
                self.after_cancel(self._lazy_refresh)
                self._lazy_refresh = None

            self.xlim_min.set(self.multiplot_plotoptions["x_axis_min"])
            self.xlim_max.set(self.multiplot_plotoptions["x_axis_max"])

            self.show_xticks.set(self.multiplot_plotoptions["show_xticks"])
            self.distance_xticks.set(self.multiplot_plotoptions["distance_xticks"])
            self.offset_xticks.set(self.multiplot_plotoptions["offset_xticks"])
            self.num_minor_xticks.set(self.multiplot_plotoptions["num_minor_xticks"])
            
            self.show_yticks.set(self.multiplot_plotoptions["show_yticks"])
            self.distance_yticks.set(self.multiplot_plotoptions["distance_yticks"])
            self.offset_yticks.set(self.multiplot_plotoptions["offset_yticks"])
            self.num_minor_yticks.set(self.multiplot_plotoptions["num_minor_yticks"])

            self.update_xlim()

            # This refresh is necessary to make sure that the plots axes is updated to reflect the settings from the underlying plot type.
            cp.refresh()
                        
        else:
            # Check whether the plot fits to the plottype of the multiplot
            if db.browser_saves[iid]["plottype"] != self.multiplot_plotoptions["plottype"]:
                plottype = db.browser_saves[iid]["plottype"]
                print(f"Invalid plot type ({plottype}). Plots need to be of the same type.")
                print(f"The plot type of this multiplot is: {self.multiplot_plotoptions['plottype']}.")
                return

        linewidth = self.plotoptions_data[self.multiplot_plotoptions["plottype"]]["lnwdth"]
        if not db.load(iid):
            print("Plot is not in database. Plot is skipped.")
            return

        color = mpl.colors.to_rgb(db.save_data[iid]["color"])
        linestyle = db.save_data[iid]["linestyle"]

        # Get the corrected baseline ypoints
        if iid not in cp.corrected_ypoints:
            
            cp.corrected_ypoints[iid] = self.correct_baseline(iid)

        # get the max and minimum values in the data set
        _, max_y = get_maximum(self.multiplot_plotoptions["x_axis_min"],
                               self.multiplot_plotoptions["x_axis_max"],
                               db.save_data[iid]["xpoints"],
                               cp.corrected_ypoints[iid])
        _, min_y = get_minimum(self.multiplot_plotoptions["x_axis_min"],
                               self.multiplot_plotoptions["x_axis_max"],
                               db.save_data[iid]["xpoints"],
                               cp.corrected_ypoints[iid])

        # First get a list of all positions of the plots
        plot_positions = [cp.multiplot_data[iid]["position"] for iid in cp.multiplot_data if iid != "PlotOptions"]

        # Now get the correct insert position for the plot
        if position is None:

            if plot_positions:
                # Get the largest position
                max_pos = max(plot_positions)
                # Insert after this number
                insert_number = max_pos + 1
            else:
                insert_number = 0

        # If a position was given, insert the plot at that position and move all other plots up
        else:
            
            insert_number = position

            # Move existing plots up to make room for the inserted plot.
            for plot_iid, plot_data in cp.multiplot_data.items():
                if plot_iid != "PlotOptions" and plot_data["position"] >= position:
                    plot_data["position"] += 1

        if (not self.multiplot_plotoptions["global_min_y"]) or min_y < self.multiplot_plotoptions["global_min_y"]:
            self.multiplot_plotoptions["global_min_y"] = min_y

        if (not self.multiplot_plotoptions["global_max_y"]) or max_y > self.multiplot_plotoptions["global_max_y"]:
            self.multiplot_plotoptions["global_max_y"] = max_y

        # Previously: cp.multiplot_data.update({iid:[db.save_data[iid]["filename"],linewidth, color, insert_number]})
        cp.multiplot_data.update({iid:{"filename": db.browser_saves[iid]["filename"],
                                       "linewidth": linewidth,
                                       "linestyle": linestyle,
                                       "alpha": 1,
                                       "color": color,
                                       "position": insert_number,
                                       "min_y": min_y,
                                       "max_y": max_y,
                                    }
                                })

        size = ceil(18.75*self.scaling)
        alpha_border_size = ceil(size/8)
        gray_border_size = ceil(1.5*alpha_border_size)
        rgb_color = return_regular_rgb_tuple(cp.multiplot_data[iid]["color"])
        
        hex_color = "#{:02x}{:02x}{:02x}".format(*map(int,rgb_color))
        img = tk.PhotoImage(width=size, height=size)
        # Put a gray block inside to create a nice border around the color of the plot, this also leaves some padding on the right
        img.put("darkgray", to=(0,
                            gray_border_size,
                            size-2*gray_border_size,
                            size-gray_border_size))
        
        # Fill the image with the current color of the plot
        img.put(hex_color, to=(2*alpha_border_size-gray_border_size,
                                2*alpha_border_size,
                                size-2*alpha_border_size-gray_border_size,
                                size-2*alpha_border_size))

        self.plotinfo.color_images[iid] = img

        self.autoadjust_y(skip_blit=True)

        self.update_multiplot_positions()

        self.apply_colormap()

    def add_to_assay(self, iid, parent=None):

        number_of_plots = len(db.multiplot_save_data[self.multiplot_iid]) - 1
        
        # Check whether the added multiplot is the first multiplot
        if number_of_plots == 0:

            self.multiplot_plotoptions["assay_plottypes"] = db.save_data[iid]["plottype"]
        
            if self._lazy_refresh:
                self.after_cancel(self._lazy_refresh)
                self._lazy_refresh = None
        
        else:
            # Check whether the plot fits to the plottype of the multiplot
            if db.save_data[iid]["plottype"] != self.multiplot_plotoptions["assay_plottypes"]:
                plottype = db.save_data[iid]["plottype"]
                print(f"Invalid plot type ({plottype}). Plots need to be of the same type.")
                print(f"The plot type of this assay is: {self.multiplot_plotoptions['assay_plottypes']}.")
                return
        
        if not db.load(iid):
            print("Plot is not in database. Plot is skipped.")
            return

        if parent is not None and parent in self.multiplot_plotoptions["assay_datapoints"]:
            self.multiplot_plotoptions["assay_datapoints"][parent]["plots"].append(iid)
        else:
            parent = None

        # For assays, you need a bit less info. Only save the filename and the parent of the plot. The parent is supposed to be the actual datapoint refering to multiplicates and such.
        cp.multiplot_data.update({iid:{"filename": db.browser_saves[iid]["filename"],
                                       "parent": parent,
                                    }
                                })

    def update_name_similarity_matrix(self):

        for iid in list(cp.multiplot_data.keys()):
            if iid == "PlotOptions":
                continue
            if not db.load(iid):
                print(f"Plot {iid} is not in database. Plot is removed.")
                cp.multiplot_data.pop(iid)

        labels = {iid: db.browser_saves[iid]["filename"] for iid in cp.multiplot_data if iid != "PlotOptions"}
        iids = list(labels)

        matrix = pd.DataFrame(index=iids, columns=iids, dtype=object)

        for i, iid1 in enumerate(iids):
            for j, iid2 in enumerate(iids):
                if i == j:
                    matrix.at[iid1, iid2] = None
                elif i <= j:
                    Matcher = SequenceMatcher(None, labels[iid1], labels[iid2])
                    # Get the String
                    longest_match = Matcher.find_longest_match(0, len(labels[iid1]), 0, len(labels[iid2]))
                    string = labels[iid1][longest_match.a:longest_match.a + longest_match.size]
                    # Store the string in the matrix
                    matrix.at[iid1, iid2] = string
                    matrix.at[iid2, iid1] = string

        pooled_plots = self.pool_assay_plots(matrix)

        self.multiplot_plotoptions["assay_datapoints"] = {}

        for pooled_plot, iids in pooled_plots.items():
            self.multiplot_plotoptions["assay_datapoints"].update({pooled_plot: {"plots": iids}})
            self.update_assay_x_for_datapoint(pooled_plot)

        if DEBUG: print(f"Finished Assay pools: {cp.multiplot_data['PlotOptions']['assay_datapoints']}")

    def pool_assay_plots(self, matrix):
        # Pool assay plots based on the similarity of their names. This function will group plots that have a high similarity into the same pool.
        # However, it needs to be checked that their are no artifacts from the similarities. To ensure this, all found "largest" similarities should have the
        # Base name inside of their sequence that is equal across all selected plots. If so, then the match is deemed correct. If not, the match is most probably an artifact.
        
        pools = {} # Label of the match: list of iids that belong to this pool
        inverted_pools = {} # iid: list of labels of the matches that this iid belongs to

        # Get the basename of all items inside of the matrix
        basename = self.check_matrix_for_basename(matrix)
        # Check which matches contain the correct basename
        valid_matches = matrix.apply(
            lambda column: column.map(
                lambda value: isinstance(value, str) and basename in value
            )
        )
        # Filter the matrix to only include valid matches, removing any matches that do not contain the correct basename
        filtered_matrix = matrix.where(valid_matches, other=None)

        # Now find the longest match in the filtered matrix for every column
        for column in filtered_matrix.columns:
            # Find the longest match in the column, ignoring NaN values
            longest_match = filtered_matrix[column].dropna().max()
            if longest_match is not None and longest_match != basename:

                if longest_match not in pools:
                    pools[longest_match] = []

                # Get all iids that have this longest match in the column
                matching_iids = filtered_matrix.index[
                    filtered_matrix[column].map(
                        lambda value: isinstance(value, str) and value.startswith(longest_match)
                    )
                ].tolist()

                matching_iids.append(column)

                pools[longest_match] = matching_iids

                # Update the inverted pool
                for iid in matching_iids:
                    if iid not in inverted_pools:
                        inverted_pools[iid] = []
                    inverted_pools[iid].append(longest_match)

            else:
                if DEBUG: print(f"No valid match found for column {column}. Longest match is {longest_match}. Basename is {basename}")
                name_of_col = db.browser_saves[column]["filename"]
                pools[name_of_col] = [column]
                if column not in inverted_pools:
                    inverted_pools[column] = [name_of_col]

        # Check whether every iid only has one pool, otherwise there is probably a larger pool that contains more values and this is just a fragment from naming
        for iid in inverted_pools:
            if len(inverted_pools[iid]) > 1:
                # First check whether the additional pool even exists still in pools
                pools_to_remove = [pool for pool in inverted_pools[iid] if pool not in pools]

                for pool in pools_to_remove:
                    inverted_pools[iid].remove(pool)

                if len(inverted_pools[iid]) == 1:
                    if DEBUG: print("Only one pool left, continuing")
                    continue
                
                if DEBUG: print(f"Warning: iid {iid} belongs to multiple pools: {inverted_pools[iid]}. This may indicate an artifact in the name similarity matching.")

                # Check which of the pools has more items and only keep that one
                largest_pool = max(inverted_pools[iid], key=lambda pool: len(pools[pool]))

                # Go through all pools that this iid belongs to and remove the smaller ones
                for pool in inverted_pools[iid]:
                    if pool != largest_pool and pool in pools:
                        pools.pop(pool)
                        if DEBUG: print(f"Removing pool {pool} due to the existance of a larger pool {largest_pool}.")

                # Update the parents accordingly
                for iid in pools[largest_pool]:
                    cp.multiplot_data[iid]["parent"] = largest_pool

            # If there is only one item in the pool, update the parent accordingly, if parent is still None or the parent is not the same as the pool name, then update it to be the pool name
            else:
                cp.multiplot_data[iid]["parent"] = inverted_pools[iid][0]
                
        return pools

    def check_matrix_for_basename(self, matrix):

        matches = matrix.stack()
        matches = matches[matches.map(lambda value: isinstance(value, str) and bool(value))]

        if matches.empty:
            return matrix
        
        unique_matches = list(dict.fromkeys(matches))

        containment_matrix = pd.DataFrame(
            [[unique_match in match for match in matches]
                for unique_match in unique_matches],
            index=unique_matches,
            columns=matches.tolist(),
            dtype=bool,
        )

        stackable_matrix = containment_matrix.copy()
        stackable_matrix.columns = range(len(matches))
        true_counts = stackable_matrix.stack().groupby(level=0).sum()
        basename = true_counts.idxmax()
        
        return basename

    def update_edited_last(self, MultiPlot=False):

        # Remove tag edited_last for all items with that tag just to be sure

        for browser in [self.browser, self.multiplot_browser]:

            edited_last = browser.tag_has("edited_last")

            for edited_iid in edited_last:
                current_tags = list(browser.item(edited_iid, "tags"))

                # Remove edited_last if in tags
                if "edited_last" in current_tags: current_tags.remove("edited_last")

                # Update the item
                browser.item(edited_iid, tags=tuple(current_tags))

                # Update the saves of that item as well
                edited_item_index = browser.treeview_saves["widgets"].index(edited_iid)
                browser.treeview_saves["tags"][edited_item_index] = tuple(current_tags)
        
        if MultiPlot:
            browser = self.multiplot_browser
        else:
            browser = self.browser

        current_tags = list(browser.item(self.iid, "tags"))

        # Add edited_last
        current_tags.append("edited_last")

        # Update the item
        browser.item(self.iid, tags=tuple(current_tags))

        index = browser.treeview_saves["widgets"].index(self.iid)   

        # Update the tags in the saves
        browser.treeview_saves["tags"][index] = tuple(current_tags)

        # Save the treeview_saves
        browser.save()

    def get_plot_data(self, iid):

        if db.load(iid):
            return db.save_data[iid]
        else:
            return None

    def get_multiplot_data(self, iid):

        if db.load(iid, True):
            return db.multiplot_save_data[iid]
        else:
            return None
        
    def bind_controls(self):
        self.bind("<Control-n>", self.new_project)
        self.bind("<Control-o>", self.open_files)
        self.bind("<Control-Shift-N>", self.new_multiplot)
        self.bind("<Control-s>", self.save_current_img)

        if str(self.notebook.select()) == str(self.notebook_frame1):
            self.bind("<F2>", self.browser.rename)
            self.bind("<Control-b>", lambda e: self.get_blank(selection=self.browser.selection()))

        elif str(self.notebook.select()) == str(self.notebook_frame2):
            self.bind("<F2>", self.multiplot_browser.rename)

    def unbind_controls(self):
        self.unbind("<Control-n>")
        self.unbind("<Control-o>")
        self.unbind("<Control-Shift-N>")
        self.unbind("<F2>")
        self.unbind("<Control-b>")
        self.unbind("<Control-s>")

    def __init_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook_frame1 = ttk.Frame(self.notebook)
        self.notebook_frame2 = ttk.Frame(self.notebook)
        self.notebook_frame1.pack(fill="both", expand = True)
        self.notebook_frame2.pack(fill="both", expand = True)
        self.notebook.add(self.notebook_frame1, text="Experimental Files")
        self.notebook.add(self.notebook_frame2, text="MultiPlots / Assays")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        
    def on_tab_change(self, event):
        
        self.unbind("<F2>")
        self.unbind("<Control-b>")

        if str(self.notebook.select()) == str(self.notebook_frame1):
            self.bind("<F2>", self.browser.rename)
            self.bind("<Control-b>", lambda e: self.get_blank(selection=self.browser.selection()))

        elif str(self.notebook.select()) == str(self.notebook_frame2):
            self.bind("<F2>", self.multiplot_browser.rename)

    def __init_browser(self):
        # Insert Treeview to manage files
        columns = ("Plottype")
        self.browser = BrowserTreeview(self.notebook_frame1, self, columns=columns)

        self.browser.heading("#0", text="Files")
        self.browser.column("#0", width=self._tk_font.measure("Files")*9+4, minwidth=self._tk_font.measure("Files"), stretch=False)

        item_width = self._tk_font.measure("Plottype")
        self.browser.heading("Plottype", text="Plottype")
        self.browser.column("Plottype", width=item_width*2, minwidth=item_width+2, stretch=False, anchor=tk.CENTER)

        self.browser.scrollbar = ttk.Scrollbar(self.notebook_frame1, orient=tk.VERTICAL, command=self.browser.yview)
        self.browser.configure(yscroll=self.browser.scrollbar.set)

        # Validate Command for Searchbar
        search_browser = (self.register(lambda value: self.search("browser",value)))

        # Searchbar
        self.browser.searchbar_frame = ttk.Frame(self.notebook_frame1)
        ttk.Label(self.browser.searchbar_frame, text=search_icon, font=("TkDefaultFont",12)).pack(side="left", fill="y")

        self.browser.searchbar = ttk.Entry(self.browser.searchbar_frame, validate="key", validatecommand=(search_browser, "%P"), foreground="gray")
        self.browser.searchbar.insert(0, "Search...")
        self.browser.searchbar.pack(side="left", fill="x", expand=True)

        self.browser.searchbar.bind("<FocusIn>", self.remove_search_placeholder)
        self.browser.searchbar.bind("<FocusOut>", self.add_search_placeholder)
        
        self.browser.searchbar_frame.pack(side="top", fill="x")
        
        self.browser.pack(side="left", fill="both", expand=True)

        self.browser.scrollbar.pack(side="right", fill="y", expand=True)

    def __init_multiplot_browser(self):
        # Insert Treeview to manage files
        columns = ("Plottype")

        self.multiplot_browser = MultiPlotTreeview(self.notebook_frame2, self, columns=columns)

        self.multiplot_browser.heading("#0", text="Files")
        self.multiplot_browser.column("#0", width=self._tk_font.measure("Files")*9+4, minwidth=self._tk_font.measure("Files"), stretch=False)

        item_width = self._tk_font.measure("Plottype")
        self.multiplot_browser.heading("Plottype", text="Plottype")
        self.multiplot_browser.column("Plottype", width=item_width*2, minwidth=item_width+2, stretch=False, anchor=tk.CENTER)

        self.multiplot_browser.scrollbar = ttk.Scrollbar(self.notebook_frame2, orient=tk.VERTICAL, command=self.multiplot_browser.yview)
        self.multiplot_browser.configure(yscroll=self.multiplot_browser.scrollbar.set)

        # Validate Command for Searchbar
        search_browser = (self.register(lambda value: self.search("multiplot_browser",value)))

        # Searchbar
        self.multiplot_browser.searchbar_frame = ttk.Frame(self.notebook_frame2)
        ttk.Label(self.multiplot_browser.searchbar_frame, text=search_icon, font=("TkDefaultFont",12)).pack(side="left", fill="y")
        
        self.multiplot_browser.searchbar = ttk.Entry(self.multiplot_browser.searchbar_frame, validate="key", validatecommand=(search_browser, "%P"), foreground="gray")
        self.multiplot_browser.searchbar.insert(0, "Search...")
        self.multiplot_browser.searchbar.pack(side="top", fill="x", expand=True)

        self.multiplot_browser.searchbar.bind("<FocusIn>", self.remove_search_placeholder)
        self.multiplot_browser.searchbar.bind("<FocusOut>", self.add_search_placeholder)

        self.multiplot_browser.searchbar_frame.pack(side="top", fill="x")

        self.multiplot_browser.pack(side="left", fill="both", expand=True)
        
        self.multiplot_browser.scrollbar.pack(side="right", fill="y", expand=True)

    def add_search_placeholder(self, event):
        
        entry = event.widget

        if not entry.get():

            entry.insert(0, "Search...")
            entry.configure(foreground="gray", background="gray")

    def remove_search_placeholder(self, event):
        
        entry = event.widget

        if entry.get() == "Search...":

            entry.delete(0, tk.END)
            color = "white" if self._dark else "black"
            entry.configure(foreground=color)

    def search(self, browser_type, value):
        if browser_type == "browser":
            browser = self.browser
        elif browser_type == "multiplot_browser":
            browser = self.multiplot_browser

        # Get the current selection of the browser
        current_selection = browser.selection()

        if value == "Search...": return True

        if value == "":

            # If all values already exist in the browser, don't load it again
            if all(browser.exists(i) for i in browser.treeview_saves["widgets"]):
                return True
            
            browser.delete(*browser.get_children())
            browser.insert_all()

            if (browser_type == "multiplot_browser" and self.plottype in ["Assay", "MultiPlot"]) or (browser_type == "browser" and self.plottype not in ["Assay", "MultiPlot"]):
                try:
                    browser.see(self.iid)
                except:
                    pass
        
        else:
            browser.delete(*browser.get_children())

            def insert_children(iid):

                count = browser.treeview_saves["widgets"].index(iid)

                children = browser.treeview_saves["children"][count]

                for child in children:
                    child_count = browser.treeview_saves["widgets"].index(child)
                    if not browser.exists(child):
                        browser.insert(iid,
                                       browser.treeview_saves["indices"][child_count],
                                       iid=child,
                                       text=browser.treeview_saves["text"][child_count],
                                       values=browser.treeview_saves["values"][child_count],
                                       tags = browser.treeview_saves["tags"][child_count])

                    # Recursively call this function to insert all children
                    insert_children(child)

            for count, iid in enumerate(browser.treeview_saves["widgets"]):

                if value.lower() in browser.treeview_saves["text"][count].lower() or (len(browser.treeview_saves["values"][count]) > 0 and value.lower() in browser.treeview_saves["values"][count][0].lower()):
                    
                    if not browser.exists(iid):
                        browser.insert("",
                                       tk.END,
                                       iid = iid, 
                                       text = browser.treeview_saves["text"][count], 
                                       values = browser.treeview_saves["values"][count], 
                                       tags = browser.treeview_saves["tags"][count])
                    else:
                        browser.see(iid)
                    
                    insert_children(iid)

            browser.yview_moveto(0)


        
        # Select the same plots if possible
        for iid in current_selection:
            if browser.exists(iid):
                browser.selection_add(iid)
                browser.see(iid)


        return True
            
    def init_plotinfo(self, plottype):
        if self.plotinfo_initialized:
            for widget in self.plotinfo_frame.winfo_children():
                widget.destroy()
        else:
            self.plotinfo_frame = ttk.Frame(self)

        if plottype == "HPLC":
            # If plottype is HPLC, initiate a table with the following columns
            columns = ("X1", "X2", "Center", "Area", "Percentage", "Include?")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="integrals", columns=columns, show="headings", height=10)
            for head in columns:
                self.plotinfo.heading(head, text=head)
                self.plotinfo.column(head, width=self._tk_font.measure(head), minwidth=self._tk_font.measure(head))
            
        elif plottype == "MALDI":
            # If plottype is MALDI then initiate a table with a list of the peaks and the ability to give a suspected Formula
            columns = ("Peak", "Label", "Suspected Molecular Formula", "Monoisotopic Mass [Da]", "Charge", "Simulate?", "Intensity [%]", "FWHM")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="peaks", columns=columns, show="headings", height=10)
            for head in columns:
                self.plotinfo.heading(head, text=head)

            self.plotinfo.column("Peak", width=self._tk_font.measure("Peak"), minwidth=self._tk_font.measure("Peak"))
            self.plotinfo.column("Label", width=self._tk_font.measure("Label")*3, minwidth=self._tk_font.measure("Label"))
            self.plotinfo.column("Suspected Molecular Formula", width=self._tk_font.measure("Suspected Molecular Formula"), minwidth=self._tk_font.measure("Suspected"))
            self.plotinfo.column("Monoisotopic Mass [Da]", width=self._tk_font.measure("Monoisotopic Mass [Da]"), minwidth=self._tk_font.measure("Mass"))
            self.plotinfo.column("Charge", width=self._tk_font.measure("Charge"), minwidth=self._tk_font.measure("Charg"))
            self.plotinfo.column("Simulate?", width=self._tk_font.measure("Simulate?"), minwidth=self._tk_font.measure("Simulate?"))
            self.plotinfo.column("Intensity [%]", width=self._tk_font.measure("Intensity [%]"), minwidth=self._tk_font.measure("Intens"))
            self.plotinfo.column("FWHM", width=self._tk_font.measure("FWHM"), minwidth=self._tk_font.measure("FWHM"))

        elif plottype == "Tm":
            # If plottype is Tm, initiate a table with the following columns
            columns = ("Curve Fit Model", "A", "B", "R²", "ΔH [kJ/mol]", "Tm [°C]")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="Tm", columns=columns, show="headings", height=10)
            for head in columns:
                self.plotinfo.heading(head, text=head)
                self.plotinfo.column(head, width=self._tk_font.measure(head), minwidth=self._tk_font.measure(head))

        elif plottype == "MultiPlot":
            # If plottype is MultiPlot, initiate a table that keeps information on the inserted plots
            columns = ("Label", "Linewidth", "Linestyle", "Alpha", "Position")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="multiplot", columns=columns, height=10)
            self.plotinfo.heading("#0", text="Files")
            self.plotinfo.column("#0", width=self._tk_font.measure("Files"), minwidth=self._tk_font.measure("Files"))

            for head in columns:
                self.plotinfo.heading(head, text=head)
                self.plotinfo.column(head, width=self._tk_font.measure(head), minwidth=self._tk_font.measure(head))

        elif plottype == "Assay":
            # If plottype is Assay, initiate a table that keeps information on the inserted plots
            columns = ("Filename", "x-Coordinate", "y-Coordinate", "R²", "Relative Nonlinearity")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="assay", columns=columns, height=10)
            self.plotinfo.heading("#0", text="Datapoint")
            self.plotinfo.column("#0", width=self._tk_font.measure("Datapoint"), minwidth=self._tk_font.measure("Datapoint"))

            for head in columns:
                self.plotinfo.heading(head, text=head)
                self.plotinfo.column(head, width=self._tk_font.measure(head), minwidth=self._tk_font.measure(head))

        elif plottype in ["Fluorescence", "UV/vis"]:
            columns = ("Peak", "Label")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="peaks", columns=columns, show="headings", height=10)
            for head in columns:
                self.plotinfo.heading(head, text=head)
            
        else:
            # If plottype is CD or anything else, initiate a table with the following columns
            columns = ("", "", "", "", "", "")

            self.plotinfo = TreeviewEdit(self.plotinfo_frame, self, treetype="CD", columns=columns, show="headings", height=10)
            for head in columns:
                self.plotinfo.heading(head, text=head)
                self.plotinfo.column(head, width=self._tk_font.measure(head), minwidth=self._tk_font.measure(head))

        self.plotinfo.scrollbar = ttk.Scrollbar(self.plotinfo_frame, orient=tk.VERTICAL, command=self.plotinfo.yview)
        self.plotinfo.configure(yscroll=self.plotinfo.scrollbar.set)
        
        self.plotinfo_initialized = True

        self.plotinfo.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.plotinfo.scrollbar.pack(side=tk.LEFT, expand=False, fill=tk.Y)

        self.plotinfo_frame.grid(column=3, row=5, columnspan=3, sticky=tk.NSEW)
            
    def _capture_plotprops_state(self):
        state = {
            "widget_function_dict": self.widget_function_dict,
            "plotprops_widgets": self.plotprops_widgets,
            "inset_widgets": getattr(self, "inset_widgets", None),
        }

        def belongs_to_plotprops(widget):
            current = widget
            try:
                while current is not None:
                    if current == self.plotprops:
                        return True
                    parent = current.winfo_parent()
                    if not parent:
                        return False
                    current = self.nametowidget(parent)
            except tk.TclError:
                return False
            return False

        for name, value in self.__dict__.items():
            if isinstance(value, tk.Misc) and belongs_to_plotprops(value):
                state[name] = value
            elif isinstance(value, tk.Image) and name.endswith("_image"):
                state[name] = value
        return state

    def _restore_plotprops_state(self, state):
        for name, value in state.items():
            setattr(self, name, value)

    def init_plotprops(self, plottype):
        if DEBUG: print(f"Current plotprops frames: {self.plotprops_frames}")
        if DEBUG: print(f"Plottype to initialize for plotprops: {plottype}")

        # Only one cached plot-properties frame may be visible at a time.
        for frame in self.plotprops_frames.values():
            if frame.winfo_manager() == "grid":
                frame.grid_remove()

        if plottype in self.plotprops_frames:
            if DEBUG: print("Reusing plot properties for", plottype)
            self._restore_plotprops_state(self.plotprops_states[plottype])
            self.plotprops = self.plotprops_frames[plottype]
            self.plotprops.grid(row=0, column=0, sticky=tk.NSEW)
            self.plotprops_sf.grid(column=5, row=1, rowspan=2, sticky=tk.NSEW)
            self.export_button.grid(column=5, row=3, sticky="esw")
            self.plotprops_initialized = True
            self.after_idle(self._update_plotprops_width)
            return

        if not hasattr(self, "plotprops_sf"):
            self.plotprops_sf = scrolled.ScrolledFrame(self, auto_hide=False)

            def update_plotprops_scrollbar(event=None):
                if self._plotprops_scrollbar_update_id is not None:
                    return

                def apply_visibility():
                    self._plotprops_scrollbar_update_id = None
                    try:
                        first, last = self.plotprops_sf.yview()
                        if last - first >= 0.999999:
                            self.plotprops_sf.hide_scrollbars()
                        else:
                            self.plotprops_sf.show_scrollbars()
                    except tk.TclError:
                        pass

                self._plotprops_scrollbar_update_id = self.after_idle(apply_visibility)

            self.plotprops_sf.bind("<Configure>", update_plotprops_scrollbar, "+")
            self.plotprops_sf.bind("<Map>", update_plotprops_scrollbar, "+")
            self.plotprops_sf.bind("<Map>", self._schedule_plotprops_width, "+")
            self.plotprops_sf.columnconfigure(0, weight=1)

        self.plotprops = ttk.Frame(self.plotprops_sf)
        self.plotprops.configure(padding=(8, 4))
        self.plotprops.columnconfigure(1, weight=1)
        self.plotprops.columnconfigure(3, weight=1)
        self.plotprops_frames[plottype] = self.plotprops

        if DEBUG: print(f"Updated plotprops_frames: {self.plotprops_frames}")

        self.widget_function_dict = {}

        # Count Rows
        row = 0

        # Validate Command for Entries
        vcmd_float = (self.register(self.validate_floats))
        vcmd_int = (self.register(self.validate_integers))

        # Create Label that shows the current Graph that is being worked on
        self.datakey_label = ttk.Label(self.plotprops, text="", font=("TkDefaultFont",18,"bold"), anchor="center")
        self.datakey_label.grid(column=0, columnspan=4, row=row)

        # Next row
        row += 1

        self.project_name = ttk.Label(self.plotprops, text="", font=("TkDefaultFont",11, "italic"))
        self.project_name.grid(column=0, columnspan=4, row=row)
        
        
        # Next row
        row += 1

        # Add a collapsible Frame for all Plot Settings
        self.plot_settings_cf = CollapsibleFrame(self.plotprops, text="Plot Settings")
        self.plot_settings_cf.expand()
        self.plot_settings_cf.grid(column=0, columnspan=4, row=row, sticky=tk.NSEW)

        # Plot_settings row
        plot_settings_row = 0

        # Entry for x-Axis from- & to- values
        ttk.Label(self.plot_settings_cf.content, text="Span of x-Axis:").grid(column=0, row=plot_settings_row, sticky=tk.W)
        self.xlim_min_entry = ttk.Entry(self.plot_settings_cf.content, textvariable = self.xlim_min, validate="key", validatecommand=(vcmd_float, "%P"))
        self.xlim_min_entry.grid(column=1, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.xlim_min_entry] = self.update_xlim

        ttk.Label(self.plot_settings_cf.content, text="-").grid(column=2, row=plot_settings_row, sticky=tk.E)
        self.xlim_max_entry = ttk.Entry(self.plot_settings_cf.content, textvariable = self.xlim_max, validate="key", validatecommand=(vcmd_float, "%P"))
        self.xlim_max_entry.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.xlim_max_entry] = self.update_xlim

        # Next row
        plot_settings_row += 1

        # Checkbox for whether to automatically adjust y-axis
        ttk.Label(self.plot_settings_cf.content, text="Auto-adjust y-Axis:").grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
        self.adjust_y_axis_checkbox = ttk.Checkbutton(self.plot_settings_cf.content, text="", command=self.autoadjust_y, variable=self.adjust_y, onvalue=True, offvalue=False)
        self.adjust_y_axis_checkbox.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

        # Set color_btn size to an emperical value that scales as well based on the tk_scaling
        color_btn_size = ceil(2**(1/2) * 10 * self.scaling)

        # Next row
        plot_settings_row += 1

        # Entry for y-Axis from- & to- values
        ttk.Label(self.plot_settings_cf.content, text="Span of y-Axis:").grid(column=0, row=plot_settings_row, sticky=tk.W)
        self.ylim_min_entry = ttk.Entry(self.plot_settings_cf.content, textvariable = self.ylim_min, validate="key", validatecommand=(vcmd_float, "%P"))
        self.ylim_min_entry.grid(column=1, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.ylim_min_entry] = self.update_ylim

        ttk.Label(self.plot_settings_cf.content, text="-").grid(column=2, row=plot_settings_row, sticky=tk.E)
        self.ylim_max_entry = ttk.Entry(self.plot_settings_cf.content, textvariable = self.ylim_max, validate="key", validatecommand=(vcmd_float, "%P"))
        self.ylim_max_entry.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.ylim_max_entry] = self.update_ylim

        # Next row
        plot_settings_row += 1

        if plottype != "MultiPlot":

            if plottype != "Assay":
                # Linestyle Combobox
                ttk.Label(self.plot_settings_cf.content, text="Linestyle:").grid(column=0, row=plot_settings_row, sticky=tk.W)
                self.linestyle_combobox = ttk.Combobox(self.plot_settings_cf.content, textvariable=self.linestyle, state="normal", values=["solid","dashed","dashdot","dotted","none"])
                self.linestyle_combobox.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
                self.linestyle_combobox.bind("<<ComboboxSelected>>", self.update_linestyle)
                self.widget_function_dict[self.linestyle_combobox] = self.update_linestyle

                # Next row
                plot_settings_row += 1

            # Color picker
            ttk.Label(self.plot_settings_cf.content, text="Color:").grid(column=0, row=plot_settings_row, sticky=tk.W)
            self.color_image = self.create_color_image(size=color_btn_size, color=self.color)
            self.color_btn = tk.Label(self.plot_settings_cf.content,
                                      image=self.color_image,
                                      bd=0,
                                      highlightthickness=0,
                                      cursor="hand2")
            self.color_btn.grid(column=3, row=plot_settings_row, sticky=tk.E, padx=(0, 13), pady=self.widget_pady)
            self.color_btn.bind("<Button-1>", self.choose_color)

            # Next row
            plot_settings_row += 1

            if plottype != "Assay":
            
                # Checkbox for Vertical Labels:
                self.vlabel_label = ttk.Label(self.plot_settings_cf.content, text="Vertical Labels:")
                self.vlabel_label.grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
                self.vlabel_checkbox = ttk.Checkbutton(self.plot_settings_cf.content, text="", command=self.update_labels, variable=self.vlabels, onvalue="vertical", offvalue="horizontal")
                self.vlabel_checkbox.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

                # Next row
                plot_settings_row += 1

                baseline_smoothing_methods = ["None", "Savitzky-Golay", "Whittaker", "FIR low-pass filtering", "Wavelet filtering", "Sparsity-assisted signal smoothing"]

                # Combobox for Baseline Smoothing Method
                ttk.Label(self.plot_settings_cf.content, text="Baseline Smoothing:").grid(column=0, row=plot_settings_row, sticky=tk.W)
                self.baseline_smoothing_combobox = ttk.Combobox(self.plot_settings_cf.content, textvariable=self.smoothing_method, state="readonly", values=baseline_smoothing_methods)
                self.baseline_smoothing_combobox.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
                self.baseline_smoothing_combobox.bind("<<ComboboxSelected>>", self.update_baseline_smoothing)

                # Next row
                plot_settings_row += 1

                background_correction_methods = ["None", "asLS", "airPLS", "arPLS", "Mixture model", "Backcor", "Local minimum values"]

                # Combobox for Baseline Correction Method
                ttk.Label(self.plot_settings_cf.content, text="Baseline Correction:").grid(column=0, row=plot_settings_row, sticky=tk.W)
                self.background_correction_combobox = ttk.Combobox(self.plot_settings_cf.content, textvariable=self.background_correction_method, state="readonly", values=background_correction_methods)
                self.background_correction_combobox.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)
                self.background_correction_combobox.bind("<<ComboboxSelected>>", self.update_background_correction)

                # Next row
                plot_settings_row += 1

            if plottype == "Kinetics":

                ttk.Label(self.plot_settings_cf.content, text="x-Axis Label:").grid(column=0, row=plot_settings_row, sticky=tk.W)
                self.kinetics_x_label_entry = ttk.Entry(self.plot_settings_cf.content, textvariable=self.kinetics_x_label, width=self.control_widths["long_entry"])
                self.kinetics_x_label_entry.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.EW, pady=self.widget_pady)
                self.widget_function_dict[self.kinetics_x_label_entry] = self.update_axis_labels

                # Next row
                plot_settings_row += 1

                ttk.Label(self.plot_settings_cf.content, text="y-Axis Label:").grid(column=0, row=plot_settings_row, sticky=tk.W)
                self.kinetics_y_label_entry = ttk.Entry(self.plot_settings_cf.content, textvariable=self.kinetics_y_label, width=self.control_widths["long_entry"])
                self.kinetics_y_label_entry.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.EW, pady=self.widget_pady)
                self.widget_function_dict[self.kinetics_y_label_entry] = self.update_axis_labels

                # Next row
                plot_settings_row += 1

        else:

            # Checkbox für Min-Max-Normalisierung
            ttk.Label(self.plot_settings_cf.content, text="Min-Max Normalization:").grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
            self.multiplot_normalization_checkbox = ttk.Checkbutton(self.plot_settings_cf.content, text="", command=self.update_multiplot_lines, variable=self.multiplot_normalization, onvalue=True, offvalue=False)
            self.multiplot_normalization_checkbox.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            plot_settings_row += 1

            # Checkbox for Offsetting Plots
            ttk.Label(self.plot_settings_cf.content, text="Offset Plots:").grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
            self.multiplot_plot_offset_checkbox = ttk.Checkbutton(self.plot_settings_cf.content, text="", command=self.update_multiplot_lines, variable=self.multiplot_plot_offset, onvalue=True, offvalue=False)
            self.multiplot_plot_offset_checkbox.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            plot_settings_row += 1

            # Combobox for label handling
            ttk.Label(self.plot_settings_cf.content, text="Labels:").grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
            self.multiplot_labels_combobox = ttk.Combobox(self.plot_settings_cf.content, textvariable=self.multiplot_labels, state="readonly", values=["In Axes", "In Legend", "Hide"])
            self.multiplot_labels_combobox.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            plot_settings_row += 1

            # Combobox for Colormaps
            colormaps = list(mpl.colormaps)
            colormaps.sort()
            ttk.Label(self.plot_settings_cf.content, text="Apply Colormap:").grid(column=0, columnspan=1, row=plot_settings_row, sticky=tk.W)
            self.multiplot_colormap_combobox = ttk.Combobox(self.plot_settings_cf.content, textvariable=self.multiplot_colormap, state="readonly", values=colormaps)
            self.multiplot_colormap_combobox.grid(column=1, columnspan=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            plot_settings_row += 1

            # Checkbox for 3D plots
            ttk.Label(self.plot_settings_cf.content, text="3D Multiplot:").grid(column=0, columnspan=2, row=plot_settings_row, sticky=tk.W)
            self.multiplot_3D_checkbox = ttk.Checkbutton(self.plot_settings_cf.content, text="", command=self.refresh, variable=self.multiplot_3D, onvalue=True, offvalue=False)
            self.multiplot_3D_checkbox.grid(column=3, row=plot_settings_row, sticky=tk.E, pady=self.widget_pady)

        # Next row
        row += 1

        # Collapsible Frame
        self.tick_settings_frame = CollapsibleFrame(self.plotprops, text="Tick Settings")
        self.tick_settings_frame.grid(column=0, columnspan= 4, row=row, sticky=tk.EW)

        tick_settings_row = 0

        # Checkbox for xticks
        ttk.Label(self.tick_settings_frame.content, text="Show Ticks on x-Axis:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.show_x_ticks_checkbox = ttk.Checkbutton(self.tick_settings_frame.content, text="", command=self.refresh, variable=self.show_xticks, onvalue=True, offvalue=False)
        self.show_x_ticks_checkbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)

        tick_settings_row += 1

        # Spinbox for distance of major ticks
        ttk.Label(self.tick_settings_frame.content, text="Distance of Major x-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.major_xtick_distance_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=1, to=np.inf, textvariable=self.distance_xticks, validate="key", validatecommand=(vcmd_float, "%P"), command=self.update_ticks)
        self.major_xtick_distance_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.major_xtick_distance_spinbox] = self.update_ticks

        tick_settings_row += 1

        # Spinbox for offset of major ticks
        ttk.Label(self.tick_settings_frame.content, text="Offset of Major x-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.major_xtick_offset_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=0, to=np.inf, textvariable=self.offset_xticks, validate="key", validatecommand=(vcmd_float, "%P"), command=self.update_ticks)
        self.major_xtick_offset_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.major_xtick_offset_spinbox] = self.update_ticks

        tick_settings_row += 1

        # Spinbox for minor ticks
        ttk.Label(self.tick_settings_frame.content, text="Number of Minor x-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.minor_xtick_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=0, to=np.inf, textvariable=self.num_minor_xticks, validate="key", validatecommand=(vcmd_int, "%P"), command=self.update_ticks)
        self.minor_xtick_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.minor_xtick_spinbox] = self.update_ticks

        tick_settings_row += 1

        # Checkbox for yticks
        ttk.Label(self.tick_settings_frame.content, text="Show Ticks on y-Axis:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.show_y_ticks_checkbox = ttk.Checkbutton(self.tick_settings_frame.content, text="", command=self.refresh, variable=self.show_yticks, onvalue=True, offvalue=False)
        self.show_y_ticks_checkbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)

        tick_settings_row += 1

        # Spinbox for distance of major ticks
        ttk.Label(self.tick_settings_frame.content, text="Distance of Major y-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.major_ytick_distance_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=1, to=np.inf, textvariable=self.distance_yticks, validate="key", validatecommand=(vcmd_float, "%P"), command=self.update_ticks)
        self.major_ytick_distance_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.major_ytick_distance_spinbox] = self.update_ticks

        tick_settings_row += 1

        # Spinbox for offset of major ticks
        ttk.Label(self.tick_settings_frame.content, text="Offset of Major y-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.major_ytick_offset_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=0, to=np.inf, textvariable=self.offset_yticks, validate="key", validatecommand=(vcmd_float, "%P"), command=self.update_ticks)
        self.major_ytick_offset_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.major_ytick_offset_spinbox] = self.update_ticks

        tick_settings_row += 1

        # Spinbox for minor ticks
        ttk.Label(self.tick_settings_frame.content, text="Number of Minor y-Ticks:").grid(column=0, row=tick_settings_row, sticky=tk.W)
        self.minor_ytick_spinbox = ttk.Spinbox(self.tick_settings_frame.content, from_=0, to=np.inf, textvariable=self.num_minor_yticks, validate="key", validatecommand=(vcmd_int, "%P"), command=self.update_ticks)
        self.minor_ytick_spinbox.grid(column=1, row=tick_settings_row, sticky=tk.E, pady=self.widget_pady)
        self.widget_function_dict[self.minor_ytick_spinbox] = self.update_ticks

        if plottype == "MultiPlot":

            # Next row
            row += 1

            # CollapsibleFrame for Label Settings
            self.multiplot_label_settings_frame = CollapsibleFrame(self.plotprops, text="Label Settings")
            self.multiplot_label_settings_frame.grid(column=0, columnspan= 4, row=row, sticky=tk.EW)

            settings_row = 0
            
            # Checkbox for automatic legend placement
            ttk.Label(self.multiplot_label_settings_frame.content, text="Automatically Place Legend:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_legend_automatic_placement_checkbox = ttk.Checkbutton(self.multiplot_label_settings_frame.content, text="", command=self.update_multiplot_legend_placement, variable=self.multiplot_legend_automatic_placement, onvalue=True, offvalue=False)
            self.multiplot_legend_automatic_placement_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Slider for  legend trancparency
            ttk.Label(self.multiplot_label_settings_frame.content, text="Legend Transparency:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_legend_transparency_entry = ttk.Entry(self.multiplot_label_settings_frame.content, textvariable=self.multiplot_legend_transparency, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_legend_transparency_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.multiplot_legend_transparency_entry] = self.update_multiplot_legend

            # Next settings_row
            settings_row += 1
            
            self.multiplot_legend_transparency_slider = ttk.Scale(self.multiplot_label_settings_frame.content, from_=0, to=1, orient="horizontal", variable=self.multiplot_legend_transparency, state="disabled", command=self.update_multiplot_legend)
            self.multiplot_legend_transparency_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Checkbox for matching color in plot
            ttk.Label(self.multiplot_label_settings_frame.content, text="Match Color:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_label_match_color_checkbox = ttk.Checkbutton(self.multiplot_label_settings_frame.content, text="", command=self.update_multiplot_label_color, variable=self.multiplot_label_match_color, onvalue=True, offvalue=False)
            self.multiplot_label_match_color_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Slider for label xposition
            ttk.Label(self.multiplot_label_settings_frame.content, text="x-Position:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_label_xposition_entry = ttk.Entry(self.multiplot_label_settings_frame.content, textvariable=self.multiplot_label_xposition, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_label_xposition_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.multiplot_label_xposition_entry] = self.update_multiplot_label_xposition

            # Next settings_row
            settings_row += 1
            
            self.multiplot_label_xposition_slider = ttk.Scale(self.multiplot_label_settings_frame.content, from_=0, to=1, orient="horizontal", 
                                                              variable=self.multiplot_label_xposition, state="disabled", command=self.update_multiplot_label_xposition)
            self.multiplot_label_xposition_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Slider for label yposition
            ttk.Label(self.multiplot_label_settings_frame.content, text="y-Position:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_label_yposition_entry = ttk.Entry(self.multiplot_label_settings_frame.content, textvariable=self.multiplot_label_yposition, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_label_yposition_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.multiplot_label_yposition_entry] = self.update_multiplot_label_yposition

            # Next settings_row
            settings_row += 1
            
            self.multiplot_label_yposition_slider = ttk.Scale(self.multiplot_label_settings_frame.content, from_=0, to=1, orient="horizontal", 
                                                              variable=self.multiplot_label_yposition, state="disabled", command=self.update_multiplot_label_yposition)
            self.multiplot_label_yposition_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Spinbox for fontsize
            ttk.Label(self.multiplot_label_settings_frame.content, text="Fontsize:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_label_fontsize_spinbox = ttk.Spinbox(self.multiplot_label_settings_frame.content, from_=1, to=np.inf, textvariable=self.multiplot_label_fontsize, command=self.update_multiplot_label_fontsize)
            self.multiplot_label_fontsize_spinbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.multiplot_label_fontsize_spinbox] = self.update_multiplot_label_fontsize

            # Next row
            row += 1

            # CollapsibleFrame for 3D plots
            self.multiplot_3D_settings_frame = CollapsibleFrame(self.plotprops, text="3D Plot Settings")
            self.multiplot_3D_settings_frame.grid(column=0, columnspan= 4, row=row, sticky=tk.EW)
            self.multiplot_3D_settings_frame.expand()

            settings_row = 0

            # Slider for elevation
            ttk.Label(self.multiplot_3D_settings_frame.content, text="Elevation:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_elevation_entry = ttk.Entry(self.multiplot_3D_settings_frame.content, textvariable=self.multiplot_3D_elev, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_elevation_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1
            
            self.multiplot_elevation_slider = ttk.Scale(self.multiplot_3D_settings_frame.content, from_=-90, to=90, orient="horizontal", variable=self.multiplot_3D_elev, state="disabled", command=self.refresh)
            self.multiplot_elevation_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Slider for rotation
            ttk.Label(self.multiplot_3D_settings_frame.content, text="Azimuth:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_rotation_entry = ttk.Entry(self.multiplot_3D_settings_frame.content, textvariable=self.multiplot_3D_azim, width=5, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_rotation_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1
            
            self.multiplot_rotation_slider = ttk.Scale(self.multiplot_3D_settings_frame.content, from_=-90, to=90, orient="horizontal", variable=self.multiplot_3D_azim, state="disabled", command=self.refresh)
            self.multiplot_rotation_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Slider for offset
            ttk.Label(self.multiplot_3D_settings_frame.content, text="Offset of Plots:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_offset_entry = ttk.Entry(self.multiplot_3D_settings_frame.content, textvariable=self.multiplot_3D_offset, validate="key", validatecommand=(vcmd_float, "%P"), state="disabled")
            self.multiplot_offset_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1
            
            self.multiplot_offset_slider = ttk.Scale(self.multiplot_3D_settings_frame.content, from_=0, to=1, orient="horizontal", variable=self.multiplot_3D_offset, state="disabled", command=self.refresh)
            self.multiplot_offset_slider.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Combobox for perspective mode
            ttk.Label(self.multiplot_3D_settings_frame.content, text="Perspective Mode:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_perspective_combobox = ttk.Combobox(self.multiplot_3D_settings_frame.content, textvariable=self.multiplot_3D_projection_type, state="disabled", values=["Perspective", "Orthographic"])
            self.multiplot_perspective_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            row += 1

            # CollapsibleFrame for Fit Settings
            self.multiplot_fit_settings_frame = CollapsibleFrame(self.plotprops, text="Fit Settings")
            self.multiplot_fit_settings_frame.grid(column=0, columnspan= 4, row=row, sticky=tk.EW)

            settings_row = 0

            # Add a checkbox whether to show fit or not
            ttk.Label(self.multiplot_fit_settings_frame.content, text="Show Fit:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_tm_fit_checkbox = ttk.Checkbutton(self.multiplot_fit_settings_frame.content, text="", command=self.update_multiplot_fit, variable=self.multiplot_fit, onvalue=True, offvalue=False)
            self.show_tm_fit_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            # Combobox for fit type
            ttk.Label(self.multiplot_fit_settings_frame.content, text="Fit:").grid(column=0, row=settings_row, sticky=tk.W)
            self.multiplot_fit_combobox = ttk.Combobox(self.multiplot_fit_settings_frame.content, textvariable=self.multiplot_fit_type, state="readonly", width=self.control_widths["long_combobox"], values=["Sigmoidal + Constant Baseline",
                                                                                                                                                           "Sigmoidal + Linear Baseline",
                                                                                                                                                           "Van't Hoff Derivative",
                                                                                                                                                           "Empirical Gauss Derivative"])
            self.multiplot_fit_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            
            # Next settings_row
            settings_row += 1

            # Add a checkbox whether to show baselines or not
            ttk.Label(self.multiplot_fit_settings_frame.content, text="Show Baselines:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_tm_baselines_checkbox = ttk.Checkbutton(self.multiplot_fit_settings_frame.content, text="", command=self.update_multiplot_fit, variable=self.multiplot_show_tm_baselines, onvalue=True, offvalue=False)
            self.show_tm_baselines_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            row += 1
                    
        if plottype == "Assay":

            # Hide Checkbox for Vertical Labels:
            try:
                self.vlabel_checkbox.grid_remove()
                self.vlabel_label.grid_remove()
            except:
                pass

            # Next row
            row += 1

            # Add a collapsible Frame for all Assay Settings
            self.assay_settings_cf = CollapsibleFrame(self.plotprops, text="Assay Settings")
            self.assay_settings_cf.expand()
            self.assay_settings_cf.grid(column=0, columnspan=4, row=row, sticky=tk.NSEW)

            settings_row = 0

            # Create a combobox to pick the model for the fit of the assay
            ttk.Label(self.assay_settings_cf.content, text="Pick Assay:").grid(column=0, row=settings_row, sticky=tk.W)

            self.assay_type_combobox = ttk.Combobox(self.assay_settings_cf.content,
                                                     textvariable=self.assay_type, 
                                                     state="readonly", 
                                                     values=sorted(list(self.assaytypes)))
            self.assay_type_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.assay_type_combobox.bind("<<ComboboxSelected>>", self.update_assay_type)

            # Next settings_row
            settings_row += 1

            # Entry for Molar Absorption Coefficient
            ttk.Label(self.assay_settings_cf.content, text="Mol. Abs. Coefficient:").grid(column=0, row=settings_row, sticky=tk.W)
            self.assay_absorption_entry = ttk.Entry(self.assay_settings_cf.content, 
                                                    textvariable = self.assay_absorption_coefficient, 
                                                    validate="key", 
                                                    validatecommand=(vcmd_float, "%P"), 
                                                    width=self.control_widths["entry"]-len("M/cm"))
            
            self.assay_absorption_entry.grid(column=1, row=settings_row, sticky=tk.E, padx=self._tk_font.measure("M/cm")+6, pady=self.widget_pady)
            self.widget_function_dict[self.assay_absorption_entry] = self.update_assay_absorption_coefficient

            # Unit label
            ttk.Label(self.assay_settings_cf.content, text="M/cm").grid(column=1, row=settings_row, sticky=tk.E, padx=0)

            # Next settings_row
            settings_row += 1

            # Combobox for x-axis unit
            ttk.Label(self.assay_settings_cf.content, text="Unit on x-Axis:").grid(column=0, row=settings_row, sticky=tk.W)
            x_axis_units = ["M", "mM", "µM", "nM", "pM"]
            self.x_axis_unit_combobox = ttk.Combobox(self.assay_settings_cf.content,
                                                     textvariable=self.x_axis_unit,
                                                     state="readonly",
                                                     values=x_axis_units)
            self.x_axis_unit_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.x_axis_unit_combobox.bind("<<ComboboxSelected>>", self.update_x_axis_unit)

            # Next settings row
            settings_row += 1

            # Entry for label on x-axis
            ttk.Label(self.assay_settings_cf.content, text="x-Axis Label:").grid(column=0, row=settings_row, sticky=tk.W)
            self.x_axis_label_entry = ttk.Entry(self.assay_settings_cf.content, textvariable=self.x_axis_label, width=self.control_widths["long_entry"])
            self.x_axis_label_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.x_axis_label_entry] = self.update_axis_labels

            # Next settings row
            settings_row += 1

            # Combobox for y-axis unit
            ttk.Label(self.assay_settings_cf.content, text="Unit on y-Axis:").grid(column=0, row=settings_row, sticky=tk.W)
            y_axis_units = ["M/s", "mM/s", "µM/s", "nM/s", "pM/s"]
            self.y_axis_unit_combobox = ttk.Combobox(self.assay_settings_cf.content,
                                                     textvariable=self.y_axis_unit,
                                                     state="readonly",
                                                     values=y_axis_units)
            self.y_axis_unit_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.y_axis_unit_combobox.bind("<<ComboboxSelected>>", self.update_y_axis_unit)

            # Next settings row
            settings_row += 1

            # Entry for label on y-axis
            ttk.Label(self.assay_settings_cf.content, text="y-Axis Label:").grid(column=0, row=settings_row, sticky=tk.W)
            self.y_axis_label_entry = ttk.Entry(self.assay_settings_cf.content, textvariable=self.y_axis_label, width=self.control_widths["long_entry"])
            self.y_axis_label_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.y_axis_label_entry] = self.update_axis_labels

            # Next settings row
            settings_row += 1

            # Checkbox whether to guess the x-Coordinate from the filename
            ttk.Label(self.assay_settings_cf.content, text="Automatically Sort Files:").grid(column=0, row=settings_row, sticky=tk.W)
            self.autosort_files_checkbox = ttk.Checkbutton(self.assay_settings_cf.content, text="", command=self.update_autosort_files, variable=self.autosort_files, onvalue=True, offvalue=False)
            self.autosort_files_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            row += 1

            # Add a collapsible Frame for all Assay Settings
            self.assay_fit_settings_cf = CollapsibleFrame(self.plotprops, text="Fit Settings")
            self.assay_fit_settings_cf.expand()
            self.assay_fit_settings_cf.grid(column=0, columnspan=4, row=row, sticky=tk.NSEW)

            settings_row = 0

            # Show Fit checkbox
            ttk.Label(self.assay_fit_settings_cf.content, text="Show Fit:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_assay_fit_checkbox = ttk.Checkbutton(self.assay_fit_settings_cf.content,
                                                           text="", 
                                                           command=self.update_assay_fit, 
                                                           variable=self.show_assay_fit, 
                                                           onvalue=True, 
                                                           offvalue=False)
            self.show_assay_fit_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings_row
            settings_row += 1

            ttk.Label(self.assay_fit_settings_cf.content, text="Color:").grid(column=0, row=settings_row, sticky=tk.W)

            self.assay_fit_color_image = self.create_color_image(size=color_btn_size, color=self.assay_fit_color)
    
            self.assay_fit_color_btn = tk.Label(self.assay_fit_settings_cf.content,
                                                image=self.assay_fit_color_image,
                                                bd=0,
                                                highlightthickness=0,
                                                cursor="hand2",
                                            )

            # padx has to be 9 so it looks somewhat centered with the checkbox
            self.assay_fit_color_btn.grid(column=1, row=settings_row, sticky=tk.E, padx=(0, 13), pady=self.widget_pady)
            self.assay_fit_color_btn.bind("<Button-1>", self.choose_assay_fit_color)

            # Next settings_row
            settings_row += 1

            # Spinbox for Linewidth of the fit
            ttk.Label(self.assay_fit_settings_cf.content, text="Linewidth:").grid(column=0, row=settings_row, sticky=tk.W)
            self.assay_fit_linewidth_spinbox = ttk.Spinbox(self.assay_fit_settings_cf.content, from_=0.1, to=np.inf, increment=0.2, textvariable=self.assay_fit_linewidth, command=self.update_assay_fit_linewidth)
            self.assay_fit_linewidth_spinbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.assay_fit_linewidth_spinbox] = self.update_assay_fit_linewidth

            # Next settings_row
            settings_row += 1

            # Combobox for Linestyle of the fit
            ttk.Label(self.assay_fit_settings_cf.content, text="Linestyle:").grid(column=0, row=settings_row, sticky=tk.W)
            self.assay_fit_linestyle_combobox = ttk.Combobox(self.assay_fit_settings_cf.content, values=["solid","dashed","dashdot","dotted","none"], textvariable=self.assay_fit_linestyle, state="normal")
            self.assay_fit_linestyle_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.assay_fit_linestyle_combobox] = self.update_assay_fit_linestyle
            self.assay_fit_linestyle_combobox.bind("<<ComboboxSelected>>", self.update_assay_fit_linestyle)

            # Next settings_row
            settings_row += 1

            # Frame to show the assay fit parameters
            self.assay_fit_parameters_frame = ttk.LabelFrame(self.assay_fit_settings_cf.content, text="Fit Parameters")
            self.assay_fit_parameters_frame.grid(column=0, columnspan=2, row=settings_row, sticky=tk.EW, padx=5, pady=self.widget_pady)
            for i in range(4):
                self.assay_fit_parameters_frame.columnconfigure(i, weight=1)

            ttk.Label(self.assay_fit_parameters_frame, text="Vmax:").grid(column=0, row=0, sticky=tk.E)
            ttk.Label(self.assay_fit_parameters_frame, textvariable=self.assay_fit_vmax).grid(column=1, row=0, sticky=tk.W)

            ttk.Label(self.assay_fit_parameters_frame, text="Km:").grid(column=2, row=0, sticky=tk.E)
            ttk.Label(self.assay_fit_parameters_frame, textvariable=self.assay_fit_Km).grid(column=3, row=0, sticky=tk.W)

            # Frame for R²
            r2_frame = ttk.Frame(self.assay_fit_parameters_frame)
            r2_frame.grid(column=0, columnspan=4, row=1, sticky=tk.EW)
            r2_frame.columnconfigure(0, weight=1)
            r2_frame.columnconfigure(1, weight=1)
            
            ttk.Label(r2_frame, text="R²:").grid(column=0, row=0, sticky=tk.E)
            ttk.Label(r2_frame, textvariable=self.assay_fit_r2).grid(column=1, row=0, sticky=tk.W)

            # Next settings row
            settings_row += 1

            # Checkbutton for showing Vmax constant in the plot
            ttk.Label(self.assay_fit_settings_cf.content, text="Show Vmax Constant:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_assay_fit_vmax_checkbox = ttk.Checkbutton(self.assay_fit_settings_cf.content, text="", command=self.update_vmax_constant, variable=self.assay_show_vmax, onvalue=True, offvalue=False)
            self.show_assay_fit_vmax_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Checkbutton for showing Km rectangle in the plot
            ttk.Label(self.assay_fit_settings_cf.content, text="Show Km Rectangle:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_assay_fit_Km_checkbox = ttk.Checkbutton(self.assay_fit_settings_cf.content, text="", command=self.update_Km_rectangle, variable=self.assay_show_Km, onvalue=True, offvalue=False)
            self.show_assay_fit_Km_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Checkbutton for showing the parameters in the plot
            ttk.Label(self.assay_fit_settings_cf.content, text="Show Fit Parameters:").grid(column=0, row=settings_row, sticky=tk.W)
            self.show_assay_fit_params_checkbox = ttk.Checkbutton(self.assay_fit_settings_cf.content, text="", command=self.update_fit_params_visibility, variable=self.assay_show_fit_data, onvalue=True, offvalue=False)
            self.show_assay_fit_params_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            row += 1

        # Check for the plottype
        elif plottype in ["CD", "Tm", "MultiPlot"]:

            # Hide Checkbox for Vertical Labels:
            try:
                self.vlabel_checkbox.grid_remove()
                self.vlabel_label.grid_remove()
            except:
                pass

            # Next row
            row += 1

            # Calculate MRE button
            self.calc_MRE_label = ttk.Label(self.plotprops, text="Calculate MRE:")
            self.calc_MRE_label.grid(column=0, columnspan=3, row=row, sticky=tk.W)
            self.calc_MRE_checkbox = ttk.Checkbutton(self.plotprops, text="", command=self.update_MRE_settings, variable=self.calc_MRE, onvalue=True, offvalue=False)
            self.calc_MRE_checkbox.grid(column=3, row=row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            row += 1

            if plottype in ["CD", "Tm"]:
                
                # Frame for Parameters
                self.CD_settings_frame = CollapsibleFrame(self.plotprops, text="Sample Parameters")
                self.CD_settings_frame.expand()
                self.CD_settings_frame.grid(column=0, columnspan=4, row=row, sticky=tk.EW)

                # Setup settings row
                settings_row = 0
                
                # Entry for Pathlength
                ttk.Label(self.CD_settings_frame.content, text="Pathlength:").grid(column=0, row=settings_row, sticky=tk.W)
                self.pathlength_entry = ttk.Entry(self.CD_settings_frame.content, textvariable = self.pathlength, validate="key", validatecommand=(vcmd_float, "%P"), width=12-len("mM"))
                self.pathlength_entry.grid(column=1, row=settings_row, sticky=tk.E, padx=self._tk_font.measure("mM")+6, pady=self.widget_pady)
                self.widget_function_dict[self.pathlength_entry] = self.update_CD_points

                # Unit
                ttk.Label(self.CD_settings_frame.content, text="mm").grid(column=1, row=settings_row, sticky=tk.E, padx=0)

                # Next settings row
                settings_row += 1

                # Entry for Concentration
                ttk.Label(self.CD_settings_frame.content, text="Concentration:").grid(column=0, row=settings_row, sticky=tk.W)
                self.concentration_entry = ttk.Entry(self.CD_settings_frame.content, textvariable = self.concentration, validate="key", validatecommand=(vcmd_float, "%P"), width=12-len("mM"))
                self.concentration_entry.grid(column=1, row=settings_row, sticky=tk.E, padx=self._tk_font.measure("mM")+6, pady=self.widget_pady)
                self.widget_function_dict[self.concentration_entry] = self.update_CD_points
                # Unit
                ttk.Label(self.CD_settings_frame.content, text="mM").grid(column=1, row=settings_row, sticky=tk.E, padx=0)

                # In case of Tm, Entry for Wavelength
                if plottype == "Tm":
                    # Next settings row
                    settings_row += 1
                    ttk.Label(self.CD_settings_frame.content, text="Wavelength:").grid(column=0, row=settings_row, sticky=tk.W)
                    self.wavelength_entry = ttk.Entry(self.CD_settings_frame.content, textvariable = self.wavelength, validate="key", validatecommand=(vcmd_float, "%P"), width=12-len("mM"))
                    self.wavelength_entry.grid(column=1, row=settings_row, sticky=tk.E, padx=self._tk_font.measure("mM")+6, pady=self.widget_pady)
                    self.widget_function_dict[self.wavelength_entry] = self.update_ylabel
                    # Unit
                    ttk.Label(self.CD_settings_frame.content, text="nm").grid(column=1, row=settings_row, sticky=tk.E, padx=0)

                # Next settings row
                settings_row += 1

                # Spinbox for Residue number
                ttk.Label(self.CD_settings_frame.content, text="Backbone Amides:").grid(column=0, row=settings_row, sticky=tk.W)
                self.nbr_of_residues_spinbox = ttk.Spinbox(self.CD_settings_frame.content, from_=1, to=np.inf, textvariable = self.nbr_of_residues, validate="key", validatecommand=(vcmd_int, "%P"), command=self.update_CD_points)
                self.nbr_of_residues_spinbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
                self.widget_function_dict[self.nbr_of_residues_spinbox] = self.update_CD_points

                # Next row
                row += 1

            if plottype == "Tm":
                
                # Add a button for calculating the curve fit
                curve_fit_button = ttk.Button(self.plotprops, text="Perform Curve Fit",  command=self.perform_CD_fits)
                curve_fit_button.grid(column=0, row=row, columnspan=4, sticky=tk.EW, pady=self.widget_pady)

                # Next row
                row += 1

                # Add a checkbox whether to show fit or not
                ttk.Label(self.plotprops, text="Show Fit:").grid(column=0, row=row, columnspan=3, sticky=tk.W)
                self.show_tm_fit_checkbox = ttk.Checkbutton(self.plotprops, text="", command=self.update_fit, variable=self.show_fit, onvalue=True, offvalue=False)
                self.show_tm_fit_checkbox.grid(column=3, row=row, sticky=tk.E, pady=self.widget_pady)

                # Next row
                row += 1

                # Add a checkbox whether to show baselines or not
                ttk.Label(self.plotprops, text="Show Baselines:").grid(column=0, row=row, columnspan=3, sticky=tk.W)
                self.show_tm_baselines_checkbox = ttk.Checkbutton(self.plotprops, text="", command=self.update_fit, variable=self.show_tm_baselines, onvalue=True, offvalue=False)
                self.show_tm_baselines_checkbox.grid(column=3, row=row, sticky=tk.E, pady=self.widget_pady)

            elif plottype == "CD":

                # Frame for Zero-Line settings
                self.zero_line_settings_frame = CollapsibleFrame(self.plotprops, text="Zero-Constant Settings")
                self.zero_line_settings_frame.grid(column=0, columnspan=4, row=row, sticky=tk.EW)

                # Setup settings row
                settings_row = 0
                
                # Checkbox for Zeroline plotting
                ttk.Label(self.zero_line_settings_frame.content, text="Show Zero-Constant:").grid(column=0, row=settings_row, sticky=tk.W)
                self.zero_line_checkbox = ttk.Checkbutton(self.zero_line_settings_frame.content, text="", command=self.toggle_zero_line, variable=self.show_zero_line, onvalue=True, offvalue=False)
                self.zero_line_checkbox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)

                # Next settings row
                settings_row += 1

                # Color picker
                ttk.Label(self.zero_line_settings_frame.content, text="Color:").grid(column=0, row=settings_row, sticky=tk.W)
                self.zero_line_color_image = self.create_color_image(size=color_btn_size, color=self.zero_line_color)
                self.zero_line_color_btn = tk.Label(self.zero_line_settings_frame.content,
                                                    image=self.zero_line_color_image,
                                                    bd=0,
                                                    highlightthickness=0,
                                                    cursor="hand2")
                self.zero_line_color_btn.grid(column=1, row=settings_row, sticky=tk.E, padx=(0, 13), pady=self.widget_pady)
                self.zero_line_color_btn.bind("<Button-1>", self.choose_zero_line_color)

                # Next settings row
                settings_row += 1

                # Combobox for Linewidth
                ttk.Label(self.zero_line_settings_frame.content, text="Linewidth:").grid(column=0, row=settings_row, sticky=tk.W)
                self.zero_line_linewidth_entry = ttk.Entry(self.zero_line_settings_frame.content, textvariable=self.zero_line_linewidth, validate="key", validatecommand=(vcmd_float, "%P"))
                self.zero_line_linewidth_entry.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
                self.widget_function_dict[self.zero_line_linewidth_entry] = self.update_zero_linewidth

                # Next settings row
                settings_row += 1

                # Combobox for Linestyles
                ttk.Label(self.zero_line_settings_frame.content, text="Linestyle:").grid(column=0, row=settings_row, sticky=tk.W)
                self.zero_line_linestyle_combobox = ttk.Combobox(self.zero_line_settings_frame.content, textvariable=self.zero_line_linestyle, state="normal", values=["solid","dashed","dashdot","dotted","none"])
                self.zero_line_linestyle_combobox.grid(column=1, row=settings_row, sticky=tk.E, pady=self.widget_pady)
                self.zero_line_linestyle_combobox.bind("<<ComboboxSelected>>", self.update_zero_linestyle)
                self.widget_function_dict[self.zero_line_linestyle_combobox] = self.update_zero_linestyle

        elif plottype == "HPLC":

            # If plottype is MALDI then initiate a table with a list of the peaks and the ability to give a suspected Formula
            columns = ("Peak", "Label")

            # Next row
            row += 1

            plotprop_tree_frame = ttk.Frame(self.plotprops)
            plotprop_tree_frame.grid(column=0, row=row, columnspan=4, sticky=tk.EW)
            
            plotprop_tree = TreeviewEdit(plotprop_tree_frame, self, treetype="peaks", columns=columns, show="headings", height=5)
            self.plotprops_widgets.append(plotprop_tree)

            plotprop_tree.scrollbar = ttk.Scrollbar(plotprop_tree_frame, orient=tk.VERTICAL, command=plotprop_tree.yview)
            plotprop_tree.configure(yscroll=plotprop_tree.scrollbar.set)

            plotprop_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
            plotprop_tree.scrollbar.pack(side=tk.LEFT, expand=False, fill=tk.Y)

            # Bind the enter method, to ensure proper and nice scrolling behavior for the treeview
            plotprop_tree.bind("<Enter>", self.on_enter)
            
            for head in columns:
                plotprop_tree.heading(head, text=head)
                plotprop_tree.column(head, width=self._tk_font.measure(head))
            
            # Next row
            row += 1

            # Add a CollapsibleFrame for integration settings
            self.integration_settings = CollapsibleFrame(self.plotprops, text="Integration Settings")
            self.integration_settings.grid(column=0, row=row, columnspan=4, sticky=tk.EW)

            # Settings row
            settings_row = 0

            # Add a checkbox to ask whether the integrated areas should be shown
            ttk.Label(self.integration_settings.content, text="Show Integrated Areas:").grid(column=0, columnspan=3, row=settings_row, sticky=tk.W)
            self.integrated_area_checkbox = ttk.Checkbutton(self.integration_settings.content, text="", command=self.toggle_integrals, variable=self.integrated_area, onvalue=True, offvalue=False)
            self.integrated_area_checkbox.grid(column=2, row=settings_row, sticky=tk.E, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            ttk.Label(self.integration_settings.content, text="Integration Mode:").grid(column=0, columnspan=3, row=settings_row, sticky=tk.W)

            # Next settings row
            settings_row += 1
            
            # Add Radiobuttons for checking which integration_mode to use
            self.radio_none = ttk.Radiobutton(self.integration_settings.content, text="Approximate Locally", value="local", variable=self.integration_mode, command=self.update_HPLC_baseline_mode)
            self.radio_none.grid(column=0, columnspan=3, row=settings_row, sticky=tk.W, padx=4, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Add next radiobutton
            self.radio_linear = ttk.Radiobutton(self.integration_settings.content, text="Approximate Linear Baseline", value="linear", variable=self.integration_mode, command=self.update_HPLC_baseline_mode)
            self.radio_linear.grid(column=0, columnspan=3, row=settings_row, sticky=tk.W, padx=4, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Put entries
            self.linear_min_entry = ttk.Entry(self.integration_settings.content, textvariable=self.integration_linear_min, validate="key", validatecommand=(vcmd_float, "%P"))
            self.linear_min_entry.grid(column=0, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.linear_min_entry] = self.update_linear_HPLC_baseline
            ttk.Label(self.integration_settings.content, text="-").grid(column=1, row=settings_row)
            self.linear_max_entry = ttk.Entry(self.integration_settings.content, textvariable=self.integration_linear_max, validate="key", validatecommand=(vcmd_float, "%P"))
            self.linear_max_entry.grid(column=2, row=settings_row, sticky=tk.W, pady=self.widget_pady)
            self.widget_function_dict[self.linear_max_entry] = self.update_linear_HPLC_baseline

            # Next settings row
            settings_row += 1

            # Add next radiobutton
            self.radio_constant = ttk.Radiobutton(self.integration_settings.content, text="Approximate Constant Baseline", value="constant", variable=self.integration_mode, command=self.update_HPLC_baseline_mode)
            self.radio_constant.grid(column=0, columnspan=3, row=settings_row, sticky=tk.W, padx=4, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Put entry
            self.constant_entry = ttk.Entry(self.integration_settings.content, textvariable=self.integration_constant, validate="key", validatecommand=(vcmd_float, "%P"))
            self.constant_entry.grid(column=2, row=settings_row, sticky=tk.E, pady=self.widget_pady)
            self.widget_function_dict[self.constant_entry] = self.update_constant_HPLC_baseline


            # Next settings row
            settings_row += 1

            # Add last radiobutton
            self.radio_manual = ttk.Radiobutton(self.integration_settings.content, text="Pick Baseline Manually", value="manual", variable=self.integration_mode, command=self.update_HPLC_baseline_mode)
            self.radio_manual.grid(column=0, columnspan=3, row=settings_row, sticky=tk.W, padx=4, pady=self.widget_pady)

            # Next settings row
            settings_row += 1

            # Put button to show baseline
            self.show_HPLC_baseline_btn = ttk.Button(self.integration_settings.content, text="Toggle Baseline", command=self.toggle_HPLC_baseline)
            self.show_HPLC_baseline_btn.grid(column=0, columnspan=3, row=settings_row, pady=self.widget_pady)

        elif plottype == "MALDI":

            # Next row
            row += 1

            self.inset_frame = CollapsibleFrame(self.plotprops, text="Inset Settings")
            self.inset_frame.expand()
            self.inset_frame.grid(column=0, columnspan=4, row=row, sticky=tk.EW)

            # Keep track of inset_rows
            inset_row = 0
            # Checkbox to ask for the inset:
            ttk.Label(self.inset_frame.content, text="Draw Inset:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.ask_inset = ttk.Checkbutton(self.inset_frame.content, text="", command=self.update_inset, variable=self.inset, onvalue=True, offvalue=False)
            self.ask_inset.grid(column=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)

            # Next row
            inset_row += 1

            # Entry for x-Axis from- & to- values
            ttk.Label(self.inset_frame.content, text="Span of x-Axis:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.EW)
            
            ttk.Label(self.inset_frame.content, text="-").grid(column=2, row=inset_row, sticky=tk.E)
            self.xlim_min_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.xlim_min_inset, validate="key", validatecommand=(vcmd_float, "%P"))
            self.xlim_min_inset_entry.grid(column=1, row=inset_row, pady=self.widget_pady)
            self.xlim_min_inset_entry.state(["disabled"])
            self.widget_function_dict[self.xlim_min_inset_entry] = self.update_xlim_inset

            self.xlim_max_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.xlim_max_inset, validate="key", validatecommand=(vcmd_float, "%P"))
            self.xlim_max_inset_entry.grid(column=3, row=inset_row, pady=self.widget_pady)
            self.xlim_max_inset_entry.state(["disabled"])
            self.widget_function_dict[self.xlim_max_inset_entry] = self.update_xlim_inset

            # Next row
            inset_row += 1

            # Entry for y-Axis Height in Percent
            ttk.Label(self.inset_frame.content, text="Height of y-Axis:").grid(column=0, columnspan=1, row=inset_row, sticky=tk.W)
            self.y_height_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.y_height_inset, validate="key", validatecommand=(vcmd_float, "%P"))
            self.y_height_inset_entry.grid(column=3, row=inset_row, sticky=tk.E, padx=self._tk_font.measure("%"), pady=self.widget_pady)
            self.y_height_inset_entry.state(["disabled"])
            self.widget_function_dict[self.y_height_inset_entry] = self.update_ylim_inset
            ttk.Label(self.inset_frame.content, text="%", padding=0).grid(column=3, row=inset_row, sticky=tk.E)

            # Next row
            inset_row += 1

            # Combobox to ask for the position of the inset
            ttk.Label(self.inset_frame.content, text="Inset Position:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            inset_positions = ["upper right", "upper center", "upper left", "center right", "center", "center left", "lower right", "lower center", "lower left"]

            self.ask_inset_pos = ttk.Combobox(self.inset_frame.content, textvariable=self.inset_pos, state="readonly", values=inset_positions)
            self.ask_inset_pos.bind("<<ComboboxSelected>>", self.update_inset)
            self.ask_inset_pos.grid(column=1, columnspan=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)
            self.ask_inset_pos.state(["disabled"])

            # Next row
            inset_row += 1
            
            # Entries to ask for width of inset
            ttk.Label(self.inset_frame.content, text="Width:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.width_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.xsize_inset, validate="key", validatecommand=(vcmd_float, "%P"))
            self.width_inset_entry.grid(column=3, row=inset_row, sticky=tk.E, padx=self._tk_font.measure("%"), pady=self.widget_pady)
            self.width_inset_entry.state(["disabled"])
            self.widget_function_dict[self.width_inset_entry] = self.update_inset
            ttk.Label(self.inset_frame.content, text="%", padding=0).grid(column=3, row=inset_row, sticky=tk.E)

            # Next row
            inset_row += 1
            
            # Entries to ask for height of the inset
            ttk.Label(self.inset_frame.content, text="Height:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.height_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.ysize_inset, validate="key", validatecommand=(vcmd_float, "%P"))
            self.height_inset_entry.grid(column=3, row=inset_row, sticky=tk.E, padx=self._tk_font.measure("%"), pady=self.widget_pady)
            self.height_inset_entry.state(["disabled"])
            self.widget_function_dict[self.height_inset_entry] = self.update_inset
            ttk.Label(self.inset_frame.content, text="%", padding=0).grid(column=3, row=inset_row, sticky=tk.E)

            # Next row
            inset_row += 1

            # Entries to ask for the borderpad of the inset
            ttk.Label(self.inset_frame.content, text="Border Pad:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.borderpad_inset_entry = ttk.Entry(self.inset_frame.content, textvariable = self.inset_borderpad)
            self.borderpad_inset_entry.grid(column=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)
            self.borderpad_inset_entry.state(["disabled"])
            self.widget_function_dict[self.borderpad_inset_entry] = self.update_inset_borderpad

            # Next row
            inset_row += 1

            # Spinbox to ask for the fontsize of the inset
            ttk.Label(self.inset_frame.content, text="Fontsize:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.fontsize_inset_spinbox = ttk.Spinbox(self.inset_frame.content,
                                                      textvariable = self.inset_fontsize, 
                                                      from_=0, 
                                                      to=np.inf, 
                                                      validate="key", 
                                                      validatecommand=(vcmd_float, "%P"), 
                                                      wrap=False, 
                                                      command=self.update_inset_fontsize)
            self.fontsize_inset_spinbox.grid(column=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)
            self.fontsize_inset_spinbox.state(["disabled"])
            self.widget_function_dict[self.fontsize_inset_spinbox] = self.update_inset_fontsize

            # Next row
            inset_row += 1
            
            # Checkbox to ask for the Mirroring of annotations to the inset:
            ttk.Label(self.inset_frame.content, text="Mirror Annotations:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.ask_mirror = ttk.Checkbutton(self.inset_frame.content, text="", command=self.mirror_annotations_to_inset, variable=self.mirror_annotations, onvalue=True, offvalue=False)
            self.ask_mirror.grid(column=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)
            self.ask_mirror.state(["disabled"])

            # Next row
            inset_row += 1

            # Checkbox to ask for vertical Labels of annotations on the inset:
            ttk.Label(self.inset_frame.content, text="Vertical Labels:").grid(column=0, columnspan=2, row=inset_row, sticky=tk.W)
            self.inset_vlabel_checkbox = ttk.Checkbutton(self.inset_frame.content, text="", command=self.update_inset_labels, variable=self.inset_vlabels, onvalue="vertical", offvalue="horizontal")
            self.inset_vlabel_checkbox.grid(column=3, row=inset_row, sticky=tk.E, pady=self.widget_pady)
            self.inset_vlabel_checkbox.state(["disabled"])

            # Keep track of all inset widgets that need to be enabled/disabled when the inset is toggled
            self.inset_widgets = [
                            self.xlim_min_inset_entry,
                            self.xlim_max_inset_entry,
                            self.y_height_inset_entry,
                            self.ask_mirror,
                            self.ask_inset_pos,
                            self.inset_vlabel_checkbox,
                            self.width_inset_entry,
                            self.height_inset_entry,
                            self.borderpad_inset_entry,
                            self.fontsize_inset_spinbox,
                        ]

        elif plottype not in self.plottypes:
            ## Gray out all boxes
            
            # Checkbox for Vertical Labels: 
            self.vlabel_checkbox.state(["disabled"])

            # Disable Entries
            self.xlim_min_entry.state(["disabled"])
            self.xlim_max_entry.state(["disabled"])

        if plottype == "MultiPlot":

            self.multiplot_3D_settings_frame.grid_remove()

        if plottype is not None:
            self.plotprops_initialized = True

        # Next row
        row += 1

        # Add a ScrolledText Widget, for keeping notes
        ttk.Label(self.plotprops, text="Notes:").grid(column=0, columnspan=4, row=row, sticky=tk.W)

        # Next row
        row += 1

        # ScrolledText does not work because it does not give a themed scrollbar, therefore create scrolledtext myself
        self.scrolledtext_frame = ttk.Frame(self.plotprops)

        self.notepad = tk.Text(self.scrolledtext_frame, height=8, width=20)
        self.notepad_scrollbar = ttk.Scrollbar(self.scrolledtext_frame, orient="vertical", command=self.notepad.yview)
        self.notepad.configure(yscrollcommand=self.notepad_scrollbar.set)

        # Pack Text and scrollbar on frame
        self.notepad.pack(side="left", fill="both", expand=True)
        self.notepad_scrollbar.pack(side="right", fill="y")

        self.scrolledtext_frame.grid(column=0, columnspan=4, row=row, sticky=tk.EW, pady=self.widget_pady)

        # Bind commands to notepad to handle proper data transfer and correct scrolling behavior
        self.notepad.bind("<FocusOut>", self.save_notepad)
        self.notepad.bind("<Enter>", self.on_enter)

        # Add a button at the bottom for exporting the current plot
        if not hasattr(self, "export_button") or not self.export_button.winfo_exists():
            self.export_button = ttk.Button(self, text="Export current plot", command=self.save_current_img)
        self.export_button.grid(column=5, row=3, sticky="esw", pady=self.widget_pady)

        # Bind Events to redrawing of the Graph
        for widget in self.widget_function_dict:
            widget.bind("<FocusIn>", self.on_focus_in)

        events = ("<Return>","<FocusOut>")

        for event in events:
            if event == "<Return>": callback = self.refresh
            else: callback = self.lazy_refresh
            
            if plottype == "MultiPlot":
                self.multiplot_elevation_entry.bind(event, callback)
                self.multiplot_rotation_entry.bind(event, callback)
                self.multiplot_offset_entry.bind(event, callback)

        if plottype == "MultiPlot":
            self.multiplot_perspective_combobox.bind("<<ComboboxSelected>>", self.refresh)
            self.multiplot_labels_combobox.bind("<<ComboboxSelected>>", self.update_multiplot_labels)
            self.multiplot_colormap_combobox.bind("<<ComboboxSelected>>", self.apply_colormap)
            self.multiplot_fit_combobox.bind("<<ComboboxSelected>>", self.update_multiplot_fit)

        self._bind_plotprops_scroll_to_widgets(self.plotprops)

        self.plotprops.grid(row=0, column=0, sticky=tk.NSEW)
        self.plotprops_sf.grid(column=5, row=1, rowspan=2, sticky=tk.NSEW)

        self.plotprops_states[plottype] = self._capture_plotprops_state()
        self.after_idle(self._update_plotprops_width)

    # A custom mousewheel function is necessary here, to handle the nested scrollbars of the scrollable Frame from ttkboostrap and the notepad
    def on_mousewheel(self, event):
        scroll = True
        widget = event.widget
        first, last = widget.yview()
        if event.delta > 0:
            if first > 0:
                widget.yview_scroll(-1, "units")
                return
            else:
                scroll = False
            
        else:
            if last < 1:
                widget.yview_scroll(1, "units")
                return
            else:
                scroll = False
        
        if not scroll:
            # If the widget cannot be scrolled, move the scrolledframe which should be the parent at some kind of level for all widgets that have this method
            if event.delta > 0:
                self.plotprops_sf.yview_scroll(-1, "units") 
            else:
                self.plotprops_sf.yview_scroll(1, "units") 

    def combobox_on_mousewheel(self, event):
        scroll = True
        widget = event.widget
        values = widget.cget("values")
        current_value = widget.get()
        if event.delta > 0:
            if current_value != values[0]:
                return
            else:
                scroll = False
            
        else:
            if current_value != values[-1]:
                return
            else:
                scroll = False
        
        if not scroll:
            # If the widget cannot be scrolled, move the scrolledframe which should be the parent at some kind of level for all widgets that have this method
            if event.delta > 0:
                self.plotprops_sf.yview_scroll(-1, "units") 
            else:
                self.plotprops_sf.yview_scroll(1, "units") 

    # A custom function to bind the mousewheel function to a widget upon entering the widget with the mouse    
    def on_enter(self, event):
        if not self._plotprops_scrolling_disabled:
            self.plotprops_sf.disable_scrolling()
            self._plotprops_scrolling_disabled = True
        event.widget.bind("<Leave>", self.on_leave)

    def on_leave(self, event):
        if self._plotprops_scrolling_disabled:
            self.plotprops_sf.enable_scrolling()
            self._plotprops_scrolling_disabled = False

    def save_notepad(self, event):
        widget = event.widget
        notepad_data = widget.get("1.0", "end-1c")

        if self.plottype not in ["Assay", "MultiPlot"]:
            cp.plot_data["notepad_text"] = notepad_data
        else:
            self.multiplot_plotoptions["notepad_text"] = notepad_data

        # Save to db
        self.save_to_db()

    def update_datakey_and_project(self):

        if self.iid is not None:
            if self.plottype not in ["Assay", "MultiPlot"]:
                datakey = db.browser_saves[self.iid]["filename"]
                browser = self.browser

            else:
                datakey = self.multiplot_plotoptions["filename"]
                browser = self.multiplot_browser

            parent = browser.parent(self.iid)

            # Setup parent_text
            if parent == "":
                parent_text = ""
            else:
                index = browser.treeview_saves["widgets"].index(parent)
                parent_text = browser.treeview_saves["text"][index]
                parent = browser.treeview_saves["parent"][index]
                # Iteratively check whether the parent also has another parent and add it to the name
                while parent != "":
                    index = browser.treeview_saves["widgets"].index(parent)
                    parent_text = browser.treeview_saves["text"][index] + f" / {parent_text}"
                    parent = browser.treeview_saves["parent"][index]
        
        else:
            datakey = ""
            parent_text = ""

        # Calculate total width of all widgets and cut of the datakey label if it is too large
        total_width = max(child.winfo_reqwidth() for child in self.plotprops.winfo_children())
        total_width = max(self.plotprops.winfo_width()-self.scrollbar_width, total_width-self.scrollbar_width, 40)
        truncated = datakey
        if self._plotprops_title_font.measure(datakey) > total_width:
            while self._plotprops_title_font.measure(f"{truncated}...") > total_width and truncated:
                truncated = truncated[:-1]
            truncated += "..."

        # Do the same for self.parent_text
        truncated_parent = parent_text
        if self._plotprops_project_font.measure(parent_text) > total_width:
            while self._plotprops_project_font.measure(f"{truncated_parent}") > total_width and truncated_parent:
                truncated_parent_split = truncated_parent.split(" / ")
                if len(truncated_parent_split) > 1:
                    if truncated_parent_split[0] != "...":
                        truncated_parent_split[0] = "..."
                    else:
                        if len(truncated_parent_split) > 2:
                            truncated_parent_split.pop(1)
                        else:
                            if truncated_parent_split[1].endswith("..."):
                                truncated_parent_split[1] = truncated_parent_split[1][:-4]
                            else:
                                truncated_parent_split[1] = truncated_parent_split[1][:-1]
                            truncated_parent_split[1] += "..."

                    truncated_parent = " / ".join(truncated_parent_split)
                else:
                    if truncated_parent_split[0].endswith("..."):
                        truncated_parent = truncated_parent_split[0][:-4]
                    else:
                        truncated_parent = truncated_parent_split[0][:-1]
                        
                    truncated_parent += "..."

        # Update Label that shows the current Graph that is being worked on
        self.datakey_label.config(text=truncated)

        self.project_name.config(text=truncated_parent)

    def on_focus_in(self, event):

        widget = event.widget
        widget.initial_value = widget.get()

        for event in ("<Return>","<FocusOut>"):
            widget.bind(event, self.on_focus_out_and_return)

    def on_focus_out_and_return(self, event):

        focus_out = False
        widget = event.widget
        widget.final_value = widget.get()

        if event.type == tk.EventType.FocusOut:
            focus_out = True
            for event in ("<Return>","<FocusOut>"):
                widget.unbind(event)

        if widget.initial_value != widget.final_value:

            # Create failsave in case a widget is left empty, even though this should not be the case
            if widget.final_value == "":
                if focus_out:
                    widget.insert(0, widget.initial_value)
                return
            
            # Update initial value in case multiple changes are made in the same entry, without losing focus
            widget.initial_value = widget.final_value

            self.widget_function_dict[widget]()
        
    def validate_floats(self, value):
        # Check whether values entered into entries are actually floats
        if value == "" or value == "-":
            return True
        try:
            float(value)
            return True
        except ValueError:
            return False
            
    def validate_integers(self, value):
        # Check whether values entered into entries are actually integers
        if value == "" or value == "-":
            return True
        if value[0] in "+-":
            value = value[1:]
        return value.isdigit()

    def lazy_refresh(self, *args):
        # Cancel previous request if called again
        if self._lazy_refresh:
            self.after_cancel(self._lazy_refresh)

        # Schedule a new resize
        self._lazy_refresh = self.after(250, self.refresh)

    def refresh_annotations(self, ax=None):
        if not ax:
            ax = cp.ax

        cp.refresh_annotations(cp.ax)
        self.save_to_db()

    # Function for showing the fit of a file inside of an assay:
    def show_assay_file_fit(self, iid):

        if not db.load(iid):
            print(f"Plot {iid} is not in database. Plot is skipped.")
            if iid != "PlotOptions":
                try:
                    cp.multiplot_data.pop(iid)
                except KeyError:
                    pass
            return

        # Delegate the task to CanvasPlot
        cp.show_assay_file_fit(iid, db.save_data[iid])

    ## Following, there will be functions with very specific re-/drawing tasks, delegated to the CanvasPlot instance.
    ## Every method will also do a database save after the function was passed to CanvasPlot

    # Update the selected assay method
    def update_assay_type(self, *args):

        self.multiplot_plotoptions["assay_type"] = self.assay_type.get()

        # Also update the labels to fit the config
        self.x_axis_label.set(config.config["Assay"][self.multiplot_plotoptions["assay_type"]]["xlabel"])
        self.y_axis_label.set(config.config["Assay"][self.multiplot_plotoptions["assay_type"]]["ylabel"])

        self.update_all_assay_y(skip_save=True)
        self.adjust_assay_y_unit()
        self.perform_assay_fit(skip_blit=True)
        self.update_axis_labels()

        self.save_to_db()

    # Update the assay fit
    def update_assay_fit(self, skip_blit=False, *args):
        cp.update_assay_fit(skip_blit=skip_blit)
        self.save_to_db()

    # Update the linewidth of the assay fit
    def update_assay_fit_linewidth(self, *args):

        cp.update_assay_fit_linewidth()
        self.save_to_db()

    def update_assay_fit_linestyle(self, *args):

        if cp.update_assay_fit_linestyle():
            self.save_to_db()

    # Update the scatterplot for the assay
    def update_assay_plot(self, skip_save=False, skip_blit=False, *args):

        cp.update_assay_plot(skip_blit=skip_blit)

        if not skip_save:
            self.save_to_db()

    def update_vmax_constant(self, *args):
        cp.update_vmax_constant()
        self.save_to_db()

    def update_Km_rectangle(self, *args):
        cp.update_Km_rectangle()
        self.save_to_db()

    def update_fit_params_visibility(self, *args):
        cp.update_fit_params_visibility()
        self.save_to_db()

    def update_autosort_files(self, *args):
        self.multiplot_plotoptions["autosort_files"] = self.autosort_files.get()

        if self.multiplot_plotoptions["autosort_files"]:

            number_of_plots = len(cp.multiplot_data) - 1  # Subtract 1 for the "PlotOptions" entry
            # Do some follow-up logic in order to calculate everything properly, only however if autosorting is enabled
            if number_of_plots > 2 and self.multiplot_plotoptions["autosort_files"]:
                # Update the name similarity matrix to check for similar names in the multiplot
                self.update_name_similarity_matrix()

            # Update only the datapoints now not everything all the time
            if self.multiplot_plotoptions["assay_type"] is not None:
                for datapoint in self.multiplot_plotoptions["assay_datapoints"]:
                    self.update_assay_y_for_datapoint(datapoint, skip_save=True)

                self.update_assay_plot(skip_save=True, skip_blit=True)

                self.perform_assay_fit()

            self.refreshTree()

        self.save_to_db()

    # Update the absorption coefficient for the assay
    def update_assay_absorption_coefficient(self, *args):

        old_absorption_coefficient = self.multiplot_plotoptions["molar_absorption_coefficient"]

        self.multiplot_plotoptions["molar_absorption_coefficient"] = self.assay_absorption_coefficient.get()
        self.adjust_y.set(True)
        self.multiplot_plotoptions["autoadjust_y"] = True

        # Calculate the conversion factor between the old and new absorption coefficient
        factor = Decimal(str(old_absorption_coefficient)) / Decimal(str(self.multiplot_plotoptions["molar_absorption_coefficient"]))

        # Update assay file values
        for datapoint, data in cp.multiplot_data.items():
            if datapoint == "PlotOptions":
                continue

            if "y" in data:
                data["y"] = float(Decimal(str(data["y"])) * factor)

            if "error" in data:
                data["error"] = float(Decimal(str(data["error"])) * factor)

        # Update assay datapoints
        for data in self.multiplot_plotoptions["assay_datapoints"].values():

            if "y" in data:
                data["y"] = float(Decimal(str(data["y"])) * factor)

            if "error" in data:
                data["error"] = float(Decimal(str(data["error"])) * factor)

        self.update_assay_plot(skip_save=True, skip_blit=True)
        self.adjust_assay_y_unit(skip_blit=True)
        self.perform_assay_fit()

    # Update the unit displayed on the x-axis for assays
    def update_x_axis_unit(self, *args):

        plot_data = self.multiplot_plotoptions

        old_x_axis_unit = plot_data["assay_x_unit"]
        old_xlim = (plot_data["x_axis_min"], plot_data["x_axis_max"])
        conversion_factors = {"M": Decimal("1"),
                              "mM": Decimal("1e-3"),
                              "µM": Decimal("1e-6"),
                              "nM": Decimal("1e-9"),
                              "pM": Decimal("1e-12")}

        plot_data["assay_x_unit"] = self.x_axis_unit.get()

        # Since the unit changes, the coordinates must also change accordingly, therefore the x-values must be recalculated
        if old_x_axis_unit in conversion_factors and plot_data["assay_x_unit"] in conversion_factors:
            # Calculate the conversion factor between the old and new units
            factor = conversion_factors[old_x_axis_unit] / conversion_factors[plot_data["assay_x_unit"]]
            for datapoint in plot_data["assay_datapoints"]:

                if "x" in plot_data["assay_datapoints"][datapoint]:
                    plot_data["assay_datapoints"][datapoint]["x"] = float(Decimal(str(plot_data["assay_datapoints"][datapoint]["x"])) * factor)

            # Update the x-axis limits accordingly
            new_xlim = (float(Decimal(str(old_xlim[0])) * factor), float(Decimal(str(old_xlim[1])) * factor))
            self.xlim_min.set(new_xlim[0])
            self.xlim_max.set(new_xlim[1])
            # Update the x-axis limits, the rest is done in the cp method
            self.update_xlim()

        self.refreshTree()
        self.update_assay_plot(skip_blit=True)
        # Update the fit as well
        self.perform_assay_fit(skip_blit=True)
        self.update_axis_labels()

    def update_axis_labels(self, skip_blit=False, *args):

        cp.update_axis_labels()
        self.save_to_db()

        if not skip_blit:
            cp._blit_redraw()

    
    # A function for updating the xlim and the units based on the datapoints
    def adjust_assay_xlim(self, *args):

        if self._idle_adjust_assay_xlim:
            self.after_cancel(self._idle_adjust_assay_xlim)
            self._idle_adjust_assay_xlim = None

        plot_data = self.multiplot_plotoptions

        if "xpoints" in plot_data and isinstance(plot_data["xpoints"], np.ndarray) and plot_data["xpoints"].size > 2:
            xpoints = plot_data["xpoints"]

        elif len(self.multiplot_plotoptions["assay_datapoints"]) > 0:
            xpoints = [0] + [plot_data["assay_datapoints"][datapoint]["x"] for datapoint in plot_data["assay_datapoints"]]

        else:
            xpoints = [0, 1]

        xpoints = np.array(xpoints)

        # Find out which unit is best for the x-axis, based on the maximum value of the xpoints
        max_x = xpoints.max()

        current_unit = plot_data["assay_x_unit"]

        conversion_factors = {"M": Decimal("1"),
                              "mM": Decimal("1e-3"),
                              "µM": Decimal("1e-6"),
                              "nM": Decimal("1e-9"),
                              "pM": Decimal("1e-12")}
        
        if current_unit in conversion_factors:
            max_x = Decimal(str(max_x)) * conversion_factors[current_unit]

        changed = False
        if max_x <= 1e-9:
            self.x_axis_unit.set("pM")
            if current_unit != "pM":
                changed = True
        elif max_x <= 1e-6:
            self.x_axis_unit.set("nM")
            if current_unit != "nM":
                changed = True
        elif max_x <= 1e-3:
            self.x_axis_unit.set("µM")
            if current_unit != "µM":
                changed = True
        elif max_x <= 1:
            self.x_axis_unit.set("mM")
            if current_unit != "mM":
                changed = True
        else:
            self.x_axis_unit.set("M")
            if current_unit != "M":
                changed = True

        self.xlim_min.set(xpoints.min())
        self.xlim_max.set(xpoints.max())

        self.update_xlim()

        if changed:
            self.update_x_axis_unit()

    # Automatically adjust the y unit based on the limits and the currently selected y unit
    def adjust_assay_y_unit(self, skip_blit=False, *args):

        plot_data = self.multiplot_plotoptions

        if "ypoints" in plot_data and isinstance(plot_data["ypoints"], np.ndarray) and plot_data["ypoints"].size > 2:
            ypoints = plot_data["ypoints"]

        elif len(self.multiplot_plotoptions["assay_datapoints"]) > 0:
            ypoints = [plot_data["assay_datapoints"][datapoint]["y"] for datapoint in plot_data["assay_datapoints"] if "y" in plot_data["assay_datapoints"][datapoint]]

        else:
            ypoints = [0, 1]

        ypoints = np.array(ypoints)

        # Find out which unit is best for the y-axis, based on the maximum value of the ypoints
        max_y = ypoints.max()

        old_unit = plot_data["assay_y_unit"]

        conversion_factors = {"M/s": Decimal("1"),
                              "mM/s": Decimal("1e-3"),
                              "µM/s": Decimal("1e-6"),
                              "nM/s": Decimal("1e-9"),
                              "pM/s": Decimal("1e-12")}
        
        if old_unit in conversion_factors:
            max_y = Decimal(str(max_y)) * conversion_factors[old_unit]

        changed = False
        if max_y <= 1e-9:
            self.y_axis_unit.set("pM/s")
            if old_unit != "pM/s":
                changed = True
        elif max_y <= 1e-6:
            self.y_axis_unit.set("nM/s")
            if old_unit != "nM/s":
                changed = True
        elif max_y <= 1e-3:
            self.y_axis_unit.set("µM/s")
            if old_unit != "µM/s":
                changed = True
        elif max_y <= 1:
            self.y_axis_unit.set("mM/s")
            if old_unit != "mM/s":
                changed = True
        else:
            self.y_axis_unit.set("M/s")
            if old_unit != "M/s":
                changed = True

        if changed:
            new_unit = self.y_axis_unit.get()
            plot_data["assay_y_unit"] = new_unit

            self.rescale_y_data(old_unit, new_unit)

            # Update the plot with the new values, the rest is done in the cp method
            self.update_assay_plot(skip_blit=True)
            self.update_axis_labels(skip_blit=skip_blit)
            self.refreshTree()

    # Update the unit displayed on the y-axis for assays
    def update_y_axis_unit(self, *args):

        old_unit = self.multiplot_plotoptions["assay_y_unit"]

        self.multiplot_plotoptions["assay_y_unit"] = self.y_axis_unit.get()

        # Since the unit changes, the coordinates must also change accordingly, therefore the y-values must be recalculated
        self.adjust_y.set(True)
        self.multiplot_plotoptions["autoadjust_y"] = True

        self.rescale_y_data(old_unit, self.multiplot_plotoptions["assay_y_unit"])
        self.perform_assay_fit(skip_blit=True)
        self.update_axis_labels()
        self.refreshTree()

    def rescale_y_data(self, old_unit, new_unit):
        conversion_factors = {"M/s": Decimal("1"),
                              "mM/s": Decimal("1e-3"),
                              "µM/s": Decimal("1e-6"),
                              "nM/s": Decimal("1e-9"),
                              "pM/s": Decimal("1e-12")}

        if old_unit in conversion_factors and new_unit in conversion_factors:
            # Calculate the conversion factor between the old and new units
            factor = conversion_factors[old_unit] / conversion_factors[new_unit]

            # Update assay file values
            for datapoint, data in cp.multiplot_data.items():
                if datapoint == "PlotOptions":
                    continue

                if "y" in data:
                    data["y"] = float(Decimal(str(data["y"])) * factor)

                if "error" in data:
                    data["error"] = float(Decimal(str(data["error"])) * factor)

            # Update assay datapoints
            for data in self.multiplot_plotoptions["assay_datapoints"].values():

                if "y" in data:
                    data["y"] = float(Decimal(str(data["y"])) * factor)

                if "error" in data:
                    data["error"] = float(Decimal(str(data["error"])) * factor)

            self.update_assay_plot(skip_save=True)

    def move_assay_files(self, iids, new_datapoint):

        for iid in iids:

            if iid not in cp.multiplot_data: continue

            # First check whether the file has a parent
            if "parent" in cp.multiplot_data[iid]:
                old_datapoint = cp.multiplot_data[iid]["parent"]
            else:
                old_datapoint = None
            
            if old_datapoint is not None:
                # Check whether the datapoint still exists
                if old_datapoint in self.multiplot_plotoptions["assay_datapoints"]:
                    # If so check whether it has the "plots" key and remove the iid out of that
                    if "plots" in self.multiplot_plotoptions["assay_datapoints"][old_datapoint] and iid in self.multiplot_plotoptions["assay_datapoints"][old_datapoint]["plots"]:
                        self.multiplot_plotoptions["assay_datapoints"][old_datapoint]["plots"].remove(iid)

                        self.update_assay_y_for_datapoint(old_datapoint, skip_save=True)

            # Change parent to the new_datapoint
            if new_datapoint != "":
                cp.multiplot_data[iid]["parent"] = new_datapoint

                # Check whether the new datapoint already has a "plots" key, if not create it
                if "plots" not in self.multiplot_plotoptions["assay_datapoints"][new_datapoint]:
                    self.multiplot_plotoptions["assay_datapoints"][new_datapoint]["plots"] = []

                # Add the iid to the new datapoint's "plots" key
                if iid not in self.multiplot_plotoptions["assay_datapoints"][new_datapoint]["plots"]:
                    self.multiplot_plotoptions["assay_datapoints"][new_datapoint]["plots"].append(iid)

                    self.update_assay_y_for_datapoint(new_datapoint, skip_save=True)

            else:
                cp.multiplot_data[iid]["parent"] = None

        # Update the assay plot after moving the file
        self.update_assay_plot(skip_save=True, skip_blit=True)
        self.perform_assay_fit()
    
    # Update all y values for an assay
    def update_all_assay_y(self, skip_save=False, *args):

        for iid in list(cp.multiplot_data.keys()):
            if iid == "PlotOptions":
                continue
            self.update_assay_y_for_file(iid, skip_save=True)

        for datapoint in self.multiplot_plotoptions["assay_datapoints"]:
            self.update_assay_y_for_datapoint(datapoint, skip_save=True)

        self.update_assay_plot(skip_save=True)

        if not skip_save:
            self.save_to_db()

    # Update the y-values for a single file of the assay, based on the selected assay type
    def update_assay_y_for_file(self, iid, skip_save=False):

        if not db.load(iid):
            print(f"Plot {iid} is not in database. Plot is skipped.")
            if iid != "PlotOptions":
                cp.multiplot_data.pop(iid)
            return

        if self.multiplot_plotoptions["assay_type"] is None:
            return

        elif self.multiplot_plotoptions["assay_type"] == "Michaelis-Menten":

            conversion_factors = {"M/s": Decimal("1"),
                                  "mM/s": Decimal("1e-3"),
                                  "µM/s": Decimal("1e-6"),
                                  "nM/s": Decimal("1e-9"),
                                  "pM/s": Decimal("1e-12")}

            # In case the plot is Michaelis Menten, each datapoint should be the initial slope of the corresponding file

            # Get the corrected baseline ypoints
            if iid not in cp.corrected_ypoints:
                cp.corrected_ypoints[iid] = self.correct_baseline(iid)

            # Do linear regression
            ypoints = cp.corrected_ypoints[iid]
            xpoints = db.save_data[iid]["xpoints"]

            # Perform the linear regression
            linear_fit = linregress(xpoints, ypoints)
            slope = linear_fit.slope
            intercept = linear_fit.intercept
            stderr = linear_fit.stderr
            r_squared = linear_fit.rvalue ** 2

            nonlinearity_dict = emancipator_kroll_nonlinearity(xpoints, ypoints)            

            dimensional_nonlinearity = nonlinearity_dict["dimensional"]
            relative_nonlinearity = nonlinearity_dict["relative"]
            polynomial_coefficients = nonlinearity_dict["polynomial_coefficients"]
            polynomial_degree = nonlinearity_dict["polynomial_degree"]

            # Using the suggested threshold in the paper by Emancipator and Kroll, 1993
            if relative_nonlinearity > 0.025:
                print(f"\nWarning: The data in plot {db.browser_saves[iid]['filename']} shows significant nonlinearity.\n"
                      "The initial slope may not be accurate.\n"
                      f"The dimensional nonlinearity is {dimensional_nonlinearity:.4g}.\n"
                      f"This results in a relatively nonlinearity of {relative_nonlinearity:.2%}.")

            # Get the important values for the Michaelis-Menten, divide by extinction coefficient
            # The calculation should give the initial slope in units of M/s, account for the unit on the y-axis with its conversion_factor

            cp.multiplot_data[iid]["y"] = float(Decimal(str(slope)) / 
                                                Decimal(str(self.multiplot_plotoptions["molar_absorption_coefficient"])) / 
                                                conversion_factors[self.multiplot_plotoptions["assay_y_unit"]])
            cp.multiplot_data[iid]["error"] = float(Decimal(str(stderr)) / 
                                                    Decimal(str(self.multiplot_plotoptions["molar_absorption_coefficient"])) / 
                                                    conversion_factors[self.multiplot_plotoptions["assay_y_unit"]])

            cp.multiplot_data[iid]["relative_data_curvature"] = float(relative_nonlinearity)
            cp.multiplot_data[iid]["fit_slope"] = float(slope)
            cp.multiplot_data[iid]["fit_intercept"] = float(intercept)
            cp.multiplot_data[iid]["fit_r_squared"] = float(r_squared)
            cp.multiplot_data[iid]["polynomial_coefficients"] = list(polynomial_coefficients)
            cp.multiplot_data[iid]["polynomial_degree"] = int(polynomial_degree)
                                                            
            if cp.multiplot_data[iid]["parent"]:
                self.update_assay_y_for_datapoint(cp.multiplot_data[iid]["parent"])

        if not skip_save:
            self.save_to_db()

    # Update the y-values for a single datapoint of the assay, based on the selected assay type
    def update_assay_y_for_datapoint(self, datapoint, skip_save=False):
        if self.multiplot_plotoptions["assay_type"] is None:
            return

        elif self.multiplot_plotoptions["assay_type"] == "Michaelis-Menten":

            # In case the plot is Michaelis Menten, each datapoint should be the initial slope of the corresponding file
            
            ypoints = []
            errors = []

            # Check whether all plots in ["plots"] are still in cp.multiplot, otherwise remove them
            old_plots = self.multiplot_plotoptions["assay_datapoints"][datapoint].get("plots", [])
            self.multiplot_plotoptions["assay_datapoints"][datapoint]["plots"] = [iid for iid in self.multiplot_plotoptions["assay_datapoints"][datapoint]["plots"] if iid in cp.multiplot_data]

            if len(old_plots) != len(self.multiplot_plotoptions["assay_datapoints"][datapoint]["plots"]):
                print(f"Warning: Some plots in datapoint '{datapoint}' are no longer available and have been removed from the datapoint.")

            for iid in self.multiplot_plotoptions["assay_datapoints"][datapoint]["plots"]:
                if "y" in cp.multiplot_data[iid] and "error" in cp.multiplot_data[iid]:
                    ypoints.append(cp.multiplot_data[iid]["y"])
                    errors.append(cp.multiplot_data[iid]["error"])

            if len(ypoints) > 1:
                y = np.mean(ypoints)
                error = np.std(ypoints, ddof=1)

            elif len(ypoints) == 1:
                y = ypoints[0]
                error = errors[0]

            else:
                y = None
                error = None

            if y is not None:
                self.multiplot_plotoptions["assay_datapoints"][datapoint]["y"] = y
            else:
                if "y" in self.multiplot_plotoptions["assay_datapoints"][datapoint]: self.multiplot_plotoptions["assay_datapoints"][datapoint].pop("y")
            if error is not None:
                self.multiplot_plotoptions["assay_datapoints"][datapoint]["error"] = error
            else:
                if "error" in self.multiplot_plotoptions["assay_datapoints"][datapoint]: self.multiplot_plotoptions["assay_datapoints"][datapoint].pop("error")

        if not skip_save:
            self.save_to_db()

        if not self._idle_refreshTree:
            self._idle_refreshTree = self.after_idle(self.refreshTree)

    def update_assay_x_for_datapoint(self, datapoint):

        datapoints = self.multiplot_plotoptions["assay_datapoints"]
        datapoint_data = datapoints[datapoint]

        if "x" not in datapoint_data:
            datapoint_data["x"] = self.guess_x_from_name(datapoint)

        if not self._idle_adjust_assay_xlim:
            self._idle_adjust_assay_xlim = self.after_idle(self.adjust_assay_xlim)

    def guess_x_from_name(self, name):

        # Guess the x-value from the name of the datapoint
        # Since the x-values most probably are concentrations, a unit for concentrations is expected in the name after the actual concentration value
        # Perhaps this is either with the units "M" "mM", "uM"/"µM", "nM" or "pM" 
        # or mol/l, mmol/l, umol/l or µmol/l, nmol/l or pmol/l
        # or "molar", "millimolar", "micromolar", "nanomolar" or "picomolar"
        # Additionally it is probably in the shape of "{number}{unit}", "{number} {unit}" or "0.12_{unit}"

        # If autosorting is not enabled, do not guess x from the name
        if not self.multiplot_plotoptions["autosort_files"]:
            return 0.0

        units = {"molar": ["M", "mol/l", "molar"],
                 "millimolar": ["mM", "mmol/l", "millimolar"],
                 "micromolar": ["uM", "µM", "umol/l", "µmol/l", "micromolar"],
                 "nanomolar": ["nM", "nmol/l", "nanomolar"],
                 "picomolar": ["pM", "pmol/l", "picomolar"]}

        conversion_factors = {"molar": Decimal("1"),
                              "millimolar": Decimal("1e-3"),
                              "micromolar": Decimal("1e-6"),
                              "nanomolar": Decimal("1e-9"),
                              "picomolar": Decimal("1e-12")}

        unit_type_in_name = None
        where_unit_in_name = None

        for unit_type, unit_collection in units.items():
            for unit in unit_collection:
                if unit in name:
                    unit_type_in_name = unit_type
                    where_unit_in_name = name.find(unit)
                    break

        if unit_type_in_name is not None:
            numbers = re.findall(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", name)
            numbers = [float(num) if "." in num else int(num) for num in numbers]

            if numbers:
                # If there are multiple numbers, take the one that is closest to the unit
                closest_number = min(numbers, key=lambda x: abs(name.find(str(x)) - where_unit_in_name))
                x = closest_number

                plot_unit_type = None
                # Get the unit type of the plot and convert them to match properly
                for unit_type, unit_collection in units.items():
                    if self.multiplot_plotoptions["assay_x_unit"] in unit_collection:
                        plot_unit_type = unit_type
                        break

                if plot_unit_type is not None and plot_unit_type != unit_type_in_name:
                    # Convert the x-value to the unit of the plot
                    x = float(Decimal(str(x)) * conversion_factors[unit_type_in_name] / conversion_factors[plot_unit_type])

            else:
                x = 0.0

        else:
            x = 0.0

        return x

    # Function for updating the baseline smoothing method
    def update_baseline_smoothing(self, *args):

        old_smoothing_method = cp.plot_data["smoothing_method"]

        cp.plot_data["smoothing_method"] = self.smoothing_method.get()

        if old_smoothing_method != cp.plot_data["smoothing_method"]:
            self.recalculate_background_correction_term()

    # Function for updating the baseline correction method
    def update_background_correction(self, *args):

        old_correction_method = cp.plot_data["background_correction_method"]

        cp.plot_data["background_correction_method"] = self.background_correction_method.get()

        if old_correction_method != cp.plot_data["background_correction_method"]:
            self.recalculate_background_correction_term()

    def recalculate_background_correction_term(self, *args):

        # Get the unfiltered ypoints of the plot after blank subtraction
        ypoints = self.correct_baseline(self.iid, only_subtract_blanks=True)

        # First apply the smoothing method to the ypoints
        ypoints_smoothed = smooth_signal(ypoints, method=cp.plot_data["smoothing_method"])

        # Then apply the baseline correction method to the smoothed ypoints
        ypoints_baseline_corrected = ypoints_smoothed - get_baseline(ypoints_smoothed, method=cp.plot_data["background_correction_method"])

        # Then calculate the correction term so that ypoints_baseline_corrected = ypoints - correction_term
        correction_term = ypoints - ypoints_baseline_corrected

        cp.plot_data["background_correction"] = correction_term

        # Update the corrected ypoints
        cp.corrected_ypoints[self.iid] = self.correct_baseline(self.iid)

        cp.update_background_correction()

        self.save_to_db()

    # Update limits of x-Axis
    def update_xlim(self, *args):

        cp.update_xlim()
        self.save_to_db()

    # Update limits of y-Axis
    def update_ylim(self, change_adjust_y=True, skip_blit=False, *args):

        if change_adjust_y:
            self.adjust_y.set(False)

        cp.update_ylim(skip_blit)
        self.save_to_db()

    # Toggle autoadjust_y and adjust limits of y_Axis accordingly
    def autoadjust_y(self, skip_blit=False):

        cp.autoadjust_y(skip_blit=skip_blit)
        self.save_to_db()

    # Update linestyle
    def update_linestyle(self, *args):

        if cp.update_linestyle():
            self.save_to_db()

    # Update color
    def update_color(self, *args):
        if self.plottype in ["Assay", "MultiPlot"]:
            plot_data = self.multiplot_plotoptions
        else:
            plot_data = cp.plot_data

        old_color = plot_data["color"]
        try:
            cp.update_color()
            self.save_to_db()
        except Exception as e:
            if DEBUG: 
                print(f"An exception occured when updating the color: {e}")
            else:
                print("Unsupported color")
                
            self.color = old_color
            plot_data["color"] = old_color
            self.color_image = self.create_color_image(size=self.color_image.width(), color=old_color)
            self.color_btn.configure(image=self.color_image)

    def choose_color(self, *args):
        color = askcolor(color=self.color, parent=self)[1]
        if color is None:
            return

        self.color = mpl.colors.to_hex(color)
        self.color_image = self.create_color_image(size=self.color_image.width(), color=self.color)
        self.color_btn.configure(image=self.color_image)
        self.update_color()

    def choose_zero_line_color(self, *args):
        color = askcolor(color=self.zero_line_color, parent=self)[1]
        if color is None:
            return

        self.zero_line_color = mpl.colors.to_hex(color)
        self.zero_line_color_image = self.create_color_image(size=self.zero_line_color_image.width(), color=self.zero_line_color)
        self.zero_line_color_btn.configure(image=self.zero_line_color_image)
        self.update_zero_color()

    def update_ticks(self):

        cp.update_ticks()
        self.save_to_db()

    # Switch between vertical and horizontal labels
    def update_labels(self):

        cp.update_labels()
        self.save_to_db()

    ## Inset specific settings

    # Update the size of the inset axes
    def update_inset(self, *args):
        
        cp.update_inset(*args)
        self.save_to_db()

    def update_inset_borderpad(self, *args):
        old_borderpad = cp.plot_data["inset_borderpad"]
        try:
            cp.update_inset(updated_borderpad=True)
            self.save_to_db()
        except Exception as e:
            if DEBUG:
                print(f"An exception occurred when updating the inset borderpad: {e}")
            else:
                print("Invalid inset borderpad value")

            self.inset_borderpad.set(str(old_borderpad))
            cp.plot_data["inset_borderpad"] = old_borderpad

    def update_inset_fontsize(self, *args):

        cp.update_inset(updated_fontsize=True)
        self.save_to_db()


    # Update the limits of the x-Axis of the inset
    def update_xlim_inset(self):

        cp.update_xlim_inset()
        self.save_to_db()

    # Update the limits of the y-Axis of the inset
    def update_ylim_inset(self):

        cp.update_ylim_inset()
        self.save_to_db()

    # Mirror annotations
    def mirror_annotations_to_inset(self):

        cp.mirror_annotations_to_inset()
        self.save_to_db()

    # Switch between vertical and horizontal labels on the inset
    def update_inset_labels(self):

        cp.update_inset_labels()
        self.save_to_db()

    def update_simulation(self):

        cp.update_simulation()
        self.save_to_db()

    ## CD and Tm specific settings

    # Update whether to calculate MRE or not
    def update_MRE_settings(self, *args):

        cp.update_MRE_settings()
        self.save_to_db()

    # Redraw CD and Tm data points whenever CD parameters are changed
    def update_CD_points(self, autoadjust_y=True, *args):
        try:
            if self.nbr_of_residues.get() <= 0:
                self.nbr_of_residues.set(1)
            elif type(self.nbr_of_residues.get()) == float:
                self.nbr_of_residues.set(int(self.nbr_of_residues.get()))
        except tk.TclError as e:
            if DEBUG:
                print(f"Error in update_CD_points: {e}")
            return

        cp.update_CD_points(autoadjust_y=autoadjust_y)
        self.save_to_db()

    # Perform all CD fits and draw said fit
    def perform_CD_fits(self): 
        # Perform all important CD fits and save them as a dictionary to cp.plot_data['fits']

        xpoints = cp.plot_data["xpoints"]
        if self.iid not in cp.corrected_ypoints:
            cp.corrected_ypoints[self.iid] = self.correct_baseline(self.iid)

        MRE = cp.corrected_ypoints[self.iid] # MRE: Mean residue ellipticity 
        
        CD_fits = {"SCB":{},
                   "SLB":{},
                   "SQB":{},
                   "VHD":{},
                   "EGD":{},
        }

        ## Sigmoidal Constant Baseline

        try:
            # Perform curve fit
            popt_scb, pcov_scb = curve_fit(sigmoidal_constant_baseline,
                                        xpoints,
                                        MRE,
                                        p0=[MRE.min(),MRE.max(),100,50],
                                        bounds=([-np.inf, -np.inf, 0, -50], [np.inf, np.inf, 10000, 150]),
                                        maxfev=1000000000)
            
            # Update Dictionary
            for c, val in enumerate(["A", "B", "H", "Tm"]):
                CD_fits["SCB"][val], CD_fits["SCB"][f"{val}_err"] = return_fit_param(popt_scb, pcov_scb, c)
            CD_fits["SCB"]["R²"] = R_square(MRE, sigmoidal_constant_baseline(xpoints,*popt_scb))
            CD_fits["SCB"]["popt"] = popt_scb 

        except Exception as e:
            if DEBUG: print(f"An exception occurred during Sigmoidal Constant Baseline fit: {e}")

            # Update Dictionary with NaN values in case of an exception
            for c, val in enumerate(["A", "B", "H", "Tm"]):
                CD_fits["SCB"][val], CD_fits["SCB"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["SCB"]["R²"] = np.nan
            CD_fits["SCB"]["popt"] = [np.nan] * 4
            
        ## Sigmoidal Linear Baseline

        try:
            # Perform curve fit
            popt_slb, pcov_slb = curve_fit(sigmoidal_linear_baseline,
                                        xpoints,
                                        MRE,
                                        p0=[0,MRE.min(),0,MRE.max(),100,50],
                                        bounds=([-np.inf, -np.inf, -np.inf, -np.inf, 0, -50], [np.inf, np.inf, np.inf, np.inf, 10000, 150]),
                                        maxfev=1000000000)
            
            # Update Dictionary
            for c, val in enumerate(["a", "b", "c", "d", "H", "Tm"]):
                CD_fits["SLB"][val], CD_fits["SLB"][f"{val}_err"] = return_fit_param(popt_slb, pcov_slb, c)
            CD_fits["SLB"]["R²"] = R_square(MRE, sigmoidal_linear_baseline(xpoints,*popt_slb))
            CD_fits["SLB"]["popt"] = popt_slb

        except Exception as e:
            if DEBUG: print(f"An exception occurred during Sigmoidal Linear Baseline fit: {e}")

            # Update Dictionary with NaN values in case of an exception
            for c, val in enumerate(["a", "b", "c", "d", "H", "Tm"]):
                CD_fits["SLB"][val], CD_fits["SLB"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["SLB"]["R²"] = np.nan
            CD_fits["SLB"]["popt"] = [np.nan] * 6

        ## Sigmoidal Quadratic Baseline
        
        try:
            # Perform curve fit
            popt_sqb, pcov_sqb = curve_fit(sigmoidal_quadratic_baseline,
                                            xpoints,
                                            MRE,
                                            p0=[0, 0, MRE.min(), 0, 0, MRE.max(),100,50],
                                            bounds=([-np.inf, -np.inf, -np.inf, -np.inf, -np.inf, -np.inf, 0, -50], 
                                                    [np.inf, np.inf, np.inf, np.inf, np.inf, np.inf, 10000, 150]),
                                            maxfev=1000000000)
            
            # Update Dictionary
            for c, val in enumerate(["a", "b", "c", "d", "e", "f", "H", "Tm"]):
                CD_fits["SQB"][val], CD_fits["SQB"][f"{val}_err"] = return_fit_param(popt_sqb, pcov_sqb, c)
            CD_fits["SQB"]["R²"] = R_square(MRE, sigmoidal_quadratic_baseline(xpoints,*popt_sqb))
            CD_fits["SQB"]["popt"] = popt_sqb

        except Exception as e:
            if DEBUG: print(f"An exception occurred during Sigmoidal Quadratic Baseline fit: {e}")

            # Update Dictionary with NaN values in case of an exception
            for c, val in enumerate(["a", "b", "c", "d", "e", "f", "H", "Tm"]):
                CD_fits["SQB"][val], CD_fits["SQB"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["SQB"]["R²"] = np.nan
            CD_fits["SQB"]["popt"] = [np.nan] * 8

        # Check whether there are enough datapoints for gradient calculation:
        if len(xpoints) < 2:
            print("Warning: Not enough datapoints for gradient calculation.")

            # Update Dictionary with NaN values for VHD
            for c, val in enumerate(["A", "B", "H", "Tm"]):
                CD_fits["VHD"][val], CD_fits["VHD"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["VHD"]["R²"] = np.nan
            CD_fits["VHD"]["popt"] = [np.nan] * 4

            # Update Dictionary with NaN values for EGD
            for c, val in enumerate(["A", "B", "w", "Tm"]):
                CD_fits["EGD"][val], CD_fits["EGD"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["EGD"]["R²"] = np.nan
            CD_fits["EGD"]["popt"] = [np.nan] * 4

            cp.plot_data["fits"] = CD_fits
                    
            # Update fit can also be used in case fit visibility changes
            cp.update_fit()
            self.refreshTree()
            self.save_to_db()

            return

        ## Calculate derivative of mean residue ellipticity
        dMRE_dT = np.gradient(MRE, xpoints)

        ## Van't Hoff Derivative
        try:
            # Smooth data for initial fit
            if dMRE_dT.size < 9:
                if dMRE_dT.size % 2 == 0:
                    window_length = dMRE_dT.size - 1
                else:
                    window_length = dMRE_dT.size
            else:
                window_length = 9

            # This is an edge case which is highly unlikely to happen because it assumes that the user is trying to fit data from just a two- or one-point measurement
            if window_length < 1:
                window_length = 1

            smooth_dMRE_dT = savgol_filter(x=dMRE_dT, window_length=window_length, polyorder=0, mode="nearest")
            popt_vhd_i, _ = curve_fit(vant_hoff,
                                    xpoints,
                                    smooth_dMRE_dT,
                                    p0=[smooth_dMRE_dT.max()-smooth_dMRE_dT.min(),0 , 100, xpoints[np.argmin(smooth_dMRE_dT)]],
                                    bounds=([0, -np.inf, 0, -50 ], [np.inf, np.inf, 10000, 150]),
                                    maxfev=1000000000)

            # Fit on real data with parameters of initial fit
            popt_vhd, pcov_vhd = curve_fit(vant_hoff,
                                        xpoints,
                                        dMRE_dT,
                                        p0=popt_vhd_i,
                                        bounds=([0, -np.inf, 0, -50], [np.inf, np.inf, 10000, 150]),
                                        maxfev=1000000000)

            # Update Dictionary
            for c, val in enumerate(["A", "B", "H", "Tm"]):
                CD_fits["VHD"][val], CD_fits["VHD"][f"{val}_err"] = return_fit_param(popt_vhd, pcov_vhd, c)
            CD_fits["VHD"]["R²"] = R_square(dMRE_dT, vant_hoff(xpoints,*popt_vhd))
            CD_fits["VHD"]["popt"] = popt_vhd

        except Exception as e:
            if DEBUG: print(f"An exception occurred during Van't Hoff Derivative fit: {e}")

            # Update Dictionary with NaN values in case of an exception
            for c, val in enumerate(["A", "B", "H", "Tm"]):
                CD_fits["VHD"][val], CD_fits["VHD"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["VHD"]["R²"] = np.nan
            CD_fits["VHD"]["popt"] = [np.nan] * 4

        ## Empirical Gauss Derivative
        try:
            popt_egd, pcov_egd = curve_fit(gaussian,
                                        xpoints,
                                        dMRE_dT,
                                        p0=[dMRE_dT.min(),dMRE_dT.max() , (xpoints.max()-xpoints.min())/2, xpoints[np.argmin(smooth_dMRE_dT)]],
                                        bounds=([-np.inf, -np.inf, 0, -50], [0, np.inf, np.inf, 150]),
                                        maxfev=1000000000)

            # Update Dictionary
            for c, val in enumerate(["A", "B", "w", "Tm"]):
                CD_fits["EGD"][val], CD_fits["EGD"][f"{val}_err"] = return_fit_param(popt_egd, pcov_egd, c)
            CD_fits["EGD"]["R²"] = R_square(dMRE_dT, gaussian(xpoints,*popt_egd))
            CD_fits["EGD"]["popt"] = popt_egd
            
        except Exception as e:
            if DEBUG: print(f"An exception occurred during Empirical Gauss Derivative fit: {e}")

            # Update Dictionary with NaN values in case of an exception
            for c, val in enumerate(["A", "B", "w", "Tm"]):
                CD_fits["EGD"][val], CD_fits["EGD"][f"{val}_err"] = (np.nan, np.nan)
            CD_fits["EGD"]["R²"] = np.nan
            CD_fits["EGD"]["popt"] = [np.nan] * 4

        cp.plot_data["fits"] = CD_fits
        
        # Update fit can also be used in case fit visibility changes
        cp.update_fit()
        self.refreshTree()
        self.save_to_db()

    def perform_assay_fit(self, skip_blit=False, *args):

        xpoints = np.asarray(self.multiplot_plotoptions["xpoints"], dtype=float)
        ypoints = np.asarray(self.multiplot_plotoptions["ypoints"], dtype=float)
        sigma = np.asarray(self.multiplot_plotoptions["sigma"], dtype=float)

        # The plot contains a synthetic origin for display. It has zero
        # uncertainty and must not be passed to a weighted fit.
        if len(xpoints) > 0 and len(ypoints) > 0 and len(sigma) > 0:
            xpoints = xpoints[1:]
            ypoints = ypoints[1:]
            sigma = sigma[1:]

        valid = np.isfinite(xpoints) & np.isfinite(ypoints)
        if len(sigma) == len(xpoints):
            valid &= np.isfinite(sigma)

        xpoints = xpoints[valid]
        ypoints = ypoints[valid]
        sigma = sigma[valid] if len(sigma) == len(valid) else np.array([])

        if len(xpoints) < 3 or len(ypoints) < 3:
            if DEBUG: print("Not enough datapoints for fitting. At least 3 datapoints are required.")
            self.save_to_db()
            return

        # Check whether all sigma values actually measure the same thing (standard deviation of the fit vs. standard error of the mean)
        # If it is a mixture do not use sigma and perform an unweighted fit
        all_sigma_measures_equal = (all([len(datapoint["plots"]) > 1 for datapoint in self.multiplot_plotoptions["assay_datapoints"].values() if "plots" in datapoint and len(datapoint["plots"]) > 0]) or 
                                    all([len(datapoint["plots"]) == 1 for datapoint in self.multiplot_plotoptions["assay_datapoints"].values() if "plots" in datapoint and len(datapoint["plots"]) > 0]))


        # Only use a weighted fit if the statistical measures used for sigma are the same (e.g. whether the datapoints have multiple files or just one)
        use_sigma = (all_sigma_measures_equal and 
                     len(sigma) == len(xpoints) and 
                     np.all(sigma > 0))
        if len(sigma) == len(xpoints) and not use_sigma and DEBUG:
            print("Invalid or zero assay uncertainties; performing an unweighted fit.")

        elif not all_sigma_measures_equal:
            print("Warning: The assay datapoints have a mixture of statistical measures for the uncertainties. Performing an unweighted fit.")

        # Set the bounds to physically meaningful values: Vmax and Km should be positive 
        # The initial guess for Vmax is the maximum y-value, while the initial guess for Km is the x-value at half of the maximum y-value
        # Perform curve fit
        popt, pcov = curve_fit(michaelis_menten,
                               xpoints,
                               ypoints,
                               p0=[xpoints[np.argmin(np.abs(ypoints - ypoints.max()/2))], ypoints.max()],
                               sigma=sigma if use_sigma else None,
                               absolute_sigma=use_sigma,
                               bounds=([0, 0], [np.inf, np.inf]),
                               maxfev=1000000000)
        r_squared = R_square(ypoints, michaelis_menten(xpoints, *popt))

        self.multiplot_plotoptions["assay_fit"] = {"popt": popt, "pcov": pcov, "r_squared": r_squared}

        if (self.multiplot_plotoptions["assay_fit"] and 
            "popt" in self.multiplot_plotoptions["assay_fit"] and 
            len(self.multiplot_plotoptions["assay_fit"]["popt"]) == 2):

            km_error, vmax_error = np.sqrt(np.diag(self.multiplot_plotoptions["assay_fit"]["pcov"]))

            self.assay_fit_Km.set(f"{self.multiplot_plotoptions['assay_fit']['popt'][0]:.4g} ± {km_error:.2g} {self.multiplot_plotoptions['assay_x_unit']}")
            self.assay_fit_vmax.set(f"{self.multiplot_plotoptions['assay_fit']['popt'][1]:.4g} ± {vmax_error:.2g} {self.multiplot_plotoptions['assay_y_unit']}")
            self.assay_fit_r2.set(f"{self.multiplot_plotoptions['assay_fit']['r_squared']:.4g}")

        else:
            self.assay_fit_Km.set(f"0 {self.multiplot_plotoptions['assay_x_unit']}")
            self.assay_fit_vmax.set(f"0 {self.multiplot_plotoptions['assay_y_unit']}")
            self.assay_fit_r2.set("0")

        self.update_assay_fit(skip_blit=skip_blit)

    # Change ylabel and/or selected wavelength in the blank in case a CD blank is selected for Tm plots
    def update_ylabel(self, *args):

        cp.update_ylabel()
        self.save_to_db()

    # Toggle fit visibility
    def update_fit(self, skip_blit=False):

        # Update fit can also be used in case a fit changes due to new perform_CD_fit
        cp.update_fit(skip_blit)
        self.save_to_db()

    # Show the zero line in the plot
    def toggle_zero_line(self, *args):

        cp.toggle_zero_line()
        self.save_to_db()

    # Change the linestyle of the zero line in the plot
    def update_zero_linestyle(self, *args):

        if cp.update_zero_linestyle():
            self.save_to_db()
        
    # Change the linewidth of the zero line in the plot
    def update_zero_linewidth(self, *args):

        cp.update_zero_linewidth()
        self.save_to_db()

    # Change the color of the zero line in the plot
    def update_zero_color(self, *args):

        cp.update_zero_color()
        self.save_to_db()

    ## HPLC specific settings

    # Toggle integral visibility
    def toggle_integrals(self):

        cp.toggle_integrals()
        self.save_to_db()

    def toggle_HPLC_baseline(self):

        self.HPLC_baseline_visible = not self.HPLC_baseline_visible

        cp.toggle_HPLC_baseline(self.HPLC_baseline_visible)

    # Update the HPLC baselines and therefore polygons as soon as changes were made
    def update_HPLC_baseline_mode(self):

        cp.update_HPLC_baseline_mode()
        self.save_to_db()

    def update_linear_HPLC_baseline(self):

        cp.update_linear_HPLC_baseline()
        self.save_to_db()

    def update_constant_HPLC_baseline(self):

        cp.update_constant_HPLC_baseline()
        self.save_to_db()

    # MultiPlot specific
    
    def update_multiplot_lines(self, *args):
        self.adjust_y.set(True)
        
        cp.update_multiplot_lines()
        self.save_to_db()

    def update_multiplot_fit(self, *args):

        cp.update_multiplot_fit()
        self.save_to_db()

    def apply_colormap(self, *args):

        cp.apply_colormap()
        self.refreshTree()
        self.save_to_db()

    def update_multiplot_labels(self, *args):

        cp.update_multiplot_labels()
        self.save_to_db()

    def update_multiplot_label_color(self):

        cp.update_multiplot_label_color()
        self.save_to_db()

    def update_multiplot_label_xposition(self, *args):

        cp.update_multiplot_label_xposition()
        self.save_to_db()

    def update_multiplot_label_yposition(self, *args):
    
        cp.update_multiplot_label_yposition()
        self.save_to_db()

    def update_multiplot_label_fontsize(self, *args):
        
        cp.update_multiplot_label_fontsize()
        self.save_to_db()

    def update_multiplot_legend(self, *args):

        cp.update_multiplot_legend()
        self.save_to_db()

    def update_multiplot_legend_placement(self, *args):

        cp.update_multiplot_legend_placement()
        self.save_to_db()

    def update_multiplot_label(self, iid):
        cp.update_multiplot_label(iid)
        self.save_to_db()

    def update_multiplot_linewidth(self, iid):
        cp.update_multiplot_linewidth(iid)
        self.save_to_db()
    
    def update_multiplot_linestyle(self, iid):
        cp.update_multiplot_linestyle(iid)
        self.save_to_db()

    def update_multiplot_alpha(self, iid):
        cp.update_multiplot_alpha(iid)
        self.save_to_db()

    def update_multiplot_position(self, iid, skip_blit=False):
        cp.update_multiplot_position(iid, skip_blit=skip_blit)
        self.after_idle(self.save_to_db)

    def update_multiplot_positions(self):
        cp.update_multiplot_positions()
        self.save_to_db()

    def update_multiplot_color(self, iid):
        cp.update_multiplot_color(iid)
        self.save_to_db()

    def refresh(self, *args, axes=None, refreshTree=False, mirror=False, resize=False):

        if self._lazy_refresh:
            self.after_cancel(self._lazy_refresh)
            self._lazy_refresh = None

        # Check whether refresh was called as an event
        if len(args) >= 1:     
            for arg in args:
                event = arg if isinstance(arg, tk.Event) else None
        else:
            event = None

        if event is not None:
            if isinstance(event.widget, ttk.Entry):
                if event.widget.get() in ["","-"]:
                    event.widget.delete(0, tk.END)
                    event.widget.insert(0, 0)
            
                
        if axes == None: axes = cp.ax

        cp.refresh(*args, axes=axes, refreshTree=refreshTree, mirror=mirror, )

        # Save new information only when not resizing
        if not resize:
            self.save_to_db()

    def save_to_db(self, immediate=False):
        if self.iid is None:
            return

        if self._save_to_db is not None:
            self.after_cancel(self._save_to_db)
            self._save_to_db = None

        if immediate:
            db.save(self.iid, MultiPlot=self.plottype in ["Assay", "MultiPlot"])
        else:
            self._save_to_db = self.after(250, self._save_to_db_now)

    def _save_to_db_now(self):
        self._save_to_db = None
        if self.iid is not None:
            db.save(self.iid, MultiPlot=self.plottype in ["Assay", "MultiPlot"])

    def refreshTree(self):

        if self.plottype in ["MALDI", "Fluorescence", "UV/vis"]:
            tree = self.plotinfo

        elif self.plottype == "HPLC":
            tree = self.plotprops_widgets[0]

            # Update Integration "Main" Tree
            # remove all widgets in the tree
            self.plotinfo.delete(*self.plotinfo.get_children())
            for data in cp.plot_data["integral_dict"]:
                self.plotinfo.insert("",tk.END, text=float(data), values=(round(float(cp.plot_data["integral_dict"][data][0]), 1),
                                                                          round(float(cp.plot_data["integral_dict"][data][1]), 1),
                                                                          round(float(data), 1),
                                                                          round(float(cp.plot_data["integral_dict"][data][2]), 6),
                                                                          str(round(float(cp.plot_data["integral_dict"][data][3]), 2))+"%",
                                                                          cp.plot_data["integral_dict"][data][4]))

            self.plotinfo.sort_treeview()

        elif self.plottype == "MultiPlot":
            # Update Plot Tree
            self.plotinfo.delete(*self.plotinfo.get_children())
            iids = list(cp.multiplot_data.keys())
            iids.remove("PlotOptions")
            positions = [cp.multiplot_data[iid]["position"] for iid in iids]
            iids_sorted = [iid for _, iid in sorted(zip(positions, iids),reverse=True)]

            try:
                for iid in iids_sorted:
                    size = ceil(18.75*self.scaling)
                    alpha_border_size = ceil(size/8)
                    gray_border_size = ceil(1.5*alpha_border_size)
                    rgb_color = return_regular_rgb_tuple(cp.multiplot_data[iid]["color"])

                    hex_color = "#{:02x}{:02x}{:02x}".format(*map(int,rgb_color))
                    img = tk.PhotoImage(width=size, height=size)
                    # Put a gray block inside to create a nice border around the color of the plot, this also leaves some padding on the right
                    img.put("darkgray", to=(0,
                                        gray_border_size,
                                        size-2*gray_border_size,
                                        size-gray_border_size))
                    
                    # Fill the image with the current color of the plot
                    img.put(hex_color, to=(2*alpha_border_size-gray_border_size,
                                            2*alpha_border_size,
                                            size-2*alpha_border_size-gray_border_size,
                                            size-2*alpha_border_size))

                    self.plotinfo.color_images[iid] = img

                    self.plotinfo.insert("",
                                            tk.END, 
                                            iid=iid, 
                                            text=db.browser_saves[iid]["filename"],
                                            image=self.plotinfo.color_images[iid],
                                            values=(cp.multiplot_data[iid]["filename"],
                                                    cp.multiplot_data[iid]["linewidth"],
                                                    str(cp.multiplot_data[iid]["linestyle"]),
                                                    cp.multiplot_data[iid]["alpha"],
                                                    cp.multiplot_data[iid]["position"]),
                                    )
            except AttributeError:
                pass

            self.plotinfo.show_watermark()

            return

        elif self.plottype == "Tm":
            # Remove all children in the tree
            self.plotinfo.delete(*self.plotinfo.get_children())

            try: fits = cp.plot_data["fits"]
            except KeyError: fits = {}
            
            if any(key in fits for key in ["SCB","SLB", "SQB", "VHD","EGD"]):

                if "SCB" in fits:
                    self.sigmoidal_cb_curve_fit = self.plotinfo.insert("", tk.END, values=(
                                                                                        "Sigmoidal + Constant Baseline", # Curve Fit Model
                                                                                        f"{fits['SCB']['A']:.4g} ± {fits['SCB']['A_err']:.2g}", # Parameter A
                                                                                        f"{fits['SCB']['B']:.4g} ± {fits['SCB']['B_err']:.2g}", # Parameter B
                                                                                        f"{fits['SCB']['R²']:.4g}", # R²
                                                                                        f"{fits['SCB']['H']:.4g} ± {fits['SCB']['H_err']:.2g}", # H
                                                                                        f"{fits['SCB']['Tm']:.4g} ± {fits['SCB']['Tm_err']:.2g}", # Tm
                                                                                        ),
                                                                    tags=["current"] if cp.plot_data["Tm_method"] == "SCB" else [],
                                                    )
                else:
                    self.sigmoidal_cb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Constant Baseline","","","","",""))

                if "SLB" in fits:
                    self.sigmoidal_lb_curve_fit = self.plotinfo.insert("", tk.END, values=(
                                                                                        "Sigmoidal + Linear Baseline", # Curve Fit Model
                                                                                        f"{fits['SLB']['a']:.4g} ± {fits['SLB']['a_err']:.2g} * x + {fits['SLB']['b']:.4g} ± {fits['SLB']['b_err']:.2g}", # Parameter A
                                                                                        f"{fits['SLB']['c']:.4g} ± {fits['SLB']['c_err']:.2g} * x + {fits['SLB']['d']:.4g} ± {fits['SLB']['d_err']:.2g}", # Parameter B
                                                                                        f"{fits['SLB']['R²']:.4g}", # R²
                                                                                        f"{fits['SLB']['H']:.4g} ± {fits['SLB']['H_err']:.2g}", # H
                                                                                        f"{fits['SLB']['Tm']:.4g} ± {fits['SLB']['Tm_err']:.2g}", # Tm
                                                                                        ),
                                                                    tags=["current"] if cp.plot_data["Tm_method"] == "SLB" else [],
                                                    )
                else:
                    self.sigmoidal_lb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Linear Baseline","","","","",""))
                                    
                if "SQB" in fits:
                    self.sigmoidal_qb_curve_fit = self.plotinfo.insert("", tk.END, values=(
                                                                                        "Sigmoidal + Quadratic Baseline", # Curve Fit Model
                                                                                            f"{fits['SQB']['a']:.4g} ± {fits['SQB']['a_err']:.2g} * x² + {fits['SQB']['b']:.4g} ± {fits['SQB']['b_err']:.2g} * x + {fits['SQB']['c']:.4g} ± {fits['SQB']['c_err']:.2g}", # Parameter A
                                                                                            f"{fits['SQB']['d']:.4g} ± {fits['SQB']['d_err']:.2g} * x² + {fits['SQB']['e']:.4g} ± {fits['SQB']['e_err']:.2g} * x + {fits['SQB']['f']:.4g} ± {fits['SQB']['f_err']:.2g}", # Parameter B
                                                                                            f"{fits['SQB']['R²']:.4g}", # R²
                                                                                            f"{fits['SQB']['H']:.4g} ± {fits['SQB']['H_err']:.2g}", # H
                                                                                            f"{fits['SQB']['Tm']:.4g} ± {fits['SQB']['Tm_err']:.2g}", # Tm
                                                                                        ),
                                                                        tags=["current"] if cp.plot_data["Tm_method"] == "SQB" else [],
                                                    )
                else:
                    self.sigmoidal_qb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Quadratic Baseline","","","","",""))

                if "VHD" in fits:
                    self.vant_hoff_curve_fit = self.plotinfo.insert("", tk.END, values=(
                                                                                        "Van't Hoff Derivative", # Curve Fit Model
                                                                                        f"{fits['VHD']['A']:.4g} ± {fits['VHD']['A_err']:.2g}", # Parameter A
                                                                                        f"{fits['VHD']['B']:.4g} ± {fits['VHD']['B_err']:.2g}", # Parameter B
                                                                                        f"{fits['VHD']['R²']:.4g}", # R²
                                                                                        f"{fits['VHD']['H']:.4g} ± {fits['VHD']['H_err']:.2g}", # H
                                                                                        f"{fits['VHD']['Tm']:.4g} ± {fits['VHD']['Tm_err']:.2g}", # Tm
                                                                                        ),
                                                                    tags=["current"] if cp.plot_data["Tm_method"] == "VHD" else [],
                                                    )
                else:
                    self.vant_hoff_curve_fit = self.plotinfo.insert("", tk.END, values=("Van't Hoff Derivative","","","","",""))
                    

                if "EGD" in fits:
                    self.empirical_Gauss_curve_fit = self.plotinfo.insert("", tk.END, values=(
                                                                                            "Empirical Gauss Derivative", # Curve Fit Model
                                                                                            f"{fits['EGD']['A']:.4g} ± {fits['EGD']['A_err']:.2g}", # Parameter A
                                                                                            f"{fits['EGD']['B']:.4g} ± {fits['EGD']['B_err']:.2g}", # Parameter B
                                                                                            f"{fits['EGD']['R²']:.4g}", # R²
                                                                                            f"Width: {fits['EGD']['w']:.4g} ± {fits['EGD']['w_err']:.2g}", # w
                                                                                            f"{fits['EGD']['Tm']:.4g} ± {fits['EGD']['Tm_err']:.2g}", # Tm
                                                                                            ),
                                                                        tags=["current"] if cp.plot_data["Tm_method"] == "EGD" else [],
                                                    )
                else:
                    self.empirical_Gauss_curve_fit = self.plotinfo.insert("", tk.END, values=("Empirical Gauss Derivative","","","","",""))

            else:
                self.sigmoidal_cb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Constant Baseline","","","","",""))
                self.sigmoidal_lb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Linear Baseline","","","","",""))
                self.sigmoidal_qb_curve_fit = self.plotinfo.insert("", tk.END, values=("Sigmoidal + Quadratic Baseline","","","","",""))

                self.vant_hoff_curve_fit = self.plotinfo.insert("", tk.END, values=("Van't Hoff Derivative","","","","",""))
                self.empirical_Gauss_curve_fit = self.plotinfo.insert("", tk.END, values=("Empirical Gauss Derivative","","","","",""))
            
            return

        elif self.plottype == "Assay":

            if self._idle_refreshTree:
                self.after_cancel(self._idle_refreshTree)
                self._idle_refreshTree = None

            # Update Plot Tree
            self.plotinfo.delete(*self.plotinfo.get_children())
            iids = list(cp.multiplot_data.keys())
            iids.remove("PlotOptions")
  
            pools = list(self.multiplot_plotoptions["assay_datapoints"]) 

            # Sort the pools using natural sorting
            sorted_pools = natsorted(pools)

            # First add the individual pools
            try:

                for pool in sorted_pools:
                    if pool in self.multiplot_plotoptions["assay_datapoints"]:
                        if "x" in self.multiplot_plotoptions["assay_datapoints"][pool]:
                            x = self.multiplot_plotoptions["assay_datapoints"][pool]["x"]
                        else:
                            x = ""
                        if "y" in self.multiplot_plotoptions["assay_datapoints"][pool]:
                            y = self.multiplot_plotoptions["assay_datapoints"][pool]["y"]
                        else:
                            y = ""
                        if "error" in self.multiplot_plotoptions["assay_datapoints"][pool]:
                            error = self.multiplot_plotoptions["assay_datapoints"][pool]["error"]
                        else:
                            error = ""
                    
                    else:
                        x = ""
                        y = ""
                        error = ""

                    self.plotinfo.insert("",
                                         tk.END, 
                                         iid=pool, 
                                         text=pool,
                                         values=("",
                                                 f"{x} {self.multiplot_plotoptions['assay_x_unit']}" if x else "",
                                             f"{y:.3g} ± {error:.2g} {self.multiplot_plotoptions['assay_y_unit']}" if y and error else y,
                                            ),
                                         open=False,
                                    )

            except KeyError:
                pass

            # Now add the individual files
            try:
                for iid in iids:

                    if iid in cp.multiplot_data:

                        if "y" in cp.multiplot_data[iid]:
                            y = cp.multiplot_data[iid]["y"]
                        else:
                            y = ""
                        if "error" in cp.multiplot_data[iid]:
                            error = cp.multiplot_data[iid]["error"]
                        else:
                            error = ""
                        if "relative_data_curvature" in cp.multiplot_data[iid]:
                            relative_data_curvature = cp.multiplot_data[iid]["relative_data_curvature"]
                        else:
                            relative_data_curvature = ""
                        if "fit_r_squared" in cp.multiplot_data[iid]:
                            fit_r_squared = cp.multiplot_data[iid]["fit_r_squared"]
                        else:
                            fit_r_squared = ""
                    
                    else:
                        y = ""
                        error = ""

                    self.plotinfo.insert(cp.multiplot_data[iid]["parent"] if cp.multiplot_data[iid]["parent"] else "",
                                         tk.END, 
                                         iid=iid, 
                                         text="",
                                         values=(cp.multiplot_data[iid]["filename"],
                                                 "",
                                                 f"{y:.3g} ± {error:.2g} {self.multiplot_plotoptions['assay_y_unit']}" if y and error else y,
                                                 f"{fit_r_squared:.3g}" if fit_r_squared else "",
                                                 f"{relative_data_curvature:.2%}" if relative_data_curvature else ""
                                                 )
                                    )
            except AttributeError:
                pass

            self.plotinfo.show_watermark()
            self.plotinfo.sort_treeview()

            return            

        else:
            return

        # remove all widgets in the tree
        tree.insert("",tk.END,values=("Test"))
        tree.delete(*tree.get_children())

        if self.plottype == "MALDI":
            peak_dicts = [cp.plot_data["peak_dict"], cp.plot_data["inset_peak_dict"]]
        elif self.plottype != "Assay":
            peak_dicts = [cp.plot_data["peak_dict"],]
        else:
            return

        for count, peak_dict in enumerate(peak_dicts):
            for data in peak_dict:
                if self.plottype == "MALDI":
                    # Append Items for the Simulation of Spectra, such as the Formula and yes/no 
                    if len(peak_dict[data]) <= 4:
                        if DEBUG: print("Appending")
                        peak_dict[data].append("")
                        peak_dict[data].append("No")
                    if len(peak_dict[data]) <= 6:
                        if DEBUG: print("Appending")
                        peak_dict[data].append("0.0")
                        peak_dict[data].append("0.0")
                    if len(peak_dict[data]) <= 8:
                        if DEBUG: print("Inserting")
                        peak_dict[data].insert(5, "1")
                    
                    # Calculate monoisotopic mass and insert it as well
                    if peak_dict[data][4] != "":
                        formula_string = self.check_if_peptide(peak_dict[data][4])
                        try:
                            f = Formula(formula_string)
                            monomass = f.monoisotopic_mass
                        except:
                            monomass = 0.0
                    else:
                        monomass = 0.0
                
                peak = data if count == 0 else "i:"+str(data)

                if self.plottype == "MALDI":
                    tree.insert("",
                                tk.END, 
                                values=(peak,
                                        peak_dict[data][0], 
                                        peak_dict[data][4], 
                                        monomass, 
                                        peak_dict[data][5], 
                                        peak_dict[data][6], 
                                        peak_dict[data][7], 
                                        peak_dict[data][8]
                                    )
                            )
                else:
                    tree.insert("",
                                tk.END, 
                                values=(peak,
                                        peak_dict[data][0], 
                                    )
                            )
                
        tree.sort_treeview()

    def get_plottype(self, iid, MultiPlot: bool = False):

        if MultiPlot:
            plottype = db.multiplot_browser_saves[iid]["plottype"]
        else:
            plottype = db.browser_saves[iid]["plottype"]

        return plottype

    def check_if_peptide(self, sequence):
        # Check if the sequence is a peptide perhaps containing defined C and N terminii
        abbreviations = {"Ac": "C2H3O", 
                         "Me": "CH3", 
                         "Fmoc": "C15H11O2", 
                         "tBu": "C4H9"}
        try:
            # If this is a regular peptide sequence without any special changes, molmass already handles this. So this function should only handle special cases
            # Peptides are often written with a leading "X-" and a trailing "-XX" to indicate the specific terminii. Therefore check for this.
            if sequence.count("-") == 2:
                split_sequence = sequence.split("-")

                # Check whether the entire peptide sequence is inside of a peptide() block
                if "peptide(" in split_sequence[0] and ")" in split_sequence[2]:
                    # Remove the peptide() block and check whether the remaining sequence is a valid peptide sequence
                    peptide_bracket_pos1 = split_sequence[0].find("peptide(")
                    peptide_bracket_pos2 = split_sequence[2].find(")")
                    before_peptide = split_sequence[0][:peptide_bracket_pos1]
                    after_peptide = split_sequence[2][peptide_bracket_pos2+1:]
                    N_terminus = split_sequence[0][peptide_bracket_pos1+8:]
                    C_terminus = split_sequence[2][:peptide_bracket_pos2]
                else:
                    before_peptide = ""
                    after_peptide = ""
                    N_terminus = split_sequence[0]
                    C_terminus = split_sequence[2]

                peptide = split_sequence[1]
                peptide_str = from_peptide(peptide)

                for abbreviation in abbreviations:
                    C_terminus = C_terminus.replace(abbreviation, abbreviations[abbreviation])
                    N_terminus = N_terminus.replace(abbreviation, abbreviations[abbreviation])

                peptide_str = peptide_str.replace("H2O", "", 1)

                complete_sequence = f"{before_peptide}{N_terminus}{peptide_str}{C_terminus}{after_peptide}"
                return complete_sequence

            else:
                return sequence

        except Exception:
            return sequence

    def correct_baseline(self, iid, only_subtract_blanks=False, skip_MRE=False):

        ypoints = db.save_data[iid]["ypoints"]
        baseline_iid = db.save_data[iid]["baseline_iid"]

        if DEBUG: print(f"Blank IID: {baseline_iid}")

        # When a baseline has been selected 
        if baseline_iid is not None:

            db.load(baseline_iid, False)

            baseline_ypoints = self.correct_baseline(baseline_iid, skip_MRE=True)
            
            # Check whether the size of both numpy arrays are equal to avoid errors and return the correct baseline ypoints

            if ypoints.size == baseline_ypoints.size:
                corrected_ypoints = self.calc_MRE_from_ypoints(iid, ypoints - baseline_ypoints, skip_MRE=skip_MRE)
                
            else:
                if ((db.browser_saves[iid]["plottype"] == "Tm" and db.browser_saves[baseline_iid]["plottype"] == "CD") or 
                    (self.plottype == "MultiPlot" and self.multiplot_plotoptions["plottype"] == "Tm" and db.browser_saves[baseline_iid]["plottype"] == "CD")):
                    # In case of a thermal denaturation curve, you might also use a CD curve as blank. In that case only the y_value of the selected wavelength is necessary.
                    # Find the index on the x axis corresponding to the selected wavelength
                    array_index = np.where(db.save_data[baseline_iid]["xpoints"] == db.save_data[iid]["wavelength"])

                    # Get the corresponding y_value
                    y_val = baseline_ypoints[array_index]
    
                    corrected_ypoints = self.calc_MRE_from_ypoints(iid, ypoints - y_val, skip_MRE=skip_MRE)

                else:
                    print("Invalid array size of blank")
                    corrected_ypoints = self.calc_MRE_from_ypoints(iid, ypoints, skip_MRE=skip_MRE)

        else:
            if DEBUG: print("No blank selected")
            corrected_ypoints = self.calc_MRE_from_ypoints(iid, ypoints, skip_MRE=skip_MRE)

        # Apply baseline correction first by smoothing the baseline with the chosen method
        if ((db.save_data[iid]["background_correction_method"] != "None" or db.save_data[iid]["smoothing_method"] != "None") and db.save_data[iid]["background_correction"].size != 0 and 
            db.save_data[iid]["background_correction"].size == ypoints.size and not only_subtract_blanks):
            # The baseline correction term is a numpy array calculated from the original ypoints and the selected correction and smoothing methods. 
            # This calculation returns ypoints as the smoothed and corrected ypoints.
            baseline_corrected_ypoints = corrected_ypoints - db.save_data[iid]["background_correction"]

        else:
            baseline_corrected_ypoints = corrected_ypoints.copy()

        return baseline_corrected_ypoints

    def calc_MRE_from_ypoints(self, iid, ypoints, skip_MRE=False):
        
        if self.plottype == "MultiPlot":
            plottype = self.multiplot_plotoptions["plottype"]
        else:
            plottype = db.browser_saves[iid]["plottype"]

        if skip_MRE or ((plottype not in ["CD", "Tm"]) or (self.plottype in ["CD", "Tm"] and iid == self.iid and not db.save_data[iid]["calc_MRE"]) or 
            (self.plottype == "MultiPlot" and not self.multiplot_plotoptions["calc_MRE"])):

            return ypoints
        
        conc = db.save_data[iid]["concentration"]*10**(-3)
        pathlength = db.save_data[iid]["pathlength"]
        num_res = db.save_data[iid]["nbr_of_residues"]
        
        return ypoints / (conc*pathlength*num_res) / (10**3)
    
    # Improved drag and drop logic

    def create_moving_entry(self, treeview, selected_iid, column, current_selection, selected_values, x, y):

        # Clear all currently floating entries in case deletion did not take place for one of them
        for entry in self.floating_entries:
            entry.destroy()
        
        # Create a floating drag preview that does not capture mouse input.
        self.entry = tk.Toplevel(self.winfo_toplevel())
        self.entry.withdraw()
        self.entry.overrideredirect(True)
        self.entry.attributes("-topmost", True)
        try:
            self.entry.attributes("-disabled", True)
        except tk.TclError:
            pass

        font = tk.font.nametofont("TkDefaultFont").actual()

        self.entry_label = tk.Label(
            self.entry,
            takefocus=False,
            cursor="arrow",
            compound="left",
            bg=self.cget("background"),
            highlightthickness=0,
            font=(font["family"], ceil(font["size"]*1.25)),
        )

        self.entry_label.pack(anchor="nw")

        self.floating_entries.append(self.entry)

        # Save bounding box to widget and initial_x and y for comparison using the after method
        self.entry.column_box = treeview.bbox(selected_iid, column)

        # Check whether iid is part of the current selection and whether multiple items are part of the selection to decide whether multiple entries are supposed to be moved or just one
        if selected_iid in current_selection and len(current_selection)>1:
            if DEBUG: print("Multiple items selected")
            selected_values = f"{selected_values} + {len(current_selection)-1}"
            self.entry.iids = current_selection

        else:
            self.entry.iids = (selected_iid,)

        # Setup the correct image to show in the moving entry
        skip_image = False
        if treeview in [self.browser, self.multiplot_browser]:
            tags = treeview.item(item=selected_iid, option="tags")
            if "Project_filled" in tags:
                image = self.folder_filled_image
            elif "Project_empty" in tags:
                image = self.folder_empty_image
            elif "Plot" in tags:
                image = self.plot_image
            else:
                image = treeview.item(item=selected_iid, option="image")
        else:
            if treeview.treetype == "multiplot":
                image = treeview.item(item=selected_iid, option="image")
            else:
                skip_image = True

        if skip_image:
            self.entry_label.config(text=selected_values)
        else:
            self.entry_label.config(text=selected_values, image=image)

        self.entry.treeview = treeview
        
        self.bind("<ButtonRelease-1>", self.fast_release)

        if treeview.tag_has("Project", item=selected_iid):
            if DEBUG: print("Selected Project")
            self.after_method = self.entry.after(150, self.moving)
        else:
            if DEBUG: print("Selected Graph File")
            self.after_method = self.entry.after(75, self.moving)

    def fast_release(self, event):
        if self.after_method is not None:
            self.entry.after_cancel(self.after_method)
            self.after_method = None
        self.unbind("<B1-Motion>")
        self.unbind("<ButtonRelease-1>")

    def moving(self):

        # Important variables to keep track of scrolling and dropping separator behavior
        self.after_method = None
        # Scrolling variables
        self.scroll_after_id = None # ID of after method for scrolling
        self.scroll_treeview = None # Treeview in which scrolling is performed
        self.scroll_direction = None
        # Dropping variables
        self.drop_treeview = None # Treeview in which the separator was drawn
        self.drop_separator_visible = False # Whether separator is visible
        self.open_project_after_id = None # ID of after method for dynamically opening project folders
        self.open_project_hovered_iid = None # iid of the item that is being hovered over when trying to open a folder

        self.bind("<B1-Motion>", self.on_move)
        self.bind("<ButtonRelease-1>", self.entry_on_release)
        
        for iid in self.entry.iids:
            tags = self.entry.treeview.item(iid, option="tags")
            taglist = list(tags)
            taglist.append("move")
            self.entry.treeview.item(iid, tags=taglist) 

        x = self.winfo_pointerx()
        y = self.winfo_pointery()

        self.entry.geometry(f"+{x+1}+{y+1}")
        self.entry.deiconify()

    def on_move(self, event):

        x = self.winfo_pointerx()
        y = self.winfo_pointery()

        hovered_widget = None
        for dx, dy in [(0, 0), (3, 0), (0, 3), (3, 3), (-3, 0), (0, -3), (-3, -3), (6, 0), (0, 6)]:
            candidate = self.winfo_containing(event.x_root + dx, event.y_root + dy)
            if candidate is not None and candidate.winfo_toplevel() is not self.entry:
                hovered_widget = candidate
                break

        treeview = self.entry.treeview

        treeviews = [self.entry.treeview]

        if self.entry.treeview == self.browser and self.plottype in ["Assay", "MultiPlot"]:
            treeviews.append(self.plotinfo)

        if hovered_widget is not None and hovered_widget in treeviews:

            for widget in treeviews:
                if widget == hovered_widget:
                    treeview = widget

            treeview.focus()
            
            treeview_height = treeview.winfo_height()
            y_rel = event.y_root - treeview.winfo_rooty()

            # Get the iid of the item that is hovered over
            hovered_iid = treeview.identify_row(y_rel)

            # Get the bbox of the item, to check whether the hovering is happening closer to the upper or lower limit of the bbox
            # .bbox returns an empty tuple when the item is not currently visible.
            hovered_bbox = treeview.bbox(hovered_iid)
            if hovered_bbox:
                (hovered_iid_x, hovered_iid_y, hovered_iid_width, hovered_iid_height) = hovered_bbox

                # If the pointer is in the lower 33 % of the entry, place a separator below
                if y_rel > hovered_iid_y + 0.67*hovered_iid_height:
                    if self.drop_separator_visible and self.drop_treeview is not treeview:
                        self.drop_treeview.drop_separator.place_forget()
                    treeview.drop_separator.place(x=hovered_iid_x,
                                                y=hovered_iid_y+hovered_iid_height,
                                                width=hovered_iid_width,
                                                height=4)
                    self.drop_separator_visible = True
                    self.drop_treeview = treeview
                    # Cancel opening of a folder
                    if self.open_project_after_id is not None:
                        self.after_cancel(self.open_project_after_id)
                        self.open_project_after_id = None
                # If the pointer is in the upper 33 % of the entry, place a separator above
                elif y_rel < hovered_iid_y + 0.33*hovered_iid_height:
                    if self.drop_separator_visible and self.drop_treeview is not treeview:
                        self.drop_treeview.drop_separator.place_forget()
                    treeview.drop_separator.place(x=hovered_iid_x,
                                                y=hovered_iid_y,
                                                width=hovered_iid_width,
                                                height=4)
                    self.drop_separator_visible = True
                    self.drop_treeview = treeview
                    # Cancel opening of a folder
                    if self.open_project_after_id is not None:
                        self.after_cancel(self.open_project_after_id)
                        self.open_project_after_id = None
                else:
                    if self.drop_separator_visible:
                        self.drop_treeview.drop_separator.place_forget()
                        self.drop_separator_visible = False
                        self.drop_treeview = None

                    # Logic for dynamically opening project folders needs to go here
                    # Changing check, first check whether the item has children and whether it is closed
                    if treeview.get_children(hovered_iid) and not treeview.item(hovered_iid, option="open"):
                        # Now check whether an after method for opening the item has already been scheduled
                        if self.open_project_after_id is not None:
                            # Check whether the item being hovered over is still the same for which the opening was scheduled
                            if self.open_project_hovered_iid != hovered_iid:
                                # If not, cancel the old method and schedule a new one
                                self.after_cancel(self.open_project_after_id)
                                self.open_project_after_id = self.after(500, self.open_treeview_item, treeview, hovered_iid)
                                self.open_project_hovered_iid = hovered_iid

                        # If not, schedule one and remember the hovered_iid
                        else:
                            self.open_project_after_id = self.after(500, self.open_treeview_item, treeview, hovered_iid)
                            self.open_project_hovered_iid = hovered_iid

                    # If it is not a project, check whether an opening has been scheduled, if so, cancel it
                    else:
                        if self.open_project_after_id is not None:
                            self.after_cancel(self.open_project_after_id)
                            self.open_project_after_id = None
            else:
                 # If the selected item is not in the visible region, remove both the separator and stop opening folders if done
                if self.drop_separator_visible:
                    self.drop_treeview.drop_separator.place_forget()
                    self.drop_separator_visible = False
                    self.drop_treeview = None
                if self.open_project_after_id is not None:
                    self.after_cancel(self.open_project_after_id)
                    self.open_project_after_id = None

            if y_rel <= treeview_height * 0.035:
                direction = "up"
            elif y_rel >= treeview_height * 0.965:
                direction = "down"
            else:
                direction = None

            if direction is None:
                if self.scroll_after_id is not None:
                    self.after_cancel(self.scroll_after_id)
                    self.scroll_after_id = None
                self.scroll_treeview = None
                self.scroll_direction = None
            else:
                if self.scroll_treeview is not treeview or self.scroll_direction != direction:
                    if self.scroll_after_id is not None:
                        self.after_cancel(self.scroll_after_id)
                    self.scroll_treeview = treeview
                    self.scroll_direction = direction
                    self.scroll_after_id = self.after(150, self.scroll_treeview_edge, treeview, direction)
        else:
            if self.scroll_after_id is not None:
                self.after_cancel(self.scroll_after_id)
                self.scroll_after_id = None
            self.scroll_treeview = None
            self.scroll_direction = None

            if self.drop_separator_visible and hovered_widget != self.drop_treeview.drop_separator:
                self.drop_treeview.drop_separator.place_forget()
                self.drop_separator_visible = False
                self.drop_treeview = None

            # If it is not a project, check whether an opening has been scheduled, if so, cancel it
            if self.open_project_after_id is not None:
                self.after_cancel(self.open_project_after_id)
                self.open_project_after_id = None

        self.entry.geometry(f"+{x+1}+{y+1}")

    def open_treeview_item(self, treeview, iid):
        treeview.item(iid, open=True)
        self.open_project_after_id = None
        self.open_project_hovered_iid = None

    def scroll_treeview_edge(self, treeview, direction):
        self.scroll_after_id = None

        if not hasattr(self, "scroll_treeview") or self.scroll_treeview is not treeview or self.scroll_direction != direction:
            return

        x = self.winfo_pointerx()
        y = self.winfo_pointery()
        hovered_widget = None
        for dx, dy in [(0, 0), (3, 0), (0, 3), (3, 3), (-3, 0), (0, -3), (-3, -3), (6, 0), (0, 6)]:
            candidate = self.winfo_containing(x + dx, y + dy)
            if candidate is not None and candidate.winfo_toplevel() is not self.entry:
                hovered_widget = candidate
                break

        if hovered_widget is None or hovered_widget != treeview:
            self.scroll_treeview = None
            self.scroll_direction = None
            return

        treeview_height = treeview.winfo_height()
        y_rel = y - treeview.winfo_rooty()
        if y_rel <= treeview_height * 0.05:
            treeview.yview_scroll(-1, "units")
            self.scroll_after_id = self.after(120, self.scroll_treeview_edge, treeview, direction)
        elif y_rel >= treeview_height * 0.95:
            treeview.yview_scroll(1, "units")
            self.scroll_after_id = self.after(120, self.scroll_treeview_edge, treeview, direction)
        else:
            self.scroll_treeview = None
            self.scroll_direction = None

    def _cancel_entry_callbacks(self):
        """Cancel callbacks and remove temporary widgets created during dragging."""
        if self.scroll_after_id is not None:
            self.after_cancel(self.scroll_after_id)
            self.scroll_after_id = None
        self.scroll_treeview = None
        self.scroll_direction = None

        # Also remove the separator widget that indicates dropping position
        if self.drop_separator_visible:
            self.drop_treeview.drop_separator.place_forget()
            self.drop_separator_visible = False
            self.drop_treeview = None

        # Stop folder opening
        if self.open_project_after_id is not None:
            self.after_cancel(self.open_project_after_id)
            self.open_project_after_id = None

    def _remove_entry_move_tags(self, treeview):
        for iid in self.entry.iids:
            tags = list(treeview.item(iid, option="tags"))
            tags.remove("move")
            treeview.item(iid, tags=tags)

    def _move_selected_treeview_entries(self, treeview, parent, index, open_parent=False):
        for iid in self.entry.iids:
            if treeview.parent(iid) in self.entry.iids:
                continue

            treeview.move(iid, parent, index)
            if open_parent:
                treeview.item(parent, open=True)
            treeview.changed_item(iid, moved=True)

    def _get_entry_drop_target(self, treeview, moved_iid, treeview_y, is_folder):
        moved_to_folder = bool(moved_iid) and is_folder(moved_iid)
        if not moved_to_folder:
            return moved_iid, False

        moved_bbox = treeview.bbox(moved_iid)
        if moved_bbox:
            (_, moved_iid_y, _, moved_iid_height) = moved_bbox
            should_use_parent = (
                treeview_y > moved_iid_y + 0.67 * moved_iid_height
                and not treeview.item(item=moved_iid, option="open")
            ) or treeview_y < moved_iid_y + 0.33 * moved_iid_height
            if should_use_parent:
                moved_iid = treeview.parent(moved_iid)

        return moved_iid, True

    def _is_invalid_entry_drop(self, treeview, moved_iid, is_folder):
        if moved_iid in self.entry.iids:
            return True

        same_parent = all(
            treeview.parent(moved_iid) == treeview.parent(iid)
            for iid in self.entry.iids
        )
        already_parent = all(
            moved_iid == treeview.parent(iid)
            for iid in self.entry.iids
        )
        return (not is_folder(moved_iid) and same_parent) or already_parent

    def entry_on_release(self, event):
        self._cancel_entry_callbacks()

        self.unbind("<B1-Motion>")
        self.unbind("<ButtonRelease-1>")
        
        self.entry.destroy()

        treeview = self.entry.treeview
    
        treeview_x = event.x_root - treeview.winfo_rootx()
        treeview_y = event.y_root - treeview.winfo_rooty()
        region_clicked = treeview.identify_region(treeview_x, treeview_y)

        # Get the widget over which the mouse was released
        widget = event.widget.winfo_containing(event.x_root, event.y_root)

        self._remove_entry_move_tags(treeview)

        if treeview in [self.browser, self.multiplot_browser]:

            # If the widget is the treeview itself, do some quick checks to see whether any changes need to be made
            if widget == treeview:

                # Get iid of the item it was moved to
                moved_iid = treeview.identify_row(treeview_y)

                moved_iid, moved_to_folder = self._get_entry_drop_target(
                    treeview,
                    moved_iid,
                    treeview_y,
                    lambda iid: treeview.tag_has(tagname="Project", item=iid),
                )

                if self._is_invalid_entry_drop(
                    treeview,
                    moved_iid,
                    lambda iid: treeview.tag_has("Project", item=iid),
                ):
                    return

            # Check which treeview is involved
            if treeview == self.browser:
                
                multiplot_browser = False
                
            elif treeview == self.multiplot_browser:
                
                multiplot_browser = True

            # First check which region was clicked and the start with fitting logic

            if region_clicked in ("nothing"):
                if widget == treeview:
                    # If the widget is the Treeview itself, move the items to the end of the treeview
                    self._move_selected_treeview_entries(treeview, "", tk.END)

                    # Only sort the item it was moved to, everything else is probably unnecessary
                    treeview.sort_treeview(parent="", recursive=False)
                    
                # If the item is moved on top of the canvas widget, the plot is initialized, however, this should only be done for the actual selected item
                elif widget == self.canvas_widget:
                    if treeview.tag_has(tagname="Project", item=self.entry.iids[0]): return
                    # Check whether the item initially stems from the browser or multiplot browser to distinguish between which of those to initialize
                    db.load(self.entry.iids[0], MultiPlot = multiplot_browser)

                    if multiplot_browser:

                        self.init_multiplot(self.entry.iids[0])

                    else:

                        self.plot(self.entry.iids[0])

                elif (treeview == self.browser and 
                      (widget == self.plotinfo or widget == self.plotinfo.watermark_label or
                       widget == self.plotinfo.drop_separator) 
                      and self.plottype in ["Assay", "MultiPlot"]):

                    # Identify the position, indicated by the marker
                    plotinfo_treeview_x = event.x_root - self.plotinfo.winfo_rootx()
                    plotinfo_treeview_y = event.y_root - self.plotinfo.winfo_rooty()
                    plotinfo_region_clicked = self.plotinfo.identify_region(plotinfo_treeview_x, plotinfo_treeview_y)
                    moved_to_folder = False

                    if plotinfo_region_clicked in ("tree", "cell", "heading"):
                         # Get iid of the item it was moved to
                        plotinfo_moved_iid = self.plotinfo.identify_row(plotinfo_treeview_y)

                        if plotinfo_moved_iid:

                            if self.plottype == "MultiPlot":
                                # For MultiPlot, the position is the index of the item in the treeview
                                position = int(self.plotinfo.item(item=plotinfo_moved_iid, option="values")[4])
                            
                                # Due to new and improved drag and drop behavior, this now needs to fit the optical separators marking the dropping location
                                plotinfo_moved_bbox = self.plotinfo.bbox(plotinfo_moved_iid)
                                if plotinfo_moved_bbox:
                                    (_, plotinfo_moved_iid_y, _, plotinfo_moved_iid_height) = plotinfo_moved_bbox
                                    # If event.y is in the upper 33 % of the entry, place the new item in the position above the item
                                    # Same thing, if the event.y is in the upper 33 % of the entry and the separator is shown above
                                    if plotinfo_treeview_y < plotinfo_moved_iid_y + 0.33*plotinfo_moved_iid_height:
                                        position += 1

                            elif self.plottype == "Assay":
                                plotinfo_moved_iid, moved_to_folder = self._get_entry_drop_target(
                                                    self.plotinfo,
                                                    plotinfo_moved_iid,
                                                    plotinfo_treeview_y,
                                                    lambda iid: self.plotinfo.item(iid, option="text") != "",
                                                )

                            else:
                                position = None
                        else:
                            first_child = self.plotinfo.get_children()[0]
                            if self.plottype == "MultiPlot":
                                position = int(self.plotinfo.item(item=first_child, option="values")[4]) + 1
                            else:
                                plotinfo_moved_iid = ""
        
                    else:
                        position = None
                        plotinfo_moved_iid = ""

                    if self.plottype == "Assay":
                                            
                        if not moved_to_folder:

                            plotinfo_moved_iid = self.plotinfo.parent(plotinfo_moved_iid) if plotinfo_moved_iid else ""

                        for iid in self.entry.iids:
                            if treeview.tag_has(tagname="Project", item=iid): continue
                            # Check whether iid is already in the treeview
                            if iid in self.plotinfo.get_children() or iid in cp.multiplot_data: continue

                            db.load(iid)
                            # Now insert at the specific position, indicated by the marker
                            self.add_to_assay(iid, parent=plotinfo_moved_iid)

                            if self.multiplot_plotoptions["assay_type"] is not None:
                                self.update_assay_y_for_file(iid, skip_save=True)

                        number_of_plots = len(db.multiplot_save_data[self.multiplot_iid]) - 1

                        # Do some follow-up logic in order to calculate everything properly, only however if autosorting is enabled
                        if number_of_plots > 2 and self.multiplot_plotoptions["autosort_files"]:
                            # Update the name similarity matrix to check for similar names in the multiplot
                            self.update_name_similarity_matrix()

                        # Update only the datapoints now not everything all the time
                        if self.multiplot_plotoptions["assay_type"] is not None:
                            for datapoint in self.multiplot_plotoptions["assay_datapoints"]:
                                self.update_assay_y_for_datapoint(datapoint, skip_save=True)

                            self.update_assay_plot(skip_save=True, skip_blit=True)

                            self.perform_assay_fit()

                        open_root_items = self.plotinfo.get_open_root_items()
                
                        self.refreshTree()

                        # Loop through open root items and open those items if they exist on the refreshed Tree
                        refreshed_root_items = self.plotinfo.get_children("")
                        self.after_idle(lambda: [self.plotinfo.item(item, open=True) for item in open_root_items if item in refreshed_root_items])

                    elif self.plottype == "MultiPlot":
                        for iid in self.entry.iids:
                            if treeview.tag_has(tagname="Project", item=iid): continue
                            # Check whether iid is already in the treeview
                            if iid in self.plotinfo.get_children(): continue

                            db.load(iid)
                            # Now insert at the specific position, indicated by the marker
                            self.add_to_multiplot(iid, position=position)
        
            elif region_clicked in ("tree", "cell"):

                # Check whether the object it is being moved to has a parent
                moved_parent = treeview.parent(moved_iid)

                if moved_parent in self.entry.iids: return
                
                if moved_to_folder:
                    self._move_selected_treeview_entries(treeview, moved_iid, 0, open_parent=True)

                    # Only sort the item it was moved to, everything else is probably unnecessary
                    treeview.sort_treeview(parent=moved_iid, recursive=False)
                    
                else:

                    # If it has a parent move it to the parent, otherwise move it to the end of the treeview
                    self._move_selected_treeview_entries(treeview, moved_parent, treeview.index(moved_iid)+1)

                    # Only sort the parent it was moved to, everything else is probably unnecessary
                    treeview.sort_treeview(parent=treeview.parent(moved_iid), recursive=False)

            # Update project label and plot label
            self.update_datakey_and_project()

        elif treeview == self.plotinfo:
            # Get iid of the item it was moved to
            treeview_x = event.x_root - treeview.winfo_rootx()
            treeview_y = event.y_root - treeview.winfo_rooty()
            region_clicked = treeview.identify_region(treeview_x, treeview_y)
            moved_iid = treeview.identify_row(treeview_y)
            # Get the iid of the selected item
            selected_iid = self.entry.iids[0]

            if treeview.treetype == "multiplot":

                # Check where the entry was released, if in nothing or heading, then there will not be a moved_iid
                if region_clicked in ["nothing", "heading"]:
                    moved_iid = ""
                else:
                    # Get the bbox of the item
                    moved_bbox = treeview.bbox(moved_iid)
                    if moved_bbox:
    
                        (_, moved_iid_y, _, moved_iid_height) = moved_bbox
    
                        # If moved_iid and self.entry.iid are the same, don't do anything
                        if moved_iid == selected_iid: return
    
                        # If moving to the upper third, visually it looks like placing the object inbetween.
                        if treeview_y < moved_iid_y + 0.33*moved_iid_height:
                            moved_iid = treeview.prev(moved_iid)
    
                        # If moved_iid and self.entry.iid are the same, don't do anything
                        if moved_iid == selected_iid: return

                # Get all iids from the multiplot and sort them according to their position
                iids = list(cp.multiplot_data.keys())
                iids.remove("PlotOptions")
                positions = [cp.multiplot_data[iid]["position"] for iid in iids]
                iids_sorted = [iid for _, iid in sorted(zip(positions, iids))]
                iids_sorted.remove(selected_iid)

                if moved_iid == "":
                    # If either heading or the highest item was selected, move to the top 
                    if region_clicked in ["heading", "tree", "cell"]:
                        iids_sorted.append(selected_iid)
                    else:
                        iids_sorted.insert(0, selected_iid)

                else:
                    index = iids_sorted.index(moved_iid)
                    iids_sorted.insert(index, selected_iid)

                
                # Refresh the Tree
                for count, iid in enumerate(iids_sorted):
                    cp.multiplot_data[iid]["position"] = count

                # Reverse order of items for correct visual appearance
                self.update_multiplot_positions()

                self.apply_colormap()

            elif treeview.treetype == "assay":

                open_root_items = treeview.get_open_root_items()

                moved_iid, moved_to_folder = self._get_entry_drop_target(
                    treeview,
                    moved_iid,
                    treeview_y,
                    lambda iid: treeview.item(iid, option="text") != "",
                )

                # Return if the item it was moved to is part of the selection
                if self._is_invalid_entry_drop(
                    treeview,
                    moved_iid,
                    lambda iid: treeview.item(iid, option="text") != "",
                ):
                    return

                # Now, moved_iid is known 
                if region_clicked in ("nothing"):
                    # If the widget is the Treeview itself, move the items to the end of the treeview
                    for iid in self.entry.iids:

                        treeview.move(iid, "", tk.END)
                    self.move_assay_files(self.entry.iids, new_datapoint="")

                # If the region clicked is either tree or cell, move the items to the respective position
                elif region_clicked in ("tree", "cell"):
                                   
                    if moved_to_folder:
    
                        for iid in self.entry.iids:

                            treeview.move(iid, moved_iid, 0)
                            treeview.item(moved_iid, open = True)

                        self.move_assay_files(self.entry.iids, new_datapoint=moved_iid)
                        
                    else:

                        # Check whether the object it is being moved to has a parent
                        moved_parent = treeview.parent(moved_iid)
    
                        # If it has a parent move it to the parent, otherwise move it to the end of the treeview
                        for iid in self.entry.iids:
                            
                            treeview.move(iid, moved_parent, treeview.index(moved_iid)+1)

                        self.move_assay_files(self.entry.iids, new_datapoint=moved_parent)

                # If this part of the skript is executed, some changes were probably made. When changes were made, deactivate the autosort function
                self.autosort_files.set(False)
                self.update_autosort_files()

                # Loop through open root items and open those items if they exist on the refreshed Tree
                refreshed_root_items = treeview.get_children("")
                self.after_idle(lambda: [treeview.item(item, open=True) for item in open_root_items if item in refreshed_root_items])

    def create_color_image(self, size, color):

        size = ceil(size)
        gray_border_size = 1

        img = tk.PhotoImage(width=size, height=size)
        # Put a gray block inside to create a nice border around the color of the plot, this also leaves some padding on the right
        img.put("darkgray", to=(0,
                                0,
                                size,
                                size))
        
        # Fill the image with the current color of the plot
        img.put(color, to=(gray_border_size,
                           gray_border_size,
                           size-gray_border_size,
                           size-gray_border_size))

        return img

    def choose_assay_fit_color(self, *args):

        color = tk.colorchooser.askcolor(color=self.assay_fit_color, parent=self)

        if color[1] is not None:
            self.assay_fit_color = color[1]
            size = self.assay_fit_color_image.width()
            self.assay_fit_color_image = self.create_color_image(size=size, color=self.assay_fit_color)
            self.assay_fit_color_btn.configure(image=self.assay_fit_color_image)

            cp.update_assay_fit_color()
            self.save_to_db()
         
    def save_current_img(self, filename=None, keep_export_figure=False, *args):

        if self.plottype is None:
            return

        expdir = self.plotoptions_data[self.plottype]["expdir"]

        # Make expdir a relative directory path if it is not an absolute path
        if expdir.startswith("./"):
            expdir_list = expdir.split("/")
            expdir = Path(__file__).resolve().parent
            for folder in expdir_list[1:]:
                expdir = expdir / folder
        elif expdir.startswith("../"):
            expdir_list = expdir.split("/")
            expdir = Path(__file__).resolve().parent.parent
            for folder in expdir_list[1:]:
                expdir = expdir / folder

        if not exists(expdir):
            try:
                print(f"Creating Directory: {expdir}")
                makedirs(expdir)
            except:
                print("Unable to create export directory")
                print("Falling back to ./Export")
                expdir = Path(__file__).resolve().parent / "Export"

        # Get the absolute platform-independent path
        expdir = str(expdir.resolve().as_posix())

        dpi = int(self.plotoptions_data[self.plottype]["dpi"])
        transparent = self.plotoptions_data[self.plottype]["transparent"] == "True"

        try:
            cp.export()

            if not expdir.endswith("/"):
                expdir += "/"

            if filename is None:
                filetype = self.plotoptions_data[self.plottype]["filetype"]
                if self.plottype in ["Assay", "MultiPlot"]:
                    filename = self.multiplot_plotoptions["filename"]
                else:
                    filename = cp.plot_data["filename"]

                if self.plottype == "Tm":
                    filename += f"_{cp.plot_data['Tm_method']}"

                # If allow duplicates is setup, then add a number iteratively until the file does not exist anymore
                if self.plotoptions_data[self.plottype]["allow_duplicates"] == "True" and exists(expdir+filename+filetype):

                    i = 0
                    while exists(expdir+filename+"("+str(i)+")"+filetype):
                        i += 1

                    print(f"Exporting {filename}({i}) to {expdir}")
                    cp.expfig.savefig(expdir+filename+"("+str(i)+")"+filetype,
                                        transparent = transparent,
                                        dpi=dpi)

                else:

                    print(f"Exporting {filename} to {expdir}")
                    cp.expfig.savefig(expdir+filename+filetype,
                                        transparent = transparent,
                                        dpi=dpi)
            else:
                print(f"Exporting {filename}")
                cp.expfig.savefig(filename,
                                  transparent = transparent,
                                  dpi=dpi)
        finally:
            export_figure = getattr(cp, "expfig", None)
            if export_figure is not None and not keep_export_figure:
                export_figure.clear()
                plt.close(export_figure)
                cp.expfig = None
                cp.expax = None

    def save_img_as(self, *args):

        filetype = self.plotoptions_data[self.plottype]["filetype"]

        filetypes = [
                    ("Portable Network Graphics", "*.png"),
                    ("Portable Document Format", "*.pdf"),
                    ("Scalable Vector Graphics", "*.svg"),
                    ("Encapsulated PostScript", "*.eps"),
                    ("PostScript", "*.ps"),
                    ("Joint Photographic Experts Group", "*.jpg *.jpeg"),
                    ("Tagged Image File Format", "*.tiff"),
                    ("WebP File", "*.webp"),
                    ("Raw Image File", "*.raw"),
                    ("RGBA File", "*.rgba"),
                    ("Progressive Graphics File", "*.pgf"),
                    ("All Files", "*.*"),
                ]

        for ft in filetypes:
            if filetype in ft[1]:
                filetypes.remove(ft)
                filetypes.insert(0, ft)
                break

        # Get initial_filename
        if self.plottype in ["Assay", "MultiPlot"]:
            initial_filename = self.multiplot_plotoptions["filename"]
        else:
            initial_filename = cp.plot_data["filename"]

        if self.plottype == "Tm":
            initial_filename += f"_{cp.plot_data['Tm_method']}"

        filename = tk.filedialog.asksaveasfilename(parent=self,
                                                   title="Save image as...",
                                                   initialdir="./",
                                                   initialfile=initial_filename+filetype,
                                                   filetypes=filetypes,
                                                   defaultextension=filetype,
                                                )
        if filename:
            self.save_current_img(filename=filename)


    def save_all_imgs(self, *args):

        ## Start with exporting the regular plots

        # Create dictionary to get all dependencies
        tree_widgets = self.browser.get_treeview_items()
            
        for iid in tree_widgets:
            if self.browser.tag_has(tagname="Project", item=iid): continue
            save_data_before = set(db.save_data)
            corrected_ypoints_before = set(cp.corrected_ypoints)
            try:
                if not db.load(iid):
                    continue
                self.plot(iid)
                self.save_current_img(keep_export_figure=True)

            except Exception:
                name = self.browser.item(iid, option="values")[0]
                print(f"Error: Plot {name} with id {iid} could not be exported.")
            finally:
                self.iid = None
                for loaded_iid in set(db.save_data) - save_data_before:
                    db.unload(loaded_iid)
                for corrected_iid in set(cp.corrected_ypoints) - corrected_ypoints_before:
                    cp.corrected_ypoints.pop(corrected_iid, None)

        export_figure = getattr(cp, "expfig", None)
        if export_figure is not None:
            export_figure.clear()
            plt.close(export_figure)
            cp.expfig = None
            cp.expax = None

        # After finishing the export, reset the currently loaded item
        if iid is not None:
            self.iid = iid
            db.load(iid)


    def import_pxp_files(self):
        # User can also import multiple files
        pxp_files = tk.filedialog.askopenfilenames(parent=self,
                                                   title="Import PeptiXPlot Files",
                                                   initialdir="../",
                                                   defaultextension=".pxp",
                                                   filetypes=[("PeptiXPlot File", "*.pxp"),
                                                              ("All Files", "*.*")
                                                        ],
                                                )

        for file_count, file in enumerate(pxp_files):
            iid_map_dict = {} # {old_iid: new_iid}

            with open(file=file, mode="rb") as f:
                import_dict = db.decompress_import(f.read())

            # I guess a similar logic here is possible to the copy/paste logic
            # All necessary saves are in the respective browser_saves including the information whether it is a folder and has children etc
            import_saves = import_dict["saves"]

            for browser, browser_data, MultiPlot in [(self.browser, import_dict["browser"], False), (self.multiplot_browser, import_dict["multiplot_browser"], True)]:

                if len(browser_data) > 0:
                    # Add a new item to keep all the imported folders in
                    if len(pxp_files) == 1:
                        text = "Import"
                    elif len(pxp_files) >= 2:
                        text = f"Import {file_count+1}"

                    import_folder = browser.insert("",
                                                   tk.END,
                                                   text = text,
                                                   open = False,
                                                   tags = ["Project","Project_empty"])

                    browser.add_item(import_folder)

                for count, iid in enumerate(browser_data["widgets"]):
                    parent = browser_data["parent"][count]
                    indices = browser_data["indices"][count]
                    text = browser_data["text"][count]
                    values = browser_data["values"][count]
                    tags = browser_data["tags"][count]

                    if parent and parent in iid_map_dict:
                        parent = iid_map_dict[parent]
                    else:
                        parent = import_folder
                        
                    # If iid is in import_saves, it is a plot. Otherwise it is just a folder
                    if iid in import_saves:
                        # Add a new save to the database
                        new_iid = db.add_new_save()
                        # Map the old iid to the new iid
                        iid_map_dict[iid] = new_iid

                        browser.insert(parent,
                                    indices,
                                    iid = new_iid,
                                    text = text,
                                    values = values,
                                    tags = tags)

                        if MultiPlot:
                            db.multiplot_save_data[new_iid] = deepcopy(import_saves[iid])
                            print(f"Importing: {db.multiplot_save_data[new_iid]['PlotOptions']['filename']}...")

                            # If it is an assay plot, convert the xpoints, ypoints, x_err and y_err of the dictionary back to NumPy arrays
                            if db.multiplot_save_data[new_iid]["PlotOptions"]["plottype"] == "Assay":
                                db.multiplot_save_data[new_iid]["PlotOptions"]["xpoints"] = np.array(db.multiplot_save_data[new_iid]["PlotOptions"]["xpoints"],dtype=np.float64)
                                db.multiplot_save_data[new_iid]["PlotOptions"]["ypoints"] = np.array(db.multiplot_save_data[new_iid]["PlotOptions"]["ypoints"],dtype=np.float64)
                                db.multiplot_save_data[new_iid]["PlotOptions"]["x_err"] = np.array(db.multiplot_save_data[new_iid]["PlotOptions"]["x_err"],dtype=np.float64)
                                db.multiplot_save_data[new_iid]["PlotOptions"]["y_err"] = np.array(db.multiplot_save_data[new_iid]["PlotOptions"]["y_err"],dtype=np.float64)
                                db.multiplot_save_data[new_iid]["PlotOptions"]["sigma"] = np.array(db.multiplot_save_data[new_iid]["PlotOptions"]["sigma"],dtype=np.float64)
                                
                        else:
                            db.save_data[new_iid] = deepcopy(import_saves[iid])
                            print(f"Importing: {db.save_data[new_iid]['filename']}...")
                            # Also convert the values back to the values they actually should be
                            # Convert the xpoints and ypoints of the dictionary back to NumPy arrays 
                            db.save_data[new_iid]["xpoints"] = np.array(db.save_data[new_iid]["xpoints"],dtype=np.float64)
                            db.save_data[new_iid]["ypoints"] = np.array(db.save_data[new_iid]["ypoints"],dtype=np.float64)
                            
                            # Convert the string keys of the dictionaries back to floats
                            peak_dict = {}
                            ipeak_dict = {}
                            for key, value in db.save_data[new_iid]["peak_dict"].items():
                                peak_dict[float(key)] = value
                            
                            if "inset_peak_dict" in db.save_data[new_iid]:
                                for key, value in db.save_data[new_iid]["inset_peak_dict"].items():
                                    ipeak_dict[float(key)] = value
                                db.save_data[new_iid]["inset_peak_dict"] = ipeak_dict
                            
                            db.save_data[new_iid]["peak_dict"] = peak_dict

                    else:
                        # Add a new entry and catch the iid
                        new_iid = browser.insert(parent,
                                                indices,
                                                text = text,
                                                open = False,
                                                tags = ["Project","Project_empty"])
                        iid_map_dict[iid] = new_iid

                    browser.add_item(new_iid)
                
                # Now go through MultiPlots and update the references according to iid_map_dict
                if MultiPlot:
                    for iid in browser_data["widgets"]:
                        # Check whether it is in import_saves, otherwise it is a folder
                        if iid in import_saves:
                            new_iid = iid_map_dict[iid]

                            multiplot_save = db.multiplot_save_data[new_iid]
                            new_multiplot_save = {}
                            for plot_iid in db.multiplot_save_data[new_iid]:
                                if plot_iid != "PlotOptions":
                                    if plot_iid in iid_map_dict:
                                        new_multiplot_save[iid_map_dict[plot_iid]] = multiplot_save[plot_iid]
                                else:
                                    new_multiplot_save[plot_iid] = multiplot_save[plot_iid]

                            db.multiplot_save_data[new_iid] = new_multiplot_save

                            db.save(new_iid, True)

                # Now go through baseline_iid, baseline_in and update the references according to iid_map_dict
                else:
                    for iid in browser_data["widgets"]:
                        # Check whether it is in import_saves, otherwise it is a folder
                        if iid in import_saves:
                            new_iid = iid_map_dict[iid]

                            baseline_iid = db.save_data[new_iid]["baseline_iid"]
                            baseline_in = db.save_data[new_iid]["baseline_in"]

                            if baseline_iid in iid_map_dict:
                                baseline_iid = iid_map_dict[baseline_iid]
                            else:
                                baseline_iid = None

                            db.save_data[new_iid]["baseline_iid"] = baseline_iid

                            new_baseline_in = []
                            for blank_iid in baseline_in:
                                if blank_iid in iid_map_dict:
                                    new_baseline_in.append(iid_map_dict[blank_iid])

                            db.save_data[new_iid]["baseline_in"] = new_baseline_in

                            db.save(new_iid, False)

                browser.save()
                browser.sort_treeview(parent="", recursive=True)

                iid_with_highest_index = None
                index = -1
                # Get the indices
                for iid in browser_data["widgets"]:
                    new_iid = iid_map_dict[iid]
                    if browser.index(new_iid) > index:
                        index = browser.index(new_iid)
                        iid_with_highest_index = new_iid

                if iid_with_highest_index:
                    browser.see(iid_with_highest_index)

        print("Import has completed successfully.")

    def export_pxp_files(self):
        # Setting up iid_list
        iid_dict = {} # Should contain tuples such as {iid:str: (MultiPlot:bool, folder:bool)}

        # Also add all children of selected items
        for iid in self.browser.selection():
            if iid not in iid_dict:
                iid_dict[iid] = (False, self.browser.tag_has(tagname="Project", item=iid))

            for child_iid in self.browser.get_all_children(iid):
                if child_iid not in iid_dict:
                    iid_dict[child_iid] = (False, self.browser.tag_has(tagname="Project", item=child_iid))

        for iid in self.multiplot_browser.selection():
            # In case of MultiPlot Project Folders, they might have the same name as regular Plot Project Folders, since they are checked second
            # Make sure, that they are only skipped, if the other object in iid_list is also a MultiPlot Object
            if (iid not in iid_dict) or (iid_dict[iid][0]):
                iid_dict[iid] = (True, self.multiplot_browser.tag_has(tagname="Project", item=iid))

            for child_iid in self.multiplot_browser.get_all_children(iid):
                if (child_iid not in iid_dict) or (iid_dict[child_iid][0]):
                    iid_dict[child_iid] = (True, self.multiplot_browser.tag_has(tagname="Project", item=child_iid))

        # Only continue if there actually is something to export
        if len(iid_dict) == 0:
            print("Nothing to export.")
            return

        export_file = tk.filedialog.asksaveasfilename(parent=self, 
                                                      title="Export selected Plots and MultiPlots",
                                                      initialdir="../",
                                                      defaultextension=".pxp",
                                                      filetypes=[("PeptiXPlot File", "*.pxp"),
                                                                 ("All Files", "*.*")
                                                            ]
                                                    )

        if export_file:
            db.export(iid_dict, export_filename=export_file)
                
    def new_project(self, *args):
      
        if self.notebook.select() == str(self.notebook_frame1):
            treeview = self.browser

        elif self.notebook.select() == str(self.notebook_frame2):
            treeview = self.multiplot_browser
        
        self.place_empty_widget_edit("Project", treeview)

    def new_multiplot(self, *args):

        # Immediately open the multiplot browser so that there are no weird visual bugs
        self.notebook.select(self.notebook_frame2)
        treeview = self.multiplot_browser

        self.place_empty_widget_edit("MultiPlot", treeview)

    def new_assay(self, *args):

        # Immediately open the multiplot browser so that there are no weird visual bugs
        self.notebook.select(self.notebook_frame2)
        treeview = self.multiplot_browser

        self.place_empty_widget_edit("Assay", treeview)

    def place_empty_widget_edit(self, widget_type, treeview):

        # Get the current selection in the treeview
        selection = treeview.selection()

        if len(selection) == 1:
            parent = selection[0]

            # Check whether the parent is a project or a graph object by checking the tags and if they are not a project, get their parent 
            if not treeview.tag_has("Project", item=parent):
                parent = treeview.parent(parent)

        else:
            parent = ""

        # Create a new entry in the database
        if widget_type in ["MultiPlot", "Assay"]:
            iid = db.add_new_save()

            treeview.insert(parent, tk.END, iid=iid, text="New", values=(widget_type,), open=True, tags=[widget_type,"Plot"])

        elif widget_type == "Project":

            iid = treeview.insert(parent, tk.END, text="New", open=True, tags=[widget_type,"Project_empty"])

        treeview.add_item(iid)

        if parent != "":
            treeview.changed_item(parent)

        treeview.sort_treeview(parent=parent, recursive=False)
        
        treeview.selection_remove(treeview.selection())

        if widget_type == "Project":
            image = self.folder_empty_image
        elif widget_type in ["MultiPlot", "Assay"]:
            image = self.plot_image

            # Add new multiplot
            # Initialize the multiplot data in the database with default values to avoid errors when trying to access it before saving the plot options for the first time
            data = {"PlotOptions":{"filename": "New", #Filename
                                   "x_axis_min": 0,     #x-Axis Start
                                   "x_axis_max": 1,     #x-Axis End
                                   "plottype": "",    #Plottype
                                }
                    }

            if widget_type == "Assay":
                data["PlotOptions"]["plottype"] = "Assay"

            data, _ = db.backwards_compatibility(data_dict=data, MultiPlot=True, skip_msg=True)

            db.multiplot_save_data.update({iid:data})
            
            db.save(iid, MultiPlot=True)
            print(f"Adding new {widget_type}")

        # Create entry over selected position
        if widget_type != "Project":
            widget_type = "Graph"
        widget_edit = ImageEntry(treeview, image=image)
        treeview.widget_edit = widget_edit
        widget_edit.entry.type = widget_type
        widget_edit.entry.bind("<Return>", treeview.on_backspace)
        widget_edit.entry.bind("<FocusOut>", treeview.on_backspace)
        widget_edit.bind_to_all("<MouseWheel>", lambda e: (treeview.yview_scroll(-1 if e.delta > 0 else 1, "units"),
                                                           treeview.on_mousewheel(e)))

        # Record column index and iid
        widget_edit.entry.editing_column_index = "#0"
        widget_edit.entry.editing_item_iid = iid

        widget_edit.insert(0, "New")
        widget_edit.select_range(0, tk.END)

        widget_edit.focus()

        # Somehow, this needs to be done twice, to make sure that the bbox is actually visible
        treeview.see(iid)
        treeview.see(iid)

        column_box = treeview.bbox(iid, "#0")

        # Only place the widget_edit, if the bbox of the new item is actually visible
        if column_box != "":
                    
            widget_edit.place(x=column_box[0]+12,
                              y=column_box[1],
                              w=column_box[2]-12,
                              h=column_box[3])
        
        else:
            # Else, destroy widget_edit again
            widget_edit.destroy()

        self.latest_project = treeview.index(iid)

    def open_files(self, *args):
        self.notebook.select(self.notebook_frame1)
        importhandler = ImportHandler(self, config, db)

    def add_imported_data(self, data_dict):

        self.browser.selection_set(())

        for key in data_dict:

            # Update all imported data_dicts to be up_to_date
            data, _ = db.backwards_compatibility(data_dict[key], MultiPlot=False, skip_msg=True)

            db.save_data.update({key:data})

            self.browser.add_item(key)

            self.browser.see(key)
            self.browser.selection_add(key)

            db.save(key, MultiPlot=False)

        key = next(iter(data_dict))

        parent = self.browser.parent(key)

        if parent != "":
            self.browser.changed_item(parent)
        

        self.browser.save()

    def on_close(self):
        choice = tk.messagebox.askyesnocancel(title="Quit", message="Do you want to save the last changes?", icon=tk.messagebox.WARNING)
        if choice is not None:
            if choice:
                if self.iid != None:
                    self.save_to_db(immediate=True)
                self.browser.save()
                self.multiplot_browser.save()
            db.close()
            self.destroy()
            lock.release()
            syexit("Terminating")

# Initiate the window

try:

    if __name__ == "__main__":

        try:
            ttk.utility.enable_high_dpi_awareness()
        except:
            pass

        if DEBUG: print("DEBUG Mode enabled")

        # Initialize ConfigHandler
        config = ConfigHandler(DEBUG)

        if config.config["General"]["dark"] == "True":
            theme = "darkly"
        else:
            theme = "flatly"
            
        root = Root(theme=theme)
        # Initialize DatabaseHandler
        db = DatabaseHandler(DEBUG, config)
        # Initialize CanvasPlot
        cp = CanvasPlot(DEBUG)
        
        root.create_widgets()
        
        root.mainloop()

finally:
    lock.release()
