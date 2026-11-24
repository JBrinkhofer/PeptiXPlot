import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from typing import Any, Protocol

search_icon = "\U0001F50D"

class BlankMaster(Protocol):
    plottype: str
    last_iid: str
    import_data: dict[str, Any]
    import_keys: dict[str, Any]

    def remove_blank(self) -> None: ...
    def refresh(self, *args: Any, **kwargs: Any) -> None: ...
    def set_blank(self) -> None: ...


class BlankTreeview(ttk.Treeview):
    def __init__(self, root: BlankMaster, master: Any = None,  **kwargs: Any):
        super().__init__(master, **kwargs)
        self.treeview_saves: dict[str, list[Any]] = {}
        
        self.plottypes = root.import_data.keys()

class BlankHandler(tk.Toplevel):

    # The BlankHandler is responsible for the selection of a blank for
    # a specific plot. It consists mainly out of a Treeview with all plots
    # available in the regular BrowserTreeview with little modifications
    # Double-Clicking on an entry causes the window to close and the blank
    # to be set.

    _instance = None
    
    def __init__(self, master: BlankMaster, CanvasPlotClass, DataBase, selection=None, plottype=None):

        if BlankHandler._instance is not None:
            master.after_idle(lambda: (BlankHandler._instance.lift(), BlankHandler._instance.focus_force()))
            return
        
        super().__init__(master=master)
        BlankHandler._instance = self

        self.title("Choose a Blank")

        self.blank_master: BlankMaster = master

        self.cp = CanvasPlotClass

        self.db = DataBase
        
        self.selection = selection
        self.plottype = plottype

        self.resizable(False, False)

        self.__create_widgets()

        self.protocol("WM_DELETE_WINDOW", self.__close)

    def __create_widgets(self):

        # Setup a frame for the treeview and scrollbar
        self.treeview_frame = ttk.Frame(self)

        # Setup the main treeview with a scrollbar
        self.blank_treeview = BlankTreeview(self.blank_master, self.treeview_frame, columns=("Plottype"))

        # Configure tags for the blank treeview, since all empty projects are deleted anyway, only folder_filled is necessary and will be given to all projects
        self.blank_treeview.tag_configure("Project", image=self.blank_master.folder_filled_image)
        self.blank_treeview.tag_configure("Plot", image=self.blank_master.plot_image)

        self.blank_treeview.heading("#0", text="Files")
        self.blank_treeview.column("#0", width=tkfont.Font().measure("Files")*9+4, minwidth=tkfont.Font().measure("Files"), stretch=False)
        self.blank_treeview.heading("Plottype", text="Plottype")
        item_width = tkfont.Font().measure("Plottype")
        self.blank_treeview.column("Plottype", width=item_width*2, minwidth=item_width+2, stretch=False, anchor=tk.CENTER)

        # Insert all values into the treeview
        self.insert_and_check_values(self.blank_treeview)

        # Create the scrollbar
        scrollbar = ttk.Scrollbar(self.treeview_frame, orient=tk.VERTICAL, command=self.blank_treeview.yview)
        self.blank_treeview.configure(yscrollcommand=scrollbar.set)

        # Create a button for removing the blank
        self.remove_blank_btn = ttk.Button(self, text="Remove current blank", command=self.remove_blank)

        self.add_blank_btn = ttk.Button(self, text="Add selected blank", command=self.set_blank, state="disabled")

        # Searchbar Validate Method
        search_browser = (self.register(lambda value: self.search(value)))

        # Searchbar
        self.searchbar_frame = ttk.Frame(self)
        ttk.Label(self.searchbar_frame, text=search_icon, font=("TkDefaultFont",12)).pack(side="left", fill="y")

        self.searchbar = ttk.Entry(self.searchbar_frame, validate="key", validatecommand=(search_browser, "%P"), foreground="gray")
        self.searchbar.insert(0, "Search...")
        self.searchbar.pack(side="left", fill="x", expand=True)

        self.searchbar.bind("<FocusIn>", self.remove_search_placeholder)
        self.searchbar.bind("<FocusOut>", self.add_search_placeholder)
        
        self.searchbar_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, padx=2, pady=1)

        # Pack treeview and scrollbar
        self.treeview_frame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
        self.blank_treeview.grid(row=1, column=0, columnspan=1, sticky=tk.NSEW, ipady=3)
        scrollbar.grid(row=1, column=2, sticky=tk.NS)

        self.add_blank_btn.grid(row=2, column=0, columnspan=1, sticky=tk.EW, padx=2, pady=1)
        self.remove_blank_btn.grid(row=2, column=1, columnspan=1, sticky=tk.EW, padx=2, pady=1)
        

        # Bind double click event
        self.blank_treeview.bind("<Double-1>", self.on_double_click)
        self.blank_treeview.bind("<Button-1>", self.on_click)

    def set_blank(self, iid=None):

        if iid is None:
            iid = self.blank_treeview.focus()
            if iid == "":
                return

        if "Project" not in self.blank_treeview.item(iid, option="tags"):
            
            self.close(iid)

    def remove_blank(self):
        self.__close()

        self.blank_master.remove_blank(self.selection)
        self.blank_master.refresh()
        
    def insert_and_check_values(self, treeview):

        # Function responsible for inserting all current values of BrowserTreevies

        # If selection is None, the choose Blank button was clicked, therefore get iid from the current plot. Otherwise get this information from the selection
        if self.selection:
            current_iids = self.selection

        else:

            # Make sure to get the current iid and not show the plot itself
            current_iids = [self.blank_master.iid,]

        widgets, text, values, parents, indices, tags = self.db.load_browser("plot")

        # Setup variables for all widgets that are displayed in the end.
        displayed_widgets = []
        displayed_text = []
        displayed_values = []
        displayed_parents = []
        displayed_indices = []
        displayed_tags = []
        displayed_children = []

        # Update the treeview
        for count, widget in enumerate(widgets):

            if "Project" in tags[count]:
                treeview.insert(parents[count],indices[count], iid=widget, text=text[count], tags = tags[count])

                displayed_widgets.append(widget)
                displayed_text.append(text[count])
                displayed_values.append(values[count])
                displayed_parents.append(parents[count])
                displayed_indices.append(indices[count])
                displayed_tags.append(tags[count])

            else:
                  
                for tag in tags[count]:
                    if tag in self.blank_master.import_data.keys(): values[count] = [tag]

                # Now only show those plots that are not current_iids and do not have a plottype other than the desired. In case of Tm show CD plots as well
                if ((self.plottype != "Tm" and self.plottype == values[count][0] and (widget not in current_iids)) or 
                    (self.plottype == "Tm" and values[count][0] in ["CD","Tm"] and (widget not in current_iids))):
                    treeview.insert(parents[count],indices[count], iid=widget, text=text[count], values=values[count], tags = tags[count])

                    displayed_widgets.append(widget)
                    displayed_text.append(text[count])
                    displayed_values.append(values[count])
                    displayed_parents.append(parents[count])
                    displayed_indices.append(indices[count])
                    displayed_tags.append(tags[count])

        # Do a second iteration to check which of the project folders actually has content. If a project folder has no content, remove it from the treeview
        for widget in treeview.tag_has("Project"):

            if len(treeview.get_children(widget)) == 0:
                # Iteratively delete the parents until a parent with content is reached or the root is reached
                parent = treeview.parent(widget)
                # Remove the widget from current saves
                removed_index = displayed_widgets.index(widget)
                displayed_widgets.pop(removed_index)
                displayed_text.pop(removed_index)
                displayed_values.pop(removed_index)
                displayed_parents.pop(removed_index)
                displayed_indices.pop(removed_index)
                displayed_tags.pop(removed_index)

                treeview.delete(widget)

                while parent and len(treeview.get_children(parent)) == 0:
                    next_parent = treeview.parent(parent)

                    # Remove the widget from current saves
                    removed_index = displayed_widgets.index(parent)
                    displayed_widgets.pop(removed_index)
                    displayed_text.pop(removed_index)
                    displayed_values.pop(removed_index)
                    displayed_parents.pop(removed_index)
                    displayed_indices.pop(removed_index)
                    displayed_tags.pop(removed_index)

                    treeview.delete(parent)
                    parent = next_parent   

        self.sort_treeview()         

        # Save current information in dictionary
        treeview.treeview_saves["widgets"] = displayed_widgets
        treeview.treeview_saves["text"] = displayed_text
        treeview.treeview_saves["values"] = displayed_values
        treeview.treeview_saves["parent"] = displayed_parents
        treeview.treeview_saves["indices"] = displayed_indices
        treeview.treeview_saves["tags"] = displayed_tags

        # Now get all the children of each item
        for widget in displayed_widgets:
            displayed_children.append(treeview.get_children(widget))

        treeview.treeview_saves["children"] = displayed_children

    def insert_all(self, treeview):

        widgets = treeview.treeview_saves["widgets"]
        text = treeview.treeview_saves["text"]
        values = treeview.treeview_saves["values"]
        parent = treeview.treeview_saves["parent"]
        indices = treeview.treeview_saves["indices"]
        tags = treeview.treeview_saves["tags"]

        children = []

        # Update the Browser Treeview to fit new format
        for count, widget in enumerate(widgets):

            # This does not work if the parent is missing, therefore check if it exists and else put it on root
            if treeview.exists(parent[count]):
                treeview.insert(parent[count],indices[count], iid=widget, text=text[count], values=values[count], tags = tags[count])
            else:
                parent[count] = ""
                treeview.insert("",tk.END, iid=widget, text=text[count], values=values[count], tags = tags[count])

        # Now get all the children of each item
        for widget in widgets:
            children.append(treeview.get_children(widget))

        treeview.treeview_saves["children"] = children

        self.sort_treeview()

    def add_search_placeholder(self, event):
        
        entry = event.widget

        if not entry.get():

            entry.insert(0, "Search...")
            entry.configure(foreground="gray", background="gray")

    def remove_search_placeholder(self, event):
        
        entry = event.widget

        if entry.get() == "Search...":

            entry.delete(0, tk.END)
            color = "white" if self.blank_master._dark else "black"
            entry.configure(foreground=color)

    def search(self, value):
        browser = self.blank_treeview

        # Get the current selection of the browser
        current_selection = browser.selection()

        if value == "Search...": return True

        if value == "":

            # If all values already exist in the browser, don't load it again
            if all(browser.exists(i) for i in browser.treeview_saves["widgets"]):
                return True
            
            browser.delete(*browser.get_children())
            self.insert_all(browser)
        
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
                                       iid=iid, 
                                       text=browser.treeview_saves["text"][count], 
                                       values=browser.treeview_saves["values"][count], 
                                       tags = browser.treeview_saves["tags"][count])
                    else:
                        browser.see(iid)
                    
                    insert_children(iid)

            browser.yview_moveto(0)

            # Sort the root node
            self.sort_treeview_root()

        
        # Select the same plots if possible
        for iid in current_selection:
            if browser.exists(iid):
                browser.selection_add(iid)
                browser.see(iid)


        return True    

    def close(self, blank_iid):

        self.__close()
        # If there was no selection passed to BlankHandler, BlankHandler was opened by clicking choose blank, therefore only add blank to current iid
        if not self.selection:
            self.cp.plot_data["baseline_iid"] = blank_iid
        else:
            for iid in self.selection:
                if self.db.load(iid):
                    self.db.save_data[iid]["baseline_iid"] = blank_iid

        self.blank_master.set_blank(selection=self.selection)
        self.blank_master.refresh()

    def __close(self):
        BlankHandler._instance = None
        self.destroy()

    def on_click(self, event):
        
        region_clicked = self.blank_treeview.identify_region(event.x, event.y)

        if region_clicked in ("cell","tree"):

            selected_iid = self.blank_treeview.identify_row(event.y)
            if "Project" not in self.blank_treeview.item(selected_iid, option="tags"):
                self.add_blank_btn.config(state="normal")
            else:  
                self.add_blank_btn.config(state="disabled")

        else:
            self.add_blank_btn.config(state="disabled")

    def on_double_click(self, event):

        region_clicked = self.blank_treeview.identify_region(event.x, event.y)

        if region_clicked in ("cell","tree"):

            selected_iid = self.blank_treeview.identify_row(event.y)

            self.set_blank(selected_iid)

    # Sort Items Alphabetically
    def sort_treeview(self, parent=""):
        
        # List for sorting of the children of the current parent node
        children = []

        # Get current children of the parent node
        current_children = self.blank_treeview.get_children(parent)
        child_index_dict = {}
        
        for child in current_children:
            # Get item text
            text = self.blank_treeview.item(child, "text")
            child_index = self.blank_treeview.index(child)
            child_index_dict[child_index] = child
            # Check whether it is a folder
            if "Project" in self.blank_treeview.item(child, "tags"):
                is_file = False
            else:
                is_file = True
            # Append item with flag indicating if text was originally empty
            children.append((text, is_file, child_index))
        
            # Sort by:
            # 1. Whether it is a folder or a file (is_file)
            # 2. Alphabetical order within each group.
            children.sort(key=lambda item: (item[1], item[0].lower()))

        # Move each child to the correct position within the parent
        for index, (text, is_file, child_index) in enumerate(children):
            
            child_iid = child_index_dict[child_index]
            
            # Move child to the new position if child and parent exist
            if self.blank_treeview.exists(child_iid) and self.blank_treeview.exists(parent):
                self.blank_treeview.move(child_iid, parent, index)

            # Recursive call to sort the sub-children of each child
            self.sort_treeview(child_iid)


    def sort_treeview_root(self):
        # Function to only sort the first layer of a treeview and not save anything, necessary for searching correctly
        children = []
        
        # Retrieve all children of the root parent ""
        for child in self.blank_treeview.get_children(""):
            # Get item text
            text = self.blank_treeview.item(child, "text")
            
            # Check whether it is a folder
            if "Project" in self.blank_treeview.item(child, "tags"):
                is_file = False
            else:
                is_file = True
            # Append item with flag indicating if text was originally empty
            children.append((text, is_file, child))
        
            # Sort by:
            # 1. Whether it is a folder or a file (is_file)
            # 2. Alphabetical order within each group.
            children.sort(key=lambda item: (item[1], item[0].lower()))

        # Move each child to the correct position within the parent
        for index, (text, is_file, child) in enumerate(children):
            
            # Move child to the new position
            self.blank_treeview.move(child, "", index)
